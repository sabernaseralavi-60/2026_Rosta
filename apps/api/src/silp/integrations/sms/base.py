"""آداپتور پیامک — رابط مشترک و پیاده‌سازی‌های توسعه.

در توسعه، OTP در لاگ چاپ می‌شود و پیامک ارسال نمی‌گردد (PRD §12.3).
در تولید، کاوه‌نگار (`kavenegar.py`، M6-04).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from silp.core.config import Settings
from silp.core.logging import get_logger

log = get_logger("silp.sms")


@dataclass(frozen=True, slots=True)
class SMSResult:
    delivered: bool
    provider_message_id: str | None = None
    error: str | None = None
    #: تکرار بی‌فایده است (گیرندهٔ نامعتبر، الگوی ناموجود) — صف مستقیم `DEAD` می‌کند.
    permanent: bool = False


class SMSSender(Protocol):
    """قرارداد ارسال پیامک."""

    async def send_otp(self, destination: str, code: str, *, template: str) -> SMSResult: ...

    async def send_text(self, destination: str, body: str) -> SMSResult: ...


class ConsoleSMSSender:
    """توسعهٔ محلی: کد در لاگ می‌آید، پیامکی ارسال نمی‌شود.

    کد عمداً در فیلدی با نام `dev_otp_code` نوشته می‌شود تا از فیلتر
    پاک‌سازی لاگ عبور کند — این فقط در development قابل استفاده است.
    """

    async def send_otp(self, destination: str, code: str, *, template: str) -> SMSResult:
        log.warning(
            "otp_not_sent_development_only",
            destination=destination,
            dev_otp_code=code,
            template=template,
        )
        return SMSResult(delivered=True, provider_message_id="console")

    async def send_text(self, destination: str, body: str) -> SMSResult:
        log.info("sms_console", destination=destination, length=len(body))
        return SMSResult(delivered=True, provider_message_id="console")


class MemorySMSSender:
    """برای تست: پیام‌ها در حافظه می‌مانند و تست آن‌ها را می‌خواند."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    async def send_otp(self, destination: str, code: str, *, template: str) -> SMSResult:
        self.sent.append((destination, code))
        return SMSResult(delivered=True, provider_message_id="memory")

    async def send_text(self, destination: str, body: str) -> SMSResult:
        self.sent.append((destination, body))
        return SMSResult(delivered=True, provider_message_id="memory")

    def last_code_for(self, destination: str) -> str | None:
        for dest, payload in reversed(self.sent):
            if dest == destination:
                return payload
        return None


_memory_sender = MemorySMSSender()


def get_sms_sender(settings: Settings) -> SMSSender:
    """انتخاب آداپتور بر اساس پیکربندی."""
    match settings.sms_provider:
        case "console":
            return ConsoleSMSSender()
        case "memory":
            return _memory_sender
        case "kavenegar":
            # import درون تابع: httpx فقط وقتی لازم است که واقعاً پیامک برود.
            from silp.integrations.sms.kavenegar import KavenegarSMSSender

            return KavenegarSMSSender(
                api_key=settings.sms_api_key,
                sender=settings.sms_sender,
                api_base=settings.sms_api_base,
                timeout=settings.messaging_timeout_seconds,
            )


def get_memory_sms_sender() -> MemorySMSSender:
    """همان نمونه‌ای که اپ در `SMS_PROVIDER=memory` استفاده می‌کند — برای تست."""
    return _memory_sender
