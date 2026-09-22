"""مدل‌های آزمون — PRD §4.5.

جداول: quizzes، question_bank، quiz_questions، quiz_attempts،
quiz_answers، grade_appeals. مهاجرت متناظر: 0007_quiz.

سه قاعده در این ماژول **تعریف نمی‌شوند، فقط بازتاب داده می‌شوند** —
جایشان دیتابیس است چون تحت رقابت‌اند (§7.12):

* یک تلاش فعال در هر لحظه → `idx_one_active_attempt`
* `attempt_no` بدون تصادم → قید یکتا + تلاش مجدد
* `quizzes.total_points` → تریگر روی `quiz_questions`

قواعد نمره اینجا هم نیستند: در `silp.domain.quiz` هستند، بدون I/O.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from silp.db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin

QUESTION_KINDS = (
    "SINGLE_CHOICE",
    "MULTI_CHOICE",
    "TRUE_FALSE",
    "SHORT_ANSWER",
    "NUMERIC",
    "ESSAY",
    "MATCHING",
)
QUIZ_STATUSES = ("DRAFT", "PUBLISHED", "CLOSED")
RESULT_VISIBILITIES = ("IMMEDIATE", "AFTER_CLOSE", "MANUAL")
ATTEMPT_STATUSES = ("IN_PROGRESS", "SUBMITTED", "AUTO_SUBMITTED", "GRADED", "VOIDED")
APPEAL_STATUSES = ("OPEN", "ACCEPTED", "REJECTED")

#: تلاش‌هایی که دیگر پاسخ نمی‌پذیرند ولی هنوز نمره‌شان نهایی نیست.
SUBMITTED_STATUSES = ("SUBMITTED", "AUTO_SUBMITTED")

RESULT_VISIBILITY_TITLE_FA: dict[str, str] = {
    "IMMEDIATE": "بلافاصله پس از ارسال",
    "AFTER_CLOSE": "پس از پایان مهلت آزمون",
    "MANUAL": "هر وقت استاد منتشر کند",
}

QUIZ_STATUS_TITLE_FA: dict[str, str] = {
    "DRAFT": "پیش‌نویس",
    "PUBLISHED": "منتشرشده",
    "CLOSED": "بسته‌شده",
}

ATTEMPT_STATUS_TITLE_FA: dict[str, str] = {
    "IN_PROGRESS": "در جریان",
    "SUBMITTED": "ارسال‌شده",
    "AUTO_SUBMITTED": "خودکار بسته‌شده",
    "GRADED": "تصحیح‌شده",
    "VOIDED": "باطل‌شده",
}

APPEAL_STATUS_TITLE_FA: dict[str, str] = {
    "OPEN": "در انتظار رسیدگی",
    "ACCEPTED": "پذیرفته‌شده",
    "REJECTED": "رد‌شده",
}

MAX_DURATION_MIN = 300
MAX_ATTEMPTS = 10


def _in_list(column: str, values: tuple[str, ...]) -> str:
    joined = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({joined})"


class Quiz(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """یک آزمون از یک ارائه — FR-QUIZ-01."""

    __tablename__ = "quizzes"

    offering_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("course_offerings.id", ondelete="CASCADE"),
        nullable=False,
    )
    week_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("course_weeks.id", ondelete="SET NULL")
    )
    title_fa: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    duration_min: Mapped[int] = mapped_column(Integer, nullable=False)
    opens_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closes_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    passing_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    shuffle_questions: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    shuffle_options: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    result_visibility: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'AFTER_CLOSE'")
    )
    show_correct_answers: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'DRAFT'"))
    # مشتق — تریگر `sync_quiz_total_points` نگهش می‌دارد. هرگز از پایتون
    # نوشته نمی‌شود؛ نوشتنش یعنی دو منبع حقیقت.
    total_points: Mapped[Decimal] = mapped_column(
        Numeric(6, 2), nullable=False, server_default=text("0")
    )
    results_published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id")
    )

    questions: Mapped[list[QuizQuestion]] = relationship(
        back_populates="quiz",
        cascade="all, delete-orphan",
        order_by="QuizQuestion.sort_order",
    )

    __table_args__ = (
        CheckConstraint("closes_at > opens_at", name="window"),
        CheckConstraint(f"duration_min BETWEEN 1 AND {MAX_DURATION_MIN}", name="duration_range"),
        CheckConstraint(f"max_attempts BETWEEN 1 AND {MAX_ATTEMPTS}", name="max_attempts_range"),
        CheckConstraint(
            "passing_score IS NULL OR passing_score >= 0", name="passing_score_positive"
        ),
        CheckConstraint(
            _in_list("result_visibility", RESULT_VISIBILITIES), name="result_visibility_valid"
        ),
        CheckConstraint(_in_list("status", QUIZ_STATUSES), name="status_valid"),
        Index("idx_quizzes_offering", "offering_id", "status"),
        Index("idx_quizzes_week", "week_id", postgresql_where=text("week_id IS NOT NULL")),
        Index(
            "idx_quizzes_open_window",
            "closes_at",
            postgresql_where=text("status = 'PUBLISHED'"),
        ),
    )

    @property
    def is_live(self) -> bool:
        """آیا دانشجو اصلاً می‌تواند این آزمون را ببیند؟

        «منتشرشده» کافی نیست — پیش‌نویس و آزمون حذف‌شده هم نباید در
        فهرست دانشجو بیایند. پنجرهٔ زمانی جداگانه در `timing.availability`
        سنجیده می‌شود، چون به «حالا» نیاز دارد و این نباید ساعت بخواند.
        """
        return self.status in ("PUBLISHED", "CLOSED") and self.deleted_at is None


class QuestionBankItem(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """سؤال ذخیره‌شده برای استفادهٔ مجدد — FR-QUIZ-01.

    به **درس** بسته است نه ارائه، چون سؤالِ «تفاوت پواسون و دوجمله‌ای
    منفی» هر ترم همان سؤال است. همان استدلال ADR-0008 برای کتابخانه.
    """

    __tablename__ = "question_bank"

    owner_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    course_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("courses.id")
    )
    category: Mapped[str | None] = mapped_column(Text)
    difficulty: Mapped[int | None] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    explanation: Mapped[str | None] = mapped_column(Text)
    usage_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    __table_args__ = (
        CheckConstraint(_in_list("kind", QUESTION_KINDS), name="kind_valid"),
        CheckConstraint(
            "difficulty IS NULL OR difficulty BETWEEN 1 AND 5", name="difficulty_range"
        ),
        CheckConstraint("jsonb_typeof(payload) = 'object'", name="payload_is_object"),
        CheckConstraint("usage_count >= 0", name="usage_count_positive"),
        Index(
            "idx_question_bank_pick",
            "course_id",
            "category",
            "difficulty",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("idx_question_bank_owner", "owner_id"),
    )


class QuizQuestion(UUIDPrimaryKeyMixin, Base):
    """یک سؤال داخل یک آزمون — §4.5.

    اگر از بانک آمده باشد، **کپی** است نه ارجاع: ویرایش بعدی سؤال در
    بانک نباید نمرهٔ آزمونی که قبلاً برگزار شده را عوض کند. `bank_id`
    فقط منشأ را نگه می‌دارد، برای شمارش استفاده و ردیابی.
    """

    __tablename__ = "quiz_questions"

    quiz_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("quizzes.id", ondelete="CASCADE"), nullable=False
    )
    bank_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("question_bank.id", ondelete="SET NULL")
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    explanation: Mapped[str | None] = mapped_column(Text)
    points: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, server_default=text("1"))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    quiz: Mapped[Quiz] = relationship(back_populates="questions")

    __table_args__ = (
        CheckConstraint(_in_list("kind", QUESTION_KINDS), name="kind_valid"),
        CheckConstraint("points > 0", name="points_positive"),
        CheckConstraint("jsonb_typeof(payload) = 'object'", name="payload_is_object"),
        Index("idx_quiz_questions_quiz", "quiz_id", "sort_order"),
    )


class QuizAttempt(UUIDPrimaryKeyMixin, Base):
    """یک تلاش یک دانشجو در یک آزمون — §7.3."""

    __tablename__ = "quiz_attempts"

    quiz_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("quizzes.id"), nullable=False
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'IN_PROGRESS'"))
    question_order: Mapped[list[uuid.UUID] | None] = mapped_column(ARRAY(PGUUID(as_uuid=True)))
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    # مرجع زمان. پس از درج **عوض نمی‌شود** — نه با تمدید، نه با ویرایش
    # مدت آزمون. §7.3 قاعدهٔ ۱.
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    graded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    auto_score: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    manual_score: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    total_score: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    is_provisional: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    integrity_events: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    graded_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id")
    )
    # زمان تمام شد، یا دانشجو خودش ارسال کرد؟ پس از تصحیح، هر دو
    # `GRADED` می‌شوند و این تفاوت جای دیگری نمی‌ماند — ADR-0011.
    auto_closed: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))

    answers: Mapped[list[QuizAnswer]] = relationship(
        back_populates="attempt", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("quiz_id", "student_id", "attempt_no"),
        CheckConstraint(_in_list("status", ATTEMPT_STATUSES), name="status_valid"),
        CheckConstraint("attempt_no > 0", name="attempt_no_positive"),
        CheckConstraint("expires_at > started_at", name="window"),
        CheckConstraint(
            "jsonb_typeof(integrity_events) = 'array'", name="integrity_events_is_array"
        ),
        Index(
            "idx_one_active_attempt",
            "quiz_id",
            "student_id",
            unique=True,
            postgresql_where=text("status = 'IN_PROGRESS'"),
        ),
        Index("idx_attempts_grading", "quiz_id", postgresql_where=text("is_provisional")),
        Index("idx_attempts_student", "student_id", "quiz_id"),
        Index(
            "idx_attempts_expiring",
            "expires_at",
            postgresql_where=text("status = 'IN_PROGRESS'"),
        ),
    )

    @property
    def is_active(self) -> bool:
        return self.status == "IN_PROGRESS"

    @property
    def accepts_answers(self) -> bool:
        """پاسخ فقط در تلاش در جریان ذخیره می‌شود — پنجرهٔ زمانی جدا
        سنجیده می‌شود (`timing.accepts_answer`)."""
        return self.status == "IN_PROGRESS"

    @property
    def is_graded(self) -> bool:
        return self.status == "GRADED"


class QuizAnswer(Base):
    """پاسخ یک دانشجو به یک سؤال — §4.5.

    کلید اصلی `(attempt_id, question_id)` است، نه شناسهٔ مستقل: ذخیرهٔ
    خودکار هر ۱۰ ثانیه یعنی همان پاسخ بارها نوشته می‌شود و `UPSERT`
    روی این کلید، «بی‌اثر در تکرار» را بدون هیچ منطقی در اپلیکیشن
    می‌سازد (§5.6).
    """

    __tablename__ = "quiz_answers"

    attempt_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("quiz_attempts.id", ondelete="CASCADE"),
        primary_key=True,
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("quiz_questions.id"), primary_key=True
    )
    response: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    is_flagged: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    auto_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    manual_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    grader_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id")
    )
    feedback: Mapped[str | None] = mapped_column(Text)
    answered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    # ادعای کلاینت دربارهٔ زمان نوشتن. همگام‌سازی پس از آفلاین با همین
    # تصمیم می‌گیرد کدام نسخه تازه‌تر است (§5.6).
    client_ts: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    attempt: Mapped[QuizAttempt] = relationship(back_populates="answers")

    __table_args__ = (
        Index(
            "idx_quiz_answers_grading_queue",
            "question_id",
            "attempt_id",
            postgresql_where=text("manual_score IS NULL"),
        ),
    )

    @property
    def effective_score(self) -> Decimal | None:
        """نمرهٔ دستی بر خودکار مقدم است — بازنویسی استاد همین است."""
        return self.manual_score if self.manual_score is not None else self.auto_score


class GradeAppeal(UUIDPrimaryKeyMixin, Base):
    """اعتراض به نمره — §7.3."""

    __tablename__ = "grade_appeals"

    attempt_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("quiz_attempts.id", ondelete="CASCADE"),
        nullable=False,
    )
    question_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("quiz_questions.id", ondelete="SET NULL")
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'OPEN'"))
    response: Mapped[str | None] = mapped_column(Text)
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id")
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint(_in_list("status", APPEAL_STATUSES), name="status_valid"),
        CheckConstraint("length(btrim(reason)) > 0", name="reason_not_blank"),
        CheckConstraint("(status = 'OPEN') = (resolved_at IS NULL)", name="resolution_paired"),
        Index(
            "idx_one_open_appeal",
            "attempt_id",
            "question_id",
            unique=True,
            postgresql_where=text("status = 'OPEN' AND question_id IS NOT NULL"),
        ),
        Index(
            "idx_one_open_overall_appeal",
            "attempt_id",
            unique=True,
            postgresql_where=text("status = 'OPEN' AND question_id IS NULL"),
        ),
        Index("idx_grade_appeals_student", "student_id", "status"),
    )


__all__ = [
    "APPEAL_STATUSES",
    "APPEAL_STATUS_TITLE_FA",
    "ATTEMPT_STATUSES",
    "ATTEMPT_STATUS_TITLE_FA",
    "QUESTION_KINDS",
    "QUIZ_STATUSES",
    "QUIZ_STATUS_TITLE_FA",
    "RESULT_VISIBILITIES",
    "RESULT_VISIBILITY_TITLE_FA",
    "SUBMITTED_STATUSES",
    "GradeAppeal",
    "QuestionBankItem",
    "Quiz",
    "QuizAnswer",
    "QuizAttempt",
    "QuizQuestion",
]
