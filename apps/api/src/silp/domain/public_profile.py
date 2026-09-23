"""نیمرخ عمومی — FR-PROF-03، ADR-0017. منطق خالص.

«کنترل دقیق حریم خصوصی: هر بخش قابل روشن/خاموش کردن.» کلید اصلی
`profiles.is_public` است — بدون آن هیچ‌چیز دیده نمی‌شود — و هر بخش در
`profiles.privacy_settings` جداگانه خاموش می‌شود. کلیدی که ثبت نشده،
روشن است: کسی که نیمرخش را عمومی کرده، همین را خواسته.

**هرگز نمایش داده نمی‌شود**، و اصلاً کلیدی برای روشن کردنش نیست: موبایل،
ایمیل، کد ملی، نمرات درسی، رتبه در کلاس.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

SECTIONS: tuple[str, ...] = (
    "university",
    "skills",
    "projects",
    "certificates",
    "research",
    "badges",
    "points",
)

SECTION_TITLE_FA: dict[str, str] = {
    "university": "دانشگاه، رشته و مقطع",
    "skills": "مهارت‌های برتر",
    "projects": "پروژه‌های تکمیل‌شده",
    "certificates": "گواهی‌ها",
    "research": "مسیر پژوهش و مقاله‌های راستی‌آزمایی‌شده",
    "badges": "نشان‌ها",
    "points": "امتیاز کل و سطح",
}

#: مهارت «برتر» — سطح ۴ و ۵ از ۵؛ حداکثر شش تا تا صفحه فهرست خرید نشود.
TOP_SKILL_MIN_LEVEL = 4
TOP_SKILL_LIMIT = 6


def sections(privacy_settings: Mapping[str, Any] | None) -> dict[str, bool]:
    stored = privacy_settings or {}
    return {key: bool(stored.get(key, True)) for key in SECTIONS}


def merge(privacy_settings: Mapping[str, Any] | None, update: Mapping[str, bool]) -> dict[str, Any]:
    """فقط کلیدهای شناخته‌شده؛ بقیهٔ محتوای ستون دست‌نخورده می‌ماند."""
    unknown = set(update) - set(SECTIONS)
    if unknown:
        msg = f"بخش ناشناختهٔ نیمرخ عمومی: {', '.join(sorted(unknown))}"
        raise ValueError(msg)
    return {**(privacy_settings or {}), **{k: bool(v) for k, v in update.items()}}


__all__ = [
    "SECTIONS",
    "SECTION_TITLE_FA",
    "TOP_SKILL_LIMIT",
    "TOP_SKILL_MIN_LEVEL",
    "merge",
    "sections",
]
