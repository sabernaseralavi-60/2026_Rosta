"""مدل‌های کارآفرینی — PRD §4.7، §7.7، FR-VEN-01/02. مهاجرت متناظر: 0009_ventures.

| جدول | نقش |
|------|-----|
| `ventures` | کسب‌وکار دانشجویی با مرحلهٔ بلوغ |
| `venture_stage_changes` | تاریخچهٔ گذار مرحله — منبع امتیاز `VENTURE_STAGE_UP` |
| `venture_metrics` | فعالیت و فروش ثبت‌شده، با تأیید (FR-VEN-02) |

تیم کسب‌وکار همان `teams` با `venture_id` است؛ بنیان‌گذار عضو `is_lead`.

امتیاز `STARTUP` فقط از شاخص **تأییدشده** می‌آید (§9 «نتیجهٔ واقعی، نه
صرف تلاش»): ثبت خودِ دانشجو ادعاست، تأیید دیگری واقعیت.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from silp.db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin

#: مراحل بلوغ به ترتیب — §7.7. شمارهٔ مرحله (اندیس) ضریب `VENTURE_STAGE_UP` است.
GROWTH_STAGES = ("IDEA", "VALIDATION", "MVP", "FIRST_REVENUE", "GROWTH")
VENTURE_STAGES = (*GROWTH_STAGES, "PAUSED", "CLOSED")

STAGE_TITLE_FA: dict[str, str] = {
    "IDEA": "ایده",
    "VALIDATION": "اعتبارسنجی",
    "MVP": "محصول کمینه",
    "FIRST_REVENUE": "اولین درآمد",
    "GROWTH": "رشد",
    "PAUSED": "متوقف",
    "CLOSED": "بسته‌شده",
}

METRIC_KINDS = (
    "CALLS",
    "MEETINGS",
    "LEADS",
    "SALES_COUNT",
    "SALES_AMOUNT",
    "CONTENT_PIECES",
    "CUSTOMERS",
)
METRIC_TITLE_FA: dict[str, str] = {
    "CALLS": "تماس فروش",
    "MEETINGS": "جلسه یا مصاحبهٔ مشتری",
    "LEADS": "سرنخ واجد شرایط",
    "SALES_COUNT": "تعداد فروش",
    "SALES_AMOUNT": "مبلغ فروش (ریال)",
    "CONTENT_PIECES": "محتوای منتشرشده",
    "CUSTOMERS": "مشتری تکرارشونده",
}
METRIC_STATUSES = ("PENDING", "VERIFIED", "REJECTED")
METRIC_STATUS_TITLE_FA: dict[str, str] = {
    "PENDING": "در انتظار تأیید",
    "VERIFIED": "تأیید شده",
    "REJECTED": "رد شده",
}

PITCH_MAX = 280
NOTE_MAX = 500
MAX_NEEDED_ROLES = 10


def _in_list(column: str, values: tuple[str, ...]) -> str:
    joined = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({joined})"


class Venture(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "ventures"

    slug: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    pitch: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    problem: Mapped[str | None] = mapped_column(Text)
    target_market: Mapped[str | None] = mapped_column(Text)
    revenue_model: Mapped[str | None] = mapped_column(Text)
    # FR-VEN-01 «وضعیت فعلی» — روایت آزاد، جدا از مرحلهٔ ساختاریافته.
    current_status: Mapped[str | None] = mapped_column(Text)
    stage: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'IDEA'"))
    # بازگشت از `PAUSED` به همان مرحله‌ای که متوقف شده بود.
    paused_from_stage: Mapped[str | None] = mapped_column(Text)
    stage_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    founder_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    looking_for_cofounder: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    needed_roles: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'::text[]")
    )
    logo_key: Mapped[str | None] = mapped_column(Text)
    origin_idea_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("ideas.id")
    )

    search_norm: Mapped[str | None] = mapped_column(
        Text, Computed("fa_normalize(name || ' ' || pitch)", persisted=True)
    )

    __table_args__ = (
        CheckConstraint(_in_list("stage", VENTURE_STAGES), name="stage_valid"),
        CheckConstraint(
            "paused_from_stage IS NULL OR " + _in_list("paused_from_stage", GROWTH_STAGES),
            name="paused_from_stage_valid",
        ),
        CheckConstraint(
            "(stage = 'PAUSED') = (paused_from_stage IS NOT NULL)", name="paused_from_matches"
        ),
        CheckConstraint(f"length(pitch) BETWEEN 10 AND {PITCH_MAX}", name="pitch_length"),
        CheckConstraint("length(name) BETWEEN 2 AND 120", name="name_length"),
        CheckConstraint(
            f"cardinality(needed_roles) <= {MAX_NEEDED_ROLES}", name="needed_roles_count"
        ),
        Index("idx_ventures_search", text("search_norm gin_trgm_ops"), postgresql_using="gin"),
        Index("idx_ventures_founder", "founder_id"),
        Index(
            "idx_ventures_cofounder",
            "created_at",
            postgresql_where=text("looking_for_cofounder AND deleted_at IS NULL"),
        ),
    )

    @property
    def stage_index(self) -> int | None:
        """شمارهٔ مرحلهٔ رشد (IDEA=0 … GROWTH=4)؛ برای متوقف و بسته None."""
        return GROWTH_STAGES.index(self.stage) if self.stage in GROWTH_STAGES else None


class VentureStageChange(UUIDPrimaryKeyMixin, Base):
    """یک گذار مرحله — تاریخچه، و کلید بی‌اثری امتیاز ارتقا."""

    __tablename__ = "venture_stage_changes"

    venture_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("ventures.id", ondelete="CASCADE"), nullable=False
    )
    from_stage: Mapped[str] = mapped_column(Text, nullable=False)
    to_stage: Mapped[str] = mapped_column(Text, nullable=False)
    changed_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id")
    )
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint(_in_list("from_stage", VENTURE_STAGES), name="from_stage_valid"),
        CheckConstraint(_in_list("to_stage", VENTURE_STAGES), name="to_stage_valid"),
        CheckConstraint("from_stage <> to_stage", name="stage_changes"),
        Index("idx_venture_stage_changes", "venture_id", "created_at"),
    )


class VentureMetric(UUIDPrimaryKeyMixin, Base):
    """یک ردیف فعالیت یا فروش — مال کسب‌وکار یا پروژهٔ عملیاتی، دقیقاً یکی."""

    __tablename__ = "venture_metrics"

    venture_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("ventures.id", ondelete="CASCADE")
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    metric: Mapped[str] = mapped_column(Text, nullable=False)
    # مبلغ به ریال برای `SALES_AMOUNT`؛ بقیه شمارش‌اند.
    value: Mapped[int] = mapped_column(BigInteger, nullable=False)
    occurred_on: Mapped[date] = mapped_column(Date, nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    evidence_file_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("files.id")
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'PENDING'"))
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_note: Mapped[str | None] = mapped_column(Text)
    # عکسی از سهم فروشنده هنگام تأیید (ADR-0025) — فقط فروش تأییدشدهٔ پروژه.
    share_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    share_rial: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint(_in_list("metric", METRIC_KINDS), name="metric_valid"),
        CheckConstraint(_in_list("status", METRIC_STATUSES), name="status_valid"),
        CheckConstraint("value > 0", name="value_positive"),
        CheckConstraint(
            "(venture_id IS NOT NULL)::int + (project_id IS NOT NULL)::int = 1", name="owner"
        ),
        CheckConstraint(
            "(status = 'PENDING') = (reviewed_at IS NULL)", name="reviewed_matches_status"
        ),
        CheckConstraint(f"note IS NULL OR length(note) <= {NOTE_MAX}", name="note_length"),
        # تأیید ادعای خود، تأیید نیست.
        CheckConstraint("reviewed_by IS NULL OR reviewed_by <> user_id", name="not_self_reviewed"),
        CheckConstraint("(share_percent IS NULL) = (share_rial IS NULL)", name="share_pair"),
        CheckConstraint(
            "share_percent IS NULL OR share_percent BETWEEN 0 AND 100", name="share_percent_range"
        ),
        CheckConstraint(
            "share_rial IS NULL OR (share_rial >= 0 AND share_rial <= value)",
            name="share_rial_range",
        ),
        CheckConstraint(
            "share_rial IS NULL OR "
            "(status = 'VERIFIED' AND metric = 'SALES_AMOUNT' AND project_id IS NOT NULL)",
            name="share_only_verified_project_sales",
        ),
        Index("idx_venture_metrics_lookup", "venture_id", "metric", "occurred_on"),
        Index("idx_venture_metrics_project", "project_id", "metric", "occurred_on"),
        Index("idx_venture_metrics_user", "user_id", text("occurred_on DESC")),
        Index(
            "idx_venture_metrics_pending", "created_at", postgresql_where=text("status = 'PENDING'")
        ),
    )


__all__ = [
    "GROWTH_STAGES",
    "MAX_NEEDED_ROLES",
    "METRIC_KINDS",
    "METRIC_STATUSES",
    "METRIC_STATUS_TITLE_FA",
    "METRIC_TITLE_FA",
    "NOTE_MAX",
    "PITCH_MAX",
    "STAGE_TITLE_FA",
    "VENTURE_STAGES",
    "Venture",
    "VentureMetric",
    "VentureStageChange",
]
