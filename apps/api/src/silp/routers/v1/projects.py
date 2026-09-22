"""مسیر /projects — §5.7، بخش M1.

در این مرحله سه چیز کار می‌کند: فهرست و جستجوی پروژه، پیشنهادهای شخصی با
دلیل، و بازخورد روی پیشنهاد. ساخت پروژه، درخواست پیوستن، تیم و مراحل در
M2 می‌آیند.

فیلتر در سطح کوئری انجام می‌شود، نه پس از واکشی — §6.4 قاعدهٔ ۳.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Query, status
from sqlalchemy import Subquery, func, select

from silp.core.exceptions import NotFound
from silp.domain.recommendation import service as recommendation
from silp.domain.recommendation.diversity import DEFAULT_RESULT_SIZE
from silp.domain.recommendation.explainer import with_reasons
from silp.domain.recommendation.schemas import EXCLUSION_NOTE_FA, MatchResult, ProjectSpec
from silp.domain.recommendation.scorer import score_project
from silp.models.project import (
    DIFFICULTY_TITLE_FA,
    KIND_TITLE_FA,
    Project,
    ProjectInterest,
    ProjectRequiredSkill,
    Team,
    TeamMember,
)
from silp.routers.deps import CurrentUserDep, OptionalUserDep, SessionDep
from silp.schemas.common import ErrorResponse, Page, PageParams
from silp.schemas.project import (
    AssetRequirementOut,
    InterestRefOut,
    MatchOut,
    ProjectDetailOut,
    ProjectSummaryOut,
    RecommendationFeedbackIn,
    RecommendationItemOut,
    RecommendationsOut,
    SkillRequirementOut,
    SortOrder,
    breakdown_of,
    reasons_of,
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


__all__ = ["feedback_router", "project_summary_of", "router"]
