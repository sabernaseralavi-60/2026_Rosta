"""مسیرهای /teams — §5.8، FR-TEAM-01/02/03، M7-07 و M7-08، ADR-0015.

* جستجوی هم‌تیمی فقط نیمرخ‌های عمومی را برمی‌گرداند و با پروژه، بر پایهٔ
  **مکملیت** با تیم آن مرتب می‌شود (§8.14).
* فهرست آگهی عمومی است؛ آگهی منقضی، پرشده یا بسته فقط برای مدیرانش و
  کسانی که به آن درخواست داده‌اند دیده می‌شود.
* تصمیم دربارهٔ درخواست با همان کسی است که حق دعوت به آن تیم را دارد —
  نه لزوماً کسی که آگهی را داده.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import or_, select

from silp.core.permissions import CurrentUser, Permission
from silp.domain.teams import stronger_reason
from silp.models.delivery import OpeningApplication, TeamOpening
from silp.models.education import CourseOffering
from silp.models.profile import Profile
from silp.models.project import Project, ProjectRole, Team, TeamMember
from silp.models.venture import Venture
from silp.routers.deps import CurrentUserDep, OptionalUserDep, SessionDep
from silp.schemas.common import ErrorResponse, Page, PageParams
from silp.schemas.team import (
    ApplyIn,
    DecideIn,
    GapOut,
    ManagedTeamOut,
    MyApplicationOut,
    OpeningApplicationOut,
    OpeningDetailOut,
    OpeningIn,
    OpeningOut,
    OpeningUpdateIn,
    PersonOut,
    ProjectBriefOut,
    SearchContextOut,
    SkillLevelOut,
    SkillRefOut,
    TargetKind,
    TargetOut,
    TeammateOut,
    TeammateUserOut,
    TeamSearchOut,
)
from silp.services import authz
from silp.services.directory import DisplayName, display_names
from silp.services.opening_service import OpeningDraft, OpeningService, OpeningTarget
from silp.services.team_search_service import SearchFilters, TeamSearchService

router = APIRouter(prefix="/teams", tags=["teams"])

STATUS_TITLE_FA: dict[str, str] = {
    "OPEN": "باز",
    "FILLED": "پر شد",
    "CLOSED": "بسته",
    "EXPIRED": "منقضی",
}
APPLICATION_STATUS_TITLE_FA: dict[str, str] = {
    "PENDING": "در انتظار",
    "ACCEPTED": "پذیرفته شد",
    "DECLINED": "پذیرفته نشد",
    "WITHDRAWN": "پس گرفته شد",
}
ACTIVE_PROJECT_STATUSES = ("OPEN", "IN_PROGRESS")


def get_opening_service(session: SessionDep) -> OpeningService:
    return OpeningService(session)


def get_search_service(session: SessionDep) -> TeamSearchService:
    return TeamSearchService(session)


OpeningServiceDep = Annotated[OpeningService, Depends(get_opening_service)]
SearchServiceDep = Annotated[TeamSearchService, Depends(get_search_service)]


def _now() -> datetime:
    return datetime.now(UTC)


def _person(names: dict[uuid.UUID, DisplayName], user_id: uuid.UUID) -> PersonOut:
    entry = names.get(user_id)
    return PersonOut(
        id=user_id,
        name=entry.full_name if entry else None,
        username=entry.username if entry else None,
    )


# ── جستجوی هم‌تیمی — FR-TEAM-01 ────────────────────────────────────────
@router.get(
    "/search",
    response_model=TeamSearchOut,
    summary="جستجوی هم‌تیمی",
    responses={403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
async def search_teammates(
    current: CurrentUserDep,
    service: SearchServiceDep,
    session: SessionDep,
    skill_id: uuid.UUID | None = None,
    min_level: Annotated[int, Query(ge=1, le=5)] = 1,
    asset_id: uuid.UUID | None = None,
    interest_id: uuid.UUID | None = None,
    offering_id: uuid.UUID | None = None,
    university_id: uuid.UUID | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    complement_project_id: uuid.UUID | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 20,
) -> TeamSearchOut:
    """`complement_project_id` ⇒ مرتب بر پایهٔ مکملیت با تیم آن پروژه (§8.14)."""
    params = PageParams(page=page, page_size=page_size)
    matches, context = await service.search(
        actor=current,
        filters=SearchFilters(
            skill_id=skill_id,
            min_level=min_level,
            asset_id=asset_id,
            interest_id=interest_id,
            offering_id=offering_id,
            university_id=university_id,
            q=q,
        ),
        complement_project_id=complement_project_id,
    )
    window = matches[params.offset : params.offset + params.page_size]
    profile = await session.get(Profile, current.id)
    items = [
        TeammateOut(
            user=TeammateUserOut(
                id=m.user_id,
                username=m.username,
                display_name=m.display_name,
                university=m.university,
            ),
            bio=m.bio,
            weekly_hours=m.weekly_hours,
            top_skills=[
                SkillLevelOut(
                    skill_id=s.skill_id, title_fa=s.title_fa, level=s.level, verified=s.verified
                )
                for s in m.top_skills
            ],
            assets=m.assets,
            shares_course=m.shares_course,
            complement_score=m.complement.score if m.complement else None,
            complement_reason=m.complement.reason if m.complement else None,
            complement_skills=[c.title_fa for c in m.complement.covered] if m.complement else [],
            stronger_skills=[c.title_fa for c in m.stronger],
            stronger_reason=None if context.project else stronger_reason(m.stronger),
        )
        for m in window
    ]
    return TeamSearchOut(
        items=items,
        total=len(matches),
        page=params.page,
        page_size=params.page_size,
        has_next=params.offset + params.page_size < len(matches),
        context=SearchContextOut(
            project=ProjectBriefOut(id=context.project.id, title=context.project.title_fa)
            if context.project
            else None,
            gaps=[GapOut(title_fa=g.title_fa, min_level=g.min_level) for g in context.gaps],
            can_invite=context.can_invite,
            my_profile_is_public=bool(profile and profile.is_public),
        ),
    )


@router.get(
    "/managed",
    response_model=list[ManagedTeamOut],
    summary="تیم‌هایی که می‌توانم برایشان آگهی بدهم یا دعوت بفرستم",
)
async def managed_teams(current: CurrentUserDep, session: SessionDep) -> list[ManagedTeamOut]:
    """پروژه‌های فعالی که `project.application.decide` دارم و کسب‌وکارهایی که بنیان‌گذارشانم."""
    lead_of = (
        select(Team.project_id)
        .join(TeamMember, TeamMember.team_id == Team.id)
        .where(
            TeamMember.user_id == current.id,
            TeamMember.status == "ACTIVE",
            TeamMember.is_lead.is_(True),
            Team.project_id.is_not(None),
        )
    )
    taught = select(CourseOffering.id).where(CourseOffering.instructor_id == current.id)
    candidates = list(
        await session.scalars(
            select(Project)
            .where(
                Project.deleted_at.is_(None),
                Project.status.in_(ACTIVE_PROJECT_STATUSES),
                or_(
                    Project.lead_id == current.id,
                    Project.id.in_(lead_of),
                    Project.offering_id.in_(taught),
                ),
            )
            .order_by(Project.updated_at.desc())
        )
    )
    result: list[ManagedTeamOut] = []
    roles_by_project: dict[uuid.UUID, list[ProjectBriefOut]] = {}
    if candidates:
        for role in await session.scalars(
            select(ProjectRole).where(ProjectRole.project_id.in_([p.id for p in candidates]))
        ):
            roles_by_project.setdefault(role.project_id, []).append(
                ProjectBriefOut(id=role.id, title=role.title_fa)
            )
    for project in candidates:
        if await authz.has_permission(
            session, current, Permission.PROJECT_APPLICATION_DECIDE, project.id
        ):
            result.append(
                ManagedTeamOut(
                    kind="PROJECT",
                    id=project.id,
                    title=project.title_fa,
                    roles=roles_by_project.get(project.id, []),
                )
            )
    for venture in await session.scalars(
        select(Venture)
        .where(
            Venture.founder_id == current.id,
            Venture.deleted_at.is_(None),
            Venture.stage != "CLOSED",
        )
        .order_by(Venture.updated_at.desc())
    ):
        result.append(ManagedTeamOut(kind="VENTURE", id=venture.id, title=venture.name))
    return result


# ── آگهی — FR-TEAM-02 ──────────────────────────────────────────────────
def _effective(opening: TeamOpening, now: datetime) -> str:
    if opening.status == "OPEN" and opening.expires_at <= now:
        return "EXPIRED"
    return opening.status


def _target_out(target: OpeningTarget) -> TargetOut:
    entity_id = target.project.id if target.project else target.venture.id  # type: ignore[union-attr]
    kind: TargetKind = "PROJECT" if target.project else "VENTURE"
    return TargetOut(kind=kind, id=entity_id, title=target.title, href=target.href)


def _application_out(
    row: OpeningApplication, names: dict[uuid.UUID, DisplayName]
) -> OpeningApplicationOut:
    return OpeningApplicationOut(
        id=row.id,
        opening_id=row.opening_id,
        applicant=_person(names, row.applicant_id),
        message=row.message,
        status=row.status,
        status_fa=APPLICATION_STATUS_TITLE_FA[row.status],
        decision_note=row.decision_note,
        decided_at=row.decided_at,
        created_at=row.created_at,
    )


async def _openings_out(
    service: OpeningService, openings: list[TeamOpening], viewer: CurrentUser | None
) -> list[OpeningOut]:
    session = service.session
    now = _now()
    targets = await service.targets_for(openings)
    skills = await service.skill_titles({s for o in openings for s in o.needed_skills})
    role_ids = {o.role_id for o in openings if o.role_id is not None}
    roles = (
        {
            r.id: r.title_fa
            for r in await session.scalars(select(ProjectRole).where(ProjectRole.id.in_(role_ids)))
        }
        if role_ids
        else {}
    )
    names = await display_names(session, [o.poster_id for o in openings])
    applied: set[uuid.UUID] = set()
    if viewer is not None and openings:
        applied = set(
            await session.scalars(
                select(OpeningApplication.opening_id).where(
                    OpeningApplication.applicant_id == viewer.id,
                    OpeningApplication.opening_id.in_([o.id for o in openings]),
                )
            )
        )
    managed: dict[uuid.UUID, bool] = {}
    for opening in openings:
        target = targets.get(opening.id)
        managed[opening.id] = target is not None and await service.can_manage(target, viewer)
    pending = await service.pending_counts([o.id for o in openings if managed[o.id]])

    result: list[OpeningOut] = []
    for opening in openings:
        target = targets.get(opening.id)
        if target is None:
            continue
        effective = _effective(opening, now)
        result.append(
            OpeningOut(
                id=opening.id,
                title=opening.title,
                description=opening.description,
                needed_skills=[
                    SkillRefOut(id=sid, title_fa=skills[sid])
                    for sid in opening.needed_skills
                    if sid in skills
                ],
                commitment_hpw=opening.commitment_hpw,
                role=ProjectBriefOut(id=opening.role_id, title=roles[opening.role_id])
                if opening.role_id and opening.role_id in roles
                else None,
                status=opening.status,
                effective_status=effective,
                status_fa=STATUS_TITLE_FA[effective],
                expires_at=opening.expires_at,
                created_at=opening.created_at,
                target=_target_out(target),
                poster=_person(names, opening.poster_id),
                pending_count=pending.get(opening.id, 0) if managed[opening.id] else None,
                has_applied=opening.id in applied,
                can_manage=managed[opening.id],
            )
        )
    return result


async def _detail(
    service: OpeningService, opening: TeamOpening, viewer: CurrentUser | None
) -> OpeningDetailOut:
    base = (await _openings_out(service, [opening], viewer))[0]
    applications: list[OpeningApplication] = []
    if base.can_manage:
        applications = await service.applications(opening)
    mine = await service.my_application(opening.id, viewer.id) if viewer else None
    names = await display_names(
        service.session,
        [*(a.applicant_id for a in applications), *([mine.applicant_id] if mine else [])],
    )
    return OpeningDetailOut(
        **base.model_dump(),
        my_application=_application_out(mine, names) if mine else None,
        applications=[_application_out(a, names) for a in applications],
    )


@router.get("/openings", response_model=Page[OpeningOut], summary="آگهی‌های نیاز به هم‌تیمی")
async def list_openings(
    service: OpeningServiceDep,
    viewer: OptionalUserDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    q: Annotated[str | None, Query(max_length=100)] = None,
    skill_id: uuid.UUID | None = None,
    kind: TargetKind | None = None,
    project_id: uuid.UUID | None = None,
    venture_id: uuid.UUID | None = None,
    mine: Annotated[bool, Query()] = False,
) -> Page[OpeningOut]:
    """آگهی‌های باز. `mine=true` آگهی‌هایی که خودم داده‌ام، با هر وضعیتی."""
    params = PageParams(page=page, page_size=page_size)
    if mine and viewer is None:
        return Page.of([], total=0, page=params.page, page_size=params.page_size)
    stmt = service.list_query(
        q=q,
        skill_id=skill_id,
        kind=kind,
        project_id=project_id,
        venture_id=venture_id,
        poster_id=viewer.id if (mine and viewer) else None,
        include_closed=mine,
    )
    openings, total = await service.page(stmt, offset=params.offset, limit=params.page_size)
    return Page.of(
        await _openings_out(service, openings, viewer),
        total=total,
        page=params.page,
        page_size=params.page_size,
    )


@router.post(
    "/openings",
    response_model=OpeningDetailOut,
    status_code=status.HTTP_201_CREATED,
    summary="ثبت آگهی نیاز به هم‌تیمی",
    responses={403: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
async def create_opening(
    payload: OpeningIn, current: CurrentUserDep, service: OpeningServiceDep
) -> OpeningDetailOut:
    opening = await service.create(
        actor=current,
        project_id=payload.project_id,
        venture_id=payload.venture_id,
        draft=OpeningDraft(
            title=payload.title,
            description=payload.description,
            needed_skills=list(payload.needed_skill_ids),
            commitment_hpw=payload.commitment_hpw,
            role_id=payload.role_id,
        ),
    )
    return await _detail(service, opening, current)


@router.get(
    "/applications/mine",
    response_model=list[MyApplicationOut],
    summary="درخواست‌های من برای آگهی‌ها",
)
async def my_applications(
    current: CurrentUserDep, service: OpeningServiceDep
) -> list[MyApplicationOut]:
    rows = await service.applications_of(current.id)
    openings = (
        {
            o.id: o
            for o in await service.session.scalars(
                select(TeamOpening).where(TeamOpening.id.in_({r.opening_id for r in rows}))
            )
        }
        if rows
        else {}
    )
    targets = await service.targets_for(list(openings.values()))
    names = await display_names(service.session, [current.id])
    result: list[MyApplicationOut] = []
    for row in rows:
        opening = openings.get(row.opening_id)
        target = targets.get(row.opening_id)
        if opening is None or target is None:
            continue
        result.append(
            MyApplicationOut(
                **_application_out(row, names).model_dump(),
                opening_title=opening.title,
                target=_target_out(target),
            )
        )
    return result


@router.get(
    "/openings/{opening_id}",
    response_model=OpeningDetailOut,
    summary="جزئیات آگهی",
    responses={404: {"model": ErrorResponse}},
)
async def get_opening(
    opening_id: uuid.UUID, service: OpeningServiceDep, viewer: OptionalUserDep
) -> OpeningDetailOut:
    opening, _ = await service.require_visible(opening_id, viewer)
    return await _detail(service, opening, viewer)


@router.patch("/openings/{opening_id}", response_model=OpeningDetailOut, summary="ویرایش آگهی")
async def update_opening(
    opening_id: uuid.UUID,
    payload: OpeningUpdateIn,
    current: CurrentUserDep,
    service: OpeningServiceDep,
) -> OpeningDetailOut:
    opening = await service.update(
        opening=await service.require(opening_id),
        actor=current,
        draft=OpeningDraft(
            title=payload.title,
            description=payload.description,
            needed_skills=list(payload.needed_skill_ids),
            commitment_hpw=payload.commitment_hpw,
            role_id=payload.role_id,
        ),
    )
    return await _detail(service, opening, current)


@router.post("/openings/{opening_id}/close", response_model=OpeningDetailOut, summary="بستن آگهی")
async def close_opening(
    opening_id: uuid.UUID, current: CurrentUserDep, service: OpeningServiceDep
) -> OpeningDetailOut:
    opening = await service.close(opening=await service.require(opening_id), actor=current)
    return await _detail(service, opening, current)


@router.post(
    "/openings/{opening_id}/renew", response_model=OpeningDetailOut, summary="تمدید ۳۰ روزه"
)
async def renew_opening(
    opening_id: uuid.UUID, current: CurrentUserDep, service: OpeningServiceDep
) -> OpeningDetailOut:
    opening = await service.renew(opening=await service.require(opening_id), actor=current)
    return await _detail(service, opening, current)


@router.post(
    "/openings/{opening_id}/apply",
    response_model=OpeningApplicationOut,
    status_code=status.HTTP_201_CREATED,
    summary="درخواست پیوستن از آگهی",
    responses={
        409: {
            "model": ErrorResponse,
            "description": "OPENING_CLOSED، PROFILE_INCOMPLETE، DUPLICATE_APPLICATION",
        }
    },
)
async def apply_to_opening(
    opening_id: uuid.UUID, payload: ApplyIn, current: CurrentUserDep, service: OpeningServiceDep
) -> OpeningApplicationOut:
    row = await service.apply(opening_id=opening_id, actor=current, message=payload.message)
    names = await display_names(service.session, [current.id])
    return _application_out(row, names)


@router.post(
    "/applications/{application_id}/decide",
    response_model=OpeningApplicationOut,
    summary="پذیرش یا رد درخواست",
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
async def decide_application(
    application_id: uuid.UUID,
    payload: DecideIn,
    current: CurrentUserDep,
    service: OpeningServiceDep,
) -> OpeningApplicationOut:
    row = await service.decide(
        application_id=application_id,
        actor=current,
        decision=payload.decision,
        note=payload.note,
    )
    names = await display_names(service.session, [row.applicant_id])
    return _application_out(row, names)


@router.post(
    "/applications/{application_id}/withdraw",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="پس گرفتن درخواست",
)
async def withdraw_application(
    application_id: uuid.UUID, current: CurrentUserDep, service: OpeningServiceDep
) -> None:
    await service.withdraw(application_id=application_id, actor=current)


__all__ = ["router"]
