"""ساخت و مدیریت آزمون — FR-QUIZ-01، §5.11.

وظیفه‌های نقشهٔ راه: M4-02 (ویرایشگر آزمون)، M4-03 (بانک سؤال).

مجوز در لایهٔ مسیر با `require(..., scope=offering_from_path)` بررسی
می‌شود و اینجا **دوباره** (§6.4 قاعدهٔ ۲): هر متد شناسهٔ ارائه را
می‌گیرد و خودش تأیید می‌کند که آزمون به همان ارائه تعلق دارد. بدون آن،
شناسهٔ آزمونِ یک ارائهٔ دیگر کافی است تا مجوز قلمرودار دور بخورد.

## دو قاعده که این ماژول نگه می‌دارد

**۱. سؤال از بانک، کپی می‌شود نه ارجاع.** استادی که ماه بعد غلط
تایپی یک سؤال بانک را درست می‌کند، نباید نمرهٔ آزمون برگزارشده را
تکان بدهد.

**۲. آزمونی که تلاش دارد، سؤالش عوض نمی‌شود.** افزودن یک سؤال به
آزمونی که ده نفر داده‌اند یعنی آن ده نفر سؤالی را نداشته‌اند که در
بارم کل حساب می‌شود. تنها استثنا `DRAFT` است، که هنوز کسی ندیده.
"""

from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from silp.core.exceptions import (
    Conflict,
    NotFound,
    QuizHasAttempts,
    QuizHasNoQuestions,
    ValidationFailed,
)
from silp.core.logging import get_logger
from silp.domain.quiz import InvalidQuestionPayload, validate_payload
from silp.models.education import CourseOffering, CourseWeek
from silp.models.learning import Concept, Lesson
from silp.models.quiz import (
    MAX_ATTEMPTS,
    MAX_DURATION_MIN,
    QUESTION_KINDS,
    RESULT_VISIBILITIES,
    QuestionBankItem,
    Quiz,
    QuizAttempt,
    QuizQuestion,
)
from silp.services import events

log = get_logger("silp.quiz")

MAX_QUESTIONS_PER_QUIZ = 200
MAX_BANK_PICK = 100


QUIZ_KINDS = ("EXAM", "QUIZ", "CHECKPOINT")
CHECKPOINT_MAX_MINUTES = 30
CHECKPOINT_MAX_QUESTIONS = 30


@dataclass(frozen=True, slots=True)
class QuizDraft:
    title_fa: str
    duration_min: int
    opens_at: datetime
    closes_at: datetime
    week_id: uuid.UUID | None = None
    description: str | None = None
    max_attempts: int = 1
    passing_score: Decimal | None = None
    shuffle_questions: bool = True
    shuffle_options: bool = True
    result_visibility: str = "AFTER_CLOSE"
    show_correct_answers: bool = True
    kind: str = "QUIZ"
    lesson_id: uuid.UUID | None = None
    draw_count: int | None = None


@dataclass(frozen=True, slots=True)
class QuestionDraft:
    kind: str
    body: str
    payload: dict[str, Any]
    points: Decimal = Decimal("1")
    explanation: str | None = None
    sort_order: int | None = None
    bank_id: uuid.UUID | None = None


