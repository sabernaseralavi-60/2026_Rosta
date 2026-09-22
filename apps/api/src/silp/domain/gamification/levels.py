"""سطح از امتیاز کل — PRD §9.4، FR-GAM-03.

```
آستانهٔ سطح n  =  round(50 × (n − 1)^1.6)      n ≥ 1
```

جدول §9.4 مرجع تست است (`test_level_thresholds_match_table`): اگر فرمول
عوض شد، جدول هم باید عوض شود. نسخهٔ پیش‌نویس جدول از سطح ۷ به بعد با
فرمول نمی‌خواند (۸۸۰ به‌جای ۸۷۹ و …) — خطای حساب دستی بود و اصلاح شد
(ADR-0012).

گرد کردن «نیم به بالا» است، نه گرد کردن بانکی پایتون: `round(2.5)` در
پایتون ۲ می‌دهد و آستانه‌ای که روی نیم بیفتد، یک امتیاز جابه‌جا می‌شد.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

BASE = Decimal(50)
EXPONENT = 1.6

#: نگهبان حلقه، نه قاعدهٔ محصول. سطح ۹۹ یعنی ۷۶ هزار امتیاز.
MAX_LEVEL = 99

#: عنوان سطح‌های نام‌دار §9.4. سطح‌های میانی عنوان پایین‌ترین سطح نام‌دار
#: زیر خود را می‌گیرند — سطح ۱۱ هنوز «معمار» است تا ۱۲ «استاد کار» شود.
LEVEL_TITLES_FA: dict[int, str] = {
    1: "تازه‌وارد",
    2: "کاوشگر",
    3: "یادگیرنده",
    4: "سازنده",
    5: "همکار",
    6: "مشارکت‌کننده",
    7: "ماهر",
    8: "خبره",
    9: "پیشرو",
    10: "معمار",
    12: "استاد کار",
    15: "مرجع",
    20: "افسانه",
}


def threshold(level: int) -> int:
    """کمینهٔ امتیاز کل برای رسیدن به `level`."""
    if level < 1:
        raise ValueError("سطح از ۱ شروع می‌شود.")
    raw = BASE * Decimal(repr((level - 1) ** EXPONENT))
    return int(raw.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def level_for(total: Decimal | int) -> int:
    """سطحی که امتیاز کل `total` به آن رسیده است. امتیاز منفی = سطح ۱."""
    points = Decimal(total)
    level = 1
    while level < MAX_LEVEL and points >= threshold(level + 1):
        level += 1
    return level


def title_for(level: int) -> str:
    named = max(n for n in LEVEL_TITLES_FA if n <= max(level, 1))
    return LEVEL_TITLES_FA[named]


@dataclass(frozen=True, slots=True)
class LevelProgress:
    """آنچه نوار سطح نشان می‌دهد — «۱۳۰ امتیاز تا سطح بعد» (§9.4).

    `to_next` هرگز منفی نیست و در سقف سطح صفر است.
    """

    total: Decimal
    level: int
    title_fa: str
    current_at: int
    next_at: int | None
    to_next: Decimal
    ratio: Decimal


def progress(total: Decimal | int) -> LevelProgress:
    points = max(Decimal(total), Decimal(0))
    level = level_for(points)
    current_at = threshold(level)
    next_at = threshold(level + 1) if level < MAX_LEVEL else None
    if next_at is None:
        to_next = Decimal(0)
        ratio = Decimal(1)
    else:
        to_next = Decimal(next_at) - points
        span = Decimal(next_at - current_at)
        ratio = ((points - current_at) / span).quantize(Decimal("0.001"))
    return LevelProgress(
        total=points,
        level=level,
        title_fa=title_for(level),
        current_at=current_at,
        next_at=next_at,
        to_next=to_next,
        ratio=ratio,
    )


__all__ = [
    "LEVEL_TITLES_FA",
    "MAX_LEVEL",
    "LevelProgress",
    "level_for",
    "progress",
    "threshold",
    "title_for",
]
