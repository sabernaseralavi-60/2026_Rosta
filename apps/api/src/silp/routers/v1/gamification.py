"""مسیرهای امتیاز، نشان، رتبه‌بندی و داشبورد — M5.

| مسیر | مرجع |
|------|------|
| `GET /me/points`، `GET /me/points/summary` | §5.3، M5-09 |
| `GET /me/badges`، `POST /me/badges/seen` | §5.3، §9.10 |
| `GET /me/dashboard` | FR-DASH-01، M5-10 |
| `GET /me/learning-score/{offering_id}` | §9.6، M5-06 |
| `GET /leaderboard` | §5.8، FR-GAM-04، M5-07 |
| `GET /teach/dashboard` | §5.11، FR-DASH-02، M5-11 |
| `GET /teach/offerings/{id}/learning-scores` | §9.6 «دفتر نمره» |
| `/admin/point-rules…`، `/admin/point-entries/{id}/reverse` | §5.12، FR-GAM-02، M5-08 |

داشبورد و دفتر امتیاز فقط دادهٔ **خودِ** کاربر را برمی‌گردانند و شناسهٔ
کاربر هرگز از ورودی خوانده نمی‌شود — پس «امتیاز دیگری را ببین» حتی با
دستکاری درخواست ممکن نیست.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from silp.core.permissions import CurrentUser, Permission, Role, ScopeType
from silp.domain.gamification.learning_score import COMPONENT_TITLE_FA
from silp.domain.gamification.levels import LevelProgress
from silp.domain.project_health import HEALTH_TITLE_FA
from silp.models.gamification import (
    BADGE_TIER_TITLE_FA,
    POINT_CATEGORY_TITLE_FA,
    Badge,
    PointEntry,
    UserBadge,
)
from silp.routers.deps import CurrentUserDep, SessionDep, offering_from_path, require
from silp.schemas.common import ErrorResponse
from silp.schemas.gamification import (
    BadgeOut,
    BadgesOut,
    BadgesSeenIn,
    BadgesSeenOut,
    CourseCardOut,
    LeaderboardOut,
    LeaderRowOut,
    LeaderUserOut,
    LearningComponentOut,
    LearningScoreOut,
    LevelOut,
    MyStandingOut,
    NeedsAttentionOut,
    NextStepOut,
    OfferingStatsOut,
    PointCategory,
    PointEntryOut,
    PointLedgerOut,
    PointRuleOut,
    PointRuleUpdateIn,
    PointsSummaryOut,
    ProjectAtRiskOut,
    ProjectCardOut,
    QueueOut,
    RecalculateIn,
    RecalculateOut,
    ReverseEntryIn,
    StudentAtRiskOut,
    StudentDashboardOut,
    TeachDashboardOut,
    TrendPointOut,
    UpcomingEventOut,
)
from silp.services import authz
from silp.services.badge_service import BadgeService, BadgeStatus
from silp.services.dashboard_service import DashboardService
from silp.services.directory import display_names, name_of
from silp.services.leaderboard_service import BoardRow, LeaderboardService
from silp.services.learning_score_service import LearningScoreService, StudentLearning
from silp.services.point_sources import SOURCE_TYPE_TITLE_FA, describe
from silp.services.points_service import PointsService, PointsSummary
from silp.services.teach_dashboard_service import Queue, TeachDashboardService

RATIO_QUANTUM = Decimal("0.01")

AUTH_ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse, "description": "احراز هویت نشده"}
}

me_router = APIRouter(prefix="/me", tags=["gamification"], responses=AUTH_ERRORS)
leaderboard_router = APIRouter(prefix="/leaderboard", tags=["gamification"], responses=AUTH_ERRORS)
teach_router = APIRouter(prefix="/teach", tags=["teaching"], responses=AUTH_ERRORS)
admin_router = APIRouter(prefix="/admin", tags=["admin"], responses=AUTH_ERRORS)


# ── تبدیل‌ها ───────────────────────────────────────────────────────────
async def entries_out(session: AsyncSession, entries: list[PointEntry]) -> list[PointEntryOut]:
    if not entries:
        return []
    points = PointsService(session)
    labels = await describe(session, entries)
    reversed_ids = await points.reversed_ids([e.id for e in entries if e.reverses_id is None])
    titles: dict[str, str] = {}
    for entry in entries:
        if entry.rule_code not in titles:
            rule = await points.rule(entry.rule_code)
            titles[entry.rule_code] = rule.title_fa if rule else entry.rule_code
    result: list[PointEntryOut] = []
    for entry in entries:
        label = labels.get((entry.source_type, entry.source_id)) if entry.source_id else None
        result.append(
            PointEntryOut(
                id=entry.id,
                rule_code=entry.rule_code,
                rule_title_fa=titles[entry.rule_code],
                category=entry.category,
                category_fa=POINT_CATEGORY_TITLE_FA[entry.category],
                amount=entry.amount,
                source_type=entry.source_type,
                source_type_fa=SOURCE_TYPE_TITLE_FA.get(entry.source_type),
                source_id=entry.source_id,
                source_label=label.label if label else None,
                source_href=label.href if label else None,
                note=entry.note,
                created_at=entry.created_at,
                reverses_id=entry.reverses_id,
                is_reversed=entry.id in reversed_ids,
            )
        )
    return result


def level_out(level: LevelProgress) -> LevelOut:
    return LevelOut(
        level=level.level,
        title_fa=level.title_fa,
        current_at=level.current_at,
        next_at=level.next_at,
        to_next=level.to_next,
        ratio=level.ratio,
    )


async def summary_out(session: AsyncSession, summary: PointsSummary) -> PointsSummaryOut:
    return PointsSummaryOut(
        total=summary.level.total,
        level=level_out(summary.level),
        by_category=summary.by_category,
        term_total=summary.term_total,
        term_by_category=summary.term_by_category,
        latest_entry_id=summary.recent[0].id if summary.recent else None,
        recent=await entries_out(session, summary.recent),
    )


def badge_out(status: BadgeStatus) -> BadgeOut:
    badge = status.badge
    return BadgeOut(
        code=badge.code,
        title_fa=badge.title_fa,
        description=badge.description,
        icon=badge.icon,
        tier=badge.tier,
        tier_fa=BADGE_TIER_TITLE_FA[badge.tier],
        earned=status.earned,
        awarded_at=status.awarded_at,
        seen=not status.earned or status.seen_at is not None,
        progress_current=status.progress.current,
        progress_target=status.progress.target,
        progress_ratio=status.progress.ratio.quantize(RATIO_QUANTUM),
    )


def earned_badge_out(badge: Badge, own: UserBadge) -> BadgeOut:
    """نشان کسب‌شده بدون ارزیابی دوبارهٔ معیار — پیشرفتش به‌هرحال کامل است."""
    return BadgeOut(
        code=badge.code,
        title_fa=badge.title_fa,
        description=badge.description,
        icon=badge.icon,
        tier=badge.tier,
        tier_fa=BADGE_TIER_TITLE_FA[badge.tier],
        earned=True,
        awarded_at=own.awarded_at,
        seen=own.seen_at is not None,
        progress_current=Decimal(1),
        progress_target=Decimal(1),
        progress_ratio=Decimal(1),
    )


def learning_out(
    offering_id: uuid.UUID, row: StudentLearning, display_name: str | None = None
) -> LearningScoreOut:
    components = []
    for component in row.score.components:
        fraction = row.inputs.get(component.key)
        components.append(
            LearningComponentOut(
                key=component.key,
                title_fa=COMPONENT_TITLE_FA[component.key],
                ratio=component.ratio,
                weight=component.weight,
                earned=fraction.earned,
                possible=fraction.possible,
            )
        )
    return LearningScoreOut(
        offering_id=offering_id,
        student_id=row.student_id,
        display_name=display_name,
        score=row.score.score,
        suggested_grade=row.score.suggested_grade,
        components=components,
    )


# ── /me ────────────────────────────────────────────────────────────────
@me_router.get("/points", response_model=PointLedgerOut, summary="دفتر کل امتیاز شخصی")
async def my_points(
    current: CurrentUserDep,
    session: SessionDep,
    category: PointCategory | None = None,
    source_type: Annotated[str | None, Query(max_length=40)] = None,
    source_id: uuid.UUID | None = None,
    cursor: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
) -> PointLedgerOut:
    """تازه‌ترین اول، کرسری. فیلتر `source_*` همان پیوند «این امتیاز از کجا
    آمد» است (§9.10 شفافیت)."""
    entries, next_cursor = await PointsService(session).ledger(
        current.id,
        category=category,
        source_type=source_type,
        source_id=source_id,
        before=cursor,
        limit=limit,
    )
    return PointLedgerOut(items=await entries_out(session, entries), next_cursor=next_cursor)


@me_router.get(
    "/points/summary", response_model=PointsSummaryOut, summary="امتیاز کل، سطح و امتیاز نیم‌سال"
)
async def my_points_summary(current: CurrentUserDep, session: SessionDep) -> PointsSummaryOut:
    return await summary_out(session, await PointsService(session).summary(current.id))


@me_router.get("/badges", response_model=BadgesOut, summary="نشان‌های کسب‌شده و قفل‌شده")
async def my_badges(current: CurrentUserDep, session: SessionDep) -> BadgesOut:
    """قفل‌ها با شرط و پیشرفت — «این خودش یک راهنمای مسیر است» (§9.5)."""
    statuses = await BadgeService(session).statuses(current.id)
    earned = sorted(
        (s for s in statuses if s.earned),
        key=lambda s: s.awarded_at.timestamp() if s.awarded_at else 0.0,
        reverse=True,
    )
    locked = sorted(
        (s for s in statuses if not s.earned),
        key=lambda s: (-s.progress.ratio, s.badge.sort_order),
    )
    return BadgesOut(earned=[badge_out(s) for s in earned], locked=[badge_out(s) for s in locked])


@me_router.post("/badges/seen", response_model=BadgesSeenOut, summary="جشن نشان دیده شد")
async def mark_badges_seen(
    payload: BadgesSeenIn, current: CurrentUserDep, session: SessionDep
) -> BadgesSeenOut:
    updated = await BadgeService(session).mark_seen(current.id, payload.codes)
    return BadgesSeenOut(updated=updated)


@me_router.get("/dashboard", response_model=StudentDashboardOut, summary="داشبورد دانشجو")
async def my_dashboard(current: CurrentUserDep, session: SessionDep) -> StudentDashboardOut:
    dashboard = await DashboardService(session).for_student(current.id)
    step = dashboard.next_step
    return StudentDashboardOut(
        next_step=(
            NextStepOut(
                kind=step.kind,
                title=step.title,
                description=step.description,
                href=step.href,
                due_at=step.due_at,
            )
            if step
            else None
        ),
        points=await summary_out(session, dashboard.points),
        courses=[
            CourseCardOut(
                offering_id=c.offering_id,
                course_title_fa=c.course_title_fa,
                term_title_fa=c.term_title_fa,
                study_ratio=c.study_ratio,
                learning_score=c.learning_score,
                current_week_number=c.current_week_number,
            )
            for c in dashboard.courses
        ],
        projects=[
            ProjectCardOut(
                project_id=p.project_id,
                title_fa=p.title_fa,
                kind=p.kind,
                status=p.status,
                health=p.health,
                health_fa=HEALTH_TITLE_FA.get(p.health, p.health),
                next_milestone_title=p.next_milestone_title,
                next_milestone_due_on=p.next_milestone_due_on,
                next_milestone_status=p.next_milestone_status,
                approved_milestones=p.approved,
                required_milestones=p.required,
            )
            for p in dashboard.projects
        ],
        recent_badges=[earned_badge_out(badge, own) for badge, own in dashboard.recent_badges],
        trend=[TrendPointOut(week_start=t.week_start, total=t.total) for t in dashboard.trend],
        upcoming=[
            UpcomingEventOut(kind=e.kind, title=e.title, at=e.at, href=e.href)
            for e in dashboard.upcoming
        ],
    )


@me_router.get(
    "/learning-score/{offering_id}",
    response_model=LearningScoreOut,
    summary="نمرهٔ یادگیری من در یک درس",
    responses={404: {"model": ErrorResponse}},
)
async def my_learning_score(
    offering_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> LearningScoreOut:
    row = await LearningScoreService(session).for_student(offering_id, current.id)
    return learning_out(offering_id, row)


# ── رتبه‌بندی ───────────────────────────────────────────────────────────
@leaderboard_router.get(
    "",
    response_model=LeaderboardOut,
    summary="جدول رتبه‌بندی",
    responses={404: {"model": ErrorResponse}},
)
async def leaderboard(
    current: CurrentUserDep,
    session: SessionDep,
    scope: Annotated[str, Query(pattern="^(GLOBAL|OFFERING|UNIVERSITY)$")] = "GLOBAL",
    scope_id: uuid.UUID | None = None,
    category: PointCategory | None = None,
    limit: Annotated[int, Query(ge=1, le=10)] = 10,
) -> LeaderboardOut:
    """§9.7 — فقط ۱۰ نفر برتر، رتبهٔ خودت، و جدول رشد ۳۰ روزه.

    رتبه‌بندی درس فقط برای دانشجویان همان درس و کادر آموزشی‌اش است؛ برای
    بقیه ۴۰۴، نه ۴۰۳ (§6.4).
    """
    staff = scope == "OFFERING" and await authz.has_permission(
        session, current, Permission.OFFERING_MANAGE, scope_id
    )
    board = await LeaderboardService(session).board(
        viewer_id=current.id,
        scope=scope,
        scope_id=scope_id,
        category=category,
        limit=limit,
        can_view_any_offering=staff,
    )
    names = await display_names(
        session, [r.user_id for r in board.entries] + [r.user_id for r in board.growth]
    )

    def rows(items: list[BoardRow]) -> list[LeaderRowOut]:
        return [
            LeaderRowOut(
                rank=r.rank,
                user=LeaderUserOut(
                    user_id=r.user_id,
                    display_name=name_of(names, r.user_id),
                    username=names[r.user_id].username if r.user_id in names else None,
                ),
                total=r.total,
                level=r.level,
                is_me=r.user_id == current.id,
            )
            for r in items
        ]

    return LeaderboardOut(
        scope=board.scope,
        scope_id=board.scope_id,
        category=board.category,
        term_title_fa=board.term_title_fa,
        entries=rows(board.entries),
        growth=rows(board.growth),
        me=MyStandingOut(
            rank=board.me.rank,
            total=board.me.total,
            level=board.me.level,
            percentile=board.me.percentile,
            hidden=board.me.hidden,
            excluded_reason=board.me.excluded_reason,
        ),
    )


# ── استاد ──────────────────────────────────────────────────────────────
def _queue(q: Queue) -> QueueOut:
    return QueueOut(count=q.count, oldest_days=q.oldest_days)


def _scoped_offerings(current: CurrentUser) -> list[uuid.UUID]:
    """ارائه‌هایی که کاربر در آن‌ها نقش قلمرودار استاد یا دستیار دارد."""
    return [
        g.scope_id
        for g in current.grants
        if g.role in (Role.INSTRUCTOR, Role.TA)
        and g.scope_type is ScopeType.OFFERING
        and g.scope_id is not None
    ]


@teach_router.get("/dashboard", response_model=TeachDashboardOut, summary="داشبورد استثنامحور")
async def teach_dashboard(current: CurrentUserDep, session: SessionDep) -> TeachDashboardOut:
    """فقط آنچه اقدام می‌خواهد (FR-DASH-02). کاربری که ارائه‌ای ندارد، صف‌های
    خالی می‌بیند — همان رفتار `GET /teach/offerings`."""
    data = await TeachDashboardService(session).for_instructor(
        current.id, extra_offering_ids=_scoped_offerings(current)
    )
    return TeachDashboardOut(
        needs_attention=NeedsAttentionOut(
            deliverables_pending=_queue(data.deliverables_pending),
            essays_pending=_queue(data.essays_pending),
            enrollment_requests=_queue(data.enrollment_requests),
            grade_appeals=_queue(data.grade_appeals),
            projects_at_risk=[
                ProjectAtRiskOut(
                    id=p.project_id,
                    title_fa=p.title_fa,
                    health=p.health,
                    health_fa=HEALTH_TITLE_FA.get(p.health, p.health),
                    days_inactive=p.days_inactive,
                )
                for p in data.projects_at_risk
            ],
            students_at_risk=[
                StudentAtRiskOut(
                    user_id=s.user_id,
                    display_name=s.display_name,
                    reason=s.reason,
                    offering_id=s.offering_id,
                    course_title_fa=s.course_title_fa,
                )
                for s in data.students_at_risk
            ],
        ),
        offerings=[
            OfferingStatsOut(
                id=o.offering_id,
                title_fa=o.course_title_fa,
                status=o.status,
                students=o.students,
                avg_progress=o.avg_progress,
                avg_quiz_score=o.avg_quiz_score,
                avg_learning_score=o.avg_learning_score,
            )
            for o in data.offerings
        ],
    )


@teach_router.get(
    "/offerings/{offering_id}/learning-scores",
    response_model=list[LearningScoreOut],
    summary="نمرهٔ یادگیری همهٔ دانشجویان — ستون پیشنهادی دفتر نمره",
    responses={403: {"model": ErrorResponse}},
)
async def offering_learning_scores(
    offering_id: uuid.UUID,
    session: SessionDep,
    _: Annotated[
        CurrentUser, Depends(require(Permission.OFFERING_MANAGE, scope=offering_from_path))
    ],
) -> list[LearningScoreOut]:
    """§9.6 — «Learning Score یک پیشنهاد است، نه یک الزام.» این مسیر هیچ
    چیزی نمی‌نویسد؛ نمرهٔ نهایی با `PATCH /teach/enrollments/{id}/grade`."""
    rows = await LearningScoreService(session).for_offering(offering_id)
    names = await display_names(session, rows.keys())
    return sorted(
        (learning_out(offering_id, row, name_of(names, sid)) for sid, row in rows.items()),
        key=lambda r: (r.display_name or "", str(r.student_id)),
    )


# ── مدیریت ─────────────────────────────────────────────────────────────
@admin_router.get(
    "/point-rules",
    response_model=list[PointRuleOut],
    summary="قواعد امتیاز",
    responses={403: {"model": ErrorResponse}},
)
async def list_point_rules(
    session: SessionDep,
    _: Annotated[CurrentUser, Depends(require(Permission.POINTS_RULE_EDIT))],
) -> list[PointRuleOut]:
    return [
        PointRuleOut.model_validate(r, from_attributes=True)
        for r in await PointsService(session).rules()
    ]


@admin_router.patch(
    "/point-rules/{code}",
    response_model=PointRuleOut,
    summary="ویرایش قاعدهٔ امتیاز",
    responses={403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
async def update_point_rule(
    code: str,
    payload: PointRuleUpdateIn,
    session: SessionDep,
    _: Annotated[CurrentUser, Depends(require(Permission.POINTS_RULE_EDIT))],
) -> PointRuleOut:
    """FR-GAM-02 — **گذشته‌نگر نیست.** برای اعمال به گذشته، بازمحاسبه."""
    rule = await PointsService(session).update_rule(
        code,
        title_fa=payload.title_fa,
        base_points=payload.base_points,
        daily_cap=payload.daily_cap,
        weekly_cap=payload.weekly_cap,
        term_cap=payload.term_cap,
        is_active=payload.is_active,
        clear_caps=payload.clear_caps,
    )
    return PointRuleOut.model_validate(rule, from_attributes=True)


@admin_router.post(
    "/point-rules/recalculate",
    response_model=RecalculateOut,
    summary="بازمحاسبهٔ گذشته‌نگر",
    responses={403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
async def recalculate_points(
    payload: RecalculateIn,
    session: SessionDep,
    _: Annotated[CurrentUser, Depends(require(Permission.POINTS_RECALCULATE))],
) -> RecalculateOut:
    """§9.9 — معکوس و ثبت دوباره در یک تراکنش. **هیچ ردیفی پاک نمی‌شود.**"""
    points = PointsService(session)
    result = await points.recalculate(payload.rule_code, since=payload.since, until=payload.until)
    await session.commit()
    await points.refresh_totals()
    await session.commit()
    return RecalculateOut(
        rule_code=result.rule_code,
        reversed=result.reversed,
        reawarded=result.reawarded,
        users=result.users,
    )


@admin_router.post(
    "/point-entries/{entry_id}/reverse",
    response_model=PointEntryOut,
    status_code=201,
    summary="اصلاح یک ردیف امتیاز با رکورد معکوس",
    responses={403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
async def reverse_point_entry(
    entry_id: uuid.UUID,
    payload: ReverseEntryIn,
    session: SessionDep,
    # «اصلاح دفتر کل» مدیریتی است: `POINTS_AWARD_MANUAL` را استاد هم دارد،
    # و آن سراسری است — پس با آن، هر استادی امتیاز هر دانشجویی را صفر می‌کرد.
    _: Annotated[CurrentUser, Depends(require(Permission.POINTS_RECALCULATE))],
) -> PointEntryOut:
    reversal = await PointsService(session).reverse_by_id(entry_id, payload.reason)
    await session.commit()
    return (await entries_out(session, [reversal]))[0]


__all__ = ["admin_router", "leaderboard_router", "me_router", "teach_router"]
