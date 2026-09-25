"""مدل‌های پرسش‌وپاسخ درس — PRD §4.10، FR-EDU-07، ADR-0024 برش ج. مهاجرت: 0020.

| جدول | نقش |
|------|-----|
| `qa_threads` | پرسش یک ارائه، اختیاری وابسته به یک هفته |
| `qa_replies` | پاسخ؛ `endorsed_*` یعنی استاد این پاسخ را تأیید کرد |
| `qa_reply_votes` | یک رأی «مفید» به‌ازای هر (پاسخ، کاربر) |

§4.10 سه چیز نداشت که قاعده‌های امتیاز بی‌آن‌ها اجرا نمی‌شوند: حذف نرم
(نظارت)، ذخیرهٔ «تأیید استاد» و جدول رأی. `is_official` یعنی «پاسخ را خودِ
استاد نوشته»؛ `endorsed_by` یعنی «استاد پاسخِ *دانشجو* را تأیید کرد» — دو
مفهوم جدا که `QA_ANSWER_OFFICIAL_MATCH` دومی را می‌خواهد.

`helpful_count` را تریگر افزایشی نگه می‌دارد (§7.12)، مثل `ideas.vote_count`.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    PrimaryKeyConstraint,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from silp.db.base import Base, SoftDeleteMixin, UUIDPrimaryKeyMixin

TITLE_MIN = 5
TITLE_MAX = 150
THREAD_BODY_MIN = 10
BODY_MAX = 4000
REPLY_MIN = 3


class QaThread(UUIDPrimaryKeyMixin, SoftDeleteMixin, Base):
    __tablename__ = "qa_threads"

    week_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("course_weeks.id", ondelete="CASCADE")
    )
    offering_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("course_offerings.id", ondelete="CASCADE"), nullable=False
    )
    author_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    # نام پرسنده برای همکلاسی‌ها پنهان است؛ استادِ ارائه و خودش می‌بینند.
    is_anonymous: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    is_resolved: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint(f"length(title) BETWEEN {TITLE_MIN} AND {TITLE_MAX}", name="title_length"),
        CheckConstraint(
            f"length(body) BETWEEN {THREAD_BODY_MIN} AND {BODY_MAX}", name="body_length"
        ),
        Index("idx_qa_threads_offering", "offering_id", text("created_at DESC")),
        Index("idx_qa_threads_week", "week_id"),
        Index("idx_qa_threads_author", "author_id"),
    )


class QaReply(UUIDPrimaryKeyMixin, SoftDeleteMixin, Base):
    __tablename__ = "qa_replies"

    thread_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("qa_threads.id", ondelete="CASCADE"), nullable=False
    )
    author_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    #: پاسخ خودِ استاد (کسی با `OFFERING_MANAGE` در قلمرو ارائه) — سرور می‌گذارد.
    is_official: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    helpful_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    #: تأیید استاد بر پاسخِ *دانشجو* — منبع `QA_ANSWER_OFFICIAL_MATCH`.
    endorsed_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id")
    )
    endorsed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint(f"length(body) BETWEEN {REPLY_MIN} AND {BODY_MAX}", name="body_length"),
        CheckConstraint("helpful_count >= 0", name="helpful_not_negative"),
        CheckConstraint("(endorsed_by IS NULL) = (endorsed_at IS NULL)", name="endorsement_pair"),
        CheckConstraint(
            "NOT (is_official AND endorsed_by IS NOT NULL)", name="official_not_endorsed"
        ),
        Index("idx_qa_replies_thread", "thread_id", "created_at"),
        Index("idx_qa_replies_author", "author_id"),
    )


class QaReplyVote(Base):
    __tablename__ = "qa_reply_votes"

    reply_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("qa_replies.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        PrimaryKeyConstraint("reply_id", "user_id"),
        Index("idx_qa_reply_votes_user", "user_id"),
    )


__all__ = [
    "BODY_MAX",
    "REPLY_MIN",
    "THREAD_BODY_MIN",
    "TITLE_MAX",
    "TITLE_MIN",
    "QaReply",
    "QaReplyVote",
    "QaThread",
]
