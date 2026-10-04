"""حلقهٔ یادگیری روزانه — ADR-0036، مهاجرت ۰۰۳۱."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from silp.db.base import Base, UUIDPrimaryKeyMixin

LESSON_STATUSES = ("DRAFT", "PUBLISHED")


class Module(UUIDPrimaryKeyMixin, Base):
    """گروه‌بندی درس‌نامه‌ها زیر یک ارائه (مثلاً «جریان ترافیک»)."""

    __tablename__ = "modules"

    offering_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("course_offerings.id", ondelete="CASCADE"), nullable=False
    )
    title_fa: Mapped[str] = mapped_column(Text, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (Index("idx_modules_offering", "offering_id", "sort_order"),)


class Lesson(UUIDPrimaryKeyMixin, Base):
    """درس‌نامهٔ کوتاه (یا بخشی از مقاله) که هر روز منتشر می‌شود."""

    __tablename__ = "lessons"

    offering_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("course_offerings.id", ondelete="CASCADE"), nullable=False
    )
    module_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("modules.id", ondelete="SET NULL")
    )
    week_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("course_weeks.id", ondelete="SET NULL")
    )
    title_fa: Mapped[str] = mapped_column(Text, nullable=False)
    body_md: Mapped[str] = mapped_column(Text, nullable=False)
    est_minutes: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("5"))
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'DRAFT'"))
    #: زمان نمایش به دانشجو؛ NULL و منتشرشده یعنی همین الان.
    publish_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint("status IN ('DRAFT', 'PUBLISHED')", name="status_valid"),
        CheckConstraint("est_minutes BETWEEN 1 AND 120", name="est_minutes_range"),
        CheckConstraint("length(body_md) <= 60000", name="body_length"),
        Index("idx_lessons_offering", "offering_id", "status", "publish_at"),
    )


class Topic(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "topics"

    course_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    title_fa: Mapped[str] = mapped_column(Text, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))


class Competency(UUIDPrimaryKeyMixin, Base):
    """شایستگی درسی («تحلیل ظرفیت»). جدا از `skills` پرسشنامهٔ نیمرخ."""

    __tablename__ = "competencies"

    code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    title_fa: Mapped[str] = mapped_column(Text, nullable=False)
    domain: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))


class Concept(UUIDPrimaryKeyMixin, Base):
    """مفهوم («HCM — سطح سرویس»)؛ سؤال به این وصل می‌شود، مفهوم به یک شایستگی."""

    __tablename__ = "concepts"

    competency_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("competencies.id", ondelete="CASCADE"), nullable=False
    )
    topic_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("topics.id", ondelete="SET NULL")
    )
    code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    title_fa: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (Index("idx_concepts_competency", "competency_id"),)


class CompetencyMastery(Base):
    """مشتق از `quiz_answers` — بازسازی‌پذیر. `evidence_n` کم یعنی «کم‌داده»."""

    __tablename__ = "competency_mastery"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    competency_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("competencies.id", ondelete="CASCADE"), primary_key=True
    )
    score: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    evidence_n: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (CheckConstraint("score BETWEEN 0 AND 1", name="score_range"),)


class Streak(Base):
    """استمرار چالش روزانه برای یک (دانشجو، ارائه). روز = روز تقویمی تهران."""

    __tablename__ = "streaks"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    offering_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("course_offerings.id", ondelete="CASCADE"),
        primary_key=True,
    )
    current: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    longest: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    started_on: Mapped[date | None] = mapped_column(Date)
    last_day: Mapped[date | None] = mapped_column(Date)
    #: شروع هفته‌ای (شنبه) که معافیت‌اش مصرف شده؛ هر هفته فقط یک معافیت.
    freeze_week: Mapped[date | None] = mapped_column(Date)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class CheckpointResult(Base):
    """نتیجهٔ پردازش‌شدهٔ یک تلاشِ چالش روزانه؛ قفل بی‌اثری و تاریخچهٔ داشبورد."""

    __tablename__ = "checkpoint_results"

    attempt_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("quiz_attempts.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    quiz_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("quizzes.id", ondelete="CASCADE"), nullable=False
    )
    offering_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("course_offerings.id", ondelete="CASCADE"), nullable=False
    )
    day: Mapped[date] = mapped_column(Date, nullable=False)
    correct: Mapped[int] = mapped_column(Integer, nullable=False)
    total: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint("correct BETWEEN 0 AND total", name="counts_valid"),
        Index("idx_checkpoint_results_user_day", "user_id", "day"),
    )
