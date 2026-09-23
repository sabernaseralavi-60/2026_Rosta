"""مدل‌های مدیریت — PRD §4.9، FR-ADM-02.

جدول: audit_logs. مهاجرت متناظر: 0016_admin.

لاگ حسابرسی **فقط افزودنی** است: تریگر `audit_logs_append_only` در
دیتابیس هر `UPDATE` و `DELETE` را رد می‌کند، حتی برای مالک جدول. پس این
مدل فقط درج می‌شود و هیچ سرویسی نباید ردیفش را تغییر دهد (ADR-0017).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, Index, Text, text
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from silp.db.base import Base, UUIDPrimaryKeyMixin


class AuditLog(UUIDPrimaryKeyMixin, Base):
    """یک عمل حساس: کیست، چه کرد، روی چه چیزی، کی، از کجا، قبل و بعد.

    `actor_id` کلید خارجی ندارد: لاگ هفت سال می‌ماند (§4.12) و نباید به
    ردیفی گره بخورد که فرایند رسمی حذف ممکن است پاکش کند؛ `ON DELETE SET
    NULL` هم خودش یک `UPDATE` روی لاگ بود.
    """

    __tablename__ = "audit_logs"

    actor_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True))
    # §6.5 — در جعل هویت، `actor_id` کاربر هدف است و این، پشتیبان.
    impersonated_by: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True))
    action: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True))
    before: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    ip_address: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint("action ~ '^[A-Z][A-Z_]*$'", name="action_code"),
        Index("idx_audit_entity", "entity_type", "entity_id", text("created_at DESC")),
        Index("idx_audit_actor", "actor_id", text("created_at DESC")),
        Index("idx_audit_created", text("created_at DESC")),
        Index("idx_audit_action", "action", text("created_at DESC")),
        Index(
            "idx_audit_impersonator",
            "impersonated_by",
            text("created_at DESC"),
            postgresql_where=text("impersonated_by IS NOT NULL"),
        ),
    )


__all__ = ["AuditLog"]
