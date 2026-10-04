"""مدل‌های Pydantic برای /quizzes و /attempts — قرارداد §5.6.

قاعدهٔ حاکم بر این فایل، همان قاعدهٔ §5.5 است: **کلاینت هیچ منطقی را
بازتولید نمی‌کند.** وضعیت آزمون، متن فارسی‌اش، زمان باقی‌مانده و اینکه
دکمهٔ «شروع» فعال باشد یا نه، همه از سرور می‌آیند.

برای زمان، دلیلش فراتر از سلیقه است: اگر کلاینت `expires_at` را با
ساعت خودش مقایسه کند، دانشجویی که ساعت سیستمش عقب است وقت اضافه
می‌بیند و دانشجویی که جلوست زودتر بیرون می‌افتد. پس هر پاسخِ مربوط به
تلاش، `server_time` و `seconds_remaining` را با هم می‌دهد؛ کلاینت فقط
شمارش معکوس را نمایش می‌دهد (§5.6، FR-QUIZ-02).

**هیچ اسکیمایی در این فایل کلید پاسخ ندارد** مگر `QuestionReviewOut`
که فقط پس از انتشار نتیجه ساخته می‌شود.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

QuestionKindOut = Literal[
    "SINGLE_CHOICE",
    "MULTI_CHOICE",
    "TRUE_FALSE",
    "SHORT_ANSWER",
    "NUMERIC",
    "ESSAY",
    "MATCHING",
]
QuizStatus = Literal["DRAFT", "PUBLISHED", "CLOSED"]
ResultVisibility = Literal["IMMEDIATE", "AFTER_CLOSE", "MANUAL"]
AttemptStatus = Literal["IN_PROGRESS", "SUBMITTED", "AUTO_SUBMITTED", "GRADED", "VOIDED"]
AvailabilityOut = Literal["NOT_OPEN", "AVAILABLE", "IN_PROGRESS", "EXHAUSTED", "CLOSED"]
AppealStatus = Literal["OPEN", "ACCEPTED", "REJECTED"]
IntegrityEventKind = Literal["TAB_BLUR", "WINDOW_RESIZE", "LONG_PASTE", "RECONNECT"]

MAX_TITLE = 200
MAX_BODY = 4000
MAX_REASON = 1000
MAX_FEEDBACK = 1000


# ── آزمون از دید دانشجو ────────────────────────────────────────────────
class QuizSummaryOut(BaseModel):
    """فراداده — **بدون سؤالات** (§5.6)."""

    id: uuid.UUID
    title_fa: str
    description: str | None = None
    week_number: int | None = None
    duration_min: int
    opens_at: datetime
    closes_at: datetime
    max_attempts: int
    total_points: Decimal
    question_count: int
    passing_score: Decimal | None = None

    # وضعیت و متنش هر دو از سرور — کلاینت جدول §7.3 را بازنمی‌سازد.
    state: AvailabilityOut
    state_fa: str
    server_time: datetime
    used_attempts: int
    active_attempt_id: uuid.UUID | None = None
    # چقدر وقت واقعی باقی است اگر همین حالا شروع کند؟ ممکن است از
    # `duration_min` کمتر باشد — ADR-0011 مسئلهٔ ۳.
    effective_duration_sec: int | None = None


class AttemptStartOut(BaseModel):
    attempt_id: uuid.UUID
    server_time: datetime
    expires_at: datetime
    seconds_remaining: int
    question_count: int
    total_points: Decimal


class VisibleQuestionOut(BaseModel):
    """سؤال در تلاش فعال — `payload` هرگز کلید پاسخ ندارد (§5.6)."""

    id: uuid.UUID
    kind: QuestionKindOut
    kind_fa: str
    body: str
    points: Decimal
    payload: dict[str, Any]
    my_answer: dict[str, Any] | None = None
    is_flagged: bool = False


class AttemptViewOut(BaseModel):
    attempt_id: uuid.UUID
    quiz_id: uuid.UUID
    quiz_title_fa: str
    status: AttemptStatus
    server_time: datetime
    expires_at: datetime
    seconds_remaining: int
    total_points: Decimal
    questions: list[VisibleQuestionOut]


class SaveAnswerIn(BaseModel):
    response: dict[str, Any] | None = None
    is_flagged: bool = False
    # ادعای کلاینت دربارهٔ زمان نوشتن — فقط برای پذیرش پاسخ دیررسیده
    # به کار می‌رود (§7.3 قاعدهٔ ۳) و هرگز جای ساعت سرور را نمی‌گیرد.
    client_ts: datetime | None = None


class SaveAnswerOut(BaseModel):
    saved_at: datetime
    seconds_remaining: int


class SyncAnswerIn(BaseModel):
    question_id: uuid.UUID
    response: dict[str, Any] | None = None
    is_flagged: bool = False
    client_ts: datetime | None = None


class SyncIn(BaseModel):
    answers: Annotated[list[SyncAnswerIn], Field(max_length=200)]


class SyncOut(BaseModel):
    accepted: list[uuid.UUID]
    rejected: list[uuid.UUID]
    seconds_remaining: int


class SubmitIn(BaseModel):
    # کلاینت تعداد بی‌پاسخ را تأیید می‌کند — §5.6. سرور به آن اعتماد
    # نمی‌کند، فقط در لاگ می‌نشیند تا «فکر می‌کردم همه را زده‌ام» قابل
    # بررسی باشد.
    confirm_unanswered: int = 0


class SubmitOut(BaseModel):
    status: AttemptStatus
    auto_score: Decimal
    is_provisional: bool
    total_points: Decimal
    result_available: bool


class IntegrityEventIn(BaseModel):
    kind: IntegrityEventKind
    detail: dict[str, Any] | None = None


class IntegrityEventOut(BaseModel):
    recorded: int


# ── نتیجه — FR-QUIZ-04 ─────────────────────────────────────────────────
class QuestionReviewOut(BaseModel):
    """کلید پاسخ و توضیح — **فقط** پس از انتشار نتیجه."""

    correct: Any = None
    accepted: list[str] | None = None
    tolerance: str | None = None
    explanation: str | None = None


class ResultQuestionOut(BaseModel):
    id: uuid.UUID
    kind: QuestionKindOut
    kind_fa: str
    body: str
    points: Decimal
    score: Decimal | None = None
    is_correct: bool | None = None
    my_answer: dict[str, Any] | None = None
    feedback: str | None = None
    review: QuestionReviewOut | None = None


class AttemptResultOut(BaseModel):
    attempt_id: uuid.UUID
    quiz_id: uuid.UUID
    quiz_title_fa: str
    attempt_no: int
    status: AttemptStatus
    submitted_at: datetime | None = None
    total_score: Decimal | None = None
    total_points: Decimal
    is_provisional: bool
    # ADR-0011 مسئلهٔ ۵ — «زمانت تمام شد» با «ارسال کردی» یکی نیست.
    auto_closed: bool = False
    passed: bool | None = None
    # میانگین کلاس زیر آستانهٔ حریم خصوصی `null` می‌ماند.
    class_average: Decimal | None = None
    cohort_size: int = 0
    questions: list[ResultQuestionOut]


# ── اعتراض — §7.3 ──────────────────────────────────────────────────────
class AppealIn(BaseModel):
    reason: Annotated[str, Field(min_length=1, max_length=MAX_REASON)]
    question_id: uuid.UUID | None = None


class AppealOut(BaseModel):
    id: uuid.UUID
    attempt_id: uuid.UUID
    question_id: uuid.UUID | None = None
    status: AppealStatus
    status_fa: str
    reason: str
    response: str | None = None
    created_at: datetime
    resolved_at: datetime | None = None


class AppealDecisionIn(BaseModel):
    accept: bool
    response: Annotated[str, Field(min_length=1, max_length=MAX_FEEDBACK)]
    new_score: Decimal | None = None


# ── ناحیهٔ استاد — §5.11 ───────────────────────────────────────────────
class QuizIn(BaseModel):
    title_fa: Annotated[str, Field(min_length=1, max_length=MAX_TITLE)]
    duration_min: Annotated[int, Field(ge=1, le=300)]
    opens_at: datetime
    closes_at: datetime
    week_id: uuid.UUID | None = None
    description: Annotated[str | None, Field(max_length=MAX_BODY)] = None
    max_attempts: Annotated[int, Field(ge=1, le=10)] = 1
    passing_score: Decimal | None = None
    shuffle_questions: bool = True
    shuffle_options: bool = True
    result_visibility: ResultVisibility = "AFTER_CLOSE"
    show_correct_answers: bool = True
    kind: Literal["EXAM", "QUIZ", "CHECKPOINT"] = "QUIZ"
    lesson_id: uuid.UUID | None = None
    draw_count: Annotated[int | None, Field(ge=1, le=100)] = None


class QuestionIn(BaseModel):
    kind: QuestionKindOut
    body: Annotated[str, Field(min_length=1, max_length=MAX_BODY)]
    payload: dict[str, Any]
    points: Decimal = Decimal("1")
    explanation: Annotated[str | None, Field(max_length=MAX_BODY)] = None
    sort_order: int | None = None


class QuestionOut(BaseModel):
    """سؤال از دید استاد — اینجا `payload` کلید پاسخ **دارد**."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: QuestionKindOut
    kind_fa: str
    body: str
    payload: dict[str, Any]
    explanation: str | None = None
    points: Decimal
    sort_order: int
    bank_id: uuid.UUID | None = None


