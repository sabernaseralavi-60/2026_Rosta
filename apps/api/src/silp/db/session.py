"""نشست دیتابیس — موتور async و وابستگی FastAPI.

قاعده: یک نشست به‌ازای هر درخواست. commit صریح در لایهٔ سرویس انجام می‌شود،
نه خودکار؛ rollback در صورت خطا تضمین شده است (NFR-11).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from silp.core.config import Settings, get_settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def create_engine(settings: Settings) -> AsyncEngine:
    """ساخت موتور. مهلت کوئری ۱۰ ثانیه است تا به‌جای انتظار نامحدود،
    خطای صریح بدهد (NFR-11)."""
    connect_args: dict[str, Any] = {
        "server_settings": {
            "application_name": f"silp-api-{settings.environment}",
            "statement_timeout": str(settings.db_statement_timeout_ms),
            "timezone": "UTC",  # D-12 — ذخیره همیشه UTC
        },
        # کش عبارت‌های آماده با PgBouncer در حالت transaction ناسازگار است.
        "statement_cache_size": 0,
    }

    return create_async_engine(
        str(settings.database_url),
        echo=settings.db_echo,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_pre_ping=True,
        pool_recycle=1800,
        connect_args=connect_args,
    )


def get_engine() -> AsyncEngine:
    global _engine  # noqa: PLW0603
    if _engine is None:
        _engine = create_engine(get_settings())
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory  # noqa: PLW0603
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(),
            expire_on_commit=False,
            autoflush=False,
        )
    return _session_factory


async def dispose_engine() -> None:
    """بستن استخر اتصال هنگام خاموشی اپ."""
    global _engine, _session_factory  # noqa: PLW0603
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None


async def get_session() -> AsyncIterator[AsyncSession]:
    """وابستگی FastAPI — یک نشست به‌ازای هر درخواست."""
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """نشست برای کارهای پس‌زمینه و اسکریپت‌ها — با commit خودکار در موفقیت."""
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
