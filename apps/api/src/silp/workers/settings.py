"""کارگر ARQ — D-07.

در M0 فقط کارهای نگهداری وجود دارند. کارهای دامنه‌ای (انتشار زمان‌بندی‌شدهٔ
هفته، بستن تلاش‌های منقضی، ارسال اعلان) در M3 تا M6 اضافه می‌شوند.
"""

from __future__ import annotations

from typing import Any, ClassVar

from arq.connections import RedisSettings
from arq.cron import cron

from silp.core.config import get_settings
from silp.core.logging import configure_logging, get_logger
from silp.core.redis import close_redis
from silp.db.session import dispose_engine, session_scope
from silp.integrations.sms import MemorySMSSender
from silp.services.otp_service import OTPService
from silp.services.token_service import TokenService

log = get_logger("silp.worker")


async def purge_expired_otps(ctx: dict[str, Any]) -> int:
    """NFR-01 — OTP پس از ۲۴ ساعت فیزیکی حذف می‌شود.

    این کار بی‌اثر در تکرار است: اجرای دوباره چیزی را خراب نمی‌کند.
    """
    settings = get_settings()
    async with session_scope() as session:
        # پاک‌سازی چیزی ارسال نمی‌کند؛ آداپتور حافظه‌ای فقط برای کامل کردن
        # امضای سرویس است.
        service = OTPService(session, settings, MemorySMSSender())
        removed = await service.purge_expired()
    log.info("otp_purged", removed=removed)
    return removed


async def purge_expired_tokens(ctx: dict[str, Any]) -> int:
    """حذف توکن‌های مدت‌ها منقضی. یک هفته برای حسابرسی نگه داشته می‌شوند."""
    settings = get_settings()
    async with session_scope() as session:
        removed = await TokenService(session, settings).purge_expired()
    log.info("refresh_tokens_purged", removed=removed)
    return removed


async def startup(ctx: dict[str, Any]) -> None:
    settings = get_settings()
    configure_logging(
        settings.log_level,
        renderer="console" if settings.is_development else "json",
    )
    log.info("worker_starting", environment=settings.environment)


async def shutdown(ctx: dict[str, Any]) -> None:
    await close_redis()
    await dispose_engine()
    log.info("worker_stopped")


class WorkerSettings:
    functions: ClassVar[list[Any]] = [purge_expired_otps, purge_expired_tokens]
    cron_jobs: ClassVar[list[Any]] = [
        # هر ساعت، دقیقهٔ ۷ — عمداً سر ساعت نیست تا با بقیهٔ کارها تصادم نکند.
        cron(purge_expired_otps, minute=7),
        # روزانه، ساعت ۳:۲۰ بامداد به وقت UTC.
        cron(purge_expired_tokens, hour=3, minute=20),
    ]
    on_startup = startup
    on_shutdown = shutdown
    max_jobs = 10
    job_timeout = 300
    keep_result = 3600
    # ARQ این را به‌صورت صفت می‌خواند، نه متد.
    redis_settings = RedisSettings.from_dsn(str(get_settings().redis_url))
