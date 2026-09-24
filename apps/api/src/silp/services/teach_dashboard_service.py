"""داشبورد استاد «استثنامحور» — PRD FR-DASH-02، §5.11، M5-11.

«فقط مواردی که نیاز به اقدام دارند.» استادی که هر صبح پنجاه عدد سبز
می‌بیند، روز سوم داشبورد را باز نمی‌کند. پس بخش اصلی فقط صف‌هاست — چه
چیزی منتظر من است و از کی — و آمار کلی درس پایین‌تر و کوتاه.

## «دانشجوی در خطر»

FR-DASH-02: «بدون فعالیت ۱۴ روز یا نمرهٔ زیر آستانه». فعالیت یعنی
تازه‌ترین یکی از: امتیاز، پیشرفت مطالعه، شروع آزمون، یا خودِ ثبت‌نام
(دانشجوی تازه‌واردی که دیروز ثبت‌نام کرد، «۱۴ روز بی‌فعالیت» نیست). نمره
یعنی نمرهٔ یادگیری زیر ۴۰ — فقط وقتی دست‌کم یک مؤلفه وجود دارد.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from silp.models.delivery import Deliverable, Milestone
from silp.models.education import (
    Course,
    CourseOffering,
    Enrollment,
    ResourceProgress,
)
from silp.models.gamification import PointEntry
from silp.models.project import Project
from silp.models.quiz import GradeAppeal, Quiz, QuizAnswer, QuizAttempt, QuizQuestion
from silp.services.directory import display_names, name_of
from silp.services.learning_score_service import LearningScoreService, StudentLearning
from silp.services.teach_projects_service import supervision_scope

INACTIVE_AFTER = timedelta(days=14)
LOW_LEARNING_SCORE = Decimal(40)
MAX_AT_RISK_ROWS = 20
QUIZ_SCALE = Decimal(20)


@dataclass(frozen=True, slots=True)
class Queue:
    count: int
    oldest_days: int | None = None


@dataclass(frozen=True, slots=True)
class ProjectAtRisk:
    project_id: uuid.UUID
    title_fa: str
    health: str
    days_inactive: int


@dataclass(frozen=True, slots=True)
class StudentAtRisk:
    user_id: uuid.UUID
    display_name: str | None
    offering_id: uuid.UUID
    course_title_fa: str
    reason: str


@dataclass(frozen=True, slots=True)
class OfferingStats:
    offering_id: uuid.UUID
    course_title_fa: str
    status: str
    students: int
    avg_progress: Decimal | None
    avg_quiz_score: Decimal | None
    """میانگین نمرهٔ آزمون روی مقیاس ۲۰، مثل نمرهٔ رسمی."""
    avg_learning_score: Decimal | None


@dataclass(slots=True)
class TeachDashboard:
    deliverables_pending: Queue
    essays_pending: Queue
    enrollment_requests: Queue
    grade_appeals: Queue
    projects_at_risk: list[ProjectAtRisk] = field(default_factory=list)
    students_at_risk: list[StudentAtRisk] = field(default_factory=list)
    offerings: list[OfferingStats] = field(default_factory=list)


def _now() -> datetime:
    return datetime.now(UTC)


def _days_since(moment: datetime | None, now: datetime) -> int | None:
    if moment is None:
        return None
    return max((now - moment).days, 0)


def _mean(values: Iterable[Decimal]) -> Decimal | None:
    items = list(values)
    if not items:
        return None
    return (sum(items, Decimal(0)) / len(items)).quantize(Decimal("0.01"))


class TeachDashboardService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def for_instructor(
        self,
        user_id: uuid.UUID,
        *,
        extra_offering_ids: Iterable[uuid.UUID] = (),
        supervised_offering_ids: Iterable[uuid.UUID] = (),
    ) -> TeachDashboard:
        """`extra_offering_ids` ارائه‌هایی است که کاربر در آن‌ها نقش قلمرودار
        استاد یا دستیار دارد — استاد رسمی ارائه نیست ولی مسئول است.

        `supervised_offering_ids` فقط آن‌هایی است که **استاد** است (نه دستیار)؛
        پروژه‌ها و تحویل‌های منتظر با همین‌ها شمرده می‌شوند تا عدد داشبورد با
        طول `/teach/review-queue` برابر باشد (ADR-0022).
        """
        now = _now()
        offerings = list(
            await self.session.execute(
                select(CourseOffering, Course.title_fa)
                .join(Course, Course.id == CourseOffering.course_id)
                .where(
                    or_(
                        CourseOffering.instructor_id == user_id,
                        CourseOffering.id.in_(list(extra_offering_ids)),
                    ),
                    CourseOffering.deleted_at.is_(None),
                    CourseOffering.status != "ARCHIVED",
                )
                .order_by(CourseOffering.created_at.desc())
            )
        )
        offering_ids = [o.id for o, _ in offerings]
        titles = {o.id: t for o, t in offerings}

        official = {o.id for o, _ in offerings if o.instructor_id == user_id}
        project_scope = supervision_scope(user_id, official | set(supervised_offering_ids))
        dashboard = TeachDashboard(
            deliverables_pending=await self._deliverables(project_scope, now),
            essays_pending=await self._essays(offering_ids, now),
            enrollment_requests=await self._enrollment_requests(offering_ids, now),
            grade_appeals=await self._appeals(offering_ids, now),
            projects_at_risk=await self._projects_at_risk(project_scope, now),
        )

        scores = LearningScoreService(self.session)
        at_risk: list[StudentAtRisk] = []
        for offering, course_title in offerings:
            learning = await scores.for_offering(offering.id)
            dashboard.offerings.append(self._stats(offering, course_title, learning))
            at_risk += await self._students_at_risk(offering.id, course_title, learning, now)
        names = await display_names(self.session, [s.user_id for s in at_risk])
        dashboard.students_at_risk = [
            StudentAtRisk(
                user_id=s.user_id,
                display_name=name_of(names, s.user_id),
                offering_id=s.offering_id,
                course_title_fa=titles[s.offering_id],
                reason=s.reason,
            )
            for s in at_risk[:MAX_AT_RISK_ROWS]
        ]
        return dashboard

    # ── صف‌ها ──────────────────────────────────────────────────────────
    async def _deliverables(self, project_scope: ColumnElement[bool], now: datetime) -> Queue:
        count, oldest = (
            await self.session.execute(
                select(func.count(Deliverable.id), func.min(Deliverable.submitted_at))
                .join(Milestone, Milestone.id == Deliverable.milestone_id)
                .join(Project, Project.id == Milestone.project_id)
                .where(
                    Deliverable.status.in_(("SUBMITTED", "UNDER_REVIEW")),
                    Project.deleted_at.is_(None),
                    project_scope,
                )
            )
        ).one()
        return Queue(count=count or 0, oldest_days=_days_since(oldest, now))

    async def _essays(self, offering_ids: list[uuid.UUID], now: datetime) -> Queue:
        if not offering_ids:
            return Queue(count=0)
        count, oldest = (
            await self.session.execute(
                select(func.count(), func.min(QuizAttempt.submitted_at))
                .select_from(QuizAnswer)
                .join(QuizQuestion, QuizQuestion.id == QuizAnswer.question_id)
                .join(QuizAttempt, QuizAttempt.id == QuizAnswer.attempt_id)
                .join(Quiz, Quiz.id == QuizAttempt.quiz_id)
                .where(
                    Quiz.offering_id.in_(offering_ids),
                    Quiz.deleted_at.is_(None),
                    QuizQuestion.kind == "ESSAY",
                    QuizAnswer.manual_score.is_(None),
                    QuizAttempt.status == "GRADED",
                    func.length(func.btrim(QuizAnswer.response["text"].astext)) > 0,
                )
            )
        ).one()
        return Queue(count=count or 0, oldest_days=_days_since(oldest, now))

    async def _enrollment_requests(self, offering_ids: list[uuid.UUID], now: datetime) -> Queue:
        if not offering_ids:
            return Queue(count=0)
        count, oldest = (
            await self.session.execute(
                select(func.count(), func.min(Enrollment.enrolled_at)).where(
                    Enrollment.offering_id.in_(offering_ids), Enrollment.status == "PENDING"
                )
            )
        ).one()
        return Queue(count=count or 0, oldest_days=_days_since(oldest, now))

    async def _appeals(self, offering_ids: list[uuid.UUID], now: datetime) -> Queue:
        if not offering_ids:
            return Queue(count=0)
        count, oldest = (
            await self.session.execute(
                select(func.count(), func.min(GradeAppeal.created_at))
                .select_from(GradeAppeal)
                .join(QuizAttempt, QuizAttempt.id == GradeAppeal.attempt_id)
                .join(Quiz, Quiz.id == QuizAttempt.quiz_id)
                .where(Quiz.offering_id.in_(offering_ids), GradeAppeal.status == "OPEN")
            )
        ).one()
        return Queue(count=count or 0, oldest_days=_days_since(oldest, now))

    async def _projects_at_risk(
        self, project_scope: ColumnElement[bool], now: datetime
    ) -> list[ProjectAtRisk]:
        rows = await self.session.scalars(
            select(Project)
            .where(
                Project.deleted_at.is_(None),
                Project.status == "IN_PROGRESS",
                Project.health != "HEALTHY",
                project_scope,
            )
            # «متوقف» پیش از «در خطر»، و در هرکدام، کهنه‌ترین اول.
            .order_by(Project.health.desc(), Project.last_activity_at)
        )
        return [
            ProjectAtRisk(
                project_id=p.id,
                title_fa=p.title_fa,
                health=p.health,
                days_inactive=_days_since(p.last_activity_at, now) or 0,
            )
            for p in rows
        ]

    # ── دانشجویان و آمار ───────────────────────────────────────────────
    async def _students_at_risk(
        self,
        offering_id: uuid.UUID,
        course_title: str,
        learning: dict[uuid.UUID, StudentLearning],
        now: datetime,
    ) -> list[StudentAtRisk]:
        active_students = list(
            await self.session.execute(
                select(Enrollment.student_id, Enrollment.enrolled_at).where(
                    Enrollment.offering_id == offering_id, Enrollment.status == "ACTIVE"
                )
            )
        )
        if not active_students:
            return []
        ids = [sid for sid, _ in active_students]
        last: dict[uuid.UUID, datetime] = {row[0]: row[1] for row in active_students}
        for query in (
            select(PointEntry.user_id, func.max(PointEntry.created_at))
            .where(PointEntry.user_id.in_(ids), PointEntry.offering_id == offering_id)
            .group_by(PointEntry.user_id),
            select(ResourceProgress.user_id, func.max(ResourceProgress.updated_at))
            .where(ResourceProgress.user_id.in_(ids))
            .group_by(ResourceProgress.user_id),
            select(QuizAttempt.student_id, func.max(QuizAttempt.started_at))
            .join(Quiz, Quiz.id == QuizAttempt.quiz_id)
            .where(QuizAttempt.student_id.in_(ids), Quiz.offering_id == offering_id)
            .group_by(QuizAttempt.student_id),
        ):
            for sid, moment in await self.session.execute(query):
                if moment is not None and moment > last[sid]:
                    last[sid] = moment

        result: list[StudentAtRisk] = []
        for sid in ids:
            idle = _days_since(last[sid], now) or 0
            score = learning[sid].score.score if sid in learning else None
            if idle >= INACTIVE_AFTER.days:
                reason = f"{idle} روز بدون فعالیت"
            elif score is not None and score < LOW_LEARNING_SCORE:
                reason = f"نمرهٔ یادگیری {score.normalize():f} از ۱۰۰"
            else:
                continue
            result.append(
                StudentAtRisk(
                    user_id=sid,
                    display_name=None,
                    offering_id=offering_id,
                    course_title_fa=course_title,
                    reason=reason,
                )
            )
        return result

    def _stats(
        self,
        offering: CourseOffering,
        course_title: str,
        learning: dict[uuid.UUID, StudentLearning],
    ) -> OfferingStats:
        rows = list(learning.values())
        study = [r.inputs.study.ratio for r in rows if r.inputs.study.is_present]
        quiz = [r.inputs.quiz.ratio * QUIZ_SCALE for r in rows if r.inputs.quiz.is_present]
        ls = [r.score.score for r in rows if r.score.score is not None]
        return OfferingStats(
            offering_id=offering.id,
            course_title_fa=course_title,
            status=offering.status,
            students=len(rows),
            avg_progress=_mean(study),
            avg_quiz_score=_mean(quiz),
            avg_learning_score=_mean(ls),
        )


__all__ = [
    "OfferingStats",
    "ProjectAtRisk",
    "Queue",
    "StudentAtRisk",
    "TeachDashboard",
    "TeachDashboardService",
]