class QuizDetailOut(BaseModel):
    """آزمون از دید استاد — با سؤال‌ها و کلید پاسخ."""

    id: uuid.UUID
    offering_id: uuid.UUID
    week_id: uuid.UUID | None = None
    title_fa: str
    description: str | None = None
    duration_min: int
    opens_at: datetime
    closes_at: datetime
    max_attempts: int
    passing_score: Decimal | None = None
    shuffle_questions: bool
    shuffle_options: bool
    result_visibility: ResultVisibility
    result_visibility_fa: str
    show_correct_answers: bool
    status: QuizStatus
    status_fa: str
    total_points: Decimal
    results_published_at: datetime | None = None
    attempt_count: int = 0
    kind: Literal["EXAM", "QUIZ", "CHECKPOINT"] = "QUIZ"
    lesson_id: uuid.UUID | None = None
    draw_count: int | None = None
    questions: list[QuestionOut] = Field(default_factory=list)


class ReorderIn(BaseModel):
    question_ids: list[uuid.UUID]


class BankItemIn(BaseModel):
    kind: QuestionKindOut
    body: Annotated[str, Field(min_length=1, max_length=MAX_BODY)]
    payload: dict[str, Any]
    explanation: Annotated[str | None, Field(max_length=MAX_BODY)] = None
    course_id: uuid.UUID | None = None
    category: Annotated[str | None, Field(max_length=MAX_TITLE)] = None
    difficulty: Annotated[int | None, Field(ge=1, le=5)] = None
    concept_id: uuid.UUID | None = None


class BankItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: QuestionKindOut
    kind_fa: str
    body: str
    payload: dict[str, Any] = Field(default_factory=dict)
    """کلید پاسخ هم هست؛ بانک فقط برای صاحبش خوانده می‌شود."""
    explanation: str | None = None
    course_id: uuid.UUID | None = None
    category: str | None = None
    difficulty: int | None = None
    concept_id: uuid.UUID | None = None
    usage_count: int


class CopyFromBankIn(BaseModel):
    bank_ids: Annotated[list[uuid.UUID], Field(min_length=1, max_length=100)]
    points: Decimal = Decimal("1")


class PickRandomIn(BaseModel):
    count: Annotated[int, Field(ge=1, le=100)]
    course_id: uuid.UUID | None = None
    category: str | None = None
    difficulty: Annotated[int | None, Field(ge=1, le=5)] = None
    points: Decimal = Decimal("1")


# ── صف تصحیح — M4-10 ───────────────────────────────────────────────────
class PendingAnswerOut(BaseModel):
    attempt_id: uuid.UUID
    question_id: uuid.UUID
    student_name: str
    attempt_no: int
    response: dict[str, Any] | None = None
    points: Decimal


class GradingQueueOut(BaseModel):
    question_id: uuid.UUID
    body: str
    points: Decimal
    rubric: str | None = None
    graded_count: int
    pending: list[PendingAnswerOut]


class GradeAnswerIn(BaseModel):
    score: Decimal
    feedback: Annotated[str | None, Field(max_length=MAX_FEEDBACK)] = None


