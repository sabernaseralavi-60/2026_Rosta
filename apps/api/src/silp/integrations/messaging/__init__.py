"""کانال‌های بیرونی اعلان — انتخاب آداپتور از روی پیکربندی.

| کانال | پیکربندی | آداپتور تولید |
|-------|----------|----------------|
| `SMS` | `SMS_PROVIDER` | کاوه‌نگار |
| `EMAIL` | `EMAIL_PROVIDER` | SMTP |
| `PUSH` | `PUSH_PROVIDER` | Web Push با VAPID — ADR-0029 |
| `TELEGRAM` | `TELEGRAM_PROVIDER` | Bot API (با پروکسی اختیاری) |
| `EITAA` | `EITAA_PROVIDER` | ایتایار |

`WHATSAPP` در اسکیما هست ولی آداپتور ندارد: API رسمی واتساپ حساب
تجاری متا می‌خواهد که از ایران در دسترس نیست (ADR-0013). کانالی که
آداپتور ندارد یا `disabled` است، به کاربر پیشنهاد نمی‌شود و پیامی هم
برایش در صف نمی‌رود.
"""

from __future__ import annotations

from silp.core.config import Settings
from silp.domain.notifications.catalog import EXTERNAL_CHANNELS
from silp.integrations.messaging.base import (
    ChannelSender,
    ConsoleChannelSender,
    MemoryChannelSender,
    OutgoingMessage,
    SendResult,
)
from silp.integrations.sms import SMSSender, get_sms_sender

_memory: dict[str, MemoryChannelSender] = {}


def memory_sender(channel: str) -> MemoryChannelSender:
    """نمونهٔ مشترک حافظه‌ای هر کانال — همان که اپ در محیط تست می‌بیند."""
    if channel not in _memory:
        _memory[channel] = MemoryChannelSender(channel)
    return _memory[channel]


class SMSChannelSender:
    """پیامک اعلان روی همان آداپتور OTP — یک حساب کاوه‌نگار، یک پیکربندی."""

    def __init__(self, sms: SMSSender) -> None:
        self._sms = sms

    async def send(self, message: OutgoingMessage) -> SendResult:
        result = await self._sms.send_text(message.recipient, message.body)
        return SendResult(
            delivered=result.delivered,
            provider_message_id=result.provider_message_id,
            error=result.error,
            permanent=result.permanent,
        )


def enabled_channels(settings: Settings) -> tuple[str, ...]:
    """کانال‌های بیرونی که آداپتور فعال دارند، به ترتیب ثابت نمایش."""
    enabled = {"SMS"}
    if settings.email_provider != "disabled":
        enabled.add("EMAIL")
    if settings.push_provider != "disabled":
        enabled.add("PUSH")
    if settings.telegram_provider != "disabled":
        enabled.add("TELEGRAM")
    if settings.eitaa_provider != "disabled":
        enabled.add("EITAA")
    return tuple(c for c in EXTERNAL_CHANNELS if c in enabled)


def channel_sender(settings: Settings, channel: str) -> ChannelSender | None:
    """آداپتور یک کانال، یا None اگر کانال خاموش است."""
    timeout = settings.messaging_timeout_seconds
    match channel:
        case "SMS":
            if settings.sms_provider == "memory":
                return memory_sender("SMS")
            if settings.sms_provider == "console":
                return ConsoleChannelSender("SMS")
            return SMSChannelSender(get_sms_sender(settings))
        case "EMAIL":
            if settings.email_provider in ("console", "memory"):
                return _dev_sender(settings.email_provider, channel)
            if settings.email_provider == "smtp":
                from silp.integrations.messaging.email import SMTPEmailSender

                return SMTPEmailSender(
                    host=settings.smtp_host,
                    port=settings.smtp_port,
                    sender=settings.mail_from,
                    user=settings.smtp_user,
                    password=settings.smtp_password,
                    use_tls=settings.smtp_tls,
                    timeout=timeout,
                )
            return None
        case "PUSH":
            if settings.push_provider in ("console", "memory"):
                return _dev_sender(settings.push_provider, channel)
            if settings.push_provider == "webpush":
                from silp.integrations.messaging.webpush import WebPushSender

                return WebPushSender(
                    private_key=settings.vapid_private_key,
                    subject=settings.vapid_subject,
                    timeout=timeout,
                )
            return None
        case "TELEGRAM":
            if settings.telegram_provider in ("console", "memory"):
                return _dev_sender(settings.telegram_provider, channel)
            if settings.telegram_provider == "bot":
                from silp.integrations.messaging.bots import TelegramBotSender

                return TelegramBotSender(
                    token=settings.telegram_bot_token,
                    api_base=settings.telegram_api_base,
                    timeout=timeout,
                )
            return None
        case "EITAA":
            if settings.eitaa_provider in ("console", "memory"):
                return _dev_sender(settings.eitaa_provider, channel)
            if settings.eitaa_provider == "eitaayar":
                from silp.integrations.messaging.bots import EitaayarSender

                return EitaayarSender(
                    token=settings.eitaa_api_token,
                    api_base=settings.eitaa_api_base,
                    timeout=timeout,
                )
            return None
        case _:
            return None


def _dev_sender(provider: str, channel: str) -> ChannelSender:
    return memory_sender(channel) if provider == "memory" else ConsoleChannelSender(channel)


__all__ = [
    "ChannelSender",
    "ConsoleChannelSender",
    "MemoryChannelSender",
    "OutgoingMessage",
    "SMSChannelSender",
    "SendResult",
    "channel_sender",
    "enabled_channels",
    "memory_sender",
]
