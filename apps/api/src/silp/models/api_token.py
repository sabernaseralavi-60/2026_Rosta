"""توکن دسترسی برنامه‌ای (PAT) — ADR-0031، مهاجرت ۰۰۲۵.

برای ابزارهایی که آدم پشتشان نیست و OTP نمی‌توانند بزنند: `vault push` از
رایانهٔ مالک. توکن **فقط یک‌بار** هنگام ساخت دیده می‌شود؛ در دیتابیس فقط
`sha256` آن است (توکن ۲۵۶ بیتیِ تصادفی است، پس هش تند کافی است).

هر توکن به یک کاربر و چند «دامنه» (scope) گره خورده است. دامنه فقط سقف
را پایین می‌آورد: توکن هرگز چیزی بیش از مجوزهای *همین لحظهٔ* صاحبش نمی‌دهد.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Text, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from silp.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

#: دامنه‌های شناخته‌شده. افزودن دامنه = افزودن این‌جا + مسیری که آن را می‌طلبد.
TOKEN_SCOPES = ("vault:publish",)
TOKEN_PREFIX = "silp_pat_"  # noqa: S105 — پیشوند عمومی، نه رمز


class ApiToken(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "api_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    token_hash: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    #: چند نویسهٔ آغازین (بی‌خطر)، تا مالک توکن‌ها را در فهرست تشخیص دهد.
    token_hint: Mapped[str] = mapped_column(Text, nullable=False)
    scopes: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'::text[]")
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("length(name) BETWEEN 1 AND 80", name="name_length"),
        CheckConstraint("cardinality(scopes) >= 1", name="scopes_required"),
        Index("idx_api_tokens_user", "user_id"),
    )
