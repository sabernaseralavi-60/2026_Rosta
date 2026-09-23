"""مدل‌های Pydantic اعلان — §5.10، FR-MSG-01/02/03.

متن اعلان را سرور می‌سازد و کلاینت فقط نمایشش می‌دهد (§5.1). دسته و
کانال‌ها برچسب فارسی همراه دارند تا رابط کاربری نگاشت کد به متن را
تکرار نکند.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from silp.domain.notifications import catalog
from silp.models.messaging import Notification

Group = Literal["COURSE", "PROJECT", "SOCIAL", "SYSTEM"]
Priority = Literal["LOW", "NORMAL", "IMPORTANT", "URGENT"]
Channel = Literal["IN_APP", "EMAIL", "SMS", "TELEGRAM", "EITAA", "WHATSAPP"]
LinkableChannel = Literal["TELEGRAM", "EITAA"]
OutboxStatus = Literal["QUEUED", "SENDING", "SENT", "FAILED", "DEAD"]


# ── مرکز اعلان ─────────────────────────────────────────────────────────
class NotificationOut(BaseModel):
    id: uuid.UUID
    kind: str
    group: Group
    group_fa: str
    title: str
    body: str
    action_url: str | None = None
    priority: Priority
    created_at: datetime
    read_at: datetime | None = None
    is_read: bool

    @classmethod
    def of(cls, notification: Notification) -> NotificationOut:
        group: Group = notification.kind_group  # type: ignore[assignment]
        return cls(
            id=notification.id,
            kind=notification.kind,
            group=group,
            group_fa=catalog.GROUP_TITLE_FA[group],
            title=notification.title,
            body=notification.body,
            action_url=notification.action_url,
            priority=notification.priority,
            created_at=notification.created_at,
            read_at=notification.read_at,
            is_read=notification.read_at is not None,
        )


class NotificationFeedOut(BaseModel):
    items: list[NotificationOut]
    next_cursor: str | None = None


class UnreadCountOut(BaseModel):
    count: int


class ReadAllOut(BaseModel):
    updated: int


# ── ترجیحات — FR-MSG-02 ────────────────────────────────────────────────
class GroupPreferenceOut(BaseModel):
    group: Group
    title_fa: str
    description_fa: str
    channels: list[Channel]


class ChannelStatusOut(BaseModel):
    channel: Channel
    title_fa: str
    available: bool
    """آداپتور فعال دارد — کانال خاموش در رابط نمایش داده نمی‌شود."""
    requires_link: bool
    linked: bool
    """برای پیامک و ایمیل: نشانی در حساب هست (و ایمیل تأییدشده است)."""
    address_masked: str | None = None
    link_flow: Literal["DEEP_LINK", "CODE"] | None = None
    pending_link: bool = False


class QuietHoursOut(BaseModel):
    start: int
    end: int


class PreferencesOut(BaseModel):
    groups: list[GroupPreferenceOut]
    channels: list[ChannelStatusOut]
    quiet_hours: QuietHoursOut


class PreferencesIn(BaseModel):
    groups: dict[Group, list[Channel]] = Field(
        description="دسته ⇒ کانال‌ها. «داخل سامانه» همیشه افزوده می‌شود."
    )


# ── پیوند پیام‌رسان ────────────────────────────────────────────────────
class ChannelLinkIn(BaseModel):
    address: Annotated[str | None, Field(max_length=64)] = None
    """فقط برای ایتا: شناسهٔ عددی یا @نام‌کاربری."""


class ChannelLinkOut(BaseModel):
    channel: LinkableChannel
    flow: Literal["DEEP_LINK", "CODE"]
    expires_at: datetime
    deep_link: str | None = None


class ChannelConfirmIn(BaseModel):
    code: Annotated[str, Field(min_length=4, max_length=12)]


# ── مدیریت — /admin ────────────────────────────────────────────────────
class OutboxMessageOut(BaseModel):
    id: uuid.UUID
    channel: Channel
    recipient_masked: str
    template: str
    priority: Priority
    status: OutboxStatus
    status_fa: str
    attempts: int
    next_attempt_at: datetime
    last_error: str | None = None
    user_id: uuid.UUID | None = None
    notification_id: uuid.UUID | None = None
    created_at: datetime
    sent_at: datetime | None = None


class OutboxPageOut(BaseModel):
    items: list[OutboxMessageOut]
    total: int
    page: int
    page_size: int
    has_next: bool
    counts: dict[OutboxStatus, int]


class RetriedOut(BaseModel):
    retried: int


class TemplateOut(BaseModel):
    code: str
    channel: Channel
    kind_title_fa: str | None = None
    subject: str | None = None
    body: str
    variables: list[str]
    is_active: bool
    updated_at: datetime


class TemplateUpdateIn(BaseModel):
    subject: Annotated[str | None, Field(max_length=200)] = None
    body: Annotated[str, Field(min_length=1, max_length=4000)]
    is_active: bool = True


class TemplatePreviewIn(BaseModel):
    code: str
    channel: Channel
    subject: Annotated[str | None, Field(max_length=200)] = None
    body: Annotated[str, Field(min_length=1, max_length=4000)]
    values: dict[str, str] = Field(default_factory=dict)
    """مقدار دلخواه برای متغیرها؛ بقیه از نمونه‌های پیش‌فرض."""


class TemplatePreviewOut(BaseModel):
    subject: str | None = None
    body: str
    length: int
    sms_parts: int | None = None
    """برای پیامک: تعداد بخش — §14.7 «≤ ۷۰ نویسه برای یک بخش»."""


__all__ = [
    "ChannelConfirmIn",
    "ChannelLinkIn",
    "ChannelLinkOut",
    "ChannelStatusOut",
    "GroupPreferenceOut",
    "NotificationFeedOut",
    "NotificationOut",
    "OutboxMessageOut",
    "OutboxPageOut",
    "PreferencesIn",
    "PreferencesOut",
    "QuietHoursOut",
    "ReadAllOut",
    "RetriedOut",
    "TemplateOut",
    "TemplatePreviewIn",
    "TemplatePreviewOut",
    "TemplateUpdateIn",
    "UnreadCountOut",
]
