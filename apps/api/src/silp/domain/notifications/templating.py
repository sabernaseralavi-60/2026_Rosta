"""الگوی پیام با متغیر جایگزین — FR-MSG-03.

نحو عمداً کوچک است: فقط `{{name}}`. نه شرط، نه حلقه، نه فیلتر. الگو را
مدیر در پنل می‌نویسد و موتور قالبی که بتواند کد اجرا کند یا به صفات
شیء برسد، سطح حملهٔ بی‌دلیل است.

دو قاعده:

* **ذخیره** الگویی با متغیر ناشناخته رد می‌شود (`validate`). غلط تایپی
  مدیر باید همان لحظه دیده شود، نه وقتی پیامک هزار دانشجو خالی رفت.
* **رندر** با متغیرِ غایب شکست می‌خورد (`TemplateError`). اعلان داخلی
  آن را بالا می‌آورد و پیام صف `DEAD` می‌شود با خطای روشن — بهتر از
  پیامی که وسطش `{{project}}` نوشته شده.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

PLACEHOLDER = re.compile(r"\{\{\s*([a-z_][a-z0-9_]*)\s*\}\}")
#: هر `{{` یا `}}` که جزء یک متغیر معتبر نباشد، اشتباه نگارشی است.
_STRAY_BRACES = re.compile(r"\{\{|\}\}")


class TemplateError(ValueError):
    """الگو نامعتبر است یا متغیری که لازم دارد داده نشده."""


@dataclass(frozen=True, slots=True)
class Rendered:
    subject: str | None
    body: str


def placeholders(text: str | None) -> set[str]:
    return set(PLACEHOLDER.findall(text or ""))


def validate(subject: str | None, body: str, allowed: Iterable[str]) -> None:
    """پیش از ذخیره: متغیرها مجازند و آکولادی سرگردان نمانده."""
    if not body.strip():
        raise TemplateError("متن الگو خالی است.")
    allowed_set = set(allowed)
    for part in (subject, body):
        if part is None:
            continue
        unknown = placeholders(part) - allowed_set
        if unknown:
            names = "، ".join(sorted(unknown))
            raise TemplateError(f"متغیر ناشناخته در الگو: {names}")
        if _STRAY_BRACES.search(PLACEHOLDER.sub("", part)):
            raise TemplateError("آکولاد باز یا بسته‌ای بی‌جفت در الگو مانده است.")


def render_text(text: str, values: Mapping[str, object]) -> str:
    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in values:
            raise TemplateError(f"مقدار متغیر «{name}» داده نشده است.")
        value = values[name]
        return "" if value is None else str(value)

    return _tidy(PLACEHOLDER.sub(replace, text))


def render(subject: str | None, body: str, values: Mapping[str, object]) -> Rendered:
    return Rendered(
        subject=render_text(subject, values) if subject is not None else None,
        body=render_text(body, values),
    )


def _tidy(text: str) -> str:
    """فاصلهٔ دوتایی که از متغیر خالی مانده جمع می‌شود — «پذیرفته نشد.  —»."""
    lines = [re.sub(r"[ \t]{2,}", " ", line).strip() for line in text.split("\n")]
    return "\n".join(lines).strip()


def sms_parts(text: str) -> int:
    """تعداد بخش پیامک — §14.7.

    متن تمام‌لاتین (GSM-7) ۱۶۰ نویسه در یک بخش و ۱۵۳ در هر بخش چندتایی
    می‌گیرد؛ هر نویسهٔ فارسی کل پیام را UCS-2 می‌کند: ۷۰ و ۶۷.
    """
    if not text:
        return 0
    unicode = any(ord(ch) > 0x7F for ch in text)
    single, multi = (70, 67) if unicode else (160, 153)
    length = len(text)
    return 1 if length <= single else -(-length // multi)


def excerpt(text: str, limit: int = 120) -> str:
    """خلاصهٔ یک‌خطی — برای متن اعلان استاد در پیامک و مرکز اعلان."""
    flat = " ".join(text.split())
    if len(flat) <= limit:
        return flat
    cut = flat[: limit - 1].rsplit(" ", 1)[0]
    return f"{cut}…"


__all__ = [
    "PLACEHOLDER",
    "Rendered",
    "TemplateError",
    "excerpt",
    "placeholders",
    "render",
    "render_text",
    "sms_parts",
    "validate",
]
