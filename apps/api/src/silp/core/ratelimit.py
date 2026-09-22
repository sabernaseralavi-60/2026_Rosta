"""محدودیت نرخ — PRD §5.1، NFR-02.

پیاده‌سازی: پنجرهٔ ثابت با INCR + EXPIRE در یک اسکریپت Lua، تا شمارش و
تنظیم انقضا اتمیک باشند (بدون آن، یک کلید بدون TTL می‌ماند و کاربر برای
همیشه قفل می‌شود).

| دسته                    | محدودیت                                   |
|-------------------------|-------------------------------------------|
| POST /auth/otp/request  | ۳ در ۱۰ دقیقه به‌ازای شماره، ۱۰/ساعت به‌ازای IP |
| POST /auth/*            | ۲۰ در دقیقه به‌ازای IP                     |
| نوشتن عمومی             | ۶۰ در دقیقه به‌ازای کاربر                  |
| خواندن                  | ۳۰۰ در دقیقه به‌ازای کاربر                 |
"""

from __future__ import annotations

from dataclasses import dataclass

from redis.asyncio import Redis
from redis.exceptions import RedisError

from silp.core.logging import get_logger
from silp.core.redis import get_redis, key_rate

log = get_logger(__name__)

# KEYS[1] = کلید شمارنده، ARGV[1] = پنجره به ثانیه
# خروجی: {شمارش فعلی, ثانیهٔ باقی‌مانده تا بازنشانی}
_INCR_WITH_TTL = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
end
local ttl = redis.call('TTL', KEYS[1])
if ttl < 0 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
  ttl = tonumber(ARGV[1])
end
return {current, ttl}
"""


@dataclass(frozen=True, slots=True)
class Limit:
    """یک سیاست محدودیت: حداکثر `count` درخواست در `window_seconds` ثانیه."""

    bucket: str
    count: int
    window_seconds: int


@dataclass(frozen=True, slots=True)
class LimitResult:
    allowed: bool
    remaining: int
    retry_after: int


# سیاست‌های ثابت §5.1
AUTH_GENERAL = Limit("auth", count=20, window_seconds=60)
WRITE_GENERAL = Limit("write", count=60, window_seconds=60)
READ_GENERAL = Limit("read", count=300, window_seconds=60)


def otp_per_destination(count: int) -> Limit:
    return Limit("otp:dest", count=count, window_seconds=600)


def otp_per_ip(count: int) -> Limit:
    return Limit("otp:ip", count=count, window_seconds=3600)


async def check(limit: Limit, identity: str, *, redis: Redis | None = None) -> LimitResult:
    """مصرف یک واحد از سهمیه و اعلام نتیجه.

    در نبود Redis اجازه داده می‌شود (NFR-11: کش اختیاری است، نه حیاتی) و
    رویداد در سطح WARNING لاگ می‌گردد تا خاموشی بی‌صدا نباشد.
    """
    client = redis or get_redis()
    redis_key = key_rate(limit.bucket, identity)

    try:
        current, ttl = await client.eval(  # type: ignore[misc]
            _INCR_WITH_TTL, 1, redis_key, str(limit.window_seconds)
        )
    except RedisError as exc:
        log.warning("ratelimit_unavailable", bucket=limit.bucket, error=str(exc))
        return LimitResult(allowed=True, remaining=limit.count, retry_after=0)

    current = int(current)
    ttl = int(ttl)
    if current > limit.count:
        return LimitResult(allowed=False, remaining=0, retry_after=max(ttl, 1))
    return LimitResult(allowed=True, remaining=limit.count - current, retry_after=0)


async def peek(limit: Limit, identity: str, *, redis: Redis | None = None) -> int:
    """شمارش فعلی بدون مصرف سهمیه — برای پیام خطای دقیق‌تر."""
    client = redis or get_redis()
    try:
        value = await client.get(key_rate(limit.bucket, identity))
    except RedisError:
        return 0
    return int(value) if value else 0


async def reset(limit: Limit, identity: str, *, redis: Redis | None = None) -> None:
    """پاک کردن شمارنده — پس از ورود موفق، تا تلاش‌های ناموفق قبلی
    کاربر را جریمه نکنند."""
    client = redis or get_redis()
    try:
        await client.delete(key_rate(limit.bucket, identity))
    except RedisError:
        pass
