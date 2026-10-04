"""نمرهٔ یادگیری هر دانشجو در هر ارائه — PRD §9.6، M5-06.

«محاسبه **بی‌درنگ** است (در لحظهٔ درخواست)، نه ذخیره‌شده.» اینجا ورودی‌های
چهار مؤلفه از دیتابیس جمع می‌شوند و فرمول در
`silp.domain.gamification.learning_score` است.

برای یک ارائه همهٔ دانشجویان با **پنج کوئری ثابت** حساب می‌شوند، نه پنج
کوئری به‌ازای هر دانشجو: داشبورد استاد و دفتر نمره فهرست کامل کلاس را
می‌خواهند (§5.14 «بدون N+1»).

## چه آزمونی در `Q` شمرده می‌شود

* تلاش **قطعی** (بدون تشریحی تصحیح‌نشده) که نتیجه‌اش برای دانشجو **دیده
  می‌شود** — بهترین تلاش. همان قاعدهٔ امتیاز آزمون (ADR-0012): عددی که
  دانشجو می‌بیند نباید نمرهٔ پنهان را لو دهد.
* آزمونی که پنجره‌اش بسته شده و نتیجه‌اش منتشر شده ولی دانشجو در آن شرکت
  نکرده — **صفر**. آزمون هنوز باز، نه: «مخرج فقط محتوای منتشرشده است».
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from silp.core.exceptions import NotFound
from silp.domain.gamification.learning_score import (
    Fraction,
    LearningInputs,
    LearningScore,
    compute,
    weights_from_policy,
)
from silp.models.delivery import Milestone
from silp.models.education import (
    AttendanceRecord,
    ClassSession,
    CourseOffering,
    CourseWeek,
    Enrollment,
    Resource,
    ResourceProgress,
)
from silp.models.project import Project, Team, TeamMember
from silp.models.quiz import Quiz, QuizAttempt
from silp.services.grading_service import results_visible

ZERO = Decimal(0)
ENROLLED_STATUSES = ("ACTIVE", "COMPLETED")
ATTENDANCE_CREDIT: dict[str, Decimal] = {
    "PRESENT": Decimal(1),
    "LATE": Decimal("0.5"),
    "EXCUSED": Decimal(1),
    "ABSENT": ZERO,
}


@dataclass(frozen=True, slots=True)
class StudentLearning:
    student_id: uuid.UUID
    inputs: LearningInputs
    score: LearningScore


def _now() -> datetime:
    return datetime.now(UTC)


class LearningScoreService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def for_student(self, offering_id: uuid.UUID, student_id: uuid.UUID) -> StudentLearning:
        result = await self.for_offering(offering_id, students=[student_id])
        if student_id not in result:
            raise NotFound("این دانشجو در این درس ثبت‌نام نیست.")
        return result[student_id]

    async def for_offering(
        self,
        offering_id: uuid.UUID,
        *,
        students: Iterable[uuid.UUID] | None = None,
    ) -> dict[uuid.UUID, StudentLearning]:
        offering = await self.session.get(CourseOffering, offering_id)
        if offering is None or offering.deleted_at is not None:
            raise NotFound("این ارائه پیدا نشد.")

        query = select(Enrollment.student_id).where(
            Enrollment.offering_id == offering_id, Enrollment.status.in_(ENROLLED_STATUSES)
        )
        if students is not None:
            query = query.where(Enrollment.student_id.in_(list(students)))
        student_ids = list(await self.session.scalars(query))
        if not student_ids:
            return {}

        quiz = await self._quiz_component(offering_id, student_ids)
        study = await self._study_component(offering_id, student_ids)
        project = await self._project_component(offering_id, student_ids)
        attendance = await self._attendance_component(offering_id, student_ids)
        weights = weights_from_policy(offering.grading_policy)

        result: dict[uuid.UUID, StudentLearning] = {}
        for sid in student_ids:
            inputs = LearningInputs(
                quiz=quiz[sid], study=study[sid], project=project[sid], attendance=attendance[sid]
            )
            result[sid] = StudentLearning(
                student_id=sid, inputs=inputs, score=compute(inputs, weights)
            )
        return result

    # ── Q ──────────────────────────────────────────────────────────────
    async def _quiz_component(
        self, offering_id: uuid.UUID, student_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, Fraction]:
        now = _now()
        quizzes = list(
            await self.session.scalars(
                select(Quiz).where(
                    Quiz.offering_id == offering_id,
                    Quiz.status.in_(("PUBLISHED", "CLOSED")),
                    Quiz.deleted_at.is_(None),
                    Quiz.kind != "CHECKPOINT",
                    Quiz.total_points > 0,
                )
            )
        )
        earned: dict[uuid.UUID, Decimal] = defaultdict(lambda: ZERO)
        possible: dict[uuid.UUID, Decimal] = defaultdict(lambda: ZERO)
        if not quizzes:
            return {sid: Fraction(ZERO, ZERO) for sid in student_ids}

        attempts: dict[tuple[uuid.UUID, uuid.UUID], list[QuizAttempt]] = defaultdict(list)
        for attempt in await self.session.scalars(
            select(QuizAttempt).where(
                QuizAttempt.quiz_id.in_([q.id for q in quizzes]),
                QuizAttempt.student_id.in_(student_ids),
                QuizAttempt.status.in_(("IN_PROGRESS", "SUBMITTED", "AUTO_SUBMITTED", "GRADED")),
            )
        ):
            attempts[(attempt.quiz_id, attempt.student_id)].append(attempt)

        for quiz in quizzes:
            closed = now > quiz.closes_at
            for sid in student_ids:
                own = attempts.get((quiz.id, sid), [])
                final = [
                    a
                    for a in own
                    if a.status == "GRADED" and not a.is_provisional and a.total_score is not None
                ]
                visible = [a for a in final if results_visible(quiz, a, now=now)]
                if visible:
                    best = max(a.total_score or ZERO for a in visible)
                    earned[sid] += best
                    possible[sid] += quiz.total_points
                elif not own and closed and _published_after_close(quiz):
                    # شرکت نکرد و فرصت تمام شد — صفر، ولی در مخرج.
                    possible[sid] += quiz.total_points
        return {sid: Fraction(earned[sid], possible[sid]) for sid in student_ids}

    # ── S ──────────────────────────────────────────────────────────────
    async def _study_component(
        self, offering_id: uuid.UUID, student_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, Fraction]:
        required = list(
            await self.session.scalars(
                select(Resource.id)
                .join(CourseWeek, CourseWeek.id == Resource.week_id)
                .where(
                    CourseWeek.offering_id == offering_id,
                    CourseWeek.status == "PUBLISHED",
                    Resource.is_required.is_(True),
                )
            )
        )
        total = Decimal(len(required))
        done: dict[uuid.UUID, int] = {}
        if required:
            for user_id, count in await self.session.execute(
                select(ResourceProgress.user_id, func.count())
                .where(
                    ResourceProgress.resource_id.in_(required),
                    ResourceProgress.user_id.in_(student_ids),
                    ResourceProgress.status == "COMPLETED",
                )
                .group_by(ResourceProgress.user_id)
            ):
                done[user_id] = count
        return {sid: Fraction(Decimal(done.get(sid, 0)), total) for sid in student_ids}

    # ── P ──────────────────────────────────────────────────────────────
    async def _project_component(
        self, offering_id: uuid.UUID, student_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, Fraction]:
        """مراحل الزامی پروژه‌های متصل به ارائه که دانشجو عضو فعالشان است."""
        rows = await self.session.execute(
            select(
                TeamMember.user_id,
                func.count(Milestone.id),
                func.count(Milestone.id).filter(Milestone.status == "APPROVED"),
            )
            .join(Team, Team.id == TeamMember.team_id)
            .join(Project, Project.id == Team.project_id)
            .join(Milestone, Milestone.project_id == Project.id)
            .where(
                Project.offering_id == offering_id,
                Project.deleted_at.is_(None),
                Project.status.notin_(("DRAFT", "CANCELLED")),
                Milestone.is_required.is_(True),
                TeamMember.status == "ACTIVE",
                TeamMember.user_id.in_(student_ids),
            )
            .group_by(TeamMember.user_id)
        )
        found = {user_id: (total, approved) for user_id, total, approved in rows}
        return {
            sid: Fraction(Decimal(found.get(sid, (0, 0))[1]), Decimal(found.get(sid, (0, 0))[0]))
            for sid in student_ids
        }

    # ── A ──────────────────────────────────────────────────────────────
    async def _attendance_component(
        self, offering_id: uuid.UUID, student_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, Fraction]:
        sessions = (
            await self.session.scalar(
                select(func.count())
                .select_from(ClassSession)
                .where(ClassSession.offering_id == offering_id)
            )
            or 0
        )
        credit: dict[uuid.UUID, Decimal] = defaultdict(lambda: ZERO)
        if sessions:
            for student_id, status in await self.session.execute(
                select(AttendanceRecord.student_id, AttendanceRecord.status)
                .join(ClassSession, ClassSession.id == AttendanceRecord.session_id)
                .where(
                    ClassSession.offering_id == offering_id,
                    AttendanceRecord.student_id.in_(student_ids),
                )
            ):
                credit[student_id] += ATTENDANCE_CREDIT.get(status, ZERO)
        return {sid: Fraction(credit[sid], Decimal(sessions)) for sid in student_ids}


def _published_after_close(quiz: Quiz) -> bool:
    """پس از بسته شدن، نتیجهٔ این آزمون برای کلاس منتشر شده است؟"""
    if quiz.result_visibility == "MANUAL":
        return quiz.results_published_at is not None
    return True


__all__ = ["LearningScoreService", "StudentLearning"]
