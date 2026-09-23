"""زمان‌بندی ارسال — ساعت آرام و عقب‌نشینی نمایی. منطق خالص — §7.10.

## ساعت آرام (FR-MSG-02)

«بین ۲۳ تا ۸ فقط اعلان `URGENT` ارسال می‌شود.» بقیه **حذف نمی‌شوند**،
تا ساعت ۸ صبح به تعویق می‌افتند (§7.10). ساعت‌ها به وقت تهران است، نه
UTC: دانشجو ساعت ۲۳ تهران می‌خوابد، نه ساعت ۲۳ گرینویچ.

فقط کانال‌های بیرونی تابع ساعت آرام‌اند. اعلان داخلی صدا ندارد؛ همان
لحظه ثبت می‌شود و فردا صبح منتظر کاربر است.

## عقب‌نشینی (§7.10)

`next = now + 2^attempts × 30s ± jitter`. پس از پنجمین تلاش ناموفق،
پیام `DEAD` است. لرزش (jitter) جلوی این را می‌گیرد که ۵۰ پیامی که با هم
شکست خوردند (مثلاً قطعی کاوه‌نگار) دقیقاً با هم هم دوباره تلاش کنند.
"""

from __future__ import annotations

import random
from datetime import datetime, time, timedelta, tzinfo

from silp.domain.gamification.formulas import LOCAL_TZ

MAX_ATTEMPTS = 5
BASE_DELAY = timedelta(seconds=30)
JITTER = 0.1
#: پیام برداشته‌شده تا این مدت در اختیار همان کارگر است. اگر کارگر وسط
#: ارسال بمیرد، پس از این مدت پیام دوباره برداشته می‌شود — ADR-0013.
LEASE = timedelta(minutes=5)


def in_quiet_hours(moment: datetime, *, start: int, end: int, tz: tzinfo = LOCAL_TZ) -> bool:
    """آیا `moment` داخل بازهٔ آرام [start, end) به وقت محلی است؟

    `start > end` یعنی بازه از نیمه‌شب رد می‌شود (۲۳ تا ۸). `start == end`
    یعنی ساعت آرام خاموش است.
    """
    if start == end:
        return False
    hour = moment.astimezone(tz).hour
    if start < end:
        return start <= hour < end
    return hour >= start or hour < end


def release_time(moment: datetime, *, start: int, end: int, tz: tzinfo = LOCAL_TZ) -> datetime:
    """نزدیک‌ترین لحظهٔ مجاز ارسال — خودِ `moment` اگر آرام نباشد."""
    if not in_quiet_hours(moment, start=start, end=end, tz=tz):
        return moment
    local = moment.astimezone(tz)
    release = datetime.combine(local.date(), time(hour=end), tzinfo=tz)
    if release <= local:
        release += timedelta(days=1)
    return release.astimezone(moment.tzinfo)


def retry_delay(attempts: int, *, rng: random.Random | None = None) -> timedelta:
    """فاصلهٔ تلاش بعدی پس از `attempts` تلاش ناموفق (۱ = اولین شکست)."""
    if attempts < 1:
        msg = "attempts باید دست‌کم ۱ باشد."
        raise ValueError(msg)
    spread = rng.uniform(-JITTER, JITTER) if rng else random.uniform(-JITTER, JITTER)  # noqa: S311
    factor = 1 + spread
    return BASE_DELAY * (1 << attempts) * factor


def is_exhausted(attempts: int) -> bool:
    return attempts >= MAX_ATTEMPTS


__all__ = [
    "BASE_DELAY",
    "JITTER",
    "LEASE",
    "MAX_ATTEMPTS",
    "in_quiet_hours",
    "is_exhausted",
    "release_time",
    "retry_delay",
]
