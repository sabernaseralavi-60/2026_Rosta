"""کمک‌های متن فارسی — منطق خالص، بدون I/O.

متن‌هایی که سرور تولید می‌کند و مستقیماً نمایش داده می‌شوند (دلایل
توصیه‌گر §8.10، پیام‌های اعلان §14.7) باید ارقام فارسی داشته باشند.
رابط کاربری نباید متن سرور را دستکاری کند — §5.1.
"""

from __future__ import annotations

_LATIN_DIGITS = "0123456789"
_PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
_TO_PERSIAN = str.maketrans(_LATIN_DIGITS, _PERSIAN_DIGITS)


def to_persian_digits(value: str | int | float) -> str:
    """ارقام لاتین را به فارسی تبدیل می‌کند.

    اعشار با ممیز فارسی «٫» نوشته می‌شود، نه نقطه.
    """
    return str(value).translate(_TO_PERSIAN).replace(".", "٫")


def join_fa(parts: list[str]) -> str:
    """پیوند فهرست با «و» فارسی: «الف، ب و ج»."""
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    return f"{'، '.join(parts[:-1])} و {parts[-1]}"


__all__ = ["join_fa", "to_persian_digits"]
