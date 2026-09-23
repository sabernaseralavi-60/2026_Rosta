"""جریان بی‌درنگ اعلان با SSE — §5.10، FR-MSG-01، M6-08.

«SSE، نه WebSocket — ساده‌تر، سازگارتر با پروکسی‌های ایرانی.»

## چطور بیدار می‌شود

```
اعلان ساخته شد ─COMMIT─► PUBLISH silp:notify:<user>  (پس از commit)
                                   │
جریان: منتظر پیام Redis (حداکثر POLL_SECONDS) ◄──┘
       └► از دیتابیس: اعلان‌های تازه‌تر از آخرین شناسهٔ دیده‌شده + شمارنده
```

Redis فقط «زنگ» است؛ حقیقت در دیتابیس است. پس اگر Redis نباشد یا
پیامی گم شود، جریان هر `POLL_SECONDS` یک بار خودش می‌پرسد و دیرتر ولی
درست به‌روز می‌شود (NFR-11).

## چرا نشست کوتاه

جریان دقیقه‌ها باز می‌ماند. نگه‌داشتن یک اتصال استخر برای هر زنگولهٔ باز،
استخر ۲۰تایی را با ۲۰ تب مرورگر خالی می‌کرد. هر پرسش یک نشست کوتاه
می‌گیرد و فوراً پس می‌دهد.

## چرا عمر محدود

جریان پس از `MAX_SECONDS` بسته می‌شود و مرورگر دوباره وصل می‌شود. توکن
دسترسی ۱۵ دقیقه عمر دارد؛ جریانی که بی‌نهایت باز بماند، با توکنی که مدت‌ها
منقضی یا باطل شده به کاربری که حسابش بسته شده اعلان می‌رساند.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from silp.core.logging import get_logger
from silp.schemas.notifications import NotificationOut
from silp.services.notification_service import NotificationService, wakeup_channel

log = get_logger("silp.notifications.stream")

POLL_SECONDS = 20.0
MAX_SECONDS = 600.0
RETRY_MS = 5000

SessionOpener = Callable[[], AbstractAsyncContextManager[AsyncSession]]


def sse(event: str, data: dict[str, Any]) -> str:
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"), default=str)
    return f"event: {event}\ndata: {payload}\n\n"


async def notification_events(
    user_id: uuid.UUID,
    *,
    open_session: SessionOpener,
    poll_seconds: float = POLL_SECONDS,
    max_seconds: float = MAX_SECONDS,
    use_redis: bool = True,
) -> AsyncIterator[str]:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + max_seconds

    async with open_session() as session:
        service = NotificationService(session)
        last_id = await service.latest_id(user_id)
        unread = await service.unread_count(user_id)
    yield f"retry: {RETRY_MS}\n\n"
    yield sse("unread", {"count": unread})

    pubsub = await _subscribe(user_id) if use_redis else None
    try:
        while (remaining := deadline - loop.time()) > 0:
            pubsub = await _wait(pubsub, min(poll_seconds, remaining))
            async with open_session() as session:
                service = NotificationService(session)
                fresh = await service.since(user_id, last_id)
                count = await service.unread_count(user_id)
            for notification in fresh:
                last_id = notification.id
                yield sse("notification", NotificationOut.of(notification).model_dump(mode="json"))
            if fresh or count != unread:
                unread = count
                yield sse("unread", {"count": unread})
            else:
                # کامنت SSE — پروکسی‌ها اتصالِ بی‌داده را پس از ۶۰ ثانیه می‌بندند.
                yield ": ping\n\n"
    finally:
        await _close(pubsub)


async def _subscribe(user_id: uuid.UUID) -> Any:
    from redis.exceptions import RedisError

    from silp.core.redis import get_redis

    try:
        pubsub = get_redis().pubsub()
        await pubsub.subscribe(wakeup_channel(user_id))
    except (RedisError, OSError) as exc:
        log.info("notification_stream_polling_only", error=type(exc).__name__)
        return None
    return pubsub


async def _wait(pubsub: Any, seconds: float) -> Any:
    """تا زنگ Redis یا پایان مهلت صبر می‌کند. Redis خراب ⇒ از این به بعد فقط پرسش."""
    if pubsub is None:
        await asyncio.sleep(seconds)
        return None
    from redis.exceptions import RedisError

    try:
        await pubsub.get_message(ignore_subscribe_messages=True, timeout=seconds)
    except (RedisError, OSError, TimeoutError) as exc:
        log.info("notification_stream_redis_lost", error=type(exc).__name__)
        await _close(pubsub)
        return None
    return pubsub


async def _close(pubsub: Any) -> None:
    if pubsub is None:
        return
    try:
        await pubsub.aclose()
    except Exception:  # noqa: BLE001 — بستن نباید خطای اصلی را بپوشاند
        log.debug("notification_stream_close_failed")


__all__ = ["MAX_SECONDS", "POLL_SECONDS", "notification_events", "sse"]
