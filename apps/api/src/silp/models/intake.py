"""مدل درخواست‌های ورودی (مسئله / همکاری) — ADR-0030، مهاجرت ۰۰۲۴."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, CITEXT, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from silp.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

INTAKE_KINDS = ("INTAKE", "COLLABORATION")
INTAKE_STATUSES = ("NEW", "IN_REVIEW", "ACCEPTED", "DECLINED", "ARCHIVED")


def _in_list(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class IntakeRequest(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """یک «مسئله / نیاز» یا «درخواست همکاری» از بازدیدکننده.

    `user_id` تهی است مگر شمارهٔ تماس با یک کاربر موجود یکی باشد.
    """

    __tablename__ = "intake_requests"

    kind: Mapped[str] = mapped_column(Text, nullable=False)
    tracking_code: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'NEW'"))
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    contact_name: Mapped[str] = mapped_column(Text, nullable=False)
    contact_mobile: Mapped[str | None] = mapped_column(Text)
    contact_email: Mapped[str | None] = mapped_column(CITEXT)
    organization: Mapped[str | None] = mapped_column(Text)
    need_type: Mapped[str | None] = mapped_column(Text)
    services: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'::text[]")
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    #: یادداشت خصوصی مالک؛ به مشتری نمی‌رسد (ADR-0032).
    owner_note: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint(_in_list("kind", INTAKE_KINDS), name="kind_valid"),
        CheckConstraint(_in_list("status", INTAKE_STATUSES), name="status_valid"),
        CheckConstraint(
            "contact_mobile IS NOT NULL OR contact_email IS NOT NULL", name="contact_required"
        ),
        CheckConstraint(
            r"contact_mobile IS NULL OR contact_mobile ~ '^09\d{9}$'", name="mobile_format"
        ),
        CheckConstraint("length(summary) BETWEEN 5 AND 4000", name="summary_length"),
        CheckConstraint(
            "owner_note IS NULL OR length(owner_note) <= 4000", name="owner_note_length"
        ),
        Index("idx_intake_requests_inbox", "kind", "status", text("created_at DESC")),
        Index("idx_intake_requests_user", "user_id"),
        Index("idx_intake_requests_mobile", "contact_mobile"),
    )


class IntakeEvent(UUIDPrimaryKeyMixin, Base):
    """یک قدم در تاریخچهٔ رسیدگی. `public_note` تنها بخشی است که مشتری می‌بیند."""

    __tablename__ = "intake_events"

    request_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("intake_requests.id", ondelete="CASCADE"), nullable=False
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    from_status: Mapped[str | None] = mapped_column(Text)
    to_status: Mapped[str] = mapped_column(Text, nullable=False)
    public_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint(_in_list("to_status", INTAKE_STATUSES), name="to_status_valid"),
        CheckConstraint(
            "public_note IS NULL OR length(public_note) BETWEEN 1 AND 1000",
            name="public_note_length",
        ),
        Index("idx_intake_events_request", "request_id", "id"),
    )
