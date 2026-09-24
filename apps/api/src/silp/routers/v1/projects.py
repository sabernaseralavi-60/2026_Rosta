"""مسیر /projects — §5.7.

فهرست و جستجو، پیشنهادهای شخصی با دلیل، بازخورد پیشنهاد (M1)، و از M2:
ساخت و ویرایش پروژه، گذارهای وضعیت، تیم و درخواست پیوستن.

مرحله، تحویل‌دادنی، وظیفه و گفتگو در `workspace.py` هستند و تصمیم روی
درخواست در `applications.py`.

فیلتر در سطح کوئری انجام می‌شود، نه پس از واکشی — §6.4 قاعدهٔ ۳.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import Subquery, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from silp.core.exceptions import NotFound, ValidationFailed
from silp.core.permissions import CurrentUser, Permission
from silp.domain.recommendation import service as recommendation
from silp.domain.recommendation.diversity import DEFAULT_RESULT_SIZE
from silp.domain.recommendation.explainer import with_reasons
from silp.domain.recommendation.schemas import EXCLUSION_NOTE_FA, MatchResult, ProjectSpec
from silp.domain.recommendation.scorer import score_project
from silp.models.project import (
    DIFFICULTY_TITLE_FA,
    KIND_TITLE_FA,
    Project,
    ProjectApplication,
    ProjectInterest,
    ProjectRequiredSkill,
    ProjectRole,
    Team,
    TeamMember,
)
from silp.routers.deps import (
    ApplicationServiceDep,
    CurrentUserDep,
    OptionalUserDep,
    ProjectServiceDep,
    SessionDep,
    project_from_path,
    require,
)
from silp.schemas.common import ErrorResponse, Page, PageParams
from silp.schemas.delivery import ActivityOut
from silp.schemas.project import (
    ApplicationIn,
    ApplicationOut,
    AssetRequirementOut,
    CompleteProjectIn,
    InterestRefOut,
    MatchOut,
    ProjectDetailOut,
    ProjectIn,
    ProjectSummaryOut,
    ReasonIn,
    RecommendationFeedbackIn,
    RecommendationItemOut,
    RecommendationsOut,
    SkillRequirementOut,
    SortOrder,
    TeamMemberOut,
    TeamOut,
    breakdown_of,
    reasons_of,
)
from silp.services.directory import display_names, name_of
from silp.services.project_service import (
    AssetRequirement,
    ProjectDraft,
    RoleSpec,
    SkillRequirement,
)

router = APIRouter(prefix="/projects", tags=["projects"])
feedback_router = APIRouter(prefix="/recommendations", tags=["projects"])

MAX_RECOMMENDATIONS = 20


def project_summary_of(spec: ProjectSpec) -> ProjectSummaryOut:
    """`ProjectSpec` دامنه → قرارداد API.

    `ProjectSpec` عمداً `slug`، `summary` و `tags` ندارد (امتیازدهی به
    آن‌ها کاری ندارد)، پس اینجا مقدار امن گذاشته می‌شود و کارت پیشنهاد
    برای متن کامل به `GET /projects/{id}` می‌رود.
    """
    return ProjectSummaryOut(
        id=spec.id,
        slug="",
        title_fa=spec.title_fa,
        summary="",
        kind=spec.kind.value,
        kind_fa=KIND_TITLE_FA[spec.kind.value],
        status="OPEN",
        difficulty=spec.difficulty,
        difficulty_fa=DIFFICULTY_TITLE_FA[spec.difficulty],
        time_commitment_hpw=spec.time_commitment_hpw,
        work_style=spec.work_style.value,
        team_size_min=spec.team_size_min,
        team_size_max=spec.team_size_max,
        active_members=spec.active_members,
        open_seats=spec.open_seats,
        deadline_on=spec.deadline_on,
        applications_close_at=spec.applications_close_at,
    )


def _summary_of_row(project: Project, active_members: int) -> ProjectSummaryOut:
    return ProjectSummaryOut(
        id=project.id,
        slug=project.slug,
        title_fa=project.title_fa,
        summary=project.summary,
        lead_id=project.lead_id,
        kind=project.kind,
        kind_fa=KIND_TITLE_FA[project.kind],
        status=project.status,
        difficulty=project.difficulty,
        difficulty_fa=DIFFICULTY_TITLE_FA[project.difficulty],
        time_commitment_hpw=project.time_commitment_hpw,
        work_style=project.work_style,
        team_size_min=project.team_size_min,
        team_size_max=project.team_size_max,
        active_members=active_members,
        open_seats=max(0, project.team_size_max - active_members),
        tags=list(project.tags),
        deadline_on=project.deadline_on,
        applications_close_at=project.applications_close_at,
        workflow=project.workflow,
    )


def _item_of(match: MatchResult) -> RecommendationItemOut:
    return RecommendationItemOut(
        project=project_summary_of(match.project),
        match_score=round(match.score, 1),
        reasons=reasons_of(match),
        breakdown=breakdown_of(match),
        is_stretch=match.is_stretch,
    )


def _member_counts() -> Subquery:
    return (
        select(Team.project_id.label("project_id"), func.count().label("members"))
        .join(TeamMember, TeamMember.team_id == Team.id)
        .where(TeamMember.status == "ACTIVE", Team.project_id.is_not(None))
        .group_by(Team.project_id)
        .subquery()
    )


@router.get(
    "/recommended",
    response_model=RecommendationsOut,
    summary="پیشنهادهای شخصی با دلیل",
    responses={401: {"model": ErrorResponse}},
)
async def recommended(
    current: CurrentUserDep,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=MAX_RECOMMENDATIONS)] = DEFAULT_RESULT_SIZE,
) -> RecommendationsOut:
    """§5.7 — هر پیشنهاد با امتیاز، تفکیک شش‌گانه و دلایل فارسی.

    متن دلیل از سرور می‌آید و مستقیماً نمایش داده می‌شود (§8.10).
    """
    matches, completeness, computed_at = await recommendation.recommend(
        session, current.id, limit=limit
    )
    return RecommendationsOut(
        items=[_item_of(m) for m in matches],
        profile_completeness=round(completeness, 2),
        computed_at=computed_at,
    )


# پیش از `/{project_id}` ثبت می‌شود، وگرنه FastAPI «mine» را شناسهٔ
# پروژه می‌خواند و ۴۲۲ برمی‌گرداند.
@router.get(
    "/mine",
    response_model=list[ProjectSummaryOut],
    summary="پروژه‌های من — مدیریت‌شده یا عضو",
)
async def my_projects(
    current: CurrentUserDep,
    session: SessionDep,
) -> list[ProjectSummaryOut]:
    """هر پروژه‌ای که کاربر مدیرش است یا در تیمش عضو فعال است.

    `DRAFT` هم می‌آید: پروژهٔ منتشرنشده در بانک پروژه نیست، ولی باید در
    فهرست خودِ سازنده باشد وگرنه گم می‌شود.
    """
    members = _member_counts()
    member_count = func.coalesce(members.c.members, 0)
    mine = (
        select(Team.project_id)
        .join(TeamMember, TeamMember.team_id == Team.id)
        .where(TeamMember.user_id == current.id, TeamMember.status == "ACTIVE")
    )
    rows = (
        await session.execute(
            select(Project, member_count.label("active_members"))
            .outerjoin(members, members.c.project_id == Project.id)
            .where(
                Project.deleted_at.is_(None),
                (Project.lead_id == current.id) | (Project.id.in_(mine)),
            )
            .order_by(Project.last_activity_at.desc())
        )
    ).all()
    return [_summary_of_row(project, int(count or 0)) for project, count in rows]


@router.get("", response_model=Page[ProjectSummaryOut], summary="فهرست و جستجوی پروژه")
async def list_projects(
    session: SessionDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    kind: Annotated[str | None, Query()] = None,
    work_style: Annotated[str | None, Query()] = None,
    difficulty_max: Annotated[int | None, Query(ge=1, le=5)] = None,
    skill_id: Annotated[uuid.UUID | None, Query()] = None,
    interest_id: Annotated[uuid.UUID | None, Query()] = None,
    q: Annotated[str | None, Query(max_length=100, description="جستجوی فارسی")] = None,
    sort: Annotated[SortOrder, Query()] = "newest",
) -> Page[ProjectSummaryOut]:
    """فهرست پروژه‌های باز.

    جستجو روی ستون تولیدشدهٔ `search_norm` با ایندکس trigram انجام می‌شود،
    نه `ILIKE '%…%'` — §4.11.
    """
    params = PageParams(page=page, page_size=page_size)
    members = _member_counts()
    member_count = func.coalesce(members.c.members, 0)

    stmt = (
        select(Project, member_count.label("active_members"))
        .outerjoin(members, members.c.project_id == Project.id)
        .where(Project.status == "OPEN", Project.deleted_at.is_(None))
    )

    if kind:
        stmt = stmt.where(Project.kind == kind)
    if work_style:
        stmt = stmt.where(Project.work_style == work_style)
    if difficulty_max is not None:
        stmt = stmt.where(Project.difficulty <= difficulty_max)
    if skill_id is not None:
        stmt = stmt.where(
            Project.id.in_(
                select(ProjectRequiredSkill.project_id).where(
                    ProjectRequiredSkill.skill_id == skill_id
                )
            )
        )
    if interest_id is not None:
        stmt = stmt.where(
            Project.id.in_(
                select(ProjectInterest.project_id).where(ProjectInterest.interest_id == interest_id)
            )
        )
    if q and q.strip():
        normalized = func.fa_normalize(q.strip())
        stmt = stmt.where(Project.search_norm.like(func.concat("%", normalized, "%")))

    match sort:
        case "deadline":
            # پروژه‌های بی‌مهلت آخر می‌آیند، نه اول.
            stmt = stmt.order_by(Project.deadline_on.is_(None), Project.deadline_on)
        case "popular":
            stmt = stmt.order_by(member_count.desc(), Project.created_at.desc())
        case _:
            # `match` بدون نیمرخ معنا ندارد؛ مرتب‌سازی شخصی در
            # `/projects/recommended` انجام می‌شود.
            stmt = stmt.order_by(Project.created_at.desc())

    total = await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = (await session.execute(stmt.offset(params.offset).limit(params.page_size))).all()

    return Page.of(
        [_summary_of_row(project, int(count or 0)) for project, count in rows],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )


@router.get(
    "/{project_id}",
    response_model=ProjectDetailOut,
    summary="جزئیات پروژه + تطابق من",
    responses={404: {"model": ErrorResponse}},
)
async def get_project(
    project_id: uuid.UUID,
    session: SessionDep,
    current: OptionalUserDep,
) -> ProjectDetailOut:
    """اگر کاربر وارد باشد، `match` هم محاسبه می‌شود.

    این محاسبه از کش پیشنهادها نمی‌آید: کاربر ممکن است پروژه‌ای را ببیند
    که در ده تای برتر نبوده و همچنان حق دارد بداند چقدر به او می‌خورد.
    """
    project = await session.get(Project, project_id)
    if project is None or project.deleted_at is not None:
        raise NotFound("پروژه پیدا نشد.")

    active_members = (
        await session.scalar(
            select(func.count())
            .select_from(TeamMember)
            .join(Team, Team.id == TeamMember.team_id)
            .where(Team.project_id == project_id, TeamMember.status == "ACTIVE")
        )
        or 0
    )

    skill_titles, asset_titles, interest_titles = await recommendation.taxonomy_titles(session)
    base = _summary_of_row(project, int(active_members))

    match: MatchOut | None = None
    if current is not None:
        now = datetime.now(UTC)
        ctx = await recommendation.load_student_context(session, current.id)
        spec = await recommendation.spec_for_project(session, project)
        scored = with_reasons(ctx, score_project(ctx, spec, now=now))
        match = MatchOut(
            match_score=round(scored.score, 1),
            breakdown=breakdown_of(scored),
            reasons=reasons_of(scored),
            is_stretch=scored.is_stretch,
            is_excluded=scored.is_excluded,
            exclusion_note=(
                EXCLUSION_NOTE_FA.get(scored.exclusion_reason or "") if scored.is_excluded else None
            ),
        )

    return ProjectDetailOut(
        **base.model_dump(),
        description=project.description,
        workflow_completed_at=project.workflow_completed_at,
        expected_output=project.expected_output,
        rewards=project.rewards,
        required_skills=[
            SkillRequirementOut(
                skill_id=r.skill_id,
                title_fa=skill_titles.get(r.skill_id, "مهارت"),
                min_level=r.min_level,
                weight=r.weight,
                is_teachable=r.is_teachable,
            )
            for r in project.required_skills
        ],
        required_assets=[
            AssetRequirementOut(
                asset_id=r.asset_id,
                title_fa=asset_titles.get(r.asset_id, "امکانات"),
                is_mandatory=r.is_mandatory,
            )
            for r in project.required_assets
        ],
        interests=[
            InterestRefOut(
                interest_id=r.interest_id,
                title_fa=interest_titles.get(r.interest_id, "این حوزه"),
            )
            for r in project.interests
        ],
        match=match,
    )


@feedback_router.post(
    "/{project_id}/feedback",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="بازخورد روی یک پیشنهاد",
    responses={404: {"model": ErrorResponse}},
)
async def submit_feedback(
    project_id: uuid.UUID,
    payload: RecommendationFeedbackIn,
    current: CurrentUserDep,
    session: SessionDep,
) -> None:
    """§8.9 — «به من نمی‌خورد» / «دیگر نشانم نده» / «فعلاً نه، ولی جالب است».

    نظر تازه جای نظر قبلی را می‌گیرد؛ دانشجو باید بتواند نظرش را عوض کند.
    """
    project = await session.get(Project, project_id)
    if project is None or project.deleted_at is not None:
        raise NotFound("پروژه پیدا نشد.")

    await recommendation.record_feedback(
        session,
        user_id=current.id,
        project_id=project_id,
        verdict=payload.verdict,
        reason=payload.reason,
    )


# ── ساخت و ویرایش — FR-PRJ-01 ──────────────────────────────────────────
APPLICATION_STATUS_FA: dict[str, str] = {
    "PENDING": "در انتظار تصمیم",
    "ACCEPTED": "پذیرفته شد",
    "REJECTED": "رد شد",
    "WAITLISTED": "در فهرست انتظار",
    "WITHDRAWN": "انصراف داده شد",
}


def _draft_of(payload: ProjectIn) -> ProjectDraft:
    return ProjectDraft(
        title_fa=payload.title_fa,
        summary=payload.summary,
        description=payload.description,
        kind=payload.kind,
        expected_output=payload.expected_output,
        difficulty=payload.difficulty,
        work_style=payload.work_style,
        team_size_min=payload.team_size_min,
        team_size_max=payload.team_size_max,
        time_commitment_hpw=payload.time_commitment_hpw,
        tags=list(payload.tags),
        rewards=dict(payload.rewards),
        starts_on=payload.starts_on,
        deadline_on=payload.deadline_on,
        applications_close_at=payload.applications_close_at,
        venture_id=payload.venture_id,
        offering_id=payload.offering_id,
        workflow=payload.workflow,
        required_skills=[
            SkillRequirement(
                skill_id=r.skill_id,
                min_level=r.min_level,
                weight=r.weight,
                is_teachable=r.is_teachable,
            )
            for r in payload.required_skills
        ],
        required_assets=[
            AssetRequirement(asset_id=r.asset_id, is_mandatory=r.is_mandatory)
            for r in payload.required_assets
        ],
        interests=list(payload.interests),
        roles=[
            RoleSpec(title_fa=r.title_fa, slots=r.slots, description=r.description)
            for r in payload.roles
        ],
    )


async def _detail_of(
    session: AsyncSession, project: Project, *, active_members: int
) -> ProjectDetailOut:
    skill_titles, asset_titles, interest_titles = await recommendation.taxonomy_titles(session)
    base = _summary_of_row(project, active_members)
    return ProjectDetailOut(
        **base.model_dump(),
        description=project.description,
        workflow_completed_at=project.workflow_completed_at,
        expected_output=project.expected_output,
        rewards=project.rewards,
        required_skills=[
            SkillRequirementOut(
                skill_id=r.skill_id,
                title_fa=skill_titles.get(r.skill_id, "مهارت"),
                min_level=r.min_level,
                weight=r.weight,
                is_teachable=r.is_teachable,
            )
            for r in project.required_skills
        ],
        required_assets=[
            AssetRequirementOut(
                asset_id=r.asset_id,
                title_fa=asset_titles.get(r.asset_id, "امکانات"),
                is_mandatory=r.is_mandatory,
            )
            for r in project.required_assets
        ],
        interests=[
            InterestRefOut(
                interest_id=r.interest_id, title_fa=interest_titles.get(r.interest_id, "این حوزه")
            )
            for r in project.interests
        ],
    )


@router.post(
    "",
    response_model=ProjectDetailOut,
    status_code=status.HTTP_201_CREATED,
    summary="ساخت پروژه",
    responses={403: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
async def create_project(
    payload: ProjectIn,
    current: CurrentUserDep,
    projects: ProjectServiceDep,
    session: SessionDep,
) -> ProjectDetailOut:
    """FR-PRJ-01 — پروژهٔ تازه `DRAFT` است و هنوز در بانک پروژه دیده نمی‌شود.

    نوع `D_PERSONAL` برای هر دانشجو باز است؛ A/B/C مجوز مدیریتی می‌خواهد
    (§6.2). بررسی در سرویس انجام می‌شود، نه با `require(...)`: به بدنهٔ
    درخواست وابسته است، نه به مسیر.
    """
    project = await projects.create(actor=current, draft=_draft_of(payload))
    return await _detail_of(session, project, active_members=0)


@router.patch(
    "/{project_id}",
    response_model=ProjectDetailOut,
    summary="ویرایش پروژه",
    responses={403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
async def update_project(
    project_id: uuid.UUID,
    payload: ProjectIn,
    projects: ProjectServiceDep,
    session: SessionDep,
    current: Annotated[
        CurrentUser, Depends(require(Permission.PROJECT_EDIT, scope=project_from_path))
    ],
) -> ProjectDetailOut:
    project = await projects.require(project_id)
    if payload.kind != project.kind:
        raise ValidationFailed("نوع پروژه پس از ساخت عوض نمی‌شود.")
    if payload.workflow != project.workflow:
        raise ValidationFailed("الگوی گردش‌کار پروژه پس از ساخت عوض نمی‌شود.")
    if payload.offering_id is not None and payload.offering_id != project.offering_id:
        raise ValidationFailed("ارائهٔ پروژه پس از ساخت عوض نمی‌شود.")
    project = await projects.update(project=project, actor=current, draft=_draft_of(payload))
    active = await projects.active_member_count(project.id)
    return await _detail_of(session, project, active_members=active)


# ── گذارهای وضعیت — §7.4 ───────────────────────────────────────────────
@router.post(
    "/{project_id}/publish",
    response_model=ProjectDetailOut,
    summary="انتشار پروژه (DRAFT → OPEN)",
    responses={403: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
async def publish_project(
    project_id: uuid.UUID,
    projects: ProjectServiceDep,
    session: SessionDep,
    current: Annotated[
        CurrentUser, Depends(require(Permission.PROJECT_PUBLISH, scope=project_from_path))
    ],
) -> ProjectDetailOut:
    """§7.12 — تیم در همین تراکنش ساخته می‌شود و مدیر عضو `is_lead` آن است."""
    project = await projects.publish(project=await projects.require(project_id), actor=current)
    active = await projects.active_member_count(project.id)
    return await _detail_of(session, project, active_members=active)


@router.post(
    "/{project_id}/start",
    response_model=ProjectDetailOut,
    summary="شروع کار پروژه (OPEN → IN_PROGRESS)",
    responses={409: {"model": ErrorResponse}},
)
async def start_project(
    project_id: uuid.UUID,
    projects: ProjectServiceDep,
    session: SessionDep,
    current: Annotated[
        CurrentUser, Depends(require(Permission.PROJECT_PUBLISH, scope=project_from_path))
    ],
) -> ProjectDetailOut:
    project = await projects.start(project=await projects.require(project_id), actor=current)
    active = await projects.active_member_count(project.id)
    return await _detail_of(session, project, active_members=active)


@router.post(
    "/{project_id}/pause",
    response_model=ProjectDetailOut,
    summary="توقف موقت پروژه",
    responses={409: {"model": ErrorResponse}},
)
async def pause_project(
    project_id: uuid.UUID,
    payload: ReasonIn,
    projects: ProjectServiceDep,
    session: SessionDep,
    current: Annotated[
        CurrentUser, Depends(require(Permission.PROJECT_CLOSE, scope=project_from_path))
    ],
) -> ProjectDetailOut:
    project = await projects.pause(
        project=await projects.require(project_id), actor=current, reason=payload.reason
    )
    active = await projects.active_member_count(project.id)
    return await _detail_of(session, project, active_members=active)


@router.post(
    "/{project_id}/resume",
    response_model=ProjectDetailOut,
    summary="از سرگیری پروژه",
    responses={409: {"model": ErrorResponse}},
)
async def resume_project(
    project_id: uuid.UUID,
    projects: ProjectServiceDep,
    session: SessionDep,
    current: Annotated[
        CurrentUser, Depends(require(Permission.PROJECT_CLOSE, scope=project_from_path))
    ],
) -> ProjectDetailOut:
    project = await projects.resume(project=await projects.require(project_id), actor=current)
    active = await projects.active_member_count(project.id)
    return await _detail_of(session, project, active_members=active)


@router.post(
    "/{project_id}/cancel",
    response_model=ProjectDetailOut,
    summary="لغو پروژه",
    responses={409: {"model": ErrorResponse}},
)
async def cancel_project(
    project_id: uuid.UUID,
    payload: ReasonIn,
    projects: ProjectServiceDep,
    session: SessionDep,
    current: Annotated[
        CurrentUser, Depends(require(Permission.PROJECT_CLOSE, scope=project_from_path))
    ],
) -> ProjectDetailOut:
    """§7.4 — امتیاز مراحل تأییدشده حفظ می‌شود؛ شکست پروژه تقصیر دانشجو نیست."""
    project = await projects.cancel(
        project=await projects.require(project_id), actor=current, reason=payload.reason
    )
    active = await projects.active_member_count(project.id)
    return await _detail_of(session, project, active_members=active)


@router.post(
    "/{project_id}/complete",
    response_model=ProjectDetailOut,
    summary="بستن پروژه",
    responses={409: {"model": ErrorResponse}},
)
async def complete_project(
    project_id: uuid.UUID,
    payload: CompleteProjectIn,
    projects: ProjectServiceDep,
    session: SessionDep,
    current: Annotated[
        CurrentUser, Depends(require(Permission.PROJECT_CLOSE, scope=project_from_path))
    ],
) -> ProjectDetailOut:
    """FR-PRJ-08 — همهٔ مراحل الزامی تأییدشده + گزارش نهایی."""
    project = await projects.complete(
        project=await projects.require(project_id),
        actor=current,
        final_report=payload.final_report,
    )
    active = await projects.active_member_count(project.id)
    return await _detail_of(session, project, active_members=active)


# ── تیم — FR-TEAM-03 ───────────────────────────────────────────────────
@router.get(
    "/{project_id}/team",
    response_model=TeamOut,
    summary="اعضای تیم",
    responses={403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
async def get_team(
    project_id: uuid.UUID,
    current: CurrentUserDep,
    projects: ProjectServiceDep,
    session: SessionDep,
) -> TeamOut:
    project = await projects.require(project_id)
    await projects.require_member(project_id, current)

    team = await projects.team_of(project_id)
    members = await projects.members(project_id)
    names = await display_names(session, [m.user_id for m in members])
    role_titles = await _role_titles(session, project_id)
    active = sum(1 for m in members if m.status == "ACTIVE")

    return TeamOut(
        project_id=project_id,
        name=team.name if team else project.title_fa,
        members=[
            TeamMemberOut(
                user_id=m.user_id,
                full_name=name_of(names, m.user_id),
                username=names[m.user_id].username if m.user_id in names else None,
                role_id=m.role_id,
                role_title_fa=role_titles.get(m.role_id) if m.role_id else None,
                is_lead=m.is_lead,
                status=m.status,
                joined_at=m.joined_at,
                left_at=m.left_at,
            )
            for m in members
        ],
        active_members=active,
        open_seats=max(0, project.team_size_max - active),
    )


@router.delete(
    "/{project_id}/team/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="حذف عضو از تیم",
    responses={403: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
async def remove_member(
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    projects: ProjectServiceDep,
    current: Annotated[
        CurrentUser, Depends(require(Permission.PROJECT_MEMBER_REMOVE, scope=project_from_path))
    ],
    # دلیل پارامتر پرس‌وجوست، نه بدنه: `DELETE` با بدنه را همهٔ پراکسی‌ها
    # و کلاینت‌ها یکسان رفتار نمی‌کنند.
    reason: Annotated[str, Query(min_length=3, max_length=500)],
) -> None:
    """FR-TEAM-03 — حذف عضو همیشه دلیل دارد؛ عضو باید بداند چرا."""
    await projects.remove_member(
        project=await projects.require(project_id),
        user_id=user_id,
        actor=current,
        reason=reason,
    )


@router.post(
    "/{project_id}/leave",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="ترک تیم",
    responses={403: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
async def leave_team(
    project_id: uuid.UUID,
    payload: ReasonIn,
    current: CurrentUserDep,
    projects: ProjectServiceDep,
) -> None:
    await projects.leave(
        project=await projects.require(project_id), actor=current, reason=payload.reason
    )


# ── درخواست پیوستن — FR-PRJ-04 ─────────────────────────────────────────
@router.post(
    "/{project_id}/applications",
    response_model=ApplicationOut,
    status_code=status.HTTP_201_CREATED,
    summary="درخواست پیوستن",
    responses={409: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
async def apply_to_project(
    project_id: uuid.UUID,
    payload: ApplicationIn,
    current: CurrentUserDep,
    applications: ApplicationServiceDep,
    projects: ProjectServiceDep,
    session: SessionDep,
) -> ApplicationOut:
    """§7.5 — چهار شرط بررسی و امتیاز تطابق عکس‌برداری می‌شود."""
    project = await projects.require(project_id)
    application = await applications.apply(
        project=project,
        actor=current,
        motivation=payload.motivation,
        role_id=payload.role_id,
    )
    return (await applications_out(session, [application]))[0]


@router.get(
    "/{project_id}/applications",
    response_model=list[ApplicationOut],
    summary="فهرست درخواست‌ها",
    responses={403: {"model": ErrorResponse}},
)
async def list_applications(
    project_id: uuid.UUID,
    applications: ApplicationServiceDep,
    session: SessionDep,
    _: Annotated[
        CurrentUser,
        Depends(require(Permission.PROJECT_APPLICATION_DECIDE, scope=project_from_path)),
    ],
    application_status: Annotated[str | None, Query(alias="status")] = None,
) -> list[ApplicationOut]:
    """§7.5 — مدیر پروژه نیمرخ متقاضی و امتیاز تطابق را کنار هم می‌بیند.

    مرتب‌سازی بر اساس امتیاز تطابق است، نه تاریخ: مدیری که بیست درخواست
    دارد باید از بالا بخواند.
    """
    rows = await applications.for_project(project_id, status=application_status)
    return await applications_out(session, rows)


# ── جریان فعالیت — FR-PRJ-06 ───────────────────────────────────────────
@router.get(
    "/{project_id}/activity",
    response_model=list[ActivityOut],
    summary="جریان فعالیت پروژه",
    responses={403: {"model": ErrorResponse}},
)
async def project_activity(
    project_id: uuid.UUID,
    current: CurrentUserDep,
    projects: ProjectServiceDep,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[ActivityOut]:
    await projects.require_member(project_id, current)
    rows = await projects.activity(project_id, limit=limit)
    names = await display_names(session, [r.actor_id for r in rows if r.actor_id])
    return [
        ActivityOut(
            id=r.id,
            actor_id=r.actor_id,
            actor_name=name_of(names, r.actor_id),
            kind=r.kind,
            summary=r.summary,
            entity_type=r.entity_type,
            entity_id=r.entity_id,
            created_at=r.created_at,
        )
        for r in rows
    ]


# ── کمکی‌های مشترک ─────────────────────────────────────────────────────
async def _role_titles(session: AsyncSession, project_id: uuid.UUID) -> dict[uuid.UUID, str]:
    rows = await session.execute(
        select(ProjectRole.id, ProjectRole.title_fa).where(ProjectRole.project_id == project_id)
    )
    return dict(rows.tuples().all())


async def applications_out(
    session: AsyncSession, rows: list[ProjectApplication]
) -> list[ApplicationOut]:
    """تبدیل دسته‌ای درخواست‌ها — §5.14 «بدون N+1»."""
    if not rows:
        return []
    names = await display_names(session, [r.applicant_id for r in rows])

    role_ids = {r.role_id for r in rows if r.role_id}
    role_titles: dict[uuid.UUID, str] = {}
    if role_ids:
        result = await session.execute(
            select(ProjectRole.id, ProjectRole.title_fa).where(ProjectRole.id.in_(role_ids))
        )
        role_titles = dict(result.tuples().all())

    result = await session.execute(
        select(Project.id, Project.title_fa).where(Project.id.in_({r.project_id for r in rows}))
    )
    project_titles = dict(result.tuples().all())

    return [
        ApplicationOut(
            id=r.id,
            project_id=r.project_id,
            project_title_fa=project_titles.get(r.project_id),
            applicant_id=r.applicant_id,
            applicant_name=name_of(names, r.applicant_id),
            role_id=r.role_id,
            role_title_fa=role_titles.get(r.role_id) if r.role_id else None,
            motivation=r.motivation,
            match_score=float(r.match_score) if r.match_score is not None else None,
            match_breakdown=r.match_breakdown,
            status=r.status,
            status_fa=APPLICATION_STATUS_FA.get(r.status, r.status),
            decision_note=r.decision_note,
            decided_at=r.decided_at,
            created_at=r.created_at,
        )
        for r in rows
    ]


__all__ = [
    "APPLICATION_STATUS_FA",
    "applications_out",
    "feedback_router",
    "project_summary_of",
    "router",
]