class GradedAnswerOut(BaseModel):
    attempt_id: uuid.UUID
    question_id: uuid.UUID
    score: Decimal
    feedback: str | None = None
    attempt_total: Decimal | None = None
    attempt_is_provisional: bool


# ── تحلیل سؤال — M4-13 ─────────────────────────────────────────────────
class QuestionStatsOut(BaseModel):
    question_id: uuid.UUID
    body: str
    kind: QuestionKindOut
    points: Decimal
    answered: int
    # میانگین نسبت نمره به بارم. بالا یعنی آسان.
    difficulty: Decimal | None = None
    # اختلاف گروه قوی و ضعیف. نزدیک صفر یعنی سؤال تمیز نمی‌دهد.
    discrimination: Decimal | None = None
    note_fa: str | None = None


class OptionStatOut(BaseModel):
    """توزیع یک گزینه — ADR-0028. فقط برای استاد؛ `is_correct` کلید را لو می‌دهد."""

    option_id: str
    text: str
    is_correct: bool
    chosen: int
    # سهم از همهٔ تلاش‌ها (۰ تا ۱).
    share: float
    # سهم در ۲۷٪ بالا و پایین؛ زیر ده تلاش null.
    top_share: float | None = None
    bottom_share: float | None = None
    note_fa: str | None = None


class ItemAnalysisOut(BaseModel):
    """تحلیل پیشرفتهٔ یک سؤال: همان آمار M4-13 + همبستگی با بقیه + گزینه‌ها."""

    question_id: uuid.UUID
    body: str
    kind: QuestionKindOut
    points: Decimal
    answered: int
    difficulty: Decimal | None = None
    discrimination: Decimal | None = None
    # همبستگی پیرسون با نمرهٔ بقیهٔ آزمون (−۱ تا ۱)؛ زیر ده تلاش null.
    item_rest: float | None = None
    note_fa: str | None = None
    options: list[OptionStatOut] = Field(default_factory=list)


class ScoreSummaryOut(BaseModel):
    n: int
    mean_percent: float
    median_percent: float
    sd_percent: float | None = None
    min_percent: float
    max_percent: float
    # ۱۰ سطل ۱۰٪ی از صفر تا صد.
    histogram: list[int]


class ReliabilityOut(BaseModel):
    alpha: float
    sem_percent: float
    label_fa: str
    advice_fa: str | None = None


class QuizAnalyticsOut(BaseModel):
    """تحلیل کل آزمون — ADR-0028."""

    summary: ScoreSummaryOut | None = None
    reliability: ReliabilityOut | None = None
    items: list[ItemAnalysisOut]


class AttemptSummaryOut(BaseModel):
    """یک تلاش در فهرست استاد."""

    id: uuid.UUID
    student_id: uuid.UUID
    student_name: str
    attempt_no: int
    status: AttemptStatus
    status_fa: str
    submitted_at: datetime | None = None
    total_score: Decimal | None = None
    is_provisional: bool
    auto_closed: bool
    integrity_event_count: int = 0


__all__ = [
    "AppealDecisionIn",
    "AppealIn",
    "AppealOut",
    "AttemptResultOut",
    "AttemptStartOut",
    "AttemptSummaryOut",
    "AttemptViewOut",
    "BankItemIn",
    "BankItemOut",
    "CopyFromBankIn",
    "GradeAnswerIn",
    "GradedAnswerOut",
    "GradingQueueOut",
    "IntegrityEventIn",
    "IntegrityEventOut",
    "ItemAnalysisOut",
    "OptionStatOut",
    "PendingAnswerOut",
    "PickRandomIn",
    "QuestionIn",
    "QuestionOut",
    "QuestionReviewOut",
    "QuestionStatsOut",
    "QuizAnalyticsOut",
    "QuizDetailOut",
    "QuizIn",
    "QuizSummaryOut",
    "ReliabilityOut",
    "ReorderIn",
    "ResultQuestionOut",
    "SaveAnswerIn",
    "SaveAnswerOut",
    "ScoreSummaryOut",
    "SubmitIn",
    "SubmitOut",
    "SyncAnswerIn",
    "SyncIn",
    "SyncOut",
    "VisibleQuestionOut",
]
