"""معیارهای Prometheus — NFR-14، M7-17.

دو نوع معیار اینجاست و از دو جا می‌آیند:

* **فرایندی** (تأخیر HTTP، مدت و شکست کار پس‌زمینه): در حافظهٔ هر فرایند
  شمرده می‌شوند. API با چهار کارگر uvicorn اجرا می‌شود، پس اگر
  `PROMETHEUS_MULTIPROC_DIR` تنظیم باشد، حالت چندفرایندی prometheus_client
  به کار می‌رود و هر خراش جمع همهٔ کارگرها را می‌بیند.
* **کسب‌وکاری و صف** (کاربر، درخواست، امتیاز، عمق صف ارسال، آزمون فعال،
  اتصال دیتابیس): هنگام خراش از خود PostgreSQL خوانده می‌شوند. شمارندهٔ
  درون‌فرایندی با هر راه‌اندازی مجدد صفر می‌شد و بین کارگرها تقسیم؛ دیتابیس
  منبع حقیقت است.

`/metrics` از Nginx عبور نمی‌کند (فقط `/api/` و `/health` به API می‌رسند) و
اگر `METRICS_TOKEN` تنظیم شده باشد، توکن Bearer هم می‌خواهد (ADR-0018).
"""

from __future__ import annotations

import functools
import os
import time
from collections.abc import Callable, Coroutine
from typing import Any, ParamSpec, TypeVar

from prometheus_client import REGISTRY as DEFAULT_REGISTRY
from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
    multiprocess,
)
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from silp.core.logging import get_logger
from silp.domain.notifications.catalog import EXTERNAL_CHANNELS
from silp.models.messaging import OUTBOX_STATUSES

log = get_logger("silp.metrics")

# الگوی مسیرِ پیدانشده. مسیر خام برچسب نمی‌شود: هر درخواست تصادفی ۴۰۴ یک
# سری زمانی تازه می‌ساخت و Prometheus را از حافظه می‌انداخت.
UNMATCHED_ROUTE = "__unmatched__"

# بودجهٔ NFR-06 بین ۲۰۰ms و ۲s است؛ سطل‌ها دور همان بازه متراکم‌اند.
HTTP_BUCKETS = (0.025, 0.05, 0.1, 0.2, 0.3, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 5.0, 10.0)
JOB_BUCKETS = (0.05, 0.1, 0.5, 1.0, 5.0, 15.0, 30.0, 60.0, 120.0, 300.0)

HTTP_DURATION = Histogram(
    "http_request_duration_seconds",
    "مدت پاسخ HTTP به تفکیک الگوی مسیر",
    ["route", "method", "status"],
    buckets=HTTP_BUCKETS,
)
# برچسب `task` و نه `job` (نام NFR-14): `job` برچسب هدف خود Prometheus است و
# برچسب هم‌نام به `exported_job` تغییر نام می‌داد — هشدارهای کار هرگز
# نمی‌سوختند. آزمون زندهٔ M7-17 این را نشان داد.
JOB_DURATION = Histogram(
    "background_job_duration_seconds",
    "مدت اجرای کار پس‌زمینه",
    ["task"],
    buckets=JOB_BUCKETS,
)
JOB_FAILURES = Counter(
    "background_job_failures",
    "شکست کار پس‌زمینه",
    ["task"],
)
JOB_LAST_SUCCESS = Gauge(
    "silp_background_job_last_success_timestamp_seconds",
    "زمان آخرین اجرای موفق هر کار",
    ["task"],
    multiprocess_mode="max",
)


def observe_request(route: str, method: str, status: int, seconds: float) -> None:
    HTTP_DURATION.labels(route=route, method=method, status=str(status)).observe(seconds)


P = ParamSpec("P")
R = TypeVar("R")


def timed_job(
    fn: Callable[P, Coroutine[Any, Any, R]],
) -> Callable[P, Coroutine[Any, Any, R]]:
    """مدت، شکست و آخرین موفقیت یک کار ARQ.

    `functools.wraps` نام تابع را نگه می‌دارد؛ ARQ کار را با همان نام
    می‌شناسد و صف‌های موجود در Redis بعد از استقرار گم نمی‌شوند.
    """
    name = fn.__name__

    @functools.wraps(fn)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        started = time.perf_counter()
        try:
            result = await fn(*args, **kwargs)
        except Exception:
            JOB_FAILURES.labels(task=name).inc()
            raise
        finally:
            JOB_DURATION.labels(task=name).observe(time.perf_counter() - started)
        JOB_LAST_SUCCESS.labels(task=name).set(time.time())
        return result

    return wrapper


