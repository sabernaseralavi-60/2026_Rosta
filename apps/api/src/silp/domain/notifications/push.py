"""قواعد اشتراک Push — ADR-0029. منطق خالص، بی‌دیتابیس و بی‌شبکه.

سرور به نقطهٔ پایانی‌ای که مرورگر می‌دهد `POST` می‌زند. اگر هر نشانی‌ای
پذیرفته شود، کاربر می‌تواند سرور را به شبکهٔ داخلی (`http://10.0.0.5`،
`https://localhost:5432`، متادیتای ابر) بفرستد — SSRF. راه‌حل فهرست مجاز
است: فقط میزبان سرویس‌های Push شناخته‌شده، روی HTTPS، بدون نام‌کاربری و
بدون IP خام.
"""

from __future__ import annotations

import ipaddress
import json
from urllib.parse import urlsplit

MAX_ENDPOINT_LENGTH = 2048
MAX_KEY_LENGTH = 256
#: هر کاربر چند دستگاه دارد؛ بیشتر از این، قدیمی‌ترین کنار می‌رود.
MAX_SUBSCRIPTIONS_PER_USER = 10


def subscription_recipient(endpoint: str, p256dh: str, auth: str) -> str:
    """قالب `recipient` ردیف صف برای یک اشتراک.

    آداپتور جلسهٔ دیتابیس ندارد؛ اشتراک کامل همراه ردیف می‌رود.
    """
    return json.dumps(
        {"endpoint": endpoint, "keys": {"p256dh": p256dh, "auth": auth}}, separators=(",", ":")
    )


def endpoint_of(recipient: str) -> str | None:
    """نقطهٔ پایانی از `recipient` — برای پاک‌کردن اشتراک لغوشده."""
    try:
        value = json.loads(recipient)
    except ValueError:
        return None
    endpoint = value.get("endpoint") if isinstance(value, dict) else None
    return endpoint if isinstance(endpoint, str) else None


def allowed_hosts(setting: str) -> tuple[str, ...]:
    return tuple(h.strip().lower() for h in setting.split(",") if h.strip())


def check_endpoint(endpoint: str, allowed: tuple[str, ...]) -> str | None:
    """`None` اگر نقطهٔ پایانی مجاز است؛ وگرنه دلیل رد، به فارسی."""
    if len(endpoint) > MAX_ENDPOINT_LENGTH:
        return "نشانی اشتراک بیش از حد بلند است."
    try:
        parts = urlsplit(endpoint)
        host = (parts.hostname or "").lower()
        port = parts.port
    except ValueError:
        return "نشانی اشتراک معتبر نیست."
    if parts.scheme != "https":
        return "نشانی اشتراک باید https باشد."
    if parts.username or parts.password or not host:
        return "نشانی اشتراک معتبر نیست."
    if port not in (None, 443):
        return "درگاه نشانی اشتراک مجاز نیست."
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        return "نشانی اشتراک نباید IP باشد."
    if not any(host == a or host.endswith(f".{a}") for a in allowed):
        return "این سرویس Push پشتیبانی نمی‌شود."
    return None


__all__ = [
    "MAX_ENDPOINT_LENGTH",
    "MAX_KEY_LENGTH",
    "MAX_SUBSCRIPTIONS_PER_USER",
    "allowed_hosts",
    "check_endpoint",
    "endpoint_of",
    "subscription_recipient",
]
