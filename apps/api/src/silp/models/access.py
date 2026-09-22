"""مدل‌های اشتراک و دسترسی — ADR-0009.

جداول: subscription_plans، subscriptions، material_access_events.
مهاجرت متناظر: 0006_education.

این‌ها در §4 سند v1 نیامده‌اند و افزودهٔ آگاهانه‌اند. قاعدهٔ کسب‌وکار
ساده است و همهٔ این جدول‌ها فقط برای اجرای همان قاعده‌اند:

> متریال هر درس برای **دانشجوی همان درس** رایگان است؛ برای بقیه با
> **اشتراک ماهانه** در دسترس است.

**پرداخت درون سامانه انجام نمی‌شود.** §13.5 «سیستم پرداخت و تسویه» را
بیرون از فاز ۱ گذاشته و §02 گفته «فاز ۱ فقط ثبت و گزارش است؛ پرداخت
خارج از سامانه انجام می‌شود». پس `subscriptions` یک **رسید** است، نه یک
تراکنش: مدیر پس از دریافت وجه، ردیف را با `payment_ref` فعال می‌کند.
وقتی درگاه آمد، همان ردیف را یک وب‌هوک می‌سازد و هیچ چیز دیگری در
سنجش دسترسی عوض نمی‌شود.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from silp.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

# دامنهٔ طرح: کل کتابخانه، یا فقط یک درس.
PLAN_SCOPES = ("ALL_COURSES", "SINGLE_COURSE")
SUBSCRIPTION_STATUSES = ("PENDING", "ACTIVE", "EXPIRED", "CANCELLED")

PLAN_SCOPE_TITLE_FA: dict[str, str] = {
    "ALL_COURSES": "همهٔ دروس",
    "SINGLE_COURSE": "یک درس",
}

SUBSCRIPTION_STATUS_TITLE_FA: dict[str, str] = {
    "PENDING": "در انتظار تأیید پرداخت",
    "ACTIVE": "فعال",
    "EXPIRED": "منقضی",
    "CANCELLED": "لغو شده",
}


def _in_list(column: str, values: tuple[str, ...]) -> str:
    joined = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({joined})"


class SubscriptionPlan(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """طرح اشتراک — «ماهانهٔ همهٔ دروس»، «سه‌ماههٔ یک درس».

    قیمت به **ریال** ذخیره می‌شود، نه تومان و نه اعشار: واحد رسمی یکی
    است و تبدیل به تومان کار لایهٔ نمایش است.
    """

    __tablename__ = "subscription_plans"

    code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    title_fa: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    scope: Mapped[str] = mapped_column(Text, nullable=False)
    duration_days: Mapped[int] = mapped_column(Integer, nullable=False)
    price_irr: Mapped[int] = mapped_column(BigInteger, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    __table_args__ = (
        CheckConstraint(_in_list("scope", PLAN_SCOPES), name="scope_valid"),
        CheckConstraint("duration_days BETWEEN 1 AND 3650", name="duration_range"),
        CheckConstraint("price_irr >= 0", name="price_non_negative"),
    )


class Subscription(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """اشتراک یک کاربر — ADR-0009.

    `course_id` فقط برای طرح `SINGLE_COURSE` پر می‌شود. قید پایگاه‌داده
    این را تضمین نمی‌کند (نیازمند ارجاع به سطر طرح است)، ولی سرویس
    هنگام ساخت بررسی می‌کند و سنجش دسترسی هر دو حالت را می‌فهمد.
    """

    __tablename__ = "subscriptions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    plan_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("subscription_plans.id"), nullable=False
    )
    course_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE")
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'PENDING'"))
    starts_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # رسید پرداخت بیرونی — شمارهٔ فیش، کد رهگیری درگاه، یا «هدیه».
    payment_ref: Mapped[str | None] = mapped_column(Text)
    amount_irr: Mapped[int | None] = mapped_column(BigInteger)
    note: Mapped[str | None] = mapped_column(Text)
    granted_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id")
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(_in_list("status", SUBSCRIPTION_STATUSES), name="status_valid"),
        CheckConstraint("ends_at > starts_at", name="date_order"),
        CheckConstraint(
            "(status = 'CANCELLED') = (cancelled_at IS NOT NULL)",
            name="cancelled_at_matches_status",
        ),
        # پرس‌وجوی داغ: «آیا این کاربر همین حالا اشتراک فعال دارد؟»
        Index(
            "idx_subscriptions_active",
            "user_id",
            "ends_at",
            postgresql_where=text("status = 'ACTIVE'"),
        ),
        Index(
            "idx_subscriptions_course", "course_id", postgresql_where=text("course_id IS NOT NULL")
        ),
    )

    def covers(self, course_id: uuid.UUID, *, now: datetime) -> bool:
        """آیا این اشتراک، همین حالا، همین درس را پوشش می‌دهد؟"""
        if self.status != "ACTIVE":
            return False
        if not (self.starts_at <= now < self.ends_at):
            return False
        # اشتراک همه‌دروس `course_id` ندارد و همه را پوشش می‌دهد.
        return self.course_id is None or self.course_id == course_id


class MaterialAccessEvent(Base):
    """رویداد `resource_accessed` — FR-EDU-03.

    فقط افزودنی. برای دو چیز لازم است: گزارش «کدام جزوه بیشتر خوانده
    شد» و شواهد استفاده در دعوای احتمالی اشتراک. کلید اصلی مصنوعی
    ندارد چون هیچ‌کس به یک ردیف منفرد ارجاع نمی‌دهد.
    """

    __tablename__ = "material_access_events"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    material_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("course_materials.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # چرا اجازه داده شد: ENROLLED / SUBSCRIPTION / PUBLIC / STAFF.
    granted_by_reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        Index("idx_material_access_material", "material_id", text("created_at DESC")),
        Index("idx_material_access_user", "user_id", text("created_at DESC")),
    )


__all__ = [
    "PLAN_SCOPES",
    "PLAN_SCOPE_TITLE_FA",
    "SUBSCRIPTION_STATUSES",
    "SUBSCRIPTION_STATUS_TITLE_FA",
    "MaterialAccessEvent",
    "Subscription",
    "SubscriptionPlan",
]
