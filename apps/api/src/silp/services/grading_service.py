"""تصحیح دستی، نتیجه، و تحلیل سؤال — FR-QUIZ-03، FR-QUIZ-04، §3.5.

وظیفه‌های نقشهٔ راه: M4-10 (صف تصحیح)، M4-11 (نتیجه)، M4-12 (اعتراض)،
M4-13 (تحلیل سؤال).

## چرا صف «بر اساس سؤال» است، نه «بر اساس دانشجو»

§3.5 صریح گفته و دلیلش روانی است، نه فنی: استادی که یک سؤال را برای
سی نفر پشت سر هم می‌خواند، معیارش ثابت می‌ماند. استادی که برگهٔ کاملِ
یک نفر را می‌خواند و بعد برگهٔ بعدی را، معیارش بین نفر اول و سی‌ام
جابه‌جا می‌شود — و این در نمرهٔ دانشجو دیده می‌شود.

ایندکس `idx_quiz_answers_grading_queue` روی `(question_id, attempt_id)`
دقیقاً برای همین چیده شده.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from silp.core.exceptions import (
    AttemptStillRunning,
    NotFound,
    PermissionDenied,
    ResultNotAvailable,
    ValidationFailed,
)
from silp.core.logging import get_logger
from silp.domain.quiz import (
    QuestionKind,
    parse_question,
    quantize,
    review_payload,
)
from silp.models.quiz import Quiz, QuizAnswer, QuizAttempt, QuizQuestion
from silp.services import events

log = get_logger("silp.grading")

#: کمینهٔ تعداد تلاش برای اینکه «میانگین کلاس» هویت کسی را لو ندهد.
#: با دو نفر، هر کس از میانگین، نمرهٔ دیگری را حساب می‌کند.
MIN_COHORT_FOR_STATS = 3

#: تحلیل تمیز (M4-13) روی یک‌سوم بالا و پایین انجام می‌شود.
DISCRIMINATION_GROUP_RATIO = Decimal("0.27")
MIN_COHORT_FOR_DISCRIMINATION = 10


@dataclass(frozen=True, slots=True)
class PendingAnswer:
    """یک پاسخ تشریحی منتظر تصحیح."""

    attempt_id: uuid.UUID
    question_id: uuid.UUID
    student_id: uuid.UUID
    attempt_no: int
    response: dict[str, Any] | None
    points: Decimal


@dataclass(frozen=True, slots=True)
class GradingQueue:
    question: QuizQuestion
    pending: list[PendingAnswer]
    graded_count: int


@dataclass(frozen=True, slots=True)
class ResultQuestion:
    question: QuizQuestion
    response: dict[str, Any] | None
    score: Decimal | None
    feedback: str | None
    is_correct: bool | None
    review: dict[str, Any] | None


@dataclass(frozen=True, slots=True)
class AttemptResult:
    attempt: QuizAttempt
    quiz: Quiz
    questions: list[ResultQuestion]
    class_average: Decimal | None
    cohort_size: int
    passed: bool | None


@dataclass(frozen=True, slots=True)
class QuestionStats:
    """تحلیل یک سؤال — M4-13."""

    question_id: uuid.UUID
    body: str
    kind: str
    points: Decimal
    answered: int
    difficulty: Decimal | None
    discrimination: Decimal | None


class GradingService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ── صف تصحیح تشریحی — M4-10 ───────────────────────────────────────
    async def queue_for_question(
        self, *, quiz_id: uuid.UUID, question_id: uuid.UUID
    ) -> GradingQueue:
        question = await self._question_of(question_id, quiz_id)
        if question.kind != QuestionKind.ESSAY.value:
            raise ValidationFailed("فقط سؤال تشریحی صف تصحیح دستی دارد.")

        rows = list(
            await self.session.execute(
                select(QuizAnswer, QuizAttempt)
                .join(QuizAttempt, QuizAttempt.id == QuizAnswer.attempt_id)
                .where(
                    QuizAnswer.question_id == question_id,
                    QuizAttempt.status == "GRADED",
                )
                .order_by(QuizAttempt.submitted_at, QuizAttempt.id)
            )
        )

        pending: list[PendingAnswer] = []
        graded = 0
        for answer, attempt in rows:
            if answer.manual_score is not None:
                graded += 1
                continue
            # پاسخ خالی به صف نمی‌رود (ADR-0011 مسئلهٔ ۴).
            if not _has_text(answer.response):
                continue
            pending.append(
                PendingAnswer(
                    attempt_id=attempt.id,
                    question_id=question_id,
                    student_id=attempt.student_id,
                    attempt_no=attempt.attempt_no,
                    response=answer.response,
                    points=question.points,
                )
            )
        return GradingQueue(question=question, pending=pending, graded_count=graded)

    async def pending_questions(self, quiz_id: uuid.UUID) -> list[QuizQuestion]:
        """سؤال‌های تشریحی این آزمون که هنوز پاسخ تصحیح‌نشده دارند."""
        return list(
            await self.session.scalars(
                select(QuizQuestion)
                .where(
                    QuizQuestion.quiz_id == quiz_id,
                    QuizQuestion.kind == QuestionKind.ESSAY.value,
                )
                .order_by(QuizQuestion.sort_order)
            )
        )

    # ── ثبت نمرهٔ دستی ────────────────────────────────────────────────
    async def grade_answer(
        self,
        *,
        quiz_id: uuid.UUID,
        attempt_id: uuid.UUID,
        question_id: uuid.UUID,
        score: Decimal,
        grader_id: uuid.UUID,
        feedback: str | None = None,
    ) -> QuizAnswer:
        """ثبت یا بازنویسی نمرهٔ یک سؤال — FR-QUIZ-03.

        همین متد هم برای تصحیح تشریحی به کار می‌رود و هم برای
        **بازنویسی** نمرهٔ یک سؤال بسته توسط استاد. تفاوتشان فقط در این
        است که دومی روی سؤالی می‌نشیند که `auto_score` دارد؛ `grader_id`
        و لاگ در هر دو حالت ثبت می‌شوند، که همان «ثبت دلیل در لاگ
        حسابرسی» سند است.
        """
        question = await self._question_of(question_id, quiz_id)
        attempt = await self._attempt_of(attempt_id, quiz_id)

        if score < 0 or score > question.points:
            raise ValidationFailed(f"نمره باید بین ۰ تا {question.points} باشد.")

        answer = await self.session.get(QuizAnswer, (attempt_id, question_id))
        if answer is None:
            raise NotFound("پاسخی برای این سؤال ثبت نشده است.")

        previous = answer.manual_score
        answer.manual_score = quantize(score)
        answer.grader_id = grader_id
        answer.feedback = feedback

        await self._recalculate(attempt)
        await events.publish(self.session, events.QuizGraded(attempt_id=attempt.id))
        await self.session.commit()
        await self.session.refresh(answer)

        log.info(
            "answer_graded_manually",
            attempt_id=str(attempt_id),
            question_id=str(question_id),
            grader_id=str(grader_id),
            previous=str(previous) if previous is not None else None,
            score=str(answer.manual_score),
            was_auto_graded=answer.auto_score is not None,
        )
        return answer

    async def _recalculate(self, attempt: QuizAttempt) -> None:
        """جمع تازهٔ نمره‌ها و به‌روزرسانی پرچم «موقت».

        `flush` لازم است: نشست `autoflush=False` دارد (D-01)، پس نمرهٔ
        تازه‌ای که هنوز در حافظه است در این `SELECT` دیده نمی‌شود و
        جمع، همان جمع قبلی درمی‌آید.
        """
        await self.session.flush()
        rows = list(
            await self.session.execute(
                select(QuizAnswer, QuizQuestion)
                .join(QuizQuestion, QuizQuestion.id == QuizAnswer.question_id)
                .where(QuizAnswer.attempt_id == attempt.id)
            )
        )

        auto = Decimal("0")
        manual = Decimal("0")
        still_pending = False
        for answer, question in rows:
            if answer.manual_score is not None:
                manual += answer.manual_score
            elif answer.auto_score is not None:
                auto += answer.auto_score
            if (
                question.kind == QuestionKind.ESSAY.value
                and answer.manual_score is None
                and _has_text(answer.response)
            ):
                still_pending = True

        attempt.auto_score = quantize(auto)
        attempt.manual_score = quantize(manual)
        attempt.total_score = quantize(auto + manual)
        attempt.is_provisional = still_pending
        attempt.graded_at = datetime.now(UTC)

    async def finalize_attempt(
        self, *, quiz_id: uuid.UUID, attempt_id: uuid.UUID, grader_id: uuid.UUID
    ) -> QuizAttempt:
        """پایان تصحیح دستی یک تلاش — `is_provisional` خاموش می‌شود."""
        attempt = await self._attempt_of(attempt_id, quiz_id)
        await self._recalculate(attempt)
        attempt.graded_by = grader_id
        await events.publish(self.session, events.QuizGraded(attempt_id=attempt.id))
        await self.session.commit()
        await self.session.refresh(attempt)
        return attempt

    async def void_attempt(
        self, *, quiz_id: uuid.UUID, attempt_id: uuid.UUID, grader_id: uuid.UUID
    ) -> QuizAttempt:
        """ابطال یک تلاش توسط استاد — §7.3.

        تلاش باطل‌شده از شمارش دفعات مجاز بیرون می‌رود (`_attempt_counts`)
        تا ابطالِ یک تلاشِ خراب، دفعهٔ دانشجو را نسوزاند.
        """
        attempt = await self._attempt_of(attempt_id, quiz_id, must_be_finished=False)
        attempt.status = "VOIDED"
        attempt.is_provisional = False
        attempt.graded_by = grader_id
        # تلاش باطل‌شده امتیازش را پس می‌دهد؛ اگر بهترین تلاش بود، تلاش
        # بعدیِ دانشجو جایش را می‌گیرد (§7.12).
        await events.publish(self.session, events.QuizGraded(attempt_id=attempt.id))
        await self.session.commit()
        await self.session.refresh(attempt)
        log.info("attempt_voided", attempt_id=str(attempt_id), grader_id=str(grader_id))
        return attempt

    # ── نتیجه — FR-QUIZ-04 ────────────────────────────────────────────
    async def result(
        self, *, attempt_id: uuid.UUID, viewer_id: uuid.UUID, is_staff: bool = False
    ) -> AttemptResult:
        attempt = await self.session.get(QuizAttempt, attempt_id)
        if attempt is None:
            raise NotFound("این تلاش پیدا نشد.")
        if not is_staff and attempt.student_id != viewer_id:
            raise NotFound("این تلاش پیدا نشد.")

        quiz = await self.session.get(Quiz, attempt.quiz_id)
        if quiz is None:  # pragma: no cover
            raise NotFound("این آزمون پیدا نشد.")

        now = datetime.now(UTC)
        if not is_staff and not results_visible(quiz, attempt, now=now):
            raise ResultNotAvailable()
        if attempt.status == "IN_PROGRESS":
            raise ResultNotAvailable("این آزمون هنوز تمام نشده است.")

        show_key = is_staff or quiz.show_correct_answers
        rows = await self._answers_with_questions(attempt_id)

        questions: list[ResultQuestion] = []
        for answer, question in rows:
            score = answer.effective_score
            questions.append(
                ResultQuestion(
                    question=question,
                    response=answer.response,
                    score=score,
                    feedback=answer.feedback,
                    is_correct=_verdict(score, question.points),
                    review=_review_of(question) if show_key else None,
                )
            )

        average, cohort = await self._class_average(quiz.id)
        return AttemptResult(
            attempt=attempt,
            quiz=quiz,
            questions=questions,
            class_average=average,
            cohort_size=cohort,
            passed=_passed(attempt, quiz),
        )

    async def _class_average(self, quiz_id: uuid.UUID) -> tuple[Decimal | None, int]:
        """میانگین کلاس — بدون افشای هویت کسی (FR-QUIZ-04).

        زیر آستانه، میانگین **برگردانده نمی‌شود**: در کلاسی با دو تلاش،
        هر کس از میانگین و نمرهٔ خودش، نمرهٔ دیگری را حساب می‌کند.
        """
        row = (
            await self.session.execute(
                select(func.avg(QuizAttempt.total_score), func.count()).where(
                    QuizAttempt.quiz_id == quiz_id,
                    QuizAttempt.status == "GRADED",
                    QuizAttempt.total_score.is_not(None),
                )
            )
        ).one()
        average, count = row
        if count < MIN_COHORT_FOR_STATS or average is None:
            return None, int(count or 0)
        return quantize(Decimal(str(average))), int(count)

    # ── تحلیل سؤال — M4-13 ────────────────────────────────────────────
    async def question_stats(self, quiz_id: uuid.UUID) -> list[QuestionStats]:
        """ضریب دشواری و ضریب تمیز هر سؤال.

        * **دشواری** = میانگین نسبت نمرهٔ کسب‌شده به بارم. عدد بالا یعنی
          سؤال آسان بود.
        * **تمیز** = دشواری در گروه قوی منهای دشواری در گروه ضعیف. عدد
          نزدیک صفر یا منفی یعنی سؤال بین دانشجوی بلد و نابلد فرقی
          نگذاشته — یعنی سؤال بد است، نه دانشجوی بد.

        گروه‌ها ۲۷٪ بالا و ۲۷٪ پایینِ نمرهٔ کل‌اند (قاعدهٔ متعارف
        Kelley). زیر ده تلاش، تمیز محاسبه **نمی‌شود**: با پنج نفر عددش
        نویز است و نویزی که شکل شاخص دارد، بدتر از نبودن شاخص است.
        """
        questions = list(
            await self.session.scalars(
                select(QuizQuestion)
                .where(QuizQuestion.quiz_id == quiz_id)
                .order_by(QuizQuestion.sort_order)
            )
        )
        if not questions:
            return []

        attempts = list(
            await self.session.scalars(
                select(QuizAttempt)
                .where(QuizAttempt.quiz_id == quiz_id, QuizAttempt.status == "GRADED")
                .order_by(QuizAttempt.total_score.desc().nulls_last())
            )
        )
        scores = await self._scores_by_question(quiz_id)

        cohort = len(attempts)
        group_size = int(cohort * DISCRIMINATION_GROUP_RATIO)
        top = {a.id for a in attempts[:group_size]} if group_size else set()
        bottom = {a.id for a in attempts[-group_size:]} if group_size else set()

        stats: list[QuestionStats] = []
        for question in questions:
            per_attempt = scores.get(question.id, {})
            ratios = [
                score / question.points
                for score in per_attempt.values()
                if score is not None and question.points > 0
            ]
            difficulty = _mean(ratios)

            discrimination = None
            if cohort >= MIN_COHORT_FOR_DISCRIMINATION and top and bottom:
                high = _mean(_ratios(per_attempt, top, question.points))
                low = _mean(_ratios(per_attempt, bottom, question.points))
                if high is not None and low is not None:
                    discrimination = quantize(high - low)

            stats.append(
                QuestionStats(
                    question_id=question.id,
                    body=question.body,
                    kind=question.kind,
                    points=question.points,
                    answered=len(ratios),
                    difficulty=quantize(difficulty) if difficulty is not None else None,
                    discrimination=discrimination,
                )
            )
        return stats

    async def _scores_by_question(
        self, quiz_id: uuid.UUID
    ) -> dict[uuid.UUID, dict[uuid.UUID, Decimal | None]]:
        rows = list(
            await self.session.execute(
                select(QuizAnswer.question_id, QuizAnswer.attempt_id, QuizAnswer)
                .join(QuizAttempt, QuizAttempt.id == QuizAnswer.attempt_id)
                .where(QuizAttempt.quiz_id == quiz_id, QuizAttempt.status == "GRADED")
            )
        )
        result: dict[uuid.UUID, dict[uuid.UUID, Decimal | None]] = {}
        for question_id, attempt_id, answer in rows:
            result.setdefault(question_id, {})[attempt_id] = answer.effective_score
        return result

    # ── کمکی ───────────────────────────────────────────────────────────
    async def _question_of(self, question_id: uuid.UUID, quiz_id: uuid.UUID) -> QuizQuestion:
        question = await self.session.get(QuizQuestion, question_id)
        if question is None or question.quiz_id != quiz_id:
            raise NotFound("این سؤال پیدا نشد.")
        return question

    async def _attempt_of(
        self, attempt_id: uuid.UUID, quiz_id: uuid.UUID, *, must_be_finished: bool = True
    ) -> QuizAttempt:
        """تلاش، با تأیید تعلقش به همین آزمون.

        `must_be_finished` پیش‌فرضِ سخت‌گیرانه دارد: **تلاشی که دانشجو
        هنوز در آن است نمره نمی‌گیرد.** بدون این، استاد می‌توانست وسط
        آزمون نمرهٔ یک پاسخ را بنویسد و `total_score` روی تلاشی بنشیند
        که هنوز تمام نشده — عددی که دانشجو ندیده و بر اساس پاسخ‌های
        نیمه‌کاره است.
        """
        attempt = await self.session.get(QuizAttempt, attempt_id)
        if attempt is None or attempt.quiz_id != quiz_id:
            raise NotFound("این تلاش پیدا نشد.")
        if attempt.status == "VOIDED":
            raise PermissionDenied("این تلاش باطل شده است.")
        if must_be_finished and attempt.status == "IN_PROGRESS":
            raise AttemptStillRunning()
        return attempt

    async def _answers_with_questions(
        self, attempt_id: uuid.UUID
    ) -> list[tuple[QuizAnswer, QuizQuestion]]:
        rows = await self.session.execute(
            select(QuizAnswer, QuizQuestion)
            .join(QuizQuestion, QuizQuestion.id == QuizAnswer.question_id)
            .where(QuizAnswer.attempt_id == attempt_id)
            .order_by(QuizQuestion.sort_order)
        )
        return list(rows)  # type: ignore[arg-type]


# ── توابع ماژول ────────────────────────────────────────────────────────


def results_visible(quiz: Quiz, attempt: QuizAttempt, *, now: datetime) -> bool:
    """FR-QUIZ-04 — سه حالت نمایش نتیجه.

    عمومی است چون امتیاز آزمون هم به آن وابسته است: امتیاز «نمرهٔ آزمون»
    پیش از دیده شدن نتیجه ثبت نمی‌شود، وگرنه Toast «+۲۴ امتیاز» نمره را
    زودتر از خود صفحهٔ نتیجه لو می‌داد (ADR-0012).
    """
    match quiz.result_visibility:
        case "IMMEDIATE":
            return attempt.status in ("GRADED", "SUBMITTED", "AUTO_SUBMITTED")
        case "AFTER_CLOSE":
            return now > quiz.closes_at
        case "MANUAL":
            return quiz.results_published_at is not None
    return False  # pragma: no cover


def _passed(attempt: QuizAttempt, quiz: Quiz) -> bool | None:
    if quiz.passing_score is None or attempt.total_score is None:
        return None
    return attempt.total_score >= quiz.passing_score


def _verdict(score: Decimal | None, points: Decimal) -> bool | None:
    """سه‌حالته، مثل `GradedAnswer.is_correct`: نمرهٔ جزئی نه درست است
    نه غلط."""
    if score is None:
        return None
    if score >= points:
        return True
    if score <= 0:
        return False
    return None


def _review_of(question: QuizQuestion) -> dict[str, Any] | None:
    try:
        parsed = parse_question(
            question_id=str(question.id),
            kind=question.kind,
            points=question.points,
            payload=question.payload,
        )
    except ValueError:  # pragma: no cover — سؤال معیوب نباید ذخیره شده باشد
        return None
    data = review_payload(parsed)
    data["explanation"] = question.explanation
    return data


def _has_text(response: dict[str, Any] | None) -> bool:
    if not response:
        return False
    text = response.get("text")
    return isinstance(text, str) and bool(text.strip())


def _ratios(
    per_attempt: dict[uuid.UUID, Decimal | None],
    group: set[uuid.UUID],
    points: Decimal,
) -> list[Decimal]:
    return [
        score / points
        for attempt_id in group
        if (score := per_attempt.get(attempt_id)) is not None and points > 0
    ]


def _mean(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    return sum(values, Decimal("0")) / Decimal(len(values))


__all__ = [
    "MIN_COHORT_FOR_STATS",
    "AttemptResult",
    "GradingQueue",
    "GradingService",
    "PendingAnswer",
    "QuestionStats",
    "ResultQuestion",
    "results_visible",
]
