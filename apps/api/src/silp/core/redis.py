"""اتصال Redis — کش نقش، محدودیت نرخ، صف ARQ.

قاعدهٔ NFR-11: اگر Redis از کار بیفتد، اپ کار می‌کند، کندتر. کش اختیاری
است، نه حیاتی. اما محدودیت نرخ در نبود Redis **محافظه‌کارانه** عمل می‌کند:
درخواست رد نمی‌شود (در دسترس بودن مهم‌تر است)، ولی رویداد لاگ می‌شود.
"""

from __future__ import annotations

from redis.asyncio import Redis, from_url

from silp.core.config import get_settings
from silp.core.logging import get_logger

log = get_logger(__name__)

_client: Redis | None = None


def get_redis() -> Redis:
    """کلاینت مشترک. اتصال تنبل است و در اولین فرمان برقرار می‌شود."""
    global _client  # noqa: PLW0603
    if _client is None:
        settings = get_settings()
        _client = from_url(  # type: ignore[no-untyped-call]
            str(settings.redis_url),
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
            health_check_interval=30,
        )
    return _client


async def close_redis() -> None:
    global _client  # noqa: PLW0603
    if _client is not None:
        await _client.aclose()
    _client = None


async def ping() -> bool:
    """برای /health — شکست را بلعیده و False برمی‌گرداند."""
    try:
        return bool(await get_redis().ping())
    except Exception as exc:  # noqa: BLE001 — سلامت هرگز نباید بالا بیاید
        log.warning("redis_ping_failed", error=str(exc))
        return False


# ── فضای نام کلیدها ────────────────────────────────────────────────────
# قرارداد: silp:<دامنه>:<شناسه>. هر پیشوند TTL مستقل دارد (NFR-09).
def key_roles(user_id: str) -> str:
    return f"silp:roles:{user_id}"


def key_rate(bucket: str, identity: str) -> str:
    return f"silp:rate:{bucket}:{identity}"


def key_otp_resend(destination_hash: str) -> str:
    return f"silp:otp:resend:{destination_hash}"


def key_idempotency(user_id: str, idem_key: str) -> str:
    return f"silp:idem:{user_id}:{idem_key}"


ROLES_TTL_SECONDS = 60  # §6.4 — کش نقش
TAXONOMY_TTL_SECONDS = 3600
IDEMPOTENCY_TTL_SECONDS = 86_400
