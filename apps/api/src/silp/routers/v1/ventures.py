"""مسیرهای /ventures، /metrics و دعوت به تیم — §5.8، FR-VEN-01/02، FR-TEAM-03.

* صفحهٔ کسب‌وکار عمومی است، ولی **آمادگی مرحله و جمع فروش فقط برای
  اعضا و مدیران** — عدد فروش یک کسب‌وکار دانشجویی دادهٔ تجاری اوست.
* شاخص پروژهٔ عملیاتی (نوع A) زیر `/projects/{id}/metrics` است و شاخص
  کسب‌وکار زیر `/ventures/{id}/metrics`؛ بررسی هر دو `/metrics/{id}/review`.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from silp.core.exceptions import NotFound
from silp.core.permissions import CurrentUser
from silp.domain.ventures import stage_title
from silp.models.identity import User
from silp.models.project import Project, ProjectRole, TeamInvitation
from silp.models.venture import (
    METRIC_STATUS_TITLE_FA,
    METRIC_TITLE_FA,
    Venture,
    VentureMetric,
)
from silp.routers.deps import CurrentUserDep, OptionalUserDep, SessionDep
from silp.schemas.common import ErrorResponse, Page, PageParams
from silp.schemas.venture import (
    AcceptedOut,
    CriterionOut,
    InvitationOut,
    InviteIn,
    LinkedProjectOut,
    MemberOut,
    MemberTotalsOut,
    MetricIn,
    MetricOut,
    MetricReviewIn,
    MetricsOut,
    MetricStatus,
    MetricTotalsOut,
    ReadinessOut,
    RemoveMemberIn,
    StageChangeIn,
    StageChangeOut,
    VentureDetailOut,
    VentureIn,
    VentureStage,
    VentureSummaryOut,
)
from silp.services.directory import DisplayName, display_names, name_of
from silp.services.invitation_service import InvitationService
from silp.services.metric_service import MetricOwner, MetricService
from silp.services.project_service import ProjectService
from silp.services.venture_service import VentureDraft, VentureService

router = APIRouter(prefix="/ventures", tags=["ventures"])
metrics_router = APIRouter(prefix="/metrics", tags=["ventures"])
project_metrics_router = APIRouter(prefix="/projects", tags=["ventures"])
invitations_router = APIRouter(tags=["teams"])


def get_venture_service(session: SessionDep) -> VentureService:
    return VentureService(session)


def get_metric_service(session: SessionDep) -> MetricService:
    return MetricService(session)


def get_invitation_service(session: SessionDep) -> InvitationService:
    return InvitationService(session)


VentureServiceDep = Annotated[VentureService, Depends(get_venture_service)]
MetricServiceDep = Annotated[MetricService, Depends(get_metric_service)]
InvitationServiceDep = Annotated[InvitationService, Depends(get_invitation_service)]


# ── تبدیل‌ها ───────────────────────────────────────────────────────────
def _member(
    user_id: uuid.UUID,
    names: dict[uuid.UUID, DisplayName],
    *,
    founder_id: uuid.UUID,
    joined_at: datetime,
) -> MemberOut:
    entry = names.get(user_id)
    return MemberOut(
        user_id=user_id,
        name=entry.full_name if entry else None,
        username=entry.username if entry else None,
        is_founder=user_id == founder_id,
        joined_at=joined_at,
    )


def _summary(
    venture: Venture, names: dict[uuid.UUID, DisplayName], member_count: int
) -> VentureSummaryOut:
    entry = names.get(venture.founder_id)
    return VentureSummaryOut(
        id=venture.id,
        slug=venture.slug,
        name=venture.name,
        pitch=venture.pitch,
        stage=venture.stage,
        stage_fa=stage_title(venture.stage),
        founder=MemberOut(
            user_id=venture.founder_id,
            name=entry.full_name if entry else None,
            username=entry.username if entry else None,
            is_founder=True,
            joined_at=venture.created_at,
        ),
        looking_for_cofounder=venture.looking_for_cofounder,
        needed_roles=list(venture.needed_roles),
        member_count=member_count,
        created_at=venture.created_at,
    )


def _draft(payload: VentureIn) -> VentureDraft:
    return VentureDraft(
        name=payload.name,
        pitch=payload.pitch,
        description=payload.description,
        problem=payload.problem,
        target_market=payload.target_market,
        revenue_model=payload.revenue_model,
        current_status=payload.current_status,
        looking_for_cofounder=payload.looking_for_cofounder,
        needed_roles=payload.needed_roles,
    )


async def _detail(
    service: VentureService,
    metrics: MetricService,
    venture: Venture,
    viewer: CurrentUser | None,
) -> VentureDetailOut:
    members = await service.members(venture.id)
    history = await service.history(venture.id)
    names = await display_names(
        service.session,
        [venture.founder_id, *(m.user_id for m in members), *(h.changed_by for h in history)],
    )
    is_member = viewer is not None and any(m.user_id == viewer.id for m in members)
    can_manage = viewer is not None and await service.can_manage(venture, viewer)
    insider = (
        is_member
        or can_manage
        or (viewer is not None and await metrics.can_view(MetricOwner(venture=venture), viewer))
    )

    readiness_out: ReadinessOut | None = None
    totals_out: MetricTotalsOut | None = None
    if insider:
        readiness = await service.readiness(venture)
        readiness_out = ReadinessOut(
            next_stage=readiness.next_stage,
            next_stage_fa=stage_title(readiness.next_stage) if readiness.next_stage else None,
            ready=readiness.ready,
            criteria=[
                CriterionOut(
                    code=c.code, text=c.text, met=c.met, current=c.current, target=c.target
                )
                for c in readiness.criteria
            ],
        )
        overall, _ = await metrics.totals(MetricOwner(venture=venture))
        totals_out = MetricTotalsOut(verified=overall.verified, pending=overall.pending)

    base = _summary(venture, names, len(members))
    return VentureDetailOut(
        **base.model_dump(),
        description=venture.description,
        problem=venture.problem,
        target_market=venture.target_market,
        revenue_model=venture.revenue_model,
        current_status=venture.current_status,
        paused_from_stage=venture.paused_from_stage,
        stage_changed_at=venture.stage_changed_at,
        origin_idea_id=venture.origin_idea_id,
        members=[
            _member(m.user_id, names, founder_id=venture.founder_id, joined_at=m.joined_at)
            for m in members
        ],
        projects=[
            LinkedProjectOut(id=p.id, title_fa=p.title_fa, status=p.status, kind=p.kind)
            for p in await service.projects(venture.id)
        ],
        history=[
            StageChangeOut(
                id=h.id,
                from_stage=h.from_stage,
                to_stage=h.to_stage,
                from_stage_fa=stage_title(h.from_stage),
                to_stage_fa=stage_title(h.to_stage),
                reason=h.reason,
                changed_by_name=name_of(names, h.changed_by),
                created_at=h.created_at,
            )
            for h in history
        ],
        readiness=readiness_out,
        totals=totals_out,
        is_member=is_member,
        can_manage=can_manage,
    )


async def _metric_out(
    metrics: MetricService,
    rows: list[VentureMetric],
    viewer: CurrentUser,
    *,
    owner_titles: dict[uuid.UUID, str] | None = None,
) -> list[MetricOut]:
    names = await display_names(
        metrics.session, [*(r.user_id for r in rows), *(r.reviewed_by for r in rows)]
    )
    result: list[MetricOut] = []
    for row in rows:
        owner_key = row.venture_id or row.project_id
        result.append(
            MetricOut(
                id=row.id,
                venture_id=row.venture_id,
                project_id=row.project_id,
                owner_title=(owner_titles or {}).get(owner_key) if owner_key else None,
                user_id=row.user_id,
                user_name=name_of(names, row.user_id),
                metric=row.metric,
                metric_fa=METRIC_TITLE_FA[row.metric],
                value=row.value,
                occurred_on=row.occurred_on,
                note=row.note,
                evidence_file_id=row.evidence_file_id,
                status=row.status,
                status_fa=METRIC_STATUS_TITLE_FA[row.status],
                reviewed_by_name=name_of(names, row.reviewed_by),
                reviewed_at=row.reviewed_at,
                review_note=row.review_note,
                can_review=row.status == "PENDING" and await metrics.can_review(row, viewer),
                is_mine=row.user_id == viewer.id,
                created_at=row.created_at,
            )
        )
    return result


async def _metrics_page(
    metrics: MetricService, owner: MetricOwner, viewer: CurrentUser, status_filter: str | None
) -> MetricsOut:
    if not await metrics.can_view(owner, viewer):
        # §6.4 قاعدهٔ ۴ — دادهٔ فروش برای غیرعضو «وجود ندارد».
        raise NotFound("موردی که دنبالش هستید پیدا نشد.")
    rows = await metrics.list_for(owner, status=status_filter)
    overall, by_member = await metrics.totals(owner)
    names = await display_names(metrics.session, list(by_member))
    return MetricsOut(
        items=await _metric_out(metrics, rows, viewer),
        totals=MetricTotalsOut(verified=overall.verified, pending=overall.pending),
        by_member=[
            MemberTotalsOut(
                user_id=uid, name=name_of(names, uid), verified=t.verified, pending=t.pending
            )
            for uid, t in by_member.items()
        ],
        metric_titles=dict(METRIC_TITLE_FA),
    )


# ── کسب‌وکار ───────────────────────────────────────────────────────────
@router.get("", response_model=Page[VentureSummaryOut], summary="فهرست کسب‌وکارها")
async def list_ventures(
    session: SessionDep,
    service: VentureServiceDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    q: Annotated[str | None, Query(max_length=100)] = None,
    stage: Annotated[VentureStage | None, Query()] = None,
    looking_for_cofounder: Annotated[bool | None, Query()] = None,
) -> Page[VentureSummaryOut]:
    params = PageParams(page=page, page_size=page_size)
    stmt = select(Venture).where(Venture.deleted_at.is_(None))
    if stage:
        stmt = stmt.where(Venture.stage == stage)
    else:
        stmt = stmt.where(Venture.stage != "CLOSED")
    if looking_for_cofounder is not None:
        stmt = stmt.where(Venture.looking_for_cofounder.is_(looking_for_cofounder))
    if q and q.strip():
        normalized = func.fa_normalize(q.strip())
        stmt = stmt.where(Venture.search_norm.like(func.concat("%", normalized, "%")))
    total = await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = list(
        await session.scalars(
            stmt.order_by(Venture.stage_changed_at.desc(), Venture.id.desc())
            .offset(params.offset)
            .limit(params.page_size)
        )
    )
    names = await display_names(session, [v.founder_id for v in rows])
    counts = await service.member_counts([v.id for v in rows])
    return Page.of(
        [_summary(v, names, counts.get(v.id, 0)) for v in rows],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )


@router.get("/mine", response_model=list[VentureSummaryOut], summary="کسب‌وکارهای من")
async def my_ventures(
    service: VentureServiceDep, current: CurrentUserDep
) -> list[VentureSummaryOut]:
    rows = await service.mine(current.id)
    names = await display_names(service.session, [v.founder_id for v in rows])
    counts = await service.member_counts([v.id for v in rows])
    return [_summary(v, names, counts.get(v.id, 0)) for v in rows]


@router.post(
    "",
    response_model=VentureDetailOut,
    status_code=status.HTTP_201_CREATED,
    summary="ثبت کسب‌وکار",
)
async def create_venture(
    payload: VentureIn,
    service: VentureServiceDep,
    metrics: MetricServiceDep,
    current: CurrentUserDep,
) -> VentureDetailOut:
    venture = await service.create(actor=current, draft=_draft(payload))
    return await _detail(service, metrics, venture, current)


@router.get(
    "/{venture_id}",
    response_model=VentureDetailOut,
    summary="صفحهٔ کسب‌وکار",
    responses={404: {"model": ErrorResponse}},
)
async def get_venture(
    venture_id: uuid.UUID,
    service: VentureServiceDep,
    metrics: MetricServiceDep,
    viewer: OptionalUserDep,
) -> VentureDetailOut:
    venture = await service.require(venture_id)
    return await _detail(service, metrics, venture, viewer)


@router.patch("/{venture_id}", response_model=VentureDetailOut, summary="ویرایش کسب‌وکار")
async def update_venture(
    venture_id: uuid.UUID,
    payload: VentureIn,
    service: VentureServiceDep,
    metrics: MetricServiceDep,
    current: CurrentUserDep,
) -> VentureDetailOut:
    venture = await service.require(venture_id)
    venture = await service.update(venture=venture, actor=current, draft=_draft(payload))
    return await _detail(service, metrics, venture, current)


@router.delete(
    "/{venture_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="حذف (فقط مرحلهٔ ایده)",
)
async def delete_venture(
    venture_id: uuid.UUID, service: VentureServiceDep, current: CurrentUserDep
) -> None:
    venture = await service.require(venture_id)
    await service.delete(venture=venture, actor=current)


@router.post(
    "/{venture_id}/stage",
    response_model=VentureDetailOut,
    summary="ارتقا، توقف، ازسرگیری یا بستن",
    responses={409: {"model": ErrorResponse}},
)
async def change_stage(
    venture_id: uuid.UUID,
    payload: StageChangeIn,
    service: VentureServiceDep,
    metrics: MetricServiceDep,
    current: CurrentUserDep,
) -> VentureDetailOut:
    """§7.7 — ارتقا فقط یک گام و با معیار خروج؛ کمبودها در `details.missing`."""
    venture = await service.require(venture_id)
    await service.change_stage(
        venture=venture, actor=current, action=payload.action, reason=payload.reason
    )
    return await _detail(service, metrics, venture, current)


@router.post(
    "/{venture_id}/leave",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="ترک تیم",
)
async def leave_venture(
    venture_id: uuid.UUID, service: VentureServiceDep, current: CurrentUserDep
) -> None:
    venture = await service.require(venture_id)
    await service.leave(venture=venture, actor=current)


@router.post(
    "/{venture_id}/members/{user_id}/remove",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="حذف عضو با ذکر دلیل",
)
async def remove_member(
    venture_id: uuid.UUID,
    user_id: uuid.UUID,
    payload: RemoveMemberIn,
    service: VentureServiceDep,
    current: CurrentUserDep,
) -> None:
    venture = await service.require(venture_id)
    await service.remove_member(
        venture=venture, actor=current, user_id=user_id, reason=payload.reason
    )


@router.get("/{venture_id}/metrics", response_model=MetricsOut, summary="فعالیت و فروش")
async def venture_metrics(
    venture_id: uuid.UUID,
    service: VentureServiceDep,
    metrics: MetricServiceDep,
    current: CurrentUserDep,
    status_filter: Annotated[MetricStatus | None, Query(alias="status")] = None,
) -> MetricsOut:
    venture = await service.require(venture_id)
    return await _metrics_page(metrics, MetricOwner(venture=venture), current, status_filter)


@router.post(
    "/{venture_id}/metrics",
    response_model=MetricOut,
    status_code=status.HTTP_201_CREATED,
    summary="ثبت فعالیت یا فروش",
)
async def record_venture_metric(
    venture_id: uuid.UUID,
    payload: MetricIn,
    service: VentureServiceDep,
    metrics: MetricServiceDep,
    current: CurrentUserDep,
) -> MetricOut:
    venture = await service.require(venture_id)
    row = await metrics.record(
        owner=MetricOwner(venture=venture),
        actor=current,
        metric=payload.metric,
        value=payload.value,
        occurred_on=payload.occurred_on,
        note=payload.note,
        evidence_file_id=payload.evidence_file_id,
    )
    return (await _metric_out(metrics, [row], current))[0]


@router.post(
    "/{venture_id}/invitations",
    response_model=InvitationOut,
    status_code=status.HTTP_201_CREATED,
    summary="دعوت به تیم کسب‌وکار",
)
async def invite_to_venture(
    venture_id: uuid.UUID,
    payload: InviteIn,
    service: VentureServiceDep,
    invitations: InvitationServiceDep,
    current: CurrentUserDep,
) -> InvitationOut:
    venture = await service.require(venture_id)
    invitee = await _user_by_username(invitations.session, payload.username)
    invitation = await invitations.invite_to_venture(
        venture=venture, actor=current, invitee_id=invitee, message=payload.message
    )
    return (await _invitations_out(invitations, [invitation]))[0]


@router.get("/{venture_id}/invitations", response_model=list[InvitationOut], summary="دعوت‌های باز")
async def venture_invitations(
    venture_id: uuid.UUID,
    service: VentureServiceDep,
    invitations: InvitationServiceDep,
    current: CurrentUserDep,
) -> list[InvitationOut]:
    venture = await service.require(venture_id)
    await service.require_manager(venture, current)
    team = await service.team_of(venture.id)
    rows = await invitations.sent_for_team(team.id) if team else []
    return await _invitations_out(invitations, rows)


# ── شاخص پروژهٔ عملیاتی ────────────────────────────────────────────────
@project_metrics_router.get(
    "/{project_id}/metrics", response_model=MetricsOut, summary="فعالیت و فروش پروژه"
)
async def project_metrics(
    project_id: uuid.UUID,
    metrics: MetricServiceDep,
    current: CurrentUserDep,
    status_filter: Annotated[MetricStatus | None, Query(alias="status")] = None,
) -> MetricsOut:
    """FR-VEN-02 — `by_member` همان «داشبورد عملکرد هر عضو» است."""
    project = await ProjectService(metrics.session).require(project_id)
    return await _metrics_page(metrics, MetricOwner(project=project), current, status_filter)


@project_metrics_router.post(
    "/{project_id}/metrics",
    response_model=MetricOut,
    status_code=status.HTTP_201_CREATED,
    summary="ثبت فعالیت یا فروش در پروژه",
)
async def record_project_metric(
    project_id: uuid.UUID, payload: MetricIn, metrics: MetricServiceDep, current: CurrentUserDep
) -> MetricOut:
    project = await ProjectService(metrics.session).require(project_id)
    row = await metrics.record(
        owner=MetricOwner(project=project),
        actor=current,
        metric=payload.metric,
        value=payload.value,
        occurred_on=payload.occurred_on,
        note=payload.note,
        evidence_file_id=payload.evidence_file_id,
    )
    return (await _metric_out(metrics, [row], current))[0]


@project_metrics_router.post(
    "/{project_id}/invitations",
    response_model=InvitationOut,
    status_code=status.HTTP_201_CREATED,
    summary="دعوت مستقیم به تیم پروژه",
)
async def invite_to_project(
    project_id: uuid.UUID,
    payload: InviteIn,
    invitations: InvitationServiceDep,
    current: CurrentUserDep,
) -> InvitationOut:
    project = await invitations.projects.require(project_id)
    invitee = await _user_by_username(invitations.session, payload.username)
    invitation = await invitations.invite_to_project(
        project=project,
        actor=current,
        invitee_id=invitee,
        message=payload.message,
        role_id=payload.role_id,
    )
    return (await _invitations_out(invitations, [invitation]))[0]


# ── بررسی شاخص ─────────────────────────────────────────────────────────
@metrics_router.get("/review-queue", response_model=list[MetricOut], summary="صف تأیید شاخص")
async def review_queue(metrics: MetricServiceDep, current: CurrentUserDep) -> list[MetricOut]:
    rows = await metrics.review_queue(current)
    titles: dict[uuid.UUID, str] = {}
    venture_ids = {r.venture_id for r in rows if r.venture_id}
    project_ids = {r.project_id for r in rows if r.project_id}
    if venture_ids:
        for vid, name in await metrics.session.execute(
            select(Venture.id, Venture.name).where(Venture.id.in_(venture_ids))
        ):
            titles[vid] = name
    if project_ids:
        for pid, title in await metrics.session.execute(
            select(Project.id, Project.title_fa).where(Project.id.in_(project_ids))
        ):
            titles[pid] = title
    return await _metric_out(metrics, rows, current, owner_titles=titles)


@metrics_router.post(
    "/{metric_id}/review",
    response_model=MetricOut,
    summary="تأیید یا رد شاخص",
    responses={403: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
async def review_metric(
    metric_id: uuid.UUID,
    payload: MetricReviewIn,
    metrics: MetricServiceDep,
    current: CurrentUserDep,
) -> MetricOut:
    row = await metrics.review(
        metric_id=metric_id, actor=current, decision=payload.decision, note=payload.note
    )
    return (await _metric_out(metrics, [row], current))[0]


@metrics_router.delete(
    "/{metric_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="حذف ثبت در انتظار",
)
async def delete_metric(
    metric_id: uuid.UUID, metrics: MetricServiceDep, current: CurrentUserDep
) -> None:
    await metrics.delete(metric_id=metric_id, actor=current)


# ── دعوت ───────────────────────────────────────────────────────────────
async def _user_by_username(session: AsyncSession, username: str) -> uuid.UUID:
    user_id: uuid.UUID | None = await session.scalar(
        select(User.id).where(
            User.username == username.strip().lstrip("@"), User.deleted_at.is_(None)
        )
    )
    if user_id is None:
        raise NotFound("کاربری با این نام کاربری پیدا نشد.")
    return user_id


async def _invitations_out(
    service: InvitationService, rows: list[TeamInvitation]
) -> list[InvitationOut]:
    names = await display_names(
        service.session, [*(r.inviter_id for r in rows), *(r.invitee_id for r in rows)]
    )
    role_ids = {r.role_id for r in rows if r.role_id}
    roles: dict[uuid.UUID, str] = {}
    if role_ids:
        for rid, title in await service.session.execute(
            select(ProjectRole.id, ProjectRole.title_fa).where(ProjectRole.id.in_(role_ids))
        ):
            roles[rid] = title
    result: list[InvitationOut] = []
    for row in rows:
        target = await service.target_of(row.team_id)
        result.append(
            InvitationOut(
                id=row.id,
                target_type=target.kind,
                target_id=target.target_id,
                target_title=target.title,
                href=target.href,
                inviter_name=name_of(names, row.inviter_id),
                invitee_name=name_of(names, row.invitee_id),
                message=row.message,
                role_title=roles.get(row.role_id) if row.role_id else None,
                source=row.source,
                status=row.status,
                expires_at=row.expires_at,
                created_at=row.created_at,
            )
        )
    return result


@invitations_router.get(
    "/me/invitations", response_model=list[InvitationOut], summary="دعوت‌های باز من"
)
async def my_invitations(
    invitations: InvitationServiceDep, current: CurrentUserDep
) -> list[InvitationOut]:
    return await _invitations_out(invitations, await invitations.pending_for(current.id))


@invitations_router.post(
    "/invitations/{invitation_id}/accept",
    response_model=AcceptedOut,
    summary="پذیرش دعوت",
    responses={409: {"model": ErrorResponse}},
)
async def accept_invitation(
    invitation_id: uuid.UUID, invitations: InvitationServiceDep, current: CurrentUserDep
) -> AcceptedOut:
    target = await invitations.accept(invitation_id=invitation_id, actor=current)
    return AcceptedOut(
        target_type=target.kind,
        target_id=target.target_id,
        href=target.href,
    )


@invitations_router.post(
    "/invitations/{invitation_id}/decline",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="رد دعوت",
)
async def decline_invitation(
    invitation_id: uuid.UUID, invitations: InvitationServiceDep, current: CurrentUserDep
) -> None:
    await invitations.decline(invitation_id=invitation_id, actor=current)


@invitations_router.delete(
    "/invitations/{invitation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="لغو دعوت",
)
async def cancel_invitation(
    invitation_id: uuid.UUID, invitations: InvitationServiceDep, current: CurrentUserDep
) -> None:
    await invitations.cancel(invitation_id=invitation_id, actor=current)


__all__ = [
    "invitations_router",
    "metrics_router",
    "project_metrics_router",
    "router",
]
