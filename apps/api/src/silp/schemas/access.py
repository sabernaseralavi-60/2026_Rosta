"""مدل‌های Pydantic برای /subscriptions — ADR-0009.

قیمت در پاسخ **دو شکل** دارد: `price_irr` برای محاسبه و `price_fa`
برای نمایش. کاربر ایرانی به تومان فکر می‌کند و پایگاه‌داده به ریال؛
تبدیل یک‌بار اینجا انجام می‌شود تا در هیچ کامپوننتی تکرار نشود.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

PlanScope = Literal["ALL_COURSES", "SINGLE_COURSE"]
SubscriptionStatus = Literal["PENDING", "ACTIVE", "EXPIRED", "CANCELLED"]

RIAL_PER_TOMAN = 10


class PlanOut(BaseModel):
    id: uuid.UUID
    code: str
    title_fa: str
    description: str | None = None
    scope: PlanScope
    scope_fa: str
    duration_days: int
    price_irr: int
    price_toman: int
    price_fa: str


class SubscriptionOut(BaseModel):
    id: uuid.UUID
    plan_code: str
    plan_title_fa: str
    course_id: uuid.UUID | None = None
    course_title_fa: str | None = None
    status: SubscriptionStatus
    status_fa: str
    starts_at: datetime
    ends_at: datetime
    days_remaining: int
    payment_ref: str | None = None
    amount_irr: int | None = None


class MySubscriptionsOut(BaseModel):
    """وضعیت اشتراک کاربر — همان چیزی که صفحهٔ «اشتراک من» می‌خواهد."""

    has_active: bool
    covers_all_courses: bool
    items: list[SubscriptionOut] = Field(default_factory=list)


class SubscriptionRequestIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_code: Annotated[str, Field(min_length=1, max_length=64)]
    # فقط برای طرح تک‌درسی — نشانی درس، نه شناسه: همان چیزی که در URL است.
    course_slug: Annotated[str | None, Field(max_length=200)] = None
    note: Annotated[str | None, Field(max_length=500)] = None


class SubscriptionGrantIn(BaseModel):
    """فعال‌سازی دستی توسط پشتیبانی — §02 «پرداخت خارج از سامانه»."""

    model_config = ConfigDict(extra="forbid")

    user_id: uuid.UUID
    plan_code: Annotated[str, Field(min_length=1, max_length=64)]
    course_slug: Annotated[str | None, Field(max_length=200)] = None
    payment_ref: Annotated[str | None, Field(max_length=200)] = None
    note: Annotated[str | None, Field(max_length=500)] = None


class SubscriptionActivateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    payment_ref: Annotated[str | None, Field(max_length=200)] = None


__all__ = [
    "RIAL_PER_TOMAN",
    "MySubscriptionsOut",
    "PlanOut",
    "SubscriptionActivateIn",
    "SubscriptionGrantIn",
    "SubscriptionOut",
    "SubscriptionRequestIn",
]
