"""آداپتور Push وب (VAPID، RFC 8030/8291/8292) — ADR-0029.

`pywebpush` رمزنگاری بار پیام (`aes128gcm`) و امضای VAPID را انجام می‌دهد؛
همان کتابخانهٔ آزموده‌شده، نه رمزنگاری دست‌نویس. کتابخانه هم‌زمان است و
روی `to_thread` اجرا می‌شود تا حلقهٔ ارسال صف را نبندد.

## گیرنده

`OutgoingMessage.recipient` اینجا JSON اشتراک مرورگر است
(`{"endpoint": …, "keys": {"p256dh": …, "auth": …}}`): آداپتور جلسهٔ دیتابیس
ندارد و اشتراک همهٔ چیزی است که برای ارسال لازم است.

## پاسخ سرویس Push

| وضعیت | معنا | نتیجه |
|-------|------|-------|
| ۲۰۱ | پذیرفته شد | تحویل |
| ۴۰۴، ۴۱۰ | اشتراک لغو یا منقضی شده | دائمی + `revoked` |
| ۴۰۰، ۴۱۳ | بار نامعتبر یا بزرگ | دائمی |
| ۴۰۱، ۴۰۳ | کلید VAPID نمی‌خواند | دائمی (مشکل پیکربندی، نه گیرنده) |
| ۴۲۹، ۵۰۰ به بالا، شبکه | موقت | تلاش دوباره |

## در ایران

سرویس Push کروم FCM است و ممکن است از سرور داخل ایران در دسترس نباشد.
آن‌وقت پیام‌ها `FAILED` و سپس `DEAD` می‌شوند و بقیهٔ کانال‌ها بی‌اثر
می‌مانند (FR-MSG-02).
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from urllib.parse import urlsplit

from pywebpush import WebPushException, webpush

from silp.core.logging import get_logger
from silp.integrations.messaging.base import OutgoingMessage, SendResult

log = get_logger("silp.messaging.webpush")

#: بار پیام Push حداکثر ۴۰۹۶ بایت است؛ متن بلند برش می‌خورد.
MAX_BODY_CHARS = 180
#: اگر مرورگر تا این مدت خاموش/آفلاین بود، پیام دور ریخته می‌شود — اعلان کهنه بدتر از بی‌اعلان است.
TTL_SECONDS = 24 * 3600
REVOKED_STATUSES = frozenset({404, 410})
PERMANENT_STATUSES = frozenset({400, 401, 403, 413})
URGENCY = {"LOW": "low", "NORMAL": "normal", "IMPORTANT": "normal", "URGENT": "high"}


def push_payload(message: OutgoingMessage) -> str:
    """بار پیام: عنوان، متن کوتاه و مسیر داخلی (نه نشانی مطلق).

    سرویس‌کارگر مسیر را با مبدأ خودش می‌سازد؛ پس حتی اگر نشانی جعلی به
    اینجا برسد، اعلان فقط داخل همین سایت باز می‌شود.
    """
    body = message.body.strip()
    if len(body) > MAX_BODY_CHARS:
        body = body[: MAX_BODY_CHARS - 1].rstrip() + "…"
    url = "/notifications"
    if message.link:
        parts = urlsplit(message.link)
        path = parts.path or "/"
        url = f"{path}?{parts.query}" if parts.query else path
    return json.dumps(
        {
            "title": message.subject or "سابِر",
            "body": body,
            "url": url,
            "urgent": message.priority == "URGENT",
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


class WebPushSender:
    def __init__(
        self,
        *,
        private_key: str,
        subject: str,
        timeout: float = 10.0,
    ) -> None:
        self._private_key = private_key
        self._subject = subject
        self._timeout = timeout

    async def send(self, message: OutgoingMessage) -> SendResult:
        try:
            subscription = json.loads(message.recipient)
        except ValueError:
            return SendResult(delivered=False, error="اشتراک Push خراب است.", permanent=True)
        try:
            await asyncio.to_thread(self._post, subscription, message)
        except WebPushException as exc:
            return _failure(exc)
        except Exception as exc:  # noqa: BLE001 — شبکه و کلید؛ آداپتور هرگز استثنا بالا نمی‌آورد
            log.warning("webpush_unreachable", error=type(exc).__name__)
            return SendResult(delivered=False, error=f"webpush: {type(exc).__name__}")
        return SendResult(delivered=True)

    def _post(self, subscription: dict[str, Any], message: OutgoingMessage) -> None:
        webpush(
            subscription_info=subscription,
            data=push_payload(message),
            vapid_private_key=self._private_key,
            vapid_claims={"sub": self._subject},
            ttl=TTL_SECONDS,
            timeout=self._timeout,
            headers={"Urgency": URGENCY.get(message.priority, "normal")},
        )


def _failure(exc: WebPushException) -> SendResult:
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    log.warning("webpush_rejected", status=status)
    if status in REVOKED_STATUSES:
        return SendResult(delivered=False, error=f"webpush: {status}", permanent=True, revoked=True)
    if status in PERMANENT_STATUSES:
        return SendResult(delivered=False, error=f"webpush: {status}", permanent=True)
    return SendResult(delivered=False, error=f"webpush: {status or 'شبکه'}")


__all__ = ["WebPushSender", "push_payload"]