def _process_registry() -> CollectorRegistry:
    if os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)  # type: ignore[no-untyped-call]
        return registry
    return DEFAULT_REGISTRY


# ── معیارهای خوانده‌شده از دیتابیس ──────────────────────────────────────


_BUSINESS_QUERIES: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    (
        "silp_users_registered_total",
        "کاربران ثبت‌شده",
        "SELECT count(*) FROM users WHERE deleted_at IS NULL",
        (),
    ),
    (
        "silp_survey_completed_total",
        "نیمرخ‌ها به تفکیک گام تکمیل‌شده",
        "SELECT survey_completed_steps::text, count(*) FROM profiles GROUP BY 1",
        ("step",),
    ),
    (
        "silp_applications_submitted_total",
        "درخواست پیوستن به پروژه به تفکیک نتیجه",
        "SELECT status, count(*) FROM project_applications GROUP BY 1",
        ("result",),
    ),
    (
        "silp_milestones_approved_total",
        "مراحل تأییدشده",
        "SELECT count(*) FROM milestones WHERE status = 'APPROVED'",
        (),
    ),
    (
        "silp_points_awarded_total",
        "امتیاز خالص اعطاشده به تفکیک دسته",
        "SELECT category, coalesce(sum(amount * multiplier), 0) FROM point_entries GROUP BY 1",
        ("category",),
    ),
    (
        "silp_quiz_attempts_active",
        "تلاش‌های آزمون در جریان",
        "SELECT count(*) FROM quiz_attempts WHERE status = 'IN_PROGRESS'",
        (),
    ),
    (
        "outbox_queue_depth",
        "پیام‌های صف ارسال به تفکیک کانال و وضعیت",
        # هر جفت کانال×وضعیت حتی با صفر سری دارد: هشدار «بیش از ۱۰ DEAD در
        # ساعت» با delta() کار می‌کند و سری‌ای که تازه ظاهر شود delta ندارد.
        "SELECT c.channel, s.status, count(o.id)"
        " FROM unnest(CAST(:channels AS text[])) c(channel)"
        " CROSS JOIN unnest(CAST(:statuses AS text[])) s(status)"
        " LEFT JOIN outbox_messages o ON o.channel = c.channel AND o.status = s.status"
        " GROUP BY 1, 2",
        ("channel", "status"),
    ),
    (
        "silp_db_connections",
        "اتصال‌های دیتابیس سامانه به تفکیک وضعیت",
        "SELECT coalesce(state, 'unknown'), count(*) FROM pg_stat_activity"
        " WHERE datname = current_database() GROUP BY 1",
        ("state",),
    ),
    (
        "silp_db_max_connections",
        "سقف اتصال PostgreSQL",
        "SELECT current_setting('max_connections')::int",
        (),
    ),
)


# پارامترهای بسته‌شده، نه رشتهٔ ساخته‌شده؛ کوئری‌ای که نیازش ندارد نادیده می‌گیرد.
_PARAMS: dict[str, list[str]] = {
    "channels": list(EXTERNAL_CHANNELS),
    "statuses": [status for status in OUTBOX_STATUSES if status != "SENT"],
}


async def business_registry(session: AsyncSession) -> CollectorRegistry:
    """یک رجیستری تازه با مقدار لحظه‌ای هر معیار دیتابیسی.

    هر کوئری جدا شکست می‌خورد: یک جدول قفل‌شده نباید کل خراش را بی‌داده کند.
    `silp_metrics_scrape_errors` همان را نشان می‌دهد تا بی‌صدا نماند.
    """
    registry = CollectorRegistry()
    errors = Gauge(
        "silp_metrics_scrape_errors",
        "کوئری‌های معیار که در این خراش شکست خوردند",
        registry=registry,
    )
    failed = 0
    for name, doc, sql, labels in _BUSINESS_QUERIES:
        gauge = Gauge(name, doc, list(labels), registry=registry)
        try:
            rows = (await session.execute(text(sql), _PARAMS)).all()
        except Exception as exc:  # noqa: BLE001 — خراش هرگز نباید ۵۰۰ بدهد
            failed += 1
            log.warning("metrics_query_failed", metric=name, error=str(exc))
            await session.rollback()
            continue
        for row in rows:
            *label_values, value = row
            if labels:
                gauge.labels(*[str(v) for v in label_values]).set(float(value or 0))
            else:
                gauge.set(float(value or 0))
    errors.set(failed)
    return registry


async def render(session: AsyncSession) -> bytes:
    business = await business_registry(session)
    return generate_latest(_process_registry()) + generate_latest(business)


__all__ = [
    "UNMATCHED_ROUTE",
    "business_registry",
    "observe_request",
    "render",
    "timed_job",
]
