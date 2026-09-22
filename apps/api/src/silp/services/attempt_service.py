"""برگزاری آزمون — FR-QUIZ-02، §5.6، §7.3.

وظیفه‌های نقشهٔ راه: M4-04 تا M4-08.

**این حساس‌ترین ماژول سامانه است.** چیزی که اینجا اشتباه شود، نمرهٔ یک
دانشجوی واقعی را خراب می‌کند و برخلاف بیشتر باگ‌ها، قابل جبران هم نیست:
آزمون دوباره برگزار نمی‌شود.

سه چیزی که این ماژول **به خودش اجازه نمی‌دهد**:

۱. **به ساعت کلاینت اعتماد کند.** `expires_at` در لحظهٔ شروع، سروری،
   محاسبه و ذخیره می‌شود و بعد از آن عوض نمی‌شود. `client_ts` فقط در
   یک جا اثر دارد: پذیرش پاسخی که پیش از انقضا نوشته شده و شبکه دیر
   رسانده (§7.3 قاعدهٔ ۳) — و آنجا هم سقف سودش ۳۰ ثانیه است.

۲. **به `submit` کلاینت تکیه کند.** کار پس‌زمینهٔ `auto_close_expired`
   هر ۶۰ ثانیه تلاش‌های منقضی را می‌بندد. دانشجویی که لپ‌تاپش خاموش
   شد، پاسخ‌های ذخیره‌شده‌اش تصحیح می‌شود.

۳. **کلید پاسخ را در تلاش فعال بفرستد.** `public_payload` allow-list
   است و `test_correct_answers_never_leak_in_active_attempt` نگهبانش.

قواعد نمره اینجا نیستند: در `silp.domain.quiz.grading` هستند، خالص و
بدون I/O.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from silp.core.exceptions import (
    ActiveAttemptExists,
    AttemptAlreadySubmitted,
    AttemptExpired,
    AttemptsExhausted,
    ConcurrentModification,
    NotFound,
    PermissionDenied,
    QuizClosed,
    QuizNotOpen,
    ValidationFailed,
)
from silp.core.logging import get_logger
from silp.domain.quiz import (
    AUTO_GRADED_KINDS,
    CHOICE_KINDS,
    GradedAnswer,
    Question,
    QuestionKind,
    QuizAvailability,
    accepts_answer,
    availability,
    compute_expires_at,
    grade_attempt,
    needs_manual_grading,
    option_order,
    parse_question,
    public_payload,
    question_order,
    total_auto_score,
)
from silp.models.education import Enrollment
from silp.models.quiz import Quiz, QuizAnswer, QuizAttempt, QuizQuestion
from silp.services import events

log = get_logger("silp.attempt")

ATTEMPT_NO_RETRIES = 3
MAX_SYNC_ANSWERS = 200
MAX_INTEGRITY_EVENTS = 500
INTEGRITY_EVENT_KINDS = ("TAB_BLUR", "WINDOW_RESIZE", "LONG_PASTE", "RECONNECT")


@dataclass(frozen=True, slots=True)
class AttemptStart:
    """پاسخ `POST /quizzes/{id}/attempts` — §5.6."""

    attempt_id: uuid.UUID
    server_time: datetime
    expires_at: datetime
    seconds_remaining: int
    question_count: int
    total_points: Decimal


@dataclass(frozen=True, slots=True)
class VisibleQuestion:
    """سؤال آن‌طور که دانشجوی در حال آزمون می‌بیند — بدون کلید پاسخ."""

    id: uuid.UUID
    kind: str
    body: str
    points: Decimal
    payload: dict[str, Any]
    my_answer: dict[str, Any] | None
    is_flagged: bool


@dataclass(frozen=True, slots=True)
class AttemptView:
    attempt: QuizAttempt
    quiz: Quiz
    server_time: datetime
    seconds_remaining: int
    questions: list[VisibleQuestion]


@dataclass(frozen=True, slots=True)
class SavedAnswer:
    saved_at: datetime
    seconds_remaining: int


@dataclass(frozen=True, slots=True)
class SyncOutcome:
    """نتیجهٔ همگام‌سازی پس از آفلاین — §5.6.

    `accepted` و `rejected` جدا گزارش می‌شوند چون دانشجو حق دارد بداند
    کدام پاسخش نرسید؛ «همه‌اش ذخیره شد» وقتی نشده، بدترین پاسخ ممکن است.
    """

    accepted: list[uuid.UUID]
    rejected: list[uuid.UUID]
    seconds_remaining: int


@dataclass(frozen=True, slots=True)
class SubmitOutcome:
    attempt: QuizAttempt
    auto_score: Decimal
    is_provisional: bool
    graded_count: int


class AttemptService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ── شروع ───────────────────────────────────────────────────────────
    async def start(self, *, quiz_id: uuid.UUID, student_id: uuid.UUID) -> AttemptStart:
        """شروع یک تلاش تازه — §5.6، §7.3."""
        quiz = await self._live_quiz(quiz_id)
        await self._require_enrolled(quiz.offering_id, student_id)

        now = _now()
        used, active = await self._attempt_counts(quiz_id, student_id)
        state = availability(
            now=now,
            opens_at=quiz.opens_at,
            closes_at=quiz.closes_at,
            has_active_attempt=active is not None,
            used_attempts=used,
            max_attempts=quiz.max_attempts,
        )
        match state:
            case QuizAvailability.NOT_OPEN:
                raise QuizNotOpen()
            case QuizAvailability.CLOSED:
                raise QuizClosed()
            case QuizAvailability.IN_PROGRESS:
                raise ActiveAttemptExists(
                    details={"attempt_id": str(active.id)} if active else None
                )
            case QuizAvailability.EXHAUSTED:
                raise AttemptsExhausted()
            case QuizAvailability.AVAILABLE:
                pass

        question_ids = list(
            await self.session.scalars(
                select(QuizQuestion.id)
                .where(QuizQuestion.quiz_id == quiz_id)
                .order_by(QuizQuestion.sort_order, QuizQuestion.id)
            )
        )
        if not question_ids:
            raise NotFound("این آزمون هنوز سؤالی ندارد.")

        expires_at = compute_expires_at(
            started_at=now, duration_min=quiz.duration_min, closes_at=quiz.closes_at
        )
        attempt = await self._insert_with_attempt_no(
            quiz_id=quiz_id,
            student_id=student_id,
            first_no=used + 1,
            started_at=now,
            expires_at=expires_at,
        )
        # ترتیب پس از درج تولید می‌شود چون دانه‌اش شناسهٔ همان تلاش است.
        attempt.question_order = question_order(
            question_ids, attempt_id=attempt.id, shuffle=quiz.shuffle_questions
        )
        await self.session.commit()
        await self.session.refresh(attempt)

        log.info(
            "attempt_started",
            attempt_id=str(attempt.id),
            quiz_id=str(quiz_id),
            attempt_no=attempt.attempt_no,
        )
        return AttemptStart(
            attempt_id=attempt.id,
            server_time=now,
            expires_at=attempt.expires_at,
            seconds_remaining=_remaining(attempt.expires_at, now),
            question_count=len(question_ids),
            total_points=quiz.total_points,
        )

    # ── دیدن ───────────────────────────────────────────────────────────
    async def view(self, *, attempt_id: uuid.UUID, student_id: uuid.UUID) -> AttemptView:
        """سؤال‌ها + پاسخ‌های ذخیره‌شده + زمان باقی — §5.6.

        ترتیب، همانی است که در `question_order` ذخیره شده؛ پس رفرش صفحه
        هیچ چیزی را جابه‌جا نمی‌کند.
        """
        attempt = await self._own_attempt(attempt_id, student_id)
        quiz = await self._quiz_of(attempt)
        now = _now()

        questions = await self._questions_in_order(attempt)
        saved = await self._saved_answers(attempt_id)

        visible: list[VisibleQuestion] = []
        for row in questions:
            parsed = _parse(row)
            order = None
            if quiz.shuffle_options and parsed.kind in CHOICE_KINDS:
                order = option_order(
                    [o.id for o in parsed.options],
                    attempt_id=attempt.id,
                    question_id=row.id,
                    shuffle=True,
                )
            elif quiz.shuffle_options and parsed.kind is QuestionKind.MATCHING:
                order = option_order(
                    [o.id for o in parsed.right_items],
                    attempt_id=attempt.id,
                    question_id=row.id,
                    shuffle=True,
                )
            answer = saved.get(row.id)
            visible.append(
                VisibleQuestion(
                    id=row.id,
                    kind=row.kind,
                    body=row.body,
                    points=row.points,
                    payload=public_payload(parsed, option_order=order),
                    my_answer=answer.response if answer else None,
                    is_flagged=bool(answer.is_flagged) if answer else False,
                )
            )

        return AttemptView(
            attempt=attempt,
            quiz=quiz,
            server_time=now,
            seconds_remaining=_remaining(attempt.expires_at, now),
            questions=visible,
        )

    # ── ذخیرهٔ پاسخ ────────────────────────────────────────────────────
    async def save_answer(
        self,
        *,
        attempt_id: uuid.UUID,
        student_id: uuid.UUID,
        question_id: uuid.UUID,
        response: dict[str, Any] | None,
        is_flagged: bool = False,
        client_ts: datetime | None = None,
    ) -> SavedAnswer:
        """ذخیرهٔ یک پاسخ — بی‌اثر در تکرار (§5.6).

        «بی‌اثر در تکرار» را کلید اصلی `(attempt_id, question_id)` و
        `ON CONFLICT DO UPDATE` می‌سازند، نه منطق اپلیکیشن: ذخیرهٔ
        خودکار هر ۱۰ ثانیه یعنی همان پاسخ ده‌ها بار نوشته می‌شود.
        """
        attempt = await self._own_attempt(attempt_id, student_id)
        self._require_open(attempt)

        now = _now()
        if not accepts_answer(now=now, expires_at=attempt.expires_at, client_ts=client_ts):
            raise AttemptExpired()

        await self._require_question_of_attempt(question_id, attempt)
        await self._upsert_answer(
            attempt_id=attempt_id,
            question_id=question_id,
            response=response,
            is_flagged=is_flagged,
            client_ts=client_ts,
            now=now,
        )
        await self.session.commit()
        return SavedAnswer(saved_at=now, seconds_remaining=_remaining(attempt.expires_at, now))

    async def sync(
        self,
        *,
        attempt_id: uuid.UUID,
        student_id: uuid.UUID,
        answers: list[dict[str, Any]],
    ) -> SyncOutcome:
        """همگام‌سازی دسته‌ای پس از قطعی اینترنت — M4-06، §5.6.

        دو قاعده:

        * **جدیدترین `client_ts` برنده است.** اگر دانشجو در دو دستگاه
          پاسخ داده باشد، آخرین نوشته می‌ماند نه آخرین رسیده.
        * **پاسخ‌های پیش از انقضا ذخیره می‌شوند، حتی اگر مهلت گذشته
          باشد.** این کل هدف این endpoint است: کسی که اینترنتش قطع شد
          نباید کارِ انجام‌شده‌اش را از دست بدهد.
        """
        attempt = await self._own_attempt(attempt_id, student_id)
        if attempt.status not in ("IN_PROGRESS", "SUBMITTED", "AUTO_SUBMITTED"):
            raise AttemptAlreadySubmitted()
        if len(answers) > MAX_SYNC_ANSWERS:
            raise ValidationFailed("تعداد پاسخ‌های همگام‌سازی بیش از حد مجاز است.")

        now = _now()
        valid_ids = {q.id for q in await self._questions_in_order(attempt)}
        existing = await self._saved_answers(attempt_id)

        # جدیدترین نسخهٔ هر سؤال در خودِ دسته — کلاینت آفلاین ممکن است
        # چند نسخه از یک پاسخ را نگه داشته باشد.
        latest: dict[uuid.UUID, dict[str, Any]] = {}
        rejected: list[uuid.UUID] = []
        for item in answers:
            question_id = _as_uuid(item.get("question_id"))
            if question_id is None or question_id not in valid_ids:
                continue
            client_ts = _as_datetime(item.get("client_ts"))
            if not accepts_answer(
                now=now, expires_at=attempt.expires_at, client_ts=client_ts
            ) or not _is_gradeable_after_close(attempt, client_ts):
                rejected.append(question_id)
                continue
            current = latest.get(question_id)
            if current is None or _newer(client_ts, _as_datetime(current.get("client_ts"))):
                latest[question_id] = {**item, "client_ts": client_ts}

        accepted: list[uuid.UUID] = []
        for question_id, item in latest.items():
            client_ts = item.get("client_ts")
            stored = existing.get(question_id)
            # پاسخ ذخیره‌شدهٔ تازه‌تر با نسخهٔ قدیمی‌ترِ آفلاین بازنویسی
            # نمی‌شود.
            if stored is not None and not _newer(client_ts, stored.client_ts):
                rejected.append(question_id)
                continue
            await self._upsert_answer(
                attempt_id=attempt_id,
                question_id=question_id,
                response=item.get("response"),
                is_flagged=bool(item.get("is_flagged", False)),
                client_ts=client_ts,
                now=now,
            )
            accepted.append(question_id)

        await self.session.commit()
        log.info(
            "attempt_synced",
            attempt_id=str(attempt_id),
            accepted=len(accepted),
            rejected=len(rejected),
        )
        return SyncOutcome(
            accepted=accepted,
            rejected=rejected,
            seconds_remaining=_remaining(attempt.expires_at, now),
        )

    # ── ارسال و تصحیح ──────────────────────────────────────────────────
    async def submit(self, *, attempt_id: uuid.UUID, student_id: uuid.UUID) -> SubmitOutcome:
        """ارسال نهایی توسط دانشجو — §5.6."""
        attempt = await self._own_attempt(attempt_id, student_id)
        if attempt.status != "IN_PROGRESS":
            raise AttemptAlreadySubmitted()
        return await self._finish(attempt, status="SUBMITTED", now=_now())

    async def auto_close_expired(self, *, limit: int = 200) -> int:
        """بستن خودکار تلاش‌های منقضی — M4-07، §7.3 قاعدهٔ ۲.

        **بی‌اثر در تکرار:** هر تلاش با `UPDATE ... WHERE status =
        'IN_PROGRESS'` گرفته می‌شود، پس دو اجرای هم‌زمان کار یکدیگر را
        دوباره انجام نمی‌دهند و یک تلاش دو بار تصحیح نمی‌شود.
        """
        now = _now()
        due = list(
            await self.session.scalars(
                select(QuizAttempt)
                .where(QuizAttempt.status == "IN_PROGRESS", QuizAttempt.expires_at <= now)
                .order_by(QuizAttempt.expires_at)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        )
        closed = 0
        for attempt in due:
            await self._finish(attempt, status="AUTO_SUBMITTED", now=now)
            closed += 1
        if closed:
            log.info("attempts_auto_closed", count=closed)
        return closed

    async def _finish(self, attempt: QuizAttempt, *, status: str, now: datetime) -> SubmitOutcome:
        """تصحیح خودکار و بستن یک تلاش — §7.3."""
        rows = await self._questions_in_order(attempt)
        parsed = [_parse(row) for row in rows]
        saved = await self._saved_answers(attempt.id)
        responses = {str(qid): answer.response for qid, answer in saved.items()}

        graded = grade_attempt(parsed, responses)
        await self._write_answer_scores(attempt, rows, graded, now=now)

        auto = total_auto_score(graded)
        provisional = needs_manual_grading(graded)

        # §7.3: هر دو مسیرِ ارسال به `GRADED` می‌رسند و «موقت بودن» را
        # `is_provisional` می‌گوید، نه وضعیت. ولی «زمانم تمام شد» با
        # «ارسال کردم» یکی نیست و پس از این نقطه از `status` قابل
        # بازیابی نیست — پس صریح ثبت می‌شود (ADR-0011).
        attempt.auto_closed = status == "AUTO_SUBMITTED"
        attempt.status = "GRADED"
        attempt.submitted_at = attempt.submitted_at or now
        attempt.graded_at = now
        attempt.auto_score = auto
        attempt.total_score = auto
        attempt.is_provisional = provisional
        if attempt.auto_closed:
            log.info("attempt_auto_submitted", attempt_id=str(attempt.id))

        await events.publish(self.session, events.QuizGraded(attempt_id=attempt.id))
        await self.session.commit()
        await self.session.refresh(attempt)
        return SubmitOutcome(
            attempt=attempt,
            auto_score=auto,
            is_provisional=provisional,
            graded_count=len(graded),
        )

    async def _write_answer_scores(
        self,
        attempt: QuizAttempt,
        rows: list[QuizQuestion],
        graded: dict[str, GradedAnswer],
        *,
        now: datetime,
    ) -> None:
        """نمرهٔ هر سؤال روی ردیف پاسخ نوشته می‌شود.

        سؤال بی‌پاسخ هم ردیف می‌گیرد: «بی‌پاسخ، صفر» یک واقعیت است و
        در کارنامه باید دیده شود. بدون ردیف، صفحهٔ نتیجه نمی‌تواند بین
        «نرسیدم» و «سؤال وجود نداشت» فرق بگذارد.
        """
        for row in rows:
            result = graded.get(str(row.id))
            if result is None:  # pragma: no cover
                continue
            auto = result.score if row.kind in AUTO_GRADED_KINDS else None
            await self.session.execute(
                insert(QuizAnswer)
                .values(
                    attempt_id=attempt.id,
                    question_id=row.id,
                    response=None,
                    auto_score=auto,
                    answered_at=now,
                )
                .on_conflict_do_update(
                    index_elements=["attempt_id", "question_id"],
                    set_={"auto_score": auto},
                )
            )

    # ── تمامیت — FR-QUIZ-05 ────────────────────────────────────────────
    async def record_integrity_event(
        self,
        *,
        attempt_id: uuid.UUID,
        student_id: uuid.UUID,
        kind: str,
        detail: dict[str, Any] | None = None,
    ) -> int:
        """ثبت رویداد مشکوک — M4-14.

        **این رویدادها تقلب نیستند، گزارش‌اند.** §02 صریح است: تصمیم با
        استاد است. پس ثبتشان هیچ اثری بر وضعیت تلاش یا نمره ندارد و
        هرگز نباید داشته باشد.
        """
        if kind not in INTEGRITY_EVENT_KINDS:
            raise ValidationFailed("نوع رویداد شناخته نیست.")
        attempt = await self._own_attempt(attempt_id, student_id)

        events = list(attempt.integrity_events or [])
        if len(events) >= MAX_INTEGRITY_EVENTS:
            # سقف دارد تا یک کلاینت پرحرف ردیف را بی‌نهایت بزرگ نکند.
            return len(events)
        events.append({"kind": kind, "at": _now().isoformat(), "detail": detail or {}})
        attempt.integrity_events = events
        await self.session.commit()
        return len(events)

    # ── کمکی ───────────────────────────────────────────────────────────
    async def _live_quiz(self, quiz_id: uuid.UUID) -> Quiz:
        quiz = await self.session.get(Quiz, quiz_id)
        if quiz is None or not quiz.is_live:
            raise NotFound("این آزمون پیدا نشد.")
        return quiz

    async def _quiz_of(self, attempt: QuizAttempt) -> Quiz:
        quiz = await self.session.get(Quiz, attempt.quiz_id)
        if quiz is None:  # pragma: no cover — کلید خارجی تضمینش می‌کند
            raise NotFound("این آزمون پیدا نشد.")
        return quiz

    async def _own_attempt(self, attempt_id: uuid.UUID, student_id: uuid.UUID) -> QuizAttempt:
        attempt = await self.session.get(QuizAttempt, attempt_id)
        # تلاش کس دیگر، «پیدا نشد» است نه «اجازه نداری» — §6.4 قاعدهٔ ۴.
        if attempt is None or attempt.student_id != student_id:
            raise NotFound("این تلاش پیدا نشد.")
        if attempt.status == "VOIDED":
            raise PermissionDenied("این تلاش باطل شده است.")
        return attempt

    def _require_open(self, attempt: QuizAttempt) -> None:
        if not attempt.accepts_answers:
            raise AttemptAlreadySubmitted()

    async def _require_enrolled(self, offering_id: uuid.UUID, student_id: uuid.UUID) -> None:
        """آزمون فقط برای دانشجوی همین ارائه — اشتراک اینجا کاری نمی‌کند.

        ADR-0009: سطح `ENROLLED` فروختنی نیست. آزمون نمره‌دار دقیقاً
        همان چیزی است که آن قاعده برایش نوشته شد.
        """
        enrollment = await self.session.scalar(
            select(Enrollment).where(
                Enrollment.offering_id == offering_id, Enrollment.student_id == student_id
            )
        )
        if enrollment is None or not enrollment.is_active:
            raise PermissionDenied("برای شرکت در این آزمون باید در درس ثبت‌نام کرده باشید.")

    async def _attempt_counts(
        self, quiz_id: uuid.UUID, student_id: uuid.UUID
    ) -> tuple[int, QuizAttempt | None]:
        """(تعداد تلاش مصرف‌شده، تلاش فعال اگر هست).

        تلاش `VOIDED` از شمارش بیرون است: ابطال توسط استاد نباید دفعهٔ
        دانشجو را بسوزاند.
        """
        rows = list(
            await self.session.scalars(
                select(QuizAttempt).where(
                    QuizAttempt.quiz_id == quiz_id, QuizAttempt.student_id == student_id
                )
            )
        )
        counted = [row for row in rows if row.status != "VOIDED"]
        active = next((row for row in counted if row.is_active), None)
        return len(counted), active

    async def _insert_with_attempt_no(
        self,
        *,
        quiz_id: uuid.UUID,
        student_id: uuid.UUID,
        first_no: int,
        started_at: datetime,
        expires_at: datetime,
    ) -> QuizAttempt:
        """§7.12 — قید یکتا + تلاش مجدد، نه `MAX(attempt_no) + 1` خام.

        دو قید ممکن است بشکنند و معنایشان فرق دارد:

        * `uq_quiz_attempts_…_attempt_no` — کس دیگری شماره را گرفت؛
          شماره را تازه می‌کنیم و دوباره.
        * `idx_one_active_attempt` — همین دانشجو تلاش فعال دارد؛ تلاش
          مجدد کمکی نمی‌کند و باید `409` برگردد.
        """
        attempt_no = first_no
        for retry in range(ATTEMPT_NO_RETRIES):
            attempt = QuizAttempt(
                quiz_id=quiz_id,
                student_id=student_id,
                attempt_no=attempt_no,
                status="IN_PROGRESS",
                started_at=started_at,
                expires_at=expires_at,
            )
            try:
                async with self.session.begin_nested():
                    self.session.add(attempt)
                    await self.session.flush()
            except IntegrityError as exc:
                if _is_active_attempt_clash(exc):
                    raise ActiveAttemptExists from None
                if retry == ATTEMPT_NO_RETRIES - 1:
                    raise ConcurrentModification from None
                highest = await self.session.scalar(
                    select(func.max(QuizAttempt.attempt_no)).where(
                        QuizAttempt.quiz_id == quiz_id, QuizAttempt.student_id == student_id
                    )
                )
                attempt_no = (highest or 0) + 1
                continue
            return attempt
        raise ConcurrentModification  # pragma: no cover

    async def _questions_in_order(self, attempt: QuizAttempt) -> list[QuizQuestion]:
        """سؤال‌ها با ترتیب ذخیره‌شدهٔ همین تلاش.

        سؤالی که پس از شروع تلاش به آزمون افزوده شده، در
        `question_order` نیست و به این دانشجو نشان داده **نمی‌شود** —
        و در تصحیحش هم نمی‌آید. دیدن سؤالی که وقتش گذشته بدتر از
        ندیدنش است.
        """
        rows = list(
            await self.session.scalars(
                select(QuizQuestion).where(QuizQuestion.quiz_id == attempt.quiz_id)
            )
        )
        if not attempt.question_order:
            return sorted(rows, key=lambda r: (r.sort_order, str(r.id)))
        by_id = {row.id: row for row in rows}
        return [by_id[qid] for qid in attempt.question_order if qid in by_id]

    async def _saved_answers(self, attempt_id: uuid.UUID) -> dict[uuid.UUID, QuizAnswer]:
        rows = await self.session.scalars(
            select(QuizAnswer).where(QuizAnswer.attempt_id == attempt_id)
        )
        return {row.question_id: row for row in rows}

    async def _require_question_of_attempt(
        self, question_id: uuid.UUID, attempt: QuizAttempt
    ) -> None:
        if attempt.question_order and question_id not in attempt.question_order:
            raise NotFound("این سؤال در آزمون شما نیست.")
        exists = await self.session.scalar(
            select(QuizQuestion.id).where(
                QuizQuestion.id == question_id, QuizQuestion.quiz_id == attempt.quiz_id
            )
        )
        if exists is None:
            raise NotFound("این سؤال در آزمون شما نیست.")

    async def _upsert_answer(
        self,
        *,
        attempt_id: uuid.UUID,
        question_id: uuid.UUID,
        response: dict[str, Any] | None,
        is_flagged: bool,
        client_ts: datetime | None,
        now: datetime,
    ) -> None:
        await self.session.execute(
            insert(QuizAnswer)
            .values(
                attempt_id=attempt_id,
                question_id=question_id,
                response=response,
                is_flagged=is_flagged,
                client_ts=client_ts,
                answered_at=now,
            )
            .on_conflict_do_update(
                index_elements=["attempt_id", "question_id"],
                set_={
                    "response": response,
                    "is_flagged": is_flagged,
                    "client_ts": client_ts,
                    "answered_at": now,
                },
            )
        )


# ── توابع کمکی ماژول ───────────────────────────────────────────────────


def _now() -> datetime:
    return datetime.now(UTC)


def _remaining(expires_at: datetime, now: datetime) -> int:
    return max(0, int((expires_at - now).total_seconds()))


def _parse(row: QuizQuestion) -> Question:
    return parse_question(
        question_id=str(row.id), kind=row.kind, points=row.points, payload=row.payload
    )


def _as_uuid(value: Any) -> uuid.UUID | None:
    if isinstance(value, uuid.UUID):
        return value
    if isinstance(value, str):
        try:
            return uuid.UUID(value)
        except ValueError:
            return None
    return None


def _as_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return None


def _newer(candidate: datetime | None, current: datetime | None) -> bool:
    """آیا `candidate` تازه‌تر از `current` است؟

    نبودِ `client_ts` یعنی ادعایی دربارهٔ زمان وجود ندارد، پس نمی‌تواند
    چیزی را که زمان دارد کنار بزند.
    """
    if candidate is None:
        return current is None
    if current is None:
        return True
    return candidate > current


def _is_gradeable_after_close(attempt: QuizAttempt, client_ts: datetime | None) -> bool:
    """پس از بسته شدن تلاش، فقط پاسخ‌های پیش از انقضا پذیرفته می‌شوند."""
    if attempt.status == "IN_PROGRESS":
        return True
    return client_ts is not None and client_ts < attempt.expires_at


def _is_active_attempt_clash(exc: IntegrityError) -> bool:
    return "idx_one_active_attempt" in str(exc.orig)


__all__ = [
    "AttemptService",
    "AttemptStart",
    "AttemptView",
    "SavedAnswer",
    "SubmitOutcome",
    "SyncOutcome",
    "VisibleQuestion",
]
