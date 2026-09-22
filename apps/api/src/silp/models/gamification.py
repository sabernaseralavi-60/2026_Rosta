"""مدل‌های گیمیفیکیشن — PRD §4.8.

جداول: point_rules، point_entries، badges، user_badges، و نمای تجمیعی
user_point_totals. مهاجرت متناظر: 0012_gamification.

دفتر کل (`point_entries`) **فقط افزودنی** است (D-09). مدل اینجا این را
فقط بازتاب می‌دهد؛ نگهبان واقعی تریگر `forbid_point_entry_update` است، تا
یک `UPDATE` دستی در psql هم نتواند تاریخچه را بازنویسی کند.

سه ستون فراتر از §4.8 — `revision`، `multiplier` و `user_badges.seen_at` —
و تفسیر سقف‌ها به‌عنوان تعداد، در ADR-0012 توضیح داده شده‌اند.
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
    PrimaryKeyConstraint,
    SmallInteger,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from silp.db.base import Base, UUIDPrimaryKeyMixin

POINT_CATEGORIES = ("LEARNING", "RESEARCH", "STARTUP", "COMMUNITY")
BADGE_TIERS = ("BRONZE", "SILVER", "GOLD", "PLATINUM")

POINT_CATEGORY_TITLE_FA: dict[str, str] = {
    "LEARNING": "یادگیری",
    "RESEARCH": "پژوهش",
    "STARTUP": "کارآفرینی",
    "COMMUNITY": "جامعه",
}

BADGE_TIER_TITLE_FA: dict[str, str] = {
    "BRONZE": "برنزی",
    "SILVER": "نقره‌ای",
    "GOLD": "طلایی",
    "PLATINUM": "پلاتینیوم",
}


def _in_list(column: str, values: tuple[str, ...]) -> str:
    joined = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({joined})"


class PointRule(Base):
    """یک قاعدهٔ امتیاز — FR-GAM-02. مدیر بدون استقرار مجدد تغییرش می‌دهد."""

    __tablename__ = "point_rules"

    code: Mapped[str] = mapped_column(Text, primary_key=True)
    title_fa: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    base_points: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    formula: Mapped[str | None] = mapped_column(Text)
    # تعداد اعطا در پنجره، نه امتیاز — ADR-0012.
    daily_cap: Mapped[int | None] = mapped_column(Integer)
    weekly_cap: Mapped[int | None] = mapped_column(Integer)
    term_cap: Mapped[int | None] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint(_in_list("category", POINT_CATEGORIES), name="category_valid"),
        CheckConstraint("base_points >= 0", name="base_points_not_negative"),
    )


class PointEntry(UUIDPrimaryKeyMixin, Base):
    """یک ردیف دفتر کل — FR-GAM-01. اصلی مثبت، معکوس منفی."""

    __tablename__ = "point_entries"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    category: Mapped[str] = mapped_column(Text, nullable=False)
    rule_code: Mapped[str] = mapped_column(Text, ForeignKey("point_rules.code"), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    multiplier: Mapped[Decimal] = mapped_column(
        Numeric(10, 4), nullable=False, server_default=text("1")
    )
    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    source_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True))
    revision: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text("0"))
    term_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("terms.id"))
    offering_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("course_offerings.id")
    )
    note: Mapped[str | None] = mapped_column(Text)
    reverses_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("point_entries.id", ondelete="CASCADE")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint(_in_list("category", POINT_CATEGORIES), name="category_valid"),
        CheckConstraint(
            "(reverses_id IS NULL AND amount > 0) OR (reverses_id IS NOT NULL AND amount < 0)",
            name="sign_matches_kind",
        ),
        # FR-GAM-01 — یک رویداد، یک امتیاز؛ `revision` پس از معکوس شدن (ADR-0012).
        Index(
            "idx_point_idempotency",
            "user_id",
            "rule_code",
            "source_type",
            "source_id",
            "revision",
            unique=True,
            postgresql_where=text("reverses_id IS NULL AND source_id IS NOT NULL"),
        ),
        Index(
            "idx_point_single_reversal",
            "reverses_id",
            unique=True,
            postgresql_where=text("reverses_id IS NOT NULL"),
        ),
        Index("idx_points_user_term", "user_id", "term_id", "category"),
        Index("idx_points_created", text("created_at DESC")),
        Index("idx_points_user_rule_created", "user_id", "rule_code", "created_at"),
        Index(
            "idx_points_offering",
            "offering_id",
            "user_id",
            postgresql_where=text("offering_id IS NOT NULL"),
        ),
    )

    @property
    def is_reversal(self) -> bool:
        return self.reverses_id is not None


class Badge(Base):
    """یک نشان با معیار شفاف — FR-GAM-03، §9.5."""

    __tablename__ = "badges"

    code: Mapped[str] = mapped_column(Text, primary_key=True)
    title_fa: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    icon: Mapped[str] = mapped_column(Text, nullable=False)
    tier: Mapped[str] = mapped_column(Text, nullable=False)
    criteria: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    __table_args__ = (CheckConstraint(_in_list("tier", BADGE_TIERS), name="tier_valid"),)


class UserBadge(Base):
    """نشان کسب‌شده. یک‌بار اعطا می‌شود و پس گرفته نمی‌شود (FR-GAM-03)."""

    __tablename__ = "user_badges"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    badge_code: Mapped[str] = mapped_column(Text, ForeignKey("badges.code"))
    awarded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    context: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    # فراتر از §4.8 — لحظهٔ دیدن جشن (§9.10). ADR-0012.
    seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        PrimaryKeyConstraint("user_id", "badge_code"),
        Index("idx_user_badges_unseen", "user_id", postgresql_where=text("seen_at IS NULL")),
    )


__all__ = [
    "BADGE_TIERS",
    "BADGE_TIER_TITLE_FA",
    "POINT_CATEGORIES",
    "POINT_CATEGORY_TITLE_FA",
    "Badge",
    "PointEntry",
    "PointRule",
    "UserBadge",
]
