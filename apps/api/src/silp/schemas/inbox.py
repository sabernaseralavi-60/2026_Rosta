"""مدل‌های صندوق درخواست‌های ورودی (مالک) و پیگیری (مشتری) — ADR-0032."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, StringConstraints, field_validator, model_validator

from silp.domain.identity.normalize import normalize_email, normalize_mobile

Status = Literal["NEW", "IN_REVIEW", "ACCEPTED", "DECLINED", "ARCHIVED"]
Kind = Literal["INTAKE", "COLLABORATION"]


class EventOut(BaseModel):
    """یک قدم رسیدگی. مشتری هم همین را می‌بیند؛ پس هیچ یادداشت خصوصی‌ای اینجا نیست."""

    id: uuid.UUID
    from_status: str | None
    to_status: str
    public_note: str | None
    created_at: datetime


# ── مالک ───────────────────────────────────────────────────────────────
class InboxItemOut(BaseModel):
    id: uuid.UUID
    kind: str
    tracking_code: str
    status: str
    contact_name: str
    contact_mobile: str | None
    contact_email: str | None
    organization: str | None
    need_type: str | None
    services: list[str]
    summary: str
    person_code: str | None
    created_at: datetime
    updated_at: datetime
    #: بیش از سه روز بی‌رسیدگی (NEW / IN_REVIEW) — «نیاز به پیگیری».
    stale: bool


class InboxDetailOut(InboxItemOut):
    payload: dict[str, Any]
    owner_note: str | None
    events: list[EventOut]


class InboxPageOut(BaseModel):
    items: list[InboxItemOut]
    total: int
    #: شمار هر وضعیت، با فیلتر `kind` و جست‌وجوی جاری ولی بی‌فیلتر `status`.
    counts: dict[str, int]


Note = Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)]


class InboxUpdateIn(BaseModel):
    """تغییر وضعیت و/یا یادداشت‌ها. رشتهٔ خالی یادداشت را پاک می‌کند؛ نبودن کلید = دست‌نخورده."""

    status: Status | None = None
    owner_note: Annotated[str, StringConstraints(strip_whitespace=True, max_length=4000)] | None = (
        None
    )
    #: به مشتری نشان داده می‌شود. فقط همراه یک رویداد ثبت می‌شود.
    public_note: Note | None = None

    @model_validator(mode="after")
    def _something(self) -> Self:
        if self.status is None and self.owner_note is None and not self.public_note:
            raise ValueError("چیزی برای تغییر نیست.")
        return self


class OverviewOut(BaseModel):
    """داشبورد مالک — فقط آنچه از داده‌های واقعی می‌آید؛ آمار ساختگی نیست."""

    intake: dict[str, dict[str, int]]  # kind ← status ← تعداد
    new_7d: int
    stale: int
    oldest_new_days: int | None
    students_total: int
    students_active_7d: int
    enrollments_active: int
    courses_total: int
    content: dict[str, int]  # status ← تعداد
    clients_accepted: int
    collaborators_accepted: int
    follow_up: list[InboxItemOut]


# ── مشتری ──────────────────────────────────────────────────────────────
class MyRequestOut(BaseModel):
    tracking_code: str
    kind: str
    status: str
    need_type: str | None
    services: list[str]
    summary: str
    created_at: datetime
    updated_at: datetime
    events: list[EventOut]


class RequestTrackIn(BaseModel):
    """پیگیری بی‌ورود: کد **و** راه تماسی که هنگام ثبت داده شد."""

    tracking_code: Annotated[
        str, StringConstraints(strip_whitespace=True, pattern=r"^[QC]-\d{1,9}$")
    ]
    contact: Annotated[str, StringConstraints(strip_whitespace=True, min_length=5, max_length=200)]

    @field_validator("tracking_code", mode="before")
    @classmethod
    def _upper(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value

    @model_validator(mode="after")
    def _contact_parses(self) -> Self:
        if normalize_mobile(self.contact) is None and normalize_email(self.contact) is None:
            raise ValueError("شمارهٔ موبایل یا ایمیلِ ثبت‌شده را بنویسید.")
        return self


class RequestTrackOut(BaseModel):
    """مشتریِ بی‌ورود هیچ متنی از درخواستش را پس نمی‌گیرد: کد و راه تماس شاید لو رفته باشد."""

    tracking_code: str
    kind: str
    status: str
    need_type: str | None
    created_at: datetime
    updated_at: datetime
    events: list[EventOut]


__all__ = [
    "EventOut",
    "InboxDetailOut",
    "InboxItemOut",
    "InboxPageOut",
    "InboxUpdateIn",
    "Kind",
    "MyRequestOut",
    "OverviewOut",
    "Status",
    "RequestTrackIn",
    "RequestTrackOut",
]