class QuizService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ── خواندن ─────────────────────────────────────────────────────────
    async def get(self, quiz_id: uuid.UUID, *, offering_id: uuid.UUID | None = None) -> Quiz:
        """یک آزمون، با تأیید اینکه به ارائهٔ ادعاشده تعلق دارد.

        ناهمخوانی، `404` می‌دهد نه `403` — §6.4 قاعدهٔ ۴: وجود آزمونِ
        ارائهٔ دیگری نباید از راه تفاوت کد خطا لو برود.
        """
        quiz = await self.session.get(Quiz, quiz_id)
        if quiz is None or quiz.deleted_at is not None:
            raise NotFound("این آزمون پیدا نشد.")
        if offering_id is not None and quiz.offering_id != offering_id:
            raise NotFound("این آزمون پیدا نشد.")
        return quiz

    async def list_for_offering(
        self, offering_id: uuid.UUID, *, include_drafts: bool
    ) -> list[Quiz]:
        stmt = select(Quiz).where(Quiz.offering_id == offering_id, Quiz.deleted_at.is_(None))
        if not include_drafts:
            stmt = stmt.where(Quiz.status != "DRAFT")
        stmt = stmt.order_by(Quiz.opens_at.desc())
        return list(await self.session.scalars(stmt))

    async def questions(self, quiz_id: uuid.UUID) -> list[QuizQuestion]:
        return list(
            await self.session.scalars(
                select(QuizQuestion)
                .where(QuizQuestion.quiz_id == quiz_id)
                .order_by(QuizQuestion.sort_order, QuizQuestion.id)
            )
        )

    # ── ساخت و ویرایش آزمون ────────────────────────────────────────────
    async def create(
        self, *, offering_id: uuid.UUID, draft: QuizDraft, created_by: uuid.UUID
    ) -> Quiz:
        offering = await self.session.get(CourseOffering, offering_id)
        if offering is None or offering.deleted_at is not None:
            raise NotFound("این ارائه پیدا نشد.")

        _validate_draft(draft)
        if draft.week_id is not None:
            await self._require_week_of(draft.week_id, offering_id)
        await self._require_lesson_of(draft.lesson_id, offering_id)

        quiz = Quiz(
            offering_id=offering_id,
            week_id=draft.week_id,
            title_fa=draft.title_fa.strip(),
            description=draft.description,
            duration_min=draft.duration_min,
            opens_at=draft.opens_at,
            closes_at=draft.closes_at,
            max_attempts=draft.max_attempts,
            passing_score=draft.passing_score,
            shuffle_questions=draft.shuffle_questions,
            shuffle_options=draft.shuffle_options,
            result_visibility=draft.result_visibility,
            show_correct_answers=draft.show_correct_answers,
            kind=draft.kind,
            lesson_id=draft.lesson_id,
            draw_count=draft.draw_count,
            status="DRAFT",
            created_by=created_by,
        )
        self.session.add(quiz)
        await self.session.commit()
        await self.session.refresh(quiz)
        log.info("quiz_created", quiz_id=str(quiz.id), offering_id=str(offering_id))
        return quiz

    async def update(self, *, quiz_id: uuid.UUID, offering_id: uuid.UUID, draft: QuizDraft) -> Quiz:
        quiz = await self.get(quiz_id, offering_id=offering_id)
        _validate_draft(draft)
        if draft.week_id is not None:
            await self._require_week_of(draft.week_id, offering_id)
        await self._require_lesson_of(draft.lesson_id, offering_id)

        # مدت آزمون پس از شروع اولین تلاش عوض نمی‌شود: `expires_at` هر
        # تلاش در لحظهٔ شروع قفل شده (§7.3 قاعدهٔ ۱)، پس تغییر مدت فقط
        # روی تلاش‌های بعدی اثر می‌گذارد و دو دانشجوی یک آزمون وقت
        # متفاوت می‌گیرند بی‌آنکه کسی بداند.
        if draft.duration_min != quiz.duration_min and await self._has_attempts(quiz_id):
            raise QuizHasAttempts("مدت آزمونی که تلاش ثبت‌شده دارد قابل تغییر نیست.")

        quiz.title_fa = draft.title_fa.strip()
        quiz.description = draft.description
        quiz.duration_min = draft.duration_min
        quiz.opens_at = draft.opens_at
        quiz.closes_at = draft.closes_at
        quiz.week_id = draft.week_id
        quiz.max_attempts = draft.max_attempts
        quiz.passing_score = draft.passing_score
        quiz.shuffle_questions = draft.shuffle_questions
        quiz.shuffle_options = draft.shuffle_options
        quiz.result_visibility = draft.result_visibility
        quiz.show_correct_answers = draft.show_correct_answers
        quiz.lesson_id = draft.lesson_id
        if draft.draw_count != quiz.draw_count:
            if await self._has_attempts(quiz_id):
                raise QuizHasAttempts("اندازهٔ استخر آزمونی که تلاش ثبت‌شده دارد قابل تغییر نیست.")
            quiz.draw_count = draft.draw_count

        await self.session.commit()
        await self.session.refresh(quiz)
        return quiz

    async def publish(self, *, quiz_id: uuid.UUID, offering_id: uuid.UUID) -> Quiz:
        quiz = await self.get(quiz_id, offering_id=offering_id)
        if quiz.status == "PUBLISHED":
            return quiz
        if quiz.status == "CLOSED":
            raise Conflict("آزمون بسته‌شده دوباره منتشر نمی‌شود.")

        count = await self.session.scalar(
            select(func.count()).select_from(QuizQuestion).where(QuizQuestion.quiz_id == quiz_id)
        )
        if not count:
            raise QuizHasNoQuestions()
        if quiz.draw_count is not None:
            await self._require_valid_pool(quiz, count)

        quiz.status = "PUBLISHED"
        await events.publish(self.session, events.QuizPublished(quiz_id=quiz.id))
        await self.session.commit()
        await self.session.refresh(quiz)
        log.info("quiz_published", quiz_id=str(quiz.id), questions=count)
        return quiz

    async def close(self, *, quiz_id: uuid.UUID, offering_id: uuid.UUID) -> Quiz:
        quiz = await self.get(quiz_id, offering_id=offering_id)
        quiz.status = "CLOSED"
        await self.session.commit()
        await self.session.refresh(quiz)
        return quiz

    async def publish_results(self, *, quiz_id: uuid.UUID, offering_id: uuid.UUID) -> Quiz:
        """انتشار دستی نتیجه — حالت `MANUAL` در FR-QUIZ-04.

        لحظهٔ انتشار ذخیره می‌شود چون مهلت ۷ روزهٔ اعتراض از همین
        می‌شمارد (§7.3) و بعداً قابل بازسازی نیست.
        """
        quiz = await self.get(quiz_id, offering_id=offering_id)
        if quiz.results_published_at is None:
            quiz.results_published_at = datetime.now(UTC)
            # نتیجه‌ای که حالا دیده می‌شود، امتیازش هم حالا ثبت می‌شود (ADR-0012).
            await events.publish(self.session, events.QuizResultsPublished(quiz_id=quiz.id))
            await self.session.commit()
            await self.session.refresh(quiz)
            log.info("quiz_results_published", quiz_id=str(quiz.id))
        return quiz

    async def soft_delete(self, *, quiz_id: uuid.UUID, offering_id: uuid.UUID) -> None:
        quiz = await self.get(quiz_id, offering_id=offering_id)
        if await self._has_attempts(quiz_id):
            raise QuizHasAttempts("آزمونی که تلاش ثبت‌شده دارد حذف نمی‌شود.")
        quiz.deleted_at = datetime.now(UTC)
        await self.session.commit()

    # ── سؤال ───────────────────────────────────────────────────────────
    async def add_question(
        self, *, quiz_id: uuid.UUID, offering_id: uuid.UUID, draft: QuestionDraft
    ) -> QuizQuestion:
        quiz = await self.get(quiz_id, offering_id=offering_id)
        await self._require_editable(quiz)

        existing = await self.session.scalar(
            select(func.count()).select_from(QuizQuestion).where(QuizQuestion.quiz_id == quiz_id)
        )
        if (existing or 0) >= MAX_QUESTIONS_PER_QUIZ:
            raise Conflict(f"یک آزمون بیش از {MAX_QUESTIONS_PER_QUIZ} سؤال نمی‌گیرد.")

        question = self._build_question(quiz_id, draft, fallback_order=existing or 0)
        self.session.add(question)
        await self.session.commit()
        await self.session.refresh(question)
        return question

    async def update_question(
        self,
        *,
        quiz_id: uuid.UUID,
        offering_id: uuid.UUID,
        question_id: uuid.UUID,
        draft: QuestionDraft,
    ) -> QuizQuestion:
        quiz = await self.get(quiz_id, offering_id=offering_id)
        await self._require_editable(quiz)
        question = await self._require_question_of(question_id, quiz_id)

        _validate_question(draft)
        question.kind = draft.kind
        question.body = draft.body.strip()
        question.payload = draft.payload
        question.points = draft.points
        question.explanation = draft.explanation
        if draft.sort_order is not None:
            question.sort_order = draft.sort_order

        await self.session.commit()
        await self.session.refresh(question)
        return question

    async def delete_question(
        self, *, quiz_id: uuid.UUID, offering_id: uuid.UUID, question_id: uuid.UUID
    ) -> None:
        quiz = await self.get(quiz_id, offering_id=offering_id)
        await self._require_editable(quiz)
        question = await self._require_question_of(question_id, quiz_id)
        await self.session.delete(question)
        await self.session.commit()

    async def reorder(
        self, *, quiz_id: uuid.UUID, offering_id: uuid.UUID, ordered_ids: list[uuid.UUID]
    ) -> list[QuizQuestion]:
        quiz = await self.get(quiz_id, offering_id=offering_id)
        await self._require_editable(quiz)

        questions = await self.questions(quiz_id)
        known = {q.id for q in questions}
        if set(ordered_ids) != known:
            raise ValidationFailed("فهرست ترتیب باید دقیقاً همهٔ سؤال‌های آزمون را داشته باشد.")

        position = {qid: index for index, qid in enumerate(ordered_ids)}
        for question in questions:
            question.sort_order = position[question.id]
        await self.session.commit()
        return await self.questions(quiz_id)

    # ── بانک سؤال — M4-03 ──────────────────────────────────────────────
    async def add_to_bank(
        self,
        *,
        owner_id: uuid.UUID,
        draft: QuestionDraft,
        course_id: uuid.UUID | None = None,
        category: str | None = None,
        difficulty: int | None = None,
        concept_id: uuid.UUID | None = None,
    ) -> QuestionBankItem:
        _validate_question(draft)
        if concept_id is not None and await self.session.get(Concept, concept_id) is None:
            raise NotFound("مفهوم پیدا نشد.")
        if difficulty is not None and not 1 <= difficulty <= 5:
            raise ValidationFailed("سطح دشواری باید بین ۱ تا ۵ باشد.")

        item = QuestionBankItem(
            owner_id=owner_id,
            course_id=course_id,
            category=category.strip() if category else None,
            difficulty=difficulty,
            kind=draft.kind,
            body=draft.body.strip(),
            payload=draft.payload,
            explanation=draft.explanation,
            concept_id=concept_id,
        )
        self.session.add(item)
        await self.session.commit()
        await self.session.refresh(item)
        return item

    async def update_bank_item(
        self,
        *,
        owner_id: uuid.UUID,
        item_id: uuid.UUID,
        draft: QuestionDraft,
        course_id: uuid.UUID | None = None,
        category: str | None = None,
        difficulty: int | None = None,
        concept_id: uuid.UUID | None = None,
    ) -> QuestionBankItem:
        """جایگزینی کامل سؤال بانک — ADR-0021.

        آزمون‌ها کپی دارند نه ارجاع؛ ویرایش اینجا نمرهٔ هیچ آزمونی را عوض
        نمی‌کند، فقط کپی‌های بعدی را.
        """
        item = await self._own_bank_item(owner_id, item_id)
        _validate_question(draft)
        if difficulty is not None and not 1 <= difficulty <= 5:
            raise ValidationFailed("سطح دشواری باید بین ۱ تا ۵ باشد.")
        item.course_id = course_id
        item.category = category.strip() if category else None
        item.difficulty = difficulty
        if concept_id is not None and await self.session.get(Concept, concept_id) is None:
            raise NotFound("مفهوم پیدا نشد.")
        item.concept_id = concept_id
        item.kind = draft.kind
        item.body = draft.body.strip()
        item.payload = draft.payload
        item.explanation = draft.explanation
        await self.session.commit()
        await self.session.refresh(item)
        return item

    async def delete_bank_item(self, *, owner_id: uuid.UUID, item_id: uuid.UUID) -> None:
        """حذف نرم: `quiz_questions.bank_id` منشأ را نگه می‌دارد و شمار استفاده معنا دارد."""
        item = await self._own_bank_item(owner_id, item_id)
        item.deleted_at = datetime.now(UTC)
        await self.session.commit()

    async def _own_bank_item(self, owner_id: uuid.UUID, item_id: uuid.UUID) -> QuestionBankItem:
        """بانک شخصی است: سؤال دیگری ۴۰۴ است، نه ۴۰۳ — وجودش هم گفته نمی‌شود."""
        item = await self.session.get(QuestionBankItem, item_id)
        if item is None or item.deleted_at is not None or item.owner_id != owner_id:
            raise NotFound("این سؤال در بانک تو نیست.")
        return item

    async def search_bank(
        self,
        *,
        owner_id: uuid.UUID,
        course_id: uuid.UUID | None = None,
        category: str | None = None,
        difficulty: int | None = None,
        kind: str | None = None,
        limit: int = 50,
    ) -> list[QuestionBankItem]:
        stmt = select(QuestionBankItem).where(
            QuestionBankItem.owner_id == owner_id, QuestionBankItem.deleted_at.is_(None)
        )
        if course_id is not None:
            stmt = stmt.where(QuestionBankItem.course_id == course_id)
        if category:
            stmt = stmt.where(QuestionBankItem.category == category)
        if difficulty is not None:
            stmt = stmt.where(QuestionBankItem.difficulty == difficulty)
        if kind:
            stmt = stmt.where(QuestionBankItem.kind == kind)
        stmt = stmt.order_by(QuestionBankItem.created_at.desc()).limit(min(limit, MAX_BANK_PICK))
        return list(await self.session.scalars(stmt))

    async def copy_from_bank(
        self,
        *,
        quiz_id: uuid.UUID,
        offering_id: uuid.UUID,
        bank_ids: list[uuid.UUID],
        points: Decimal = Decimal("1"),
    ) -> list[QuizQuestion]:
        """کپی چند سؤال بانک داخل آزمون — نه ارجاع، کپی."""
        quiz = await self.get(quiz_id, offering_id=offering_id)
        await self._require_editable(quiz)
        if not bank_ids:
            return []

        items = list(
            await self.session.scalars(
                select(QuestionBankItem).where(
                    QuestionBankItem.id.in_(bank_ids), QuestionBankItem.deleted_at.is_(None)
                )
            )
        )
        found = {item.id for item in items}
        missing = set(bank_ids) - found
        if missing:
            raise NotFound("یکی از سؤال‌های خواسته‌شده در بانک پیدا نشد.")

        start = (
            await self.session.scalar(
                select(func.count())
                .select_from(QuizQuestion)
                .where(QuizQuestion.quiz_id == quiz_id)
            )
        ) or 0

        # ترتیب ورودی حفظ می‌شود، نه ترتیب دیتابیس.
        by_id = {item.id: item for item in items}
        created: list[QuizQuestion] = []
        for index, bank_id in enumerate(bank_ids):
            item = by_id[bank_id]
            question = QuizQuestion(
                quiz_id=quiz_id,
                bank_id=item.id,
                kind=item.kind,
                body=item.body,
                payload=item.payload,
                explanation=item.explanation,
                points=points,
                sort_order=start + index,
                concept_id=item.concept_id,
            )
            self.session.add(question)
            created.append(question)
            item.usage_count += 1

        await self.session.commit()
        for question in created:
            await self.session.refresh(question)
        return created

    async def pick_random_from_bank(
        self,
        *,
        quiz_id: uuid.UUID,
        offering_id: uuid.UUID,
        count: int,
        course_id: uuid.UUID | None = None,
        category: str | None = None,
        difficulty: int | None = None,
        points: Decimal = Decimal("1"),
    ) -> list[QuizQuestion]:
        """انتخاب تصادفی N سؤال از یک دستهٔ بانک — FR-QUIZ-01.

        تصادف اینجا **واقعاً تصادفی** است و قطعی نیست، برخلاف درهم‌سازی
        ترتیب سؤال‌ها: آنجا هدف بازتولیدپذیری برای یک دانشجو بود، اینجا
        هدف این است که استاد هر بار مجموعهٔ متفاوتی بگیرد.
        """
        if count < 1:
            raise ValidationFailed("تعداد سؤال باید دست‌کم ۱ باشد.")
        quiz = await self.get(quiz_id, offering_id=offering_id)
        await self._require_editable(quiz)

        stmt = select(QuestionBankItem.id).where(QuestionBankItem.deleted_at.is_(None))
        if course_id is not None:
            stmt = stmt.where(QuestionBankItem.course_id == course_id)
        if category:
            stmt = stmt.where(QuestionBankItem.category == category)
        if difficulty is not None:
            stmt = stmt.where(QuestionBankItem.difficulty == difficulty)

        candidates = list(await self.session.scalars(stmt))
        if len(candidates) < count:
            raise Conflict(
                f"این دسته فقط {len(candidates)} سؤال دارد و {count} سؤال خواسته شده است."
            )

        chosen = _sample(candidates, count)
        return await self.copy_from_bank(
            quiz_id=quiz_id, offering_id=offering_id, bank_ids=chosen, points=points
        )

    # ── چالش روزانه — ADR-0036 ─────────────────────────────────────────
    async def create_checkpoint(
        self,
        *,
        offering_id: uuid.UUID,
        created_by: uuid.UUID,
        title_fa: str,
        lesson_id: uuid.UUID | None,
        concept_ids: list[uuid.UUID],
        draw_count: int,
        opens_at: datetime,
        closes_at: datetime,
        duration_min: int,
        publish: bool,
    ) -> Quiz:
        """چالش روزانه: استخر از بانک (مفاهیم انتخابی)، هر تلاش `draw_count` سؤال.

        سؤال‌های استخر **کپی** می‌شوند (نمرهٔ یکسان ۱)؛ ویرایش بعدی بانک چالشِ برگزارشده را
        عوض نمی‌کند. دانشجو آزمونی بی‌نمرهٔ رسمی می‌بیند که فقط XP و شایستگی می‌سازد.
        """
        if not concept_ids:
            raise ValidationFailed("دست‌کم یک مفهوم برای چالش لازم است.")
        if not 1 <= duration_min <= CHECKPOINT_MAX_MINUTES:
            raise ValidationFailed(f"مدت چالش باید بین ۱ تا {CHECKPOINT_MAX_MINUTES} دقیقه باشد.")
        if not 1 <= draw_count <= CHECKPOINT_MAX_QUESTIONS:
            raise ValidationFailed(
                f"تعداد سؤال هر تلاش باید بین ۱ تا {CHECKPOINT_MAX_QUESTIONS} باشد."
            )
        pool = list(
            await self.session.scalars(
                select(QuestionBankItem.id)
                .where(
                    QuestionBankItem.concept_id.in_(concept_ids),
                    QuestionBankItem.deleted_at.is_(None),
                )
                .order_by(QuestionBankItem.id)
                .limit(MAX_QUESTIONS_PER_QUIZ)
            )
        )
        if len(pool) < draw_count:
            raise Conflict(
                f"بانک برای این مفاهیم فقط {len(pool)} سؤال دارد؛ {draw_count} سؤال خواسته شد.",
                code="POOL_TOO_SMALL",
            )
        quiz = await self.create(
            offering_id=offering_id,
            created_by=created_by,
            draft=QuizDraft(
                title_fa=title_fa,
                duration_min=duration_min,
                opens_at=opens_at,
                closes_at=closes_at,
                max_attempts=1,
                passing_score=None,
                result_visibility="AFTER_CLOSE",
                show_correct_answers=True,
                kind="CHECKPOINT",
                lesson_id=lesson_id,
                draw_count=draw_count,
            ),
        )
        await self.copy_from_bank(
            quiz_id=quiz.id, offering_id=offering_id, bank_ids=pool, points=Decimal(1)
        )
        if publish:
            return await self.publish(quiz_id=quiz.id, offering_id=offering_id)
        await self.session.refresh(quiz)
        return quiz

    async def _require_lesson_of(self, lesson_id: uuid.UUID | None, offering_id: uuid.UUID) -> None:
        if lesson_id is None:
            return
        found = await self.session.scalar(
            select(Lesson.id).where(Lesson.id == lesson_id, Lesson.offering_id == offering_id)
        )
        if found is None:
            raise NotFound("درس‌نامهٔ خواسته‌شده در این ارائه نیست.")

    async def _require_valid_pool(self, quiz: Quiz, count: int) -> None:
        """استخر: همهٔ سؤال‌ها نمرهٔ یکسان، و دست‌کم `draw_count` سؤال.

        وگرنه جمع نمرهٔ یک تلاش به سؤال‌هایی که قرعه می‌خورند بستگی می‌داشت و درصد دانشجویان
        قابل‌مقایسه نبود (`quizzes.total_points` برای استخر `draw_count × نمرهٔ هر سؤال` است).
        """
        assert quiz.draw_count is not None
        if count < quiz.draw_count:
            raise Conflict(
                f"استخر {count} سؤال دارد ولی هر تلاش {quiz.draw_count} سؤال می‌گیرد.",
                code="POOL_TOO_SMALL",
            )
        distinct = await self.session.scalar(
            select(func.count(func.distinct(QuizQuestion.points))).where(
                QuizQuestion.quiz_id == quiz.id
            )
        )
        if (distinct or 0) > 1:
            raise Conflict(
                "در آزمونِ دارای استخر، همهٔ سؤال‌ها باید نمرهٔ یکسان داشته باشند.",
                code="POOL_POINTS_MIXED",
            )

    # ── کمکی ───────────────────────────────────────────────────────────
    def _build_question(
        self, quiz_id: uuid.UUID, draft: QuestionDraft, *, fallback_order: int
    ) -> QuizQuestion:
        _validate_question(draft)
        return QuizQuestion(
            quiz_id=quiz_id,
            bank_id=draft.bank_id,
            kind=draft.kind,
            body=draft.body.strip(),
            payload=draft.payload,
            explanation=draft.explanation,
            points=draft.points,
            sort_order=draft.sort_order if draft.sort_order is not None else fallback_order,
        )

    async def _require_question_of(
        self, question_id: uuid.UUID, quiz_id: uuid.UUID
    ) -> QuizQuestion:
        question = await self.session.get(QuizQuestion, question_id)
        if question is None or question.quiz_id != quiz_id:
            raise NotFound("این سؤال پیدا نشد.")
        return question

    async def _require_week_of(self, week_id: uuid.UUID, offering_id: uuid.UUID) -> CourseWeek:
        week = await self.session.get(CourseWeek, week_id)
        if week is None or week.offering_id != offering_id:
            raise NotFound("این هفته پیدا نشد.")
        return week

    async def _has_attempts(self, quiz_id: uuid.UUID) -> bool:
        found = await self.session.scalar(
            select(QuizAttempt.id).where(QuizAttempt.quiz_id == quiz_id).limit(1)
        )
        return found is not None

    async def _require_editable(self, quiz: Quiz) -> None:
        """سؤال‌ها فقط تا پیش از اولین تلاش قابل تغییرند.

        `DRAFT` همیشه قابل ویرایش است چون هنوز به دست دانشجو نرسیده.
        آزمون منتشرشده‌ای که هیچ‌کس شروعش نکرده هم قابل ویرایش می‌ماند —
        استادی که نیم‌ساعت پیش از آزمون غلط تایپی می‌بیند نباید ناچار
        به ساخت آزمون تازه شود.
        """
        if quiz.status == "DRAFT":
            return
        if await self._has_attempts(quiz.id):
            raise QuizHasAttempts()


