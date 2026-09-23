"""تاریخ شمسی برای متن‌هایی که سرور می‌سازد — منطق خالص.

رابط وب تاریخ را خودش با `Intl` شمسی می‌کند؛ ولی متن پیامک و ایمیل را
سرور می‌سازد و «مهلت: 2026-10-01» برای دانشجو بی‌معناست (§14.7).

الگوریتم تبدیل همان روش حسابی مشهور (jdf) است که برای بازهٔ ۱۱۷۸ تا
۱۶۳۳ شمسی با تقویم رسمی یکی است — بیش از عمر این سامانه.
"""

from __future__ import annotations

from datetime import date, datetime

from silp.domain.gamification.formulas import LOCAL_TZ
from silp.domain.text import to_persian_digits

MONTHS_FA = (
    "فروردین",
    "اردیبهشت",
    "خرداد",
    "تیر",
    "مرداد",
    "شهریور",
    "مهر",
    "آبان",
    "آذر",
    "دی",
    "بهمن",
    "اسفند",
)

_G_DAYS_BEFORE_MONTH = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)


def to_jalali(day: date) -> tuple[int, int, int]:
    gy, gm, gd = day.year, day.month, day.day
    gy2 = gy + 1 if gm > 2 else gy
    days = (
        355666
        + 365 * gy
        + (gy2 + 3) // 4
        - (gy2 + 99) // 100
        + (gy2 + 399) // 400
        + gd
        + _G_DAYS_BEFORE_MONTH[gm - 1]
    )
    jy = -1595 + 33 * (days // 12053)
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        return jy, 1 + days // 31, 1 + days % 31
    return jy, 7 + (days - 186) // 30, 1 + (days - 186) % 30


def format_date_fa(day: date, *, with_year: bool = False) -> str:
    """«۹ مهر» یا «۹ مهر ۱۴۰۵»."""
    jy, jm, jd = to_jalali(day)
    text = f"{jd} {MONTHS_FA[jm - 1]}"
    if with_year:
        text = f"{text} {jy}"
    return to_persian_digits(text)


def format_datetime_fa(moment: datetime) -> str:
    """«۹ مهر، ساعت ۱۸:۰۰» — به وقت تهران."""
    local = moment.astimezone(LOCAL_TZ)
    return f"{format_date_fa(local.date())}، ساعت {to_persian_digits(local.strftime('%H:%M'))}"


__all__ = ["MONTHS_FA", "format_date_fa", "format_datetime_fa", "to_jalali"]
