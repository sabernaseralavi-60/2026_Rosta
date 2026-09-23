"""آداپتور ربات تلگرام و ایتا — M6-06.

ایتایار همان شکل Bot API تلگرام را دارد (`sendMessage` با `chat_id` و
`text`، پاسخ `{"ok": ..., "result": ...}`)، پس هر دو یک پیاده‌سازی
مشترک دارند و فقط نشانی و قالب بدنه فرق می‌کند.

توکن ربات در مسیر URL است؛ نشانی درخواست هرگز لاگ نمی‌شود.

## تلگرام در ایران

تلگرام فیلتر است و سرور داخل ایران مستقیم به `api.telegram.org` نمی‌رسد.
`TELEGRAM_API_BASE` می‌تواند به یک پروکسی بیرون از کشور اشاره کند. اگر
نرسد، پیام‌های تلگرام `FAILED` و سپس `DEAD` می‌شوند و بقیهٔ کانال‌ها
بی‌اثر می‌مانند — دقیقاً آنچه FR-MSG-02 می‌خواهد.
"""

from __future__ import annotations

from typing import Any

import httpx

from silp.core.logging import get_logger
from silp.integrations.messaging.base import OutgoingMessage, SendResult

log = get_logger("silp.messaging.bots")

#: ۴۰۰ «گفت‌وگو پیدا نشد»، ۴۰۱ توکن غلط، ۴۰۳ کاربر ربات را بسته — تکرار بی‌فایده است.
PERMANENT_BOT_ERRORS = frozenset({400, 401, 403, 404})


def bot_text(message: OutgoingMessage) -> str:
    """پیام ربات: عنوان در خط اول، سپس متن."""
    if message.subject:
        return f"{message.subject}\n\n{message.body}"
    return message.body


class _BotApiSender:
    name = "bot"

    def __init__(
        self,
        *,
        url: str,
        timeout: float = 10.0,
        as_form: bool = False,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._url = url
        self._timeout = timeout
        self._as_form = as_form
        self._transport = transport

    async def send(self, message: OutgoingMessage) -> SendResult:
        body = {"chat_id": message.recipient, "text": bot_text(message)}
        try:
            async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as http:
                if self._as_form:
                    response = await http.post(self._url, data=body)
                else:
                    response = await http.post(
                        self._url, json={**body, "disable_web_page_preview": True}
                    )
        except httpx.HTTPError as exc:
            log.warning("bot_unreachable", bot=self.name, error=type(exc).__name__)
            return SendResult(delivered=False, error=f"{self.name}: {type(exc).__name__}")

        payload = _json(response)
        if response.is_success and payload.get("ok") is True:
            result = payload.get("result")
            message_id = result.get("message_id") if isinstance(result, dict) else None
            return SendResult(
                delivered=True,
                provider_message_id=str(message_id) if message_id is not None else None,
            )
        code = int(payload.get("error_code") or response.status_code)
        description = str(payload.get("description") or response.reason_phrase or "")
        log.warning("bot_rejected", bot=self.name, status=code)
        return SendResult(
            delivered=False,
            error=f"{self.name} {code}: {description}".strip(),
            permanent=code in PERMANENT_BOT_ERRORS,
        )


class TelegramBotSender(_BotApiSender):
    name = "telegram"

    def __init__(
        self,
        *,
        token: str,
        api_base: str = "https://api.telegram.org",
        timeout: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not token:
            msg = "توکن ربات تلگرام تنظیم نشده است (TELEGRAM_BOT_TOKEN)."
            raise ValueError(msg)
        super().__init__(
            url=f"{api_base.rstrip('/')}/bot{token}/sendMessage",
            timeout=timeout,
            transport=transport,
        )


class EitaayarSender(_BotApiSender):
    name = "eitaa"

    def __init__(
        self,
        *,
        token: str,
        api_base: str = "https://eitaayar.ir/api",
        timeout: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not token:
            msg = "توکن ایتایار تنظیم نشده است (EITAA_API_TOKEN)."
            raise ValueError(msg)
        super().__init__(
            url=f"{api_base.rstrip('/')}/{token}/sendMessage",
            timeout=timeout,
            as_form=True,
            transport=transport,
        )


def parse_telegram_start(update: dict[str, Any]) -> tuple[str, str] | None:
    """`/start <code>` در گفت‌وگوی خصوصی ⇒ (شناسهٔ گفت‌وگو، کد). بقیه ⇒ None.

    پیوند فقط در گفت‌وگوی خصوصی پذیرفته می‌شود: اگر کسی ربات را به یک گروه
    اضافه کند و کد را آنجا بفرستد، اعلان‌های شخصی‌اش به همهٔ گروه می‌رسید.
    """
    message = update.get("message")
    if not isinstance(message, dict):
        return None
    chat = message.get("chat")
    text = message.get("text")
    if not isinstance(chat, dict) or not isinstance(text, str):
        return None
    if chat.get("type") != "private" or chat.get("id") is None:
        return None
    parts = text.strip().split(maxsplit=1)
    if len(parts) != 2 or parts[0].split("@", 1)[0] != "/start":
        return None
    return str(chat["id"]), parts[1].strip()


def _json(response: httpx.Response) -> dict[str, Any]:
    try:
        data = response.json()
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


__all__ = [
    "PERMANENT_BOT_ERRORS",
    "EitaayarSender",
    "TelegramBotSender",
    "bot_text",
    "parse_telegram_start",
]
