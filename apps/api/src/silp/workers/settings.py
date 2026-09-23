"""کارگر ARQ — D-07.

کارهای نگهداری از M0 هستند. `close_expired_attempts` در M4 افزوده شد
(§7.11، FR-QUIZ-02). چهار کار گیمیفیکیشن و سلامت پروژه از M5 هستند؛
ارسال صف، یادآوری مهلت، خلاصهٔ هفتگی، انتشار زمان‌بندی‌شدهٔ هفته و
پاک‌سازی اعلان از M6. آزادسازی رزرو موضوع و اعلان آگهی منقضی از M7 بخش ب.

همهٔ زمان‌بندی‌ها به وقت UTC است. «ساعت ۲ بامداد» سند به وقت تهران است،
یعنی ۲۲:۳۰ UTC شب قبل.
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
from silp.services.attempt_service import AttemptService
from silp.services.badge_service import BadgeService
from silp.services.notification_service import NotificationService
from silp.services.opening_service import OpeningService
from silp.services.otp_service import OTPService
from silp.services.outbox_service import OutboxService
from silp.services.point_listeners import LearningPoints
from silp.services.points_service import PointsService
from silp.services.project_health_service import ProjectHealthService
from silp.services.reminder_service import ReminderService
from silp.services.teaching_service import TeachingService
from silp.services.token_service import TokenService
from silp.services.topic_service import TopicService

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


async def close_expired_attempts(ctx: dict[str, Any]) -> int:
    """بستن خودکار تلاش‌های منقضی — §7.11، §7.3 قاعدهٔ ۲.

    **به `submit` کلاینت اتکا نمی‌شود.** دانشجویی که لپ‌تاپش خاموش شد یا
    تبش را بست، پاسخ‌های ذخیره‌شده‌اش باید تصحیح شود؛ اگر منتظر کلاینت
    می‌ماندیم، تلاشش تا ابد `IN_PROGRESS` می‌ماند و نمره‌ای نمی‌گرفت.

    بی‌اثر در تکرار است (الزام §7.11): هر تلاش با قفل سطری و شرط
    `status = 'IN_PROGRESS'` برداشته می‌شود، پس دو اجرای هم‌زمان یک
    تلاش را دو بار تصحیح نمی‌کنند.
    """
    async with session_scope() as session:
        closed = await AttemptService(session).auto_close_expired()
    if closed:
        log.info("attempts_auto_closed", count=closed)
    return closed


async def refresh_point_totals(ctx: dict[str, Any]) -> None:
    """§7.11 — نمای تجمیعی جدول رتبه‌بندی. `CONCURRENTLY`: خواندن را قفل نمی‌کند."""
    async with session_scope() as session:
        await PointsService(session).refresh_totals()
        await session.commit()


async def evaluate_badges(ctx: dict[str, Any]) -> int:
    """§9.5 — نشان‌های کاربرانی که اخیراً امتیاز گرفته‌اند. خارج از مسیر درخواست."""
    async with session_scope() as session:
        awarded = await BadgeService(session).evaluate_recent()
    if awarded:
        log.info("badges_evaluated", awarded=awarded)
    return awarded


async def evaluate_all_badges(ctx: dict[str, Any]) -> int:
    """جارو کردن شبانهٔ همهٔ کاربران — جاماندهٔ زمان خرابی کارگر را می‌گیرد."""
    async with session_scope() as session:
        return await BadgeService(session).evaluate_recent(all_users=True)


async def release_quiz_points(ctx: dict[str, Any]) -> int:
    """امتیاز آزمون‌های «نتیجه پس از پایان» که تازه بسته شده‌اند — ADR-0012."""
    async with session_scope() as session:
        return await LearningPoints(session).release_closed_quizzes()


async def compute_project_health(ctx: dict[str, Any]) -> int:
    """§7.4 — شاخص سلامت روزانهٔ پروژه‌های در جریان."""
    async with session_scope() as session:
        changed = await ProjectHealthService(session).recompute()
    log.info("project_health_computed", changed=changed)
    return changed


async def dispatch_outbox(ctx: dict[str, Any]) -> int:
    """§7.10 — هر ۵ ثانیه. `SKIP LOCKED`: چند کارگر هم‌زمان با هم تداخل ندارند."""
    async with session_scope() as session:
        stats = await OutboxService(session).dispatch()
    return stats.sent


async def send_deadline_reminders(ctx: dict[str, Any]) -> int:
    """§7.11 — یادآوری مهلت‌های ۳ و ۱ روزه. بی‌اثر در تکرار (`dedup_key`)."""
    async with session_scope() as session:
        stats = await ReminderService(session).send_deadline_reminders()
    return stats.milestones + stats.quizzes


async def weekly_digest(ctx: dict[str, Any]) -> int:
    """§7.11 — خلاصهٔ هفتگی دانشجو و استاد. بی‌اثر در تکرار."""
    async with session_scope() as session:
        stats = await ReminderService(session).weekly_digest()
    return stats.students + stats.teachers


async def publish_scheduled_weeks(ctx: dict[str, Any]) -> int:
    """§7.11، FR-EDU-02 — هفته‌هایی که زمان انتشارشان رسیده. اعلان هم همین‌جا."""
    published = 0
    async with session_scope() as session:
        service = TeachingService(session)
        for week in await service.due_weeks():
            await service.publish_week(week_id=week.id)
            published += 1
    if published:
        log.info("scheduled_weeks_published", count=published)
    return published


async def cleanup_notifications(ctx: dict[str, Any]) -> None:
    """§4.12 — آرشیو اعلان خوانده‌شدهٔ ۹۰ روزه، حذف پیام ارسال‌شدهٔ ۳۰ روزه."""
    async with session_scope() as session:
        archived, purged = await NotificationService(session).cleanup()
    log.info("notifications_cleaned", archived=archived, outbox_purged=purged)


async def release_stale_topics(ctx: dict[str, Any]) -> int:
    """§7.11، FR-RES-03 — هشدار روز ۲۵ و آزادسازی رزرو ۳۰ روز بی‌تحرک."""
    async with session_scope() as session:
        stats = await TopicService(session).release_stale()
    return stats.released


async def expire_team_openings(ctx: dict[str, Any]) -> int:
    """§7.11 — آگهی‌دهندهٔ آگهی تازه‌منقضی خبردار می‌شود تا تمدیدش کند.

    وضعیت عوض نمی‌شود: «منقضی» از `expires_at` خوانده می‌شود (ADR-0015).
    """
    async with session_scope() as session:
        return await OpeningService(session).notify_expired()


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
    functions: ClassVar[list[Any]] = [
        purge_expired_otps,
        purge_expired_tokens,
        close_expired_attempts,
        refresh_point_totals,
        evaluate_badges,
        evaluate_all_badges,
        release_quiz_points,
        compute_project_health,
        dispatch_outbox,
        send_deadline_reminders,
        weekly_digest,
        publish_scheduled_weeks,
        cleanup_notifications,
        release_stale_topics,
        expire_team_openings,
    ]
    cron_jobs: ClassVar[list[Any]] = [
        # هر ساعت، دقیقهٔ ۷ — عمداً سر ساعت نیست تا با بقیهٔ کارها تصادم نکند.
        cron(purge_expired_otps, minute=7),
        # روزانه، ساعت ۳:۲۰ بامداد به وقت UTC.
        cron(purge_expired_tokens, hour=3, minute=20),
        # هر ۶۰ ثانیه — §7.11. تأخیر بیشتر یعنی دانشجویی که زمانش تمام
        # شده، تا یک دقیقه نتیجه‌اش را نمی‌بیند؛ این سقف پذیرفته است.
        cron(close_expired_attempts, second={0}, run_at_startup=True),
        # §7.11 — هر ۱۵ دقیقه. دقیقه‌های ۲، ۱۷، ۳۲، ۴۷ تا با بقیه هم‌زمان نشود.
        cron(refresh_point_totals, minute={2, 17, 32, 47}),
        # §9.5 و ADR-0012 — هر ۱۰ دقیقه.
        cron(evaluate_badges, minute={4, 14, 24, 34, 44, 54}),
        cron(release_quiz_points, minute={1, 11, 21, 31, 41, 51}),
        # ۴:۴۰ بامداد تهران.
        cron(evaluate_all_badges, hour=1, minute=10),
        # §7.11 — ۲ بامداد تهران.
        cron(compute_project_health, hour=22, minute=30),
        # §7.10 — هر ۵ ثانیه. `unique` پیش‌فرض ARQ دو اجرای هم‌زمان یک
        # نوبت را نمی‌گذارد؛ هم‌پوشانی نوبت‌ها را `SKIP LOCKED` مدیریت می‌کند.
        cron(dispatch_outbox, second=set(range(0, 60, 5)), run_at_startup=True),
        # §7.11 — ۹ صبح تهران = ۵:۳۰ UTC.
        cron(send_deadline_reminders, hour=5, minute=30),
        # §7.11 — شنبه ۹ صبح تهران. ARQ دوشنبه را ۰ می‌شمارد، پس شنبه ۵ است.
        cron(weekly_digest, weekday=5, hour=5, minute=35),
        # §7.11 — هر ۵ دقیقه.
        cron(publish_scheduled_weeks, minute=set(range(3, 60, 5))),
        # §7.11 «cleanup_expired_data» — یکشنبه ۴ بامداد تهران = ۰:۳۰ UTC.
        cron(cleanup_notifications, weekday=6, hour=0, minute=30),
        # §7.11 — ۳ بامداد تهران = ۲۳:۳۰ UTC شب قبل.
        cron(release_stale_topics, hour=23, minute=30),
        cron(expire_team_openings, hour=23, minute=35),
    ]
    on_startup = startup
    on_shutdown = shutdown
    max_jobs = 10
    job_timeout = 300
    keep_result = 3600
    # ARQ این را به‌صورت صفت می‌خواند، نه متد.
    redis_settings = RedisSettings.from_dsn(str(get_settings().redis_url))
