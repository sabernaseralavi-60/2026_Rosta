"""آداپتور ایمیل با SMTP — M6-05.

کتابخانهٔ استاندارد `smtplib` همگام است؛ ارسال در یک نخ جدا اجرا می‌شود
تا حلقهٔ رویداد کارگر معطل یک سرور ایمیل کند نماند. وابستگی تازه‌ای
(`aiosmtplib`) برای چند ایمیل در روز ارزش ندارد.

متن ساده و UTF-8 است. HTML فقط وقتی ارزش دارد که قالب طراحی‌شده داشته
باشیم؛ ایمیل فارسی HTML بدون `dir="rtl"` درست، از متن ساده بدتر است.
"""

from __future__ import annotations

import asyncio
import smtplib
from email.message import EmailMessage
from email.utils import make_msgid

from silp.integrations.messaging.base import OutgoingMessage, SendResult

#: کدهای SMTP که یعنی «این نشانی هرگز نمی‌گیرد» — RFC 5321.
PERMANENT_SMTP_CODES = frozenset({550, 551, 553, 554})


class SMTPEmailSender:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        sender: str,
        user: str = "",
        password: str = "",
        use_tls: bool = False,
        timeout: float = 10.0,
    ) -> None:
        self._host = host
        self._port = port
        self._sender = sender
        self._user = user
        self._password = password
        self._use_tls = use_tls
        self._timeout = timeout

    async def send(self, message: OutgoingMessage) -> SendResult:
        return await asyncio.to_thread(self._send_sync, message)

    def _send_sync(self, message: OutgoingMessage) -> SendResult:
        email = EmailMessage()
        email["From"] = self._sender
        email["To"] = message.recipient
        email["Subject"] = message.subject or "سامانهٔ سابِر"
        message_id = make_msgid(domain=self._sender.rsplit("@", 1)[-1] or None)
        email["Message-ID"] = message_id
        email.set_content(message.body, charset="utf-8")
        try:
            with smtplib.SMTP(self._host, self._port, timeout=self._timeout) as smtp:
                if self._use_tls:
                    smtp.starttls()
                if self._user:
                    smtp.login(self._user, self._password)
                smtp.send_message(email)
        except smtplib.SMTPRecipientsRefused as exc:
            codes = {code for code, _ in exc.recipients.values()}
            return SendResult(
                delivered=False,
                error="نشانی ایمیل گیرنده پذیرفته نشد.",
                permanent=bool(codes & PERMANENT_SMTP_CODES),
            )
        except (smtplib.SMTPException, OSError) as exc:
            return SendResult(delivered=False, error=f"SMTP: {type(exc).__name__}")
        return SendResult(delivered=True, provider_message_id=message_id)


__all__ = ["PERMANENT_SMTP_CODES", "SMTPEmailSender"]