def _validate_draft(draft: QuizDraft) -> None:
    if not draft.title_fa.strip():
        raise ValidationFailed("عنوان آزمون نمی‌تواند خالی باشد.")
    if draft.closes_at <= draft.opens_at:
        raise ValidationFailed("زمان بسته شدن باید پس از زمان باز شدن باشد.")
    if not 1 <= draft.duration_min <= MAX_DURATION_MIN:
        raise ValidationFailed(f"مدت آزمون باید بین ۱ تا {MAX_DURATION_MIN} دقیقه باشد.")
    if not 1 <= draft.max_attempts <= MAX_ATTEMPTS:
        raise ValidationFailed(f"تعداد تلاش مجاز باید بین ۱ تا {MAX_ATTEMPTS} باشد.")
    if draft.result_visibility not in RESULT_VISIBILITIES:
        raise ValidationFailed("نحوهٔ نمایش نتیجه معتبر نیست.")
    if draft.passing_score is not None and draft.passing_score < 0:
        raise ValidationFailed("نمرهٔ قبولی نمی‌تواند منفی باشد.")
    if draft.kind not in QUIZ_KINDS:
        raise ValidationFailed("نوع آزمون معتبر نیست.")
    if draft.draw_count is not None and not 1 <= draft.draw_count <= 100:
        raise ValidationFailed("اندازهٔ قرعه از استخر باید بین ۱ تا ۱۰۰ باشد.")


