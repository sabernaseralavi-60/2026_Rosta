"""دفتر نمرهٔ یک ارائه — §3.5 «دفتر نمره با ویرایش درجا و خروجی Excel»، ADR-0019.

یک ردیف برای هر دانشجوی فعال یا پایان‌یافته، با ستون هر آزمون، شمار حضور،
نمرهٔ یادگیری (§9.6) با اجزایش، و نمرهٔ نهایی ثبت‌شده.

**دو عدد متفاوت، عمداً:** ستون آزمون بهترین تلاش تصحیح‌شده است، **حتی اگر
نتیجه هنوز به دانشجو نشان داده نشده** — استاد باید نمره را پیش از انتشار
ببیند. نمرهٔ یادگیری فقط از نتیجهٔ دیده‌شده ساخته می‌شود (همان عدد
داشبورد دانشجو)، پس ممکن است آزمونی را که ستونش پر است هنوز نشمارد.

همهٔ داده با تعداد ثابتی کوئری خوانده می‌شود، نه یکی برای هر دانشجو
(§5.14): کلاس ۱۲۰ نفره همان هزینهٔ کلاس ۵ نفره را دارد.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from silp.models.education import AttendanceRecord, ClassSession, Enrollment
from silp.models.quiz import Quiz, QuizAttempt
from silp.services.learning_score_service import LearningScoreService, StudentLearning
from silp.services.teaching_service import TeachingService

#: ثبت‌نام‌هایی که در دفتر نمره می‌آیند — در انتظار و انصرافی نمره ندارند.
GRADEBOOK_STATUSES = ("ACTIVE", "COMPLETED")
#: تلاش‌هایی که نمره دارند یا خواهند داشت؛ باطل‌شده و در جریان نه.
SCORED_STATUSES = ("SUBMITTED", "AUTO_SUBMITTED", "GRADED")


@dataclass(frozen=True, slots=True)
class QuizColumn:
    id: uuid.UUID
    title_fa: str
    status: str
    total_points: Decimal
    closes_at: datetime


@dataclass(frozen=True, slots=True)
class Cell:
    quiz_id: uuid.UUID
    score: Decimal | None
    is_provisional: bool
    attempts: int


@dataclass(slots=True)
class Row:
    enrollment: Enrollment
    cells: list[Cell]
    attendance: dict[str, int]
    learning: StudentLearning | None


@dataclass(slots=True)
class Gradebook:
    offering_id: uuid.UUID
    sessions_held: int
    quizzes: list[QuizColumn] = field(default_factory=list)
    rows: list[Row] = field(default_factory=list)


class GradebookService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def for_offering(self, offering_id: uuid.UUID) -> Gradebook:
        await TeachingService(self.session).offering(offering_id)

        enrollments = list(
            await self.session.scalars(
                select(Enrollment)
                .where(
                    Enrollment.offering_id == offering_id,
                    Enrollment.status.in_(GRADEBOOK_STATUSES),
                )
                .order_by(Enrollment.enrolled_at)
            )
        )
        quizzes = [
            QuizColumn(
                id=q.id,
                title_fa=q.title_fa,
                status=q.status,
                total_points=q.total_points,
                closes_at=q.closes_at,
            )
            for q in await self.session.scalars(
                select(Quiz)
                .where(
                    Quiz.offering_id == offering_id,
                    Quiz.status.in_(("PUBLISHED", "CLOSED")),
                    Quiz.deleted_at.is_(None),
                )
                .order_by(Quiz.opens_at, Quiz.created_at)
            )
        ]
        sessions_held = int(
            await self.session.scalar(
                select(func.count()).where(ClassSession.offering_id == offering_id)
            )
            or 0
        )
        book = Gradebook(offering_id=offering_id, sessions_held=sessions_held, quizzes=quizzes)
        if not enrollments:
            return book

        student_ids = [e.student_id for e in enrollments]
        best = await self._best_attempts([q.id for q in quizzes], student_ids)
        attendance = await self._attendance(offering_id, student_ids)
        learning = await LearningScoreService(self.session).for_offering(
            offering_id, students=student_ids
        )

        for enrollment in enrollments:
            sid = enrollment.student_id
            cells = []
            for quiz in quizzes:
                found = best.get((quiz.id, sid))
                cells.append(
                    Cell(
                        quiz_id=quiz.id,
                        score=found[0] if found else None,
                        is_provisional=found[1] if found else False,
                        attempts=found[2] if found else 0,
                    )
                )
            book.rows.append(
                Row(
                    enrollment=enrollment,
                    cells=cells,
                    attendance=attendance.get(sid, {}),
                    learning=learning.get(sid),
                )
            )
        return book

    async def _best_attempts(
        self, quiz_ids: list[uuid.UUID], student_ids: list[uuid.UUID]
    ) -> dict[tuple[uuid.UUID, uuid.UUID], tuple[Decimal | None, bool, int]]:
        """(آزمون، دانشجو) ← (بهترین نمره، موقت بودن همان تلاش، شمار تلاش)."""
        if not quiz_ids:
            return {}
        grouped: dict[tuple[uuid.UUID, uuid.UUID], list[QuizAttempt]] = defaultdict(list)
        for attempt in await self.session.scalars(
            select(QuizAttempt).where(
                QuizAttempt.quiz_id.in_(quiz_ids),
                QuizAttempt.student_id.in_(student_ids),
                QuizAttempt.status.in_(SCORED_STATUSES),
            )
        ):
            grouped[(attempt.quiz_id, attempt.student_id)].append(attempt)

        result: dict[tuple[uuid.UUID, uuid.UUID], tuple[Decimal | None, bool, int]] = {}
        for key, attempts in grouped.items():
            scored = [a for a in attempts if a.total_score is not None]
            if not scored:
                result[key] = (None, True, len(attempts))
                continue
            top = max(scored, key=lambda a: a.total_score or Decimal(0))
            result[key] = (top.total_score, bool(top.is_provisional), len(attempts))
        return result

    async def _attendance(
        self, offering_id: uuid.UUID, student_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, dict[str, int]]:
        rows = await self.session.execute(
            select(AttendanceRecord.student_id, AttendanceRecord.status, func.count())
            .join(ClassSession, ClassSession.id == AttendanceRecord.session_id)
            .where(
                ClassSession.offering_id == offering_id,
                AttendanceRecord.student_id.in_(student_ids),
            )
            .group_by(AttendanceRecord.student_id, AttendanceRecord.status)
        )
        tally: dict[uuid.UUID, dict[str, int]] = defaultdict(dict)
        for student_id, status, count in rows.tuples():
            tally[student_id][status] = int(count)
        return tally


__all__ = ["GRADEBOOK_STATUSES", "Cell", "Gradebook", "GradebookService", "QuizColumn", "Row"]
