"""داشبورد دانشجو — PRD FR-DASH-01، §3.4، M5-10.

یک پاسخ برای کل صفحه، نه شش درخواست موازی از کلاینت: داشبورد اولین صفحهٔ
پس از ورود است و روی اینترنت همراه ایران، شش رفت‌وبرگشت یعنی شش بار
اسکلت خالی.

| بخش | منبع |
|-----|------|
| «قدم بعدی تو» | نامزدها اینجا، انتخاب در `silp.domain.next_step` |
| امتیاز و سطح | `PointsService.summary` — دفتر کل زنده |
| دروس | ثبت‌نام‌های فعال + نمرهٔ یادگیری هر ارائه |
| پروژه‌ها | عضویت فعال + مرحلهٔ بعدی + سلامت |
| نشان‌های اخیر | سه نشان آخر |
| روند امتیاز | جمع هفتگی خالص در نیم‌سال جاری |
| رویدادهای پیش‌رو | آزمون و مهلت مرحله در ۱۴ روز آینده |
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from silp.domain.gamification import formulas
from silp.domain.next_step import NextStep, choose
from silp.models.delivery import Deliverable, Milestone
from silp.models.education import (
    Course,
    CourseOffering,
    CourseWeek,
    Enrollment,
    Resource,
    ResourceProgress,
    Term,
)
from silp.models.gamification import Badge, PointEntry, UserBadge
from silp.models.profile import TOTAL_SURVEY_STEPS, Profile
from silp.models.project import Project, Team, TeamMember
from silp.models.quiz import Quiz, QuizAttempt
from silp.services.badge_service import BadgeService
from silp.services.learning_score_service import LearningScoreService
from silp.services.points_service import PointsService, PointsSummary

UPCOMING_WINDOW = timedelta(days=14)
DUE_SOON_DAYS = 7
TREND_WEEKS = 12
ACTIVE_PROJECT_STATUSES = ("OPEN", "IN_PROGRESS", "PAUSED")
OPEN_DELIVERABLE_STATUSES = ("SUBMITTED", "UNDER_REVIEW")


@dataclass(frozen=True, slots=True)
class CourseCard:
    offering_id: uuid.UUID
    course_title_fa: str
    term_title_fa: str
    study_ratio: Decimal | None
    learning_score: Decimal | None
    current_week_number: int | None


@dataclass(frozen=True, slots=True)
class ProjectCard:
    project_id: uuid.UUID
    title_fa: str
    kind: str
    status: str
    health: str
    next_milestone_title: str | None
    next_milestone_due_on: date | None
    next_milestone_status: str | None
    approved: int
    required: int


@dataclass(frozen=True, slots=True)
class UpcomingEvent:
    kind: str
    title: str
    at: datetime
    href: str


@dataclass(frozen=True, slots=True)
class TrendPoint:
    week_start: date
    total: Decimal


@dataclass(slots=True)
class StudentDashboard:
    next_step: NextStep | None
    points: PointsSummary
    courses: list[CourseCard] = field(default_factory=list)
    projects: list[ProjectCard] = field(default_factory=list)
    recent_badges: list[tuple[Badge, UserBadge]] = field(default_factory=list)
    trend: list[TrendPoint] = field(default_factory=list)
    upcoming: list[UpcomingEvent] = field(default_factory=list)


def _now() -> datetime:
    return datetime.now(UTC)


def _local_today(now: datetime) -> date:
    return now.astimezone(formulas.LOCAL_TZ).date()


class DashboardService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def for_student(self, user_id: uuid.UUID) -> StudentDashboard:
        now = _now()
        points = await PointsService(self.session).summary(user_id)
        courses, offering_ids = await self._courses(user_id)
        projects = await self._projects(user_id)
        quizzes = await self._quiz_windows(user_id, offering_ids, now)

        candidates: list[NextStep] = []
        candidates += self._quiz_steps(quizzes, now)
        candidates += await self._milestone_steps(user_id, projects, now)
        candidates += await self._profile_steps(user_id)
        candidates += await self._study_steps(user_id, offering_ids)
        if not projects:
            candidates.append(
                NextStep(
                    kind="FIND_PROJECT",
                    title="اولین پروژه‌ات را پیدا کن",
                    description="پروژه‌هایی که با مهارت و علاقه‌ات جورند، منتظرت هستند.",
                    href="/projects",
                )
            )
        if not courses:
            candidates.append(
                NextStep(
                    kind="ENROLL",
                    title="در یک درس ثبت‌نام کن",
                    description="جزوه، آزمون و امتیاز یادگیری از ثبت‌نام شروع می‌شود.",
                    href="/courses",
                )
            )

        return StudentDashboard(
            next_step=choose(candidates, now=now),
            points=points,
            courses=courses,
            projects=projects,
            recent_badges=await BadgeService(self.session).recent(user_id),
            trend=await self._trend(user_id, points.term_id, now),
            upcoming=self._upcoming(quizzes, projects, now),
        )

    # ── دروس ───────────────────────────────────────────────────────────
    async def _courses(self, user_id: uuid.UUID) -> tuple[list[CourseCard], list[uuid.UUID]]:
        rows = list(
            await self.session.execute(
                select(CourseOffering, Course.title_fa, Term.title_fa)
                .join(Enrollment, Enrollment.offering_id == CourseOffering.id)
                .join(Course, Course.id == CourseOffering.course_id)
                .join(Term, Term.id == CourseOffering.term_id)
                .where(
                    Enrollment.student_id == user_id,
                    Enrollment.status.in_(("ACTIVE", "COMPLETED")),
                    CourseOffering.deleted_at.is_(None),
                )
                .order_by(Term.starts_on.desc(), Course.title_fa)
            )
        )
        scores = LearningScoreService(self.session)
        cards: list[CourseCard] = []
        for offering, course_title, term_title in rows:
            learning = await scores.for_student(offering.id, user_id)
            current = await self.session.scalar(
                select(func.max(CourseWeek.week_number)).where(
                    CourseWeek.offering_id == offering.id, CourseWeek.status == "PUBLISHED"
                )
            )
            study = learning.inputs.study
            cards.append(
                CourseCard(
                    offering_id=offering.id,
                    course_title_fa=course_title,
                    term_title_fa=term_title,
                    study_ratio=study.ratio if study.is_present else None,
                    learning_score=learning.score.score,
                    current_week_number=current,
                )
            )
        return cards, [offering.id for offering, _, _ in rows]

    # ── پروژه‌ها ───────────────────────────────────────────────────────
    async def _projects(self, user_id: uuid.UUID) -> list[ProjectCard]:
        projects = list(
            await self.session.scalars(
                select(Project)
                .join(Team, Team.project_id == Project.id)
                .join(TeamMember, TeamMember.team_id == Team.id)
                .where(
                    TeamMember.user_id == user_id,
                    TeamMember.status == "ACTIVE",
                    Project.deleted_at.is_(None),
                    Project.status.in_(ACTIVE_PROJECT_STATUSES),
                )
                .order_by(Project.last_activity_at.desc())
            )
        )
        if not projects:
            return []
        milestones: dict[uuid.UUID, list[Milestone]] = defaultdict(list)
        for m in await self.session.scalars(
            select(Milestone)
            .where(Milestone.project_id.in_([p.id for p in projects]))
            .order_by(Milestone.sort_order, Milestone.id)
        ):
            milestones[m.project_id].append(m)

        cards: list[ProjectCard] = []
        for project in projects:
            own = milestones[project.id]
            pending = next((m for m in own if m.status != "APPROVED"), None)
            required = [m for m in own if m.is_required]
            cards.append(
                ProjectCard(
                    project_id=project.id,
                    title_fa=project.title_fa,
                    kind=project.kind,
                    status=project.status,
                    health=project.health,
                    next_milestone_title=pending.title_fa if pending else None,
                    next_milestone_due_on=pending.due_on if pending else None,
                    next_milestone_status=pending.status if pending else None,
                    approved=sum(1 for m in required if m.status == "APPROVED"),
                    required=len(required),
                )
            )
        return cards

    # ── آزمون‌ها ───────────────────────────────────────────────────────
    async def _quiz_windows(
        self, user_id: uuid.UUID, offering_ids: list[uuid.UUID], now: datetime
    ) -> list[tuple[Quiz, QuizAttempt | None, int]]:
        """آزمون‌های منتشرشدهٔ دروس من که هنوز بسته نشده‌اند یا تا ۱۴ روز باز می‌شوند.

        خروجی: (آزمون، تلاش در جریان، تعداد تلاش‌های مصرف‌شده).
        """
        if not offering_ids:
            return []
        quizzes = list(
            await self.session.scalars(
                select(Quiz)
                .where(
                    Quiz.offering_id.in_(offering_ids),
                    Quiz.status == "PUBLISHED",
                    Quiz.deleted_at.is_(None),
                    Quiz.closes_at > now,
                    Quiz.opens_at <= now + UPCOMING_WINDOW,
                )
                .order_by(Quiz.closes_at)
            )
        )
        if not quizzes:
            return []
        used: dict[uuid.UUID, int] = defaultdict(int)
        running: dict[uuid.UUID, QuizAttempt] = {}
        for attempt in await self.session.scalars(
            select(QuizAttempt).where(
                QuizAttempt.quiz_id.in_([q.id for q in quizzes]),
                QuizAttempt.student_id == user_id,
                QuizAttempt.status != "VOIDED",
            )
        ):
            used[attempt.quiz_id] += 1
            if attempt.status == "IN_PROGRESS" and attempt.expires_at > now:
                running[attempt.quiz_id] = attempt
        return [(q, running.get(q.id), used[q.id]) for q in quizzes]

    def _quiz_steps(
        self, quizzes: list[tuple[Quiz, QuizAttempt | None, int]], now: datetime
    ) -> list[NextStep]:
        steps: list[NextStep] = []
        for quiz, running, used in quizzes:
            if quiz.opens_at > now:
                continue
            if running is not None:
                steps.append(
                    NextStep(
                        kind="QUIZ_OPEN",
                        title=f"ادامهٔ آزمون «{quiz.title_fa}»",
                        description="آزمونت نیمه‌کاره مانده و زمان در حال گذر است.",
                        href=f"/quiz/{running.id}",
                        due_at=running.expires_at,
                    )
                )
            elif used == 0:
                steps.append(
                    NextStep(
                        kind="QUIZ_OPEN",
                        title=f"آزمون «{quiz.title_fa}» باز است",
                        description=f"{quiz.duration_min} دقیقه — پیش از بسته شدن شرکت کن.",
                        href=f"/courses/{quiz.offering_id}/quizzes",
                        due_at=quiz.closes_at,
                    )
                )
        return steps

    # ── مراحل ──────────────────────────────────────────────────────────
    async def _milestone_steps(
        self, user_id: uuid.UUID, projects: list[ProjectCard], now: datetime
    ) -> list[NextStep]:
        working = [p for p in projects if p.status == "IN_PROGRESS"]
        if not working:
            return []
        today = _local_today(now)
        milestones = list(
            await self.session.scalars(
                select(Milestone).where(
                    Milestone.project_id.in_([p.project_id for p in working]),
                    Milestone.status != "APPROVED",
                    Milestone.due_on.is_not(None),
                    Milestone.due_on <= today + timedelta(days=DUE_SOON_DAYS),
                )
            )
        )
        if not milestones:
            return []
        # مرحله‌ای که تحویلش را فرستاده‌ام و منتظر بررسی است، کار من نیست.
        waiting = set(
            await self.session.scalars(
                select(Deliverable.milestone_id).where(
                    Deliverable.milestone_id.in_([m.id for m in milestones]),
                    Deliverable.submitter_id == user_id,
                    Deliverable.status.in_(OPEN_DELIVERABLE_STATUSES),
                )
            )
        )
        titles = {p.project_id: p.title_fa for p in working}
        steps: list[NextStep] = []
        for m in milestones:
            if m.id in waiting or m.due_on is None:
                continue
            overdue = m.due_on < today
            steps.append(
                NextStep(
                    kind="MILESTONE_OVERDUE" if overdue else "MILESTONE_DUE",
                    title=(
                        f"مرحلهٔ «{m.title_fa}» عقب افتاده"
                        if overdue
                        else f"مهلت مرحلهٔ «{m.title_fa}» نزدیک است"
                    ),
                    description=f"پروژهٔ {titles[m.project_id]}",
                    href=f"/projects/{m.project_id}/workspace",
                    due_at=datetime.combine(
                        m.due_on, datetime.min.time(), tzinfo=formulas.LOCAL_TZ
                    ),
                )
            )
        return steps

    # ── نیمرخ و مطالعه ─────────────────────────────────────────────────
    async def _profile_steps(self, user_id: uuid.UUID) -> list[NextStep]:
        steps = await self.session.scalar(
            select(Profile.survey_completed_steps).where(Profile.user_id == user_id)
        )
        done = steps or 0
        if done >= TOTAL_SURVEY_STEPS:
            return []
        return [
            NextStep(
                kind="PROFILE_INCOMPLETE",
                title="نیمرخت را کامل کن",
                description=(
                    f"{done} از {TOTAL_SURVEY_STEPS} گام — بدون آن پیشنهاد پروژه دقیق نیست."
                ),
                href=f"/onboarding/survey/{done + 1}",
            )
        ]

    async def _study_steps(
        self, user_id: uuid.UUID, offering_ids: list[uuid.UUID]
    ) -> list[NextStep]:
        """قدیمی‌ترین منبع الزامی نخوانده در هفته‌های منتشرشده."""
        if not offering_ids:
            return []
        completed = (
            select(ResourceProgress.resource_id)
            .where(ResourceProgress.user_id == user_id, ResourceProgress.status == "COMPLETED")
            .scalar_subquery()
        )
        row = (
            await self.session.execute(
                select(Resource.title_fa, CourseWeek.offering_id, CourseWeek.week_number)
                .join(CourseWeek, CourseWeek.id == Resource.week_id)
                .where(
                    CourseWeek.offering_id.in_(offering_ids),
                    CourseWeek.status == "PUBLISHED",
                    Resource.is_required.is_(True),
                    Resource.id.notin_(completed),
                )
                .order_by(CourseWeek.week_number, Resource.sort_order)
                .limit(1)
            )
        ).first()
        if row is None:
            return []
        title, offering_id, week_number = row
        return [
            NextStep(
                kind="STUDY",
                title=f"«{title}» را بخوان",
                description=f"منبع الزامی هفتهٔ {week_number}",
                href=f"/courses/{offering_id}/weeks/{week_number}",
            )
        ]

    # ── روند و رویدادها ────────────────────────────────────────────────
    async def _trend(
        self, user_id: uuid.UUID, term_id: uuid.UUID | None, now: datetime
    ) -> list[TrendPoint]:
        """جمع خالص هفتگی — هفته‌های بی‌امتیاز هم صفر می‌آیند تا نمودار نپرد."""
        since = formulas.local_week_start(now) - timedelta(weeks=TREND_WEEKS - 1)
        query = select(PointEntry.created_at, PointEntry.amount).where(
            PointEntry.user_id == user_id, PointEntry.created_at >= since
        )
        if term_id is not None:
            query = query.where(PointEntry.term_id == term_id)
        buckets: dict[date, Decimal] = defaultdict(Decimal)
        for created_at, amount in await self.session.execute(query):
            buckets[formulas.week_key(created_at)] += amount
        first = formulas.week_key(since)
        return [
            TrendPoint(week_start=week, total=buckets.get(week, Decimal(0)))
            for week in (first + timedelta(weeks=i) for i in range(TREND_WEEKS))
        ]

    def _upcoming(
        self,
        quizzes: list[tuple[Quiz, QuizAttempt | None, int]],
        projects: list[ProjectCard],
        now: datetime,
    ) -> list[UpcomingEvent]:
        horizon = now + UPCOMING_WINDOW
        events: list[UpcomingEvent] = []
        for quiz, _, _ in quizzes:
            href = f"/courses/{quiz.offering_id}/quizzes"
            if now < quiz.opens_at <= horizon:
                events.append(
                    UpcomingEvent(
                        "QUIZ_OPENS", f"شروع آزمون «{quiz.title_fa}»", quiz.opens_at, href
                    )
                )
            if quiz.closes_at <= horizon:
                events.append(
                    UpcomingEvent(
                        "QUIZ_CLOSES", f"پایان آزمون «{quiz.title_fa}»", quiz.closes_at, href
                    )
                )
        today = _local_today(now)
        for p in projects:
            due = p.next_milestone_due_on
            if due is not None and today <= due <= _local_today(horizon):
                events.append(
                    UpcomingEvent(
                        "MILESTONE_DUE",
                        f"مهلت «{p.next_milestone_title}»",
                        datetime.combine(due, datetime.min.time(), tzinfo=formulas.LOCAL_TZ),
                        f"/projects/{p.project_id}/workspace",
                    )
                )
        return sorted(events, key=lambda e: e.at)


__all__ = [
    "CourseCard",
    "DashboardService",
    "ProjectCard",
    "StudentDashboard",
    "TrendPoint",
    "UpcomingEvent",
]
