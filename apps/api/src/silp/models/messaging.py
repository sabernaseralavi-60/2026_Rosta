"""مدل‌های اعلان و پیام‌رسانی — PRD §4.9. مهاجرت متناظر: 0013_messaging.

| جدول | نقش |
|------|-----|
| `notifications` | مرکز اعلان داخلی (FR-MSG-01) |
| `notification_preferences` | کانال‌های هر دستهٔ اعلان برای هر کاربر (FR-MSG-02) |
| `user_channels` | شناسهٔ گفت‌وگوی تلگرام و ایتا پس از پیوند — ADR-0013 |
| `outbox_messages` | صف ارسال بیرونی با الگوی Outbox (D-08، §7.10) |
| `message_templates` | متن هر نوع اعلان برای هر کانال (FR-MSG-03) |

ایندکس‌ها و قیدها باید با مهاجرت یکی بمانند؛ `alembic check` در CI
اختلاف را می‌گیرد.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    PrimaryKeyConstraint,
    SmallInteger,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from silp.db.base import Base, UUIDPrimaryKeyMixin

OUTBOX_STATUSES = ("QUEUED", "SENDING", "SENT", "FAILED", "DEAD")
#: وضعیت‌هایی که کارگر ارسال می‌خواند — `SENDING` فقط با اجارهٔ منقضی.
DISPATCHABLE_STATUSES = ("QUEUED", "FAILED", "SENDING")
OUTBOX_STATUS_TITLE_FA: dict[str, str] = {
    "QUEUED": "در صف",
    "SENDING": "در حال ارسال",
    "SENT": "ارسال شد",
    "FAILED": "ناموفق، تلاش دوباره",
    "DEAD": "ارسال نشد",
}


class Notification(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "notifications"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    kind_group: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    action_url: Mapped[str | None] = mapped_column(Text)
    priority: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'NORMAL'"))
    data: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    dedup_key: Mapped[str | None] = mapped_column(Text)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint(
            "action_url IS NULL OR (action_url LIKE '/%' AND action_url NOT LIKE '//%')",
            name="action_url_internal",
        ),
        Index(
            "idx_notifications_unread",
            "user_id",
            text("created_at DESC"),
            postgresql_where=text("read_at IS NULL AND archived_at IS NULL"),
        ),
        Index(
            "idx_notifications_feed",
            "user_id",
            text("id DESC"),
            postgresql_where=text("archived_at IS NULL"),
        ),
        Index(
            "idx_notifications_dedup",
            "user_id",
            "dedup_key",
            unique=True,
            postgresql_where=text("dedup_key IS NOT NULL"),
        ),
    )

    @property
    def is_read(self) -> bool:
        return self.read_at is not None


class NotificationPreference(Base):
    __tablename__ = "notification_preferences"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    kind_group: Mapped[str] = mapped_column(Text, nullable=False)
    channels: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{IN_APP}'")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (PrimaryKeyConstraint("user_id", "kind_group"),)


class UserChannel(Base):
    __tablename__ = "user_channels"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    channel: Mapped[str] = mapped_column(Text, nullable=False)
    address: Mapped[str | None] = mapped_column(Text)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    link_code_hash: Mapped[str | None] = mapped_column(Text)
    link_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    link_attempts: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default=text("0")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        PrimaryKeyConstraint("user_id", "channel"),
        Index(
            "idx_user_channels_address",
            "channel",
            "address",
            unique=True,
            postgresql_where=text("verified_at IS NOT NULL"),
        ),
        Index(
            "idx_user_channels_link_code",
            "link_code_hash",
            unique=True,
            postgresql_where=text("link_code_hash IS NOT NULL"),
        ),
    )

    @property
    def is_linked(self) -> bool:
        return self.verified_at is not None and self.address is not None


class OutboxMessage(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "outbox_messages"

    channel: Mapped[str] = mapped_column(Text, nullable=False)
    recipient: Mapped[str] = mapped_column(Text, nullable=False)
    template: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    notification_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("notifications.id", ondelete="SET NULL")
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    priority: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'NORMAL'"))
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'QUEUED'"))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    last_error: Mapped[str | None] = mapped_column(Text)
    provider_message_id: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index(
            "idx_outbox_dispatch",
            "next_attempt_at",
            postgresql_where=text("status IN ('QUEUED','FAILED','SENDING')"),
        ),
        Index("idx_outbox_status", "status", text("created_at DESC")),
        Index("idx_outbox_notification", "notification_id"),
    )


class MessageTemplate(Base):
    __tablename__ = "message_templates"

    code: Mapped[str] = mapped_column(Text, nullable=False)
    channel: Mapped[str] = mapped_column(Text, nullable=False)
    subject: Mapped[str | None] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    variables: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'")
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (PrimaryKeyConstraint("code", "channel"),)


__all__ = [
    "DISPATCHABLE_STATUSES",
    "OUTBOX_STATUSES",
    "OUTBOX_STATUS_TITLE_FA",
    "MessageTemplate",
    "Notification",
    "NotificationPreference",
    "OutboxMessage",
    "UserChannel",
]
