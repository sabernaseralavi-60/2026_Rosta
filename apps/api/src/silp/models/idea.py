"""مدل‌های بانک ایده — PRD §4.7، FR-IDEA-01/02/03. مهاجرت متناظر: 0008_ideas.

| جدول | نقش |
|------|-----|
| `ideas` | ایده با شمارنده‌های غیرنرمال رأی و نظر (§7.12) |
| `idea_votes` | یک رأی مثبت به‌ازای هر (ایده، کاربر) — بدون رأی منفی |
| `idea_comments` | نظر، با نخ یک‌سطحی (`parent_id` فقط به نظر ریشه) |

`vote_count` و `comment_count` را تریگر نگه می‌دارد، نه اپلیکیشن. تریگر
**افزایشی** است، نه بازشماری: دو رأی هم‌زمان هر کدام ردیف ایده را قفل
می‌کنند و دومی مقدار به‌روزشدهٔ اولی را می‌بیند؛ بازشماری در READ COMMITTED
رأی تراکنش هم‌زمان را نمی‌دید و یکی گم می‌شد.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Computed,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    PrimaryKeyConstraint,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from silp.db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin

IDEA_STATUSES = ("OPEN", "PROMOTED", "ARCHIVED")
PROMOTION_TARGETS = ("PROJECT", "VENTURE")

#: دسته‌های ایده — §4.7 ستون `category` را آزاد گذاشته بود؛ فیلتر روی متن
#: آزاد («حمل و نقل»، «حمل‌ونقل»، «ترابری») عملاً کار نمی‌کند (ADR-0014).
IDEA_CATEGORY_TITLE_FA: dict[str, str] = {
    "TRANSPORT": "حمل‌ونقل و ترافیک",
    "AGRICULTURE": "کشاورزی و غذا",
    "COMMERCE": "تجارت و فروش",
    "EDUCATION": "آموزش",
    "TECHNOLOGY": "فناوری و نرم‌افزار",
    "ENVIRONMENT": "محیط زیست و انرژی",
    "SOCIAL": "اجتماعی و شهری",
    "OTHER": "سایر",
}
IDEA_CATEGORIES = tuple(IDEA_CATEGORY_TITLE_FA)

TITLE_MAX = 120
BODY_MAX = 4000
PROBLEM_MAX = 1000
COMMENT_MAX = 1000
MAX_TAGS = 8


def _in_list(column: str, values: tuple[str, ...]) -> str:
    joined = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({joined})"


class Idea(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "ideas"

    author_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    problem: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'::text[]")
    )
    # نام نویسنده مخفی است، ولی نویسنده در سامانه ثبت است (FR-IDEA-01):
    # امتیاز می‌گیرد، و ایدهٔ توهین‌آمیز ناشناس هم صاحب دارد.
    is_anonymous: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'OPEN'"))
    vote_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    comment_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    promoted_to_type: Mapped[str | None] = mapped_column(Text)
    promoted_to_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True))
    promoted_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id")
    )
    promoted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archived_reason: Mapped[str | None] = mapped_column(Text)

    search_norm: Mapped[str | None] = mapped_column(
        Text, Computed("fa_normalize(title || ' ' || body)", persisted=True)
    )

    __table_args__ = (
        CheckConstraint(_in_list("status", IDEA_STATUSES), name="status_valid"),
        CheckConstraint(
            f"category IS NULL OR {_in_list('category', IDEA_CATEGORIES)}", name="category_valid"
        ),
        CheckConstraint(f"length(title) BETWEEN 3 AND {TITLE_MAX}", name="title_length"),
        CheckConstraint(f"length(body) BETWEEN 10 AND {BODY_MAX}", name="body_length"),
        CheckConstraint(
            f"problem IS NULL OR length(problem) <= {PROBLEM_MAX}", name="problem_length"
        ),
        CheckConstraint(f"cardinality(tags) <= {MAX_TAGS}", name="tags_count"),
        CheckConstraint("vote_count >= 0 AND comment_count >= 0", name="counters_not_negative"),
        CheckConstraint(
            "promoted_to_type IS NULL OR " + _in_list("promoted_to_type", PROMOTION_TARGETS),
            name="promoted_to_type_valid",
        ),
        # ایدهٔ ارتقایافته بی‌مقصد، یا مقصدِ ایدهٔ ارتقانیافته، هر دو داده‌ٔ خراب‌اند.
        CheckConstraint(
            "(status = 'PROMOTED') = (promoted_to_id IS NOT NULL)"
            " AND (promoted_to_id IS NULL) = (promoted_to_type IS NULL)",
            name="promotion_consistent",
        ),
        Index("idx_ideas_search", text("search_norm gin_trgm_ops"), postgresql_using="gin"),
        Index(
            "idx_ideas_ranking",
            text("vote_count DESC"),
            text("created_at DESC"),
            postgresql_where=text("status = 'OPEN' AND deleted_at IS NULL"),
        ),
        Index("idx_ideas_author", "author_id", text("created_at DESC")),
        Index("idx_ideas_tags", "tags", postgresql_using="gin"),
    )

    @property
    def is_open(self) -> bool:
        return self.status == "OPEN" and self.deleted_at is None


class IdeaVote(Base):
    __tablename__ = "idea_votes"

    idea_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("ideas.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        PrimaryKeyConstraint("idea_id", "user_id"),
        Index("idx_idea_votes_user", "user_id"),
    )


class IdeaComment(UUIDPrimaryKeyMixin, SoftDeleteMixin, Base):
    __tablename__ = "idea_comments"

    idea_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("ideas.id", ondelete="CASCADE"), nullable=False
    )
    author_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    # نخ یک‌سطحی (FR-IDEA-02): پاسخ فقط به نظر ریشه. عمق را سرویس می‌پاید؛
    # قید CHECK نمی‌تواند ردیف دیگری را بخواند.
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("idea_comments.id", ondelete="CASCADE")
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint(f"length(body) BETWEEN 1 AND {COMMENT_MAX}", name="body_length"),
        CheckConstraint("parent_id IS NULL OR parent_id <> id", name="not_own_parent"),
        Index("idx_idea_comments_idea", "idea_id", "created_at"),
    )


__all__ = [
    "BODY_MAX",
    "COMMENT_MAX",
    "IDEA_CATEGORIES",
    "IDEA_CATEGORY_TITLE_FA",
    "IDEA_STATUSES",
    "MAX_TAGS",
    "PROBLEM_MAX",
    "PROMOTION_TARGETS",
    "TITLE_MAX",
    "Idea",
    "IdeaComment",
    "IdeaVote",
]