def _validate_question(draft: QuestionDraft) -> None:
    if draft.kind not in QUESTION_KINDS:
        raise ValidationFailed("نوع سؤال معتبر نیست.")
    if not draft.body.strip():
        raise ValidationFailed("متن سؤال نمی‌تواند خالی باشد.")
    if draft.points <= 0:
        raise ValidationFailed("بارم سؤال باید مثبت باشد.")
    try:
        validate_payload(draft.kind, draft.payload, points=draft.points)
    except InvalidQuestionPayload as exc:
        # خطای نویسندهٔ سؤال است، پس پیام دقیقش به خودش نشان داده
        # می‌شود — برخلاف خطاهای دانشجو که عمداً کلی‌اند.
        raise ValidationFailed(exc.message) from exc


def _sample(values: list[uuid.UUID], count: int) -> list[uuid.UUID]:
    """نمونهٔ تصادفی امن. `secrets` به‌جای `random` چون انتخاب سؤال
    آزمون نباید از روی دانه قابل پیش‌بینی باشد."""
    pool = list(values)
    chosen: list[uuid.UUID] = []
    for _ in range(count):
        chosen.append(pool.pop(secrets.randbelow(len(pool))))
    return chosen


__all__ = ["MAX_QUESTIONS_PER_QUIZ", "QuestionDraft", "QuizDraft", "QuizService"]
