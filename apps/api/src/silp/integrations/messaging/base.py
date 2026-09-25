"""رابط یکسان کانال‌های بیرونی — FR-MSG-02، M6-04 تا M6-06.

«هر کانال پشت یک رابط یکسان (Adapter) پیاده می‌شود تا افزودن کانال جدید
نیازی به تغییر منطق دامنه نداشته باشد.» صف ارسال فقط `ChannelSender`
می‌شناسد؛ اینکه پشتش کاوه‌نگار است یا SMTP یا ربات تلگرام، نه.

هر آداپتور **هرگز استثنا بالا نمی‌آورد** — شکست را در `SendResult`
برمی‌گرداند. یک کانال خراب نباید حلقهٔ ارسال بقیه را بشکند (FR-MSG-02).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from silp.core.logging import get_logger

log = get_logger("silp.messaging")


@dataclass(frozen=True, slots=True)
class OutgoingMessage:
    channel: str
    recipient: str
    subject: str | None
    body: str
    #: نشانی اقدام (مطلق) — فقط Push از آن استفاده می‌کند تا با یک لمس باز شود.
    link: str | None = None
    priority: str = "NORMAL"


@dataclass(frozen=True, slots=True)
class SendResult:
    delivered: bool
    provider_message_id: str | None = None
    error: str | None = None
    #: تکرار بی‌فایده است — صف مستقیم `DEAD` می‌کند (§7.10).
    permanent: bool = False
    #: گیرنده دیگر وجود ندارد (اشتراک Push لغو شده) — صف آن را پاک می‌کند.
    revoked: bool = False


class ChannelSender(Protocol):
    async def send(self, message: OutgoingMessage) -> SendResult: ...


class ConsoleChannelSender:
    """توسعهٔ محلی: پیام در لاگ می‌آید و جایی نمی‌رود."""

    def __init__(self, channel: str) -> None:
        self.channel = channel

    async def send(self, message: OutgoingMessage) -> SendResult:
        log.info(
            "message_console",
            channel=self.channel,
            recipient=message.recipient,
            subject=message.subject,
            body=message.body,
        )
        return SendResult(delivered=True, provider_message_id="console")


@dataclass
class MemoryChannelSender:
    """برای تست: پیام‌ها در حافظه، و شکستِ برنامه‌ریزی‌شده."""

    channel: str
    sent: list[OutgoingMessage] = field(default_factory=list)
    _failures: list[SendResult] = field(default_factory=list)

    async def send(self, message: OutgoingMessage) -> SendResult:
        if self._failures:
            return self._failures.pop(0)
        self.sent.append(message)
        return SendResult(delivered=True, provider_message_id=f"memory-{len(self.sent)}")

    def fail_next(
        self,
        times: int = 1,
        *,
        permanent: bool = False,
        revoked: bool = False,
        error: str = "خطای آزمایشی",
    ) -> None:
        self._failures.extend(
            SendResult(
                delivered=False, error=error, permanent=permanent or revoked, revoked=revoked
            )
            for _ in range(times)
        )

    def reset(self) -> None:
        self.sent.clear()
        self._failures.clear()


__all__ = [
    "ChannelSender",
    "ConsoleChannelSender",
    "MemoryChannelSender",
    "OutgoingMessage",
    "SendResult",
]
