"""مدل‌های هویت و دسترسی — PRD §4.2.

جداول: users, roles, user_roles, refresh_tokens, otp_challenges.
مهاجرت متناظر: 0002_identity.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import CITEXT, INET
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from silp.db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    pass

USER_STATUSES = ("ACTIVE", "SUSPENDED", "DEACTIVATED")
SCOPE_TYPES = ("GLOBAL", "OFFERING", "PROJECT", "VENTURE")
OTP_CHANNELS = ("SMS", "EMAIL")
OTP_PURPOSES = ("LOGIN", "VERIFY_EMAIL", "VERIFY_MOBILE", "RESET_PASSWORD")

# مقدار جایگزین NULL در کلید اصلی user_roles، تا قید یکتایی روی قلمرو
# سراسری هم کار کند (NULL در PostgreSQL با NULL برابر نیست).
NULL_SCOPE = uuid.UUID("00000000-0000-0000-0000-000000000000")


def _in_list(column: str, values: tuple[str, ...]) -> str:
    joined = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({joined})"


class User(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "users"

    mobile: Mapped[str | None] = mapped_column(Text, unique=True)
    email: Mapped[str | None] = mapped_column(CITEXT, unique=True)
    username: Mapped[str | None] = mapped_column(Text, unique=True)
    # NULL یعنی کاربر فقط با OTP وارد می‌شود و رمزی تعریف نکرده است.
    password_hash: Mapped[str | None] = mapped_column(Text)

    mobile_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'ACTIVE'"))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locale: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'fa'"))
    timezone: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'Asia/Tehran'")
    )

    roles: Mapped[list[UserRole]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
        foreign_keys="UserRole.user_id",
    )

    __table_args__ = (
        CheckConstraint(_in_list("status", USER_STATUSES), name="status_valid"),
        CheckConstraint("mobile IS NOT NULL OR email IS NOT NULL", name="contact_required"),
        # شمارهٔ موبایل ایرانی، نرمال‌شده — FR-AUTH-01
        CheckConstraint(r"mobile IS NULL OR mobile ~ '^09\d{9}$'", name="mobile_format"),
        Index("idx_users_status", "status", postgresql_where=text("deleted_at IS NULL")),
    )

    @property
    def is_active(self) -> bool:
        return self.status == "ACTIVE" and self.deleted_at is None


class Role(Base):
    """§6.1 — جدول مرجع نقش‌ها. کلید اصلی، خودِ کد است."""

    __tablename__ = "roles"

    code: Mapped[str] = mapped_column(Text, primary_key=True)
    title_fa: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)


class UserRole(Base):
    """اعطای نقش، احتمالاً محدود به یک قلمرو — §6.1.

    نقش می‌تواند دامنه‌دار باشد؛ این از ساخت جداول عضویت موازی جلوگیری می‌کند.
    """

    __tablename__ = "user_roles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    role_code: Mapped[str] = mapped_column(Text, ForeignKey("roles.code"), primary_key=True)
    scope_type: Mapped[str] = mapped_column(Text, primary_key=True, server_default=text("'GLOBAL'"))
    # ستون تولیدشده در مهاجرت به کلید اصلی افزوده می‌شود؛ اینجا scope_id
    # خام نگه داشته می‌شود و یکتایی با ایندکس یکتای شرطی تضمین می‌گردد.
    scope_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True))

    granted_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id")
    )
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="roles", foreign_keys=[user_id])
    role: Mapped[Role] = relationship(lazy="joined")

    __table_args__ = (
        CheckConstraint(_in_list("scope_type", SCOPE_TYPES), name="scope_type_valid"),
        CheckConstraint(
            "(scope_type = 'GLOBAL' AND scope_id IS NULL)"
            " OR (scope_type <> 'GLOBAL' AND scope_id IS NOT NULL)",
            name="scope_id_matches_type",
        ),
        Index("idx_user_roles_scope", "scope_type", "scope_id"),
        Index(
            "uq_user_roles_grant",
            "user_id",
            "role_code",
            "scope_type",
            text("COALESCE(scope_id, '00000000-0000-0000-0000-000000000000'::uuid)"),
            unique=True,
        ),
    )

    def is_effective(self, at: datetime) -> bool:
        return self.expires_at is None or self.expires_at > at


class RefreshToken(UUIDPrimaryKeyMixin, Base):
    """FR-AUTH-03 — چرخش اجباری با تشخیص سرقت توکن.

    `family_id` همهٔ توکن‌های زنجیرهٔ یک ورود را به هم می‌بندد. اگر یک توکن
    باطل‌شده دوباره استفاده شود، کل خانواده باطل می‌گردد.
    """

    __tablename__ = "refresh_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    family_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("refresh_tokens.id")
    )

    user_agent: Mapped[str | None] = mapped_column(Text)
    ip_address: Mapped[str | None] = mapped_column(INET)

    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        Index(
            "idx_refresh_user_active",
            "user_id",
            postgresql_where=text("revoked_at IS NULL"),
        ),
        Index("idx_refresh_family", "family_id"),
    )

    def is_usable(self, at: datetime) -> bool:
        return self.revoked_at is None and self.expires_at > at


class OTPChallenge(UUIDPrimaryKeyMixin, Base):
    """FR-AUTH-01 — چالش کد یک‌بارمصرف. کد به‌صورت bcrypt ذخیره می‌شود."""

    __tablename__ = "otp_challenges"

    channel: Mapped[str] = mapped_column(Text, nullable=False)
    destination: Mapped[str] = mapped_column(Text, nullable=False)
    code_hash: Mapped[str] = mapped_column(Text, nullable=False)
    purpose: Mapped[str] = mapped_column(Text, nullable=False)

    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("3"))

    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ip_address: Mapped[str | None] = mapped_column(INET)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint(_in_list("channel", OTP_CHANNELS), name="channel_valid"),
        CheckConstraint(_in_list("purpose", OTP_PURPOSES), name="purpose_valid"),
        CheckConstraint("attempts >= 0 AND attempts <= max_attempts", name="attempts_bounded"),
        Index(
            "idx_otp_dest_active",
            "destination",
            "purpose",
            postgresql_where=text("consumed_at IS NULL"),
        ),
        UniqueConstraint("id", "destination", name="id_destination"),
    )

    @property
    def is_consumed(self) -> bool:
        return self.consumed_at is not None

    @property
    def attempts_exhausted(self) -> bool:
        return self.attempts >= self.max_attempts

    def is_open(self, at: datetime) -> bool:
        """چالش هنوز قابل تأیید است؟"""
        return not self.is_consumed and not self.attempts_exhausted and self.expires_at > at
