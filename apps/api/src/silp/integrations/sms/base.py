"""آداپتور پیامک — رابط مشترک و پیاده‌سازی‌های توسعه.

در توسعه، OTP در لاگ چاپ می‌شود و پیامک ارسال نمی‌گردد (PRD §12.3).
آداپتور کاوه‌نگار در M6 اضافه می‌شود (M6-04)؛ رابط از حالا ثابت است تا
سرویس احراز هویت بعداً تغییر نکند.
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
    """انتخاب آداپتور بر اساس پیکربندی.

    کاوه‌نگار در M6-04 اضافه می‌شود. تا آن زمان انتخاب `kavenegar` در
    تولید توسط اعتبارسنجی پیکربندی رد نمی‌شود ولی اینجا صریح شکست
    می‌خورد — بهتر از ارسال بی‌صدای هیچ.
    """
    match settings.sms_provider:
        case "console":
            return ConsoleSMSSender()
        case "memory":
            return _memory_sender
        case "kavenegar":
            # پیکربندی Literal است، پس شاخهٔ پیش‌فرض لازم نیست.
            msg = "آداپتور کاوه‌نگار هنوز پیاده‌سازی نشده است (M6-04)."
            raise NotImplementedError(msg)
