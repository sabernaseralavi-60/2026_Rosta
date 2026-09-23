"""آداپتور پیامک کاوه‌نگار — M6-04، NFR-23.

دو فراخوان:

| کار | endpoint | چرا |
|-----|----------|-----|
| OTP | `verify/lookup.json` | خط خدماتی الگو؛ از فیلتر تبلیغاتی و «لیست سیاه» اپراتور عبور می‌کند |
| متن آزاد | `sms/send.json` | پیام‌های اعلان |

## شکست دائمی یا گذرا

صف ارسال (§7.10) پیام گذرا را با عقب‌نشینی دوباره می‌فرستد و دائمی را
مستقیم `DEAD` می‌کند. تشخیص با کد وضعیت کاوه‌نگار است که هم در HTTP و هم
در `return.status` می‌آید:

* **دائمی** — ورودی غلط، گیرندهٔ نامعتبر، فرستندهٔ نامعتبر، الگوی ناموجود.
  تکرار همان درخواست همان نتیجه را می‌دهد.
* **گذرا** — بقیه، از جمله `418` (اعتبار ناکافی): پس از شارژ حساب باید
  خودبه‌خود فرستاده شود، نه اینکه همهٔ پیام‌های آن ساعت از دست برود.

کلید API در مسیر URL است (طراحی کاوه‌نگار)؛ پس نشانی درخواست هرگز لاگ
نمی‌شود، فقط کد وضعیت.
"""

from __future__ import annotations

from typing import Any

import httpx

from silp.core.logging import get_logger
from silp.integrations.sms.base import SMSResult

log = get_logger("silp.sms.kavenegar")

#: کدهایی که تکرار درخواست چیزی را عوض نمی‌کند — مستندات کاوه‌نگار.
PERMANENT_STATUSES = frozenset({400, 401, 403, 411, 412, 414, 422, 424, 426, 427, 428, 431, 432})


class KavenegarSMSSender:
    def __init__(
        self,
        *,
        api_key: str,
        sender: str,
        api_base: str = "https://api.kavenegar.com/v1",
        timeout: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not api_key:
            msg = "کلید API کاوه‌نگار تنظیم نشده است (SMS_API_KEY)."
            raise ValueError(msg)
        self._base = f"{api_base.rstrip('/')}/{api_key}"
        self._sender = sender
        self._timeout = timeout
        self._transport = transport

    async def send_otp(self, destination: str, code: str, *, template: str) -> SMSResult:
        return await self._call(
            "verify/lookup.json", {"receptor": destination, "token": code, "template": template}
        )

    async def send_text(self, destination: str, body: str) -> SMSResult:
        params = {"receptor": destination, "message": body}
        if self._sender:
            params["sender"] = self._sender
        return await self._call("sms/send.json", params)

    async def _call(self, path: str, params: dict[str, str]) -> SMSResult:
        try:
            async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as http:
                # فرم، نه JSON — کاوه‌نگار متن فارسی را در فرم درست می‌خواند.
                response = await http.post(f"{self._base}/{path}", data=params)
        except httpx.HTTPError as exc:
            log.warning("kavenegar_unreachable", path=path, error=type(exc).__name__)
            return SMSResult(delivered=False, error=f"ارتباط با کاوه‌نگار: {type(exc).__name__}")

        payload = _json(response)
        raw = payload.get("return")
        ret: dict[str, Any] = raw if isinstance(raw, dict) else {}
        status = int(ret.get("status", response.status_code)) if ret else response.status_code
        if status == 200:
            entries = payload.get("entries") or []
            first = entries[0] if entries and isinstance(entries[0], dict) else {}
            message_id = first.get("messageid")
            return SMSResult(
                delivered=True,
                provider_message_id=str(message_id) if message_id is not None else None,
            )
        message = str(ret.get("message") or response.reason_phrase or "")
        log.warning("kavenegar_rejected", path=path, status=status)
        return SMSResult(
            delivered=False,
            error=f"کاوه‌نگار {status}: {message}".strip(),
            permanent=status in PERMANENT_STATUSES,
        )


def _json(response: httpx.Response) -> dict[str, Any]:
    try:
        data = response.json()
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


__all__ = ["PERMANENT_STATUSES", "KavenegarSMSSender"]
