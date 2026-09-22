"""پایهٔ مدل‌های SQLAlchemy و قراردادهای مشترک — PRD §4.0.

| قاعده      | پیاده‌سازی                                                  |
|------------|-------------------------------------------------------------|
| کلید اصلی  | UUID با DEFAULT uuidv7() در سمت دیتابیس                      |
| زمان       | TIMESTAMPTZ با now() و تریگر set_updated_at                  |
| حذف نرم    | ستون deleted_at روی موجودیت‌های دامنه (D-15)                 |
| Enum       | TEXT + CHECK، نه ENUM بومی                                   |

قرارداد نام‌گذاری قیدها صریح تعریف شده تا Alembic نام‌های پایدار تولید کند
و مهاجرت‌های downgrade قابل نوشتن باشند.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, MetaData, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column

NAMING_CONVENTION: dict[str, str] = {
    "ix": "idx_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=NAMING_CONVENTION)


class Base(DeclarativeBase):
    metadata = metadata

    def __repr__(self) -> str:
        pk = getattr(self, "id", None)
        return f"<{type(self).__name__} {pk}>"


class UUIDPrimaryKeyMixin:
    """کلید اصلی UUIDv7 که در دیتابیس تولید می‌شود.

    تولید در دیتابیس انتخاب شده تا درج مستقیم SQL (مهاجرت، seed، اسکریپت)
    هم شناسهٔ درست بگیرد — PRD §4.0.
    """

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("uuidv7()"),
    )


class TimestampMixin:
    """created_at و updated_at با پیش‌فرض سمت سرور.

    به‌روزرسانی updated_at با تریگر set_updated_at انجام می‌شود، نه در پایتون،
    تا نوشتن مستقیم SQL هم آن را رعایت کند.
    """

    @declared_attr
    @classmethod
    def created_at(cls) -> Mapped[datetime]:
        return mapped_column(
            DateTime(timezone=True),
            nullable=False,
            server_default=text("now()"),
        )

    @declared_attr
    @classmethod
    def updated_at(cls) -> Mapped[datetime]:
        return mapped_column(
            DateTime(timezone=True),
            nullable=False,
            server_default=text("now()"),
        )


class SoftDeleteMixin:
    """حذف نرم — D-15. هیچ موجودیت دامنه‌ای فیزیکی حذف نمی‌شود."""

    @declared_attr
    @classmethod
    def deleted_at(cls) -> Mapped[datetime | None]:
        return mapped_column(DateTime(timezone=True), nullable=True, default=None)

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None


def jsonb_object_check(column: str) -> Any:
    """قید CHECK برای ستون JSONB که باید شیء باشد — PRD §4.0."""
    return text(f"jsonb_typeof({column}) = 'object'")
