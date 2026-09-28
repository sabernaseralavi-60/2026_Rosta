"""فهرست دانشجویان هر ارائه و ادعای هویت — ADR-0035، مهاجرت ۰۰۲۹."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Text, text
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from silp.db.base import Base, UUIDPrimaryKeyMixin

CLAIM_STATUSES = ("AWAITING_CONFIRM", "AWAITING_CODE", "DONE", "CANCELLED")


class RosterEntry(UUIDPrimaryKeyMixin, Base):
    """یک دانشجوی فهرست یک ارائه. شمارهٔ دانشجویی فقط به‌صورت HMAC."""

    __tablename__ = "roster_entries"

    offering_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("course_offerings.id", ondelete="CASCADE"), nullable=False
    )
    first_name: Mapped[str] = mapped_column(Text, nullable=False)
    last_name: Mapped[str] = mapped_column(Text, nullable=False)
    student_no_hash: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str | None] = mapped_column(CITEXT)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint("student_no_hash ~ '^[0-9a-f]{64}$'", name="hash_format"),
        Index("uq_roster_entries_offering_no", "offering_id", "student_no_hash", unique=True),
        Index("idx_roster_entries_hash", "student_no_hash"),
        Index("idx_roster_entries_user", "user_id"),
    )


class RosterClaim(UUIDPrimaryKeyMixin, Base):
    """یک تلاش برای گرفتن حساب با موبایل + شمارهٔ دانشجویی.

    کد ایمیلی فقط به نشانیِ **ثبت‌شده در فهرست** می‌رود، نه نشانی‌ای که مهاجم بدهد.
    """

    __tablename__ = "roster_claims"

    student_no_hash: Mapped[str] = mapped_column(Text, nullable=False)
    mobile: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str | None] = mapped_column(CITEXT)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'AWAITING_CONFIRM'")
    )
    code_hash: Mapped[str | None] = mapped_column(Text)
    code_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    code_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    code_sends: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    ip_address: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "status IN ('AWAITING_CONFIRM', 'AWAITING_CODE', 'DONE', 'CANCELLED')",
            name="status_valid",
        ),
        CheckConstraint(r"mobile ~ '^09\d{9}$'", name="mobile_format"),
        Index("idx_roster_claims_hash_created", "student_no_hash", text("created_at DESC")),
    )
