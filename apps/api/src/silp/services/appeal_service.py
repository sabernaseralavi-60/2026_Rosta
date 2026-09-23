"""اعتراض به نمره — §7.3، FR-QUIZ-04. وظیفهٔ نقشهٔ راه: M4-12.

```
دانشجو اعتراض می‌کند ──► OPEN ──┬── استاد می‌پذیرد ──► ACCEPTED
                                 │      └► نمره اصلاح + لاگ
                                 └── استاد رد می‌کند ──► REJECTED + پاسخ متنی
```

دو قاعده که این ماژول نگه می‌دارد:

**۱. مهلت ۷ روزه از لحظهٔ انتشار نتیجه.** نه از لحظهٔ آزمون: دانشجویی
که نتیجه‌اش دو هفته بعد منتشر شده، مهلتش هم دو هفته بعد شروع می‌شود.

**۲. رد کردن بدون پاسخ متنی ممکن نیست.** «رد شد» بدون دلیل، اعتراض را
به یک دکمهٔ تشریفاتی تبدیل می‌کند — همان استدلالی که §7.6 برای
بازخورد اجباری در بازبینی تحویل‌دادنی دارد.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from silp.core.exceptions import (
    AppealWindowClosed,
    Conflict,
    NotFound,
    ResultNotAvailable,
    ValidationFailed,
)
from silp.core.logging import get_logger
from silp.domain.quiz import appeal_window_open
from silp.models.quiz import GradeAppeal, Quiz, QuizAttempt, QuizQuestion
from silp.services import events
from silp.services.grading_service import GradingService

log = get_logger("silp.appeal")

MAX_REASON_LENGTH = 1000
MAX_RESPONSE_LENGTH = 1000


class AppealService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def open(
        self,
        *,
        attempt_id: uuid.UUID,
        student_id: uuid.UUID,
        reason: str,
        question_id: uuid.UUID | None = None,
    ) -> GradeAppeal:
        attempt = await self._own_attempt(attempt_id, student_id)
        quiz = await self._quiz_of(attempt)

        if attempt.status != "GRADED":
            raise ResultNotAvailable("تا پیش از تصحیح، اعتراضی ثبت نمی‌شود.")

        published = _results_published_at(quiz, attempt)
        if published is None:
            raise ResultNotAvailable("نتیجهٔ این آزمون هنوز منتشر نشده است.")
        if not appeal_window_open(now=datetime.now(UTC), results_published_at=published):
            raise AppealWindowClosed()

        cleaned = reason.strip()
        if not cleaned:
            raise ValidationFailed("دلیل اعتراض نمی‌تواند خالی باشد.")
        if len(cleaned) > MAX_REASON_LENGTH:
            raise ValidationFailed(f"دلیل اعتراض بیش از {MAX_REASON_LENGTH} نویسه است.")

        if question_id is not None:
            question = await self.session.get(QuizQuestion, question_id)
            if question is None or question.quiz_id != attempt.quiz_id:
                raise NotFound("این سؤال پیدا نشد.")

        appeal = GradeAppeal(
            attempt_id=attempt_id,
            question_id=question_id,
            student_id=student_id,
            reason=cleaned,
            status="OPEN",
        )
        self.session.add(appeal)
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            # قید یکتای جزئی — یک اعتراض باز برای هر (تلاش، سؤال).
            raise Conflict("برای این مورد اعتراض بازی دارید.") from exc

        await self.session.refresh(appeal)
        log.info("appeal_opened", appeal_id=str(appeal.id), attempt_id=str(attempt_id))
        return appeal

    async def list_for_quiz(
        self, quiz_id: uuid.UUID, *, only_open: bool = True
    ) -> list[GradeAppeal]:
        stmt = (
            select(GradeAppeal)
            .join(QuizAttempt, QuizAttempt.id == GradeAppeal.attempt_id)
            .where(QuizAttempt.quiz_id == quiz_id)
        )
        if only_open:
            stmt = stmt.where(GradeAppeal.status == "OPEN")
        return list(await self.session.scalars(stmt.order_by(GradeAppeal.created_at)))

    async def list_for_student(self, student_id: uuid.UUID) -> list[GradeAppeal]:
        return list(
            await self.session.scalars(
                select(GradeAppeal)
                .where(GradeAppeal.student_id == student_id)
                .order_by(GradeAppeal.created_at.desc())
            )
        )

    async def resolve(
        self,
        *,
        appeal_id: uuid.UUID,
        quiz_id: uuid.UUID,
        resolver_id: uuid.UUID,
        accept: bool,
        response: str,
        new_score: Decimal | None = None,
    ) -> GradeAppeal:
        """رسیدگی استاد — §7.3.

        پذیرفتن اعتراض **می‌تواند** نمره را عوض کند ولی مجبور نیست:
        گاهی استاد حق را می‌دهد و نمره همان است که بود (مثلاً پاسخ
        درست بوده ولی در کلید نبوده و کلید اصلاح می‌شود). پس
        `new_score` اختیاری است.
        """
        appeal = await self.session.get(GradeAppeal, appeal_id)
        if appeal is None:
            raise NotFound("این اعتراض پیدا نشد.")

        attempt = await self.session.get(QuizAttempt, appeal.attempt_id)
        if attempt is None or attempt.quiz_id != quiz_id:
            raise NotFound("این اعتراض پیدا نشد.")
        if appeal.status != "OPEN":
            raise Conflict("این اعتراض قبلاً رسیدگی شده است.")

        cleaned = response.strip()
        if not cleaned:
            raise ValidationFailed("پاسخ به اعتراض نمی‌تواند خالی باشد.")
        if len(cleaned) > MAX_RESPONSE_LENGTH:
            raise ValidationFailed(f"پاسخ بیش از {MAX_RESPONSE_LENGTH} نویسه است.")

        if new_score is not None:
            if not accept:
                raise ValidationFailed("اعتراض ردشده نمی‌تواند نمره را عوض کند.")
            if appeal.question_id is None:
                raise ValidationFailed("برای اصلاح نمره، اعتراض باید به یک سؤال مشخص باشد.")
            # از مسیر تصحیح دستی می‌رود تا جمع نمره و پرچم «موقت» هم
            # به‌روز شوند و همان لاگ حسابرسی نوشته شود.
            await GradingService(self.session).grade_answer(
                quiz_id=quiz_id,
                attempt_id=appeal.attempt_id,
                question_id=appeal.question_id,
                score=new_score,
                grader_id=resolver_id,
                feedback=cleaned,
            )

        appeal.status = "ACCEPTED" if accept else "REJECTED"
        appeal.response = cleaned
        appeal.resolved_by = resolver_id
        appeal.resolved_at = datetime.now(UTC)
        await events.publish(self.session, events.AppealResolved(appeal_id=appeal.id))
        await self.session.commit()
        await self.session.refresh(appeal)

        log.info(
            "appeal_resolved",
            appeal_id=str(appeal_id),
            status=appeal.status,
            resolver_id=str(resolver_id),
            score_changed=new_score is not None,
        )
        return appeal

    # ── کمکی ───────────────────────────────────────────────────────────
    async def _own_attempt(self, attempt_id: uuid.UUID, student_id: uuid.UUID) -> QuizAttempt:
        attempt = await self.session.get(QuizAttempt, attempt_id)
        if attempt is None or attempt.student_id != student_id:
            raise NotFound("این تلاش پیدا نشد.")
        return attempt

    async def _quiz_of(self, attempt: QuizAttempt) -> Quiz:
        quiz = await self.session.get(Quiz, attempt.quiz_id)
        if quiz is None:  # pragma: no cover
            raise NotFound("این آزمون پیدا نشد.")
        return quiz


def _results_published_at(quiz: Quiz, attempt: QuizAttempt) -> datetime | None:
    """لحظه‌ای که مهلت ۷ روزهٔ اعتراض از آن می‌شمارد.

    برای هر سه حالت `result_visibility` تعریف می‌شود، وگرنه دانشجوی
    آزمونِ `IMMEDIATE` هیچ‌وقت نمی‌توانست اعتراض کند.
    """
    match quiz.result_visibility:
        case "IMMEDIATE":
            return attempt.graded_at
        case "AFTER_CLOSE":
            return quiz.closes_at
        case "MANUAL":
            return quiz.results_published_at
    return None  # pragma: no cover


__all__ = ["AppealService"]
