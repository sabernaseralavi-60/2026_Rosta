"""مدل موتور محتوا — ADR-0030.

جدول: content_items. مهاجرت متناظر: 0023_content_engine.

هر یادداشت Markdown در Vault شخصی مالک (پوشهٔ `12_Content`) یک ردیف است.
Vault منبع حقیقتِ **متن** است و پایگاه‌داده نمایهٔ قابل جست‌وجوی آن؛ کلید
همگام‌سازی `source_path` است و `content_sha256` می‌گوید فایل عوض شده یا نه
(همان قرارداد ADR-0008).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, Text, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from silp.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

CONTENT_KINDS = (
    "ARTICLE",
    "BOOK_SUMMARY",
    "PAPER_SUMMARY",
    "EXAMPLE",
    "CASE_STUDY",
    "DATASET_NOTE",
)
#: بازتاب `ACCESS` در نمونهٔ ظاهری فاز ۰. `MEMBER` و `PREMIUM` تا آمدن عضویت
#: فقط برای کادر آموزشی و مدیر باز است (ADR-0030).
CONTENT_ACCESS = ("PUBLIC", "REGISTERED", "STUDENT", "MEMBER", "PREMIUM")
#: `ARCHIVED`: فایل از Vault ناپدید شده است. حذف نمی‌شود، چون پیوندها و
#: نشانی صفحه برمی‌گردند اگر فایل برگردد.
CONTENT_STATUSES = ("DRAFT", "PUBLISHED", "ARCHIVED")


def _in_list(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class ContentItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "content_items"

    slug: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'ARTICLE'"))
    title_fa: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    body_md: Mapped[str] = mapped_column(Text, nullable=False)
    #: کلید عکس ثبت‌شدهٔ وب (`hero`، `learn`…) یا نشانی https؛ خالی یعنی پیش‌فرض نوع.
    cover: Mapped[str | None] = mapped_column(Text)
    access: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'PUBLIC'"))
    topics: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'::text[]")
    )
    skills: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'::text[]")
    )
    #: نام پوشهٔ درس در `Courses/` — ارجاع نرم؛ درس ممکن است هنوز همگام نشده باشد.
    course_slug: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'DRAFT'"))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reading_minutes: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    source_path: Mapped[str | None] = mapped_column(Text, unique=True)
    content_sha256: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint(_in_list("kind", CONTENT_KINDS), name="kind_valid"),
        CheckConstraint(_in_list("access", CONTENT_ACCESS), name="access_valid"),
        CheckConstraint(_in_list("status", CONTENT_STATUSES), name="status_valid"),
        CheckConstraint("length(title_fa) BETWEEN 3 AND 200", name="title_length"),
        CheckConstraint("reading_minutes >= 1", name="reading_minutes_positive"),
        Index(
            "idx_content_items_feed",
            text("published_at DESC"),
            postgresql_where=text("status = 'PUBLISHED'"),
        ),
        Index("idx_content_items_topics", "topics", postgresql_using="gin"),
        Index("idx_content_items_kind", "kind", "published_at"),
    )
