"""نرمال‌سازی مقصد OTP — منطق خالص، بدون I/O.

کاربر ایرانی شمارهٔ موبایل را به شش شکل مختلف وارد می‌کند و همه باید به یک
مقدار ذخیره‌شده برسند، وگرنه یک نفر با دو حساب مواجه می‌شود:

    ۰۹۱۲۱۲۳۴۵۶۷ · 09121234567 · +989121234567
    0098912... · 989121234567 · 0912 123 4567

قالب ذخیره‌شده همیشه ``^09\\d{9}$`` است (PRD §4.2).
"""

from __future__ import annotations

import re
import unicodedata
from typing import Literal

Channel = Literal["SMS", "EMAIL"]

# ارقام فارسی (۰-۹) و عربی-هندی (٠-٩) به لاتین
_PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
_ARABIC_DIGITS = "٠١٢٣٤٥٦٧٨٩"
_LATIN_DIGITS = "0123456789"
_DIGIT_MAP = str.maketrans(_PERSIAN_DIGITS + _ARABIC_DIGITS, _LATIN_DIGITS * 2)

# کاراکترهایی که کاربر برای خوانایی وارد می‌کند و معنایی ندارند
_SEPARATORS = re.compile(r"[\s\-().‌‏‎]")

MOBILE_RE = re.compile(r"^09\d{9}$")
# اعتبارسنجی عملی ایمیل. اعتبارسنجی قطعی فقط با ارسال نامه ممکن است.
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s.]+(\.[^@\s.]+)+$")

MOBILE_LENGTH = 11


def to_latin_digits(value: str) -> str:
    """ارقام فارسی و عربی را به لاتین تبدیل می‌کند."""
    return value.translate(_DIGIT_MAP)


def normalize_mobile(raw: str | None) -> str | None:
    """تبدیل هر شکل ورودی به قالب ذخیره‌شده، یا None اگر معتبر نباشد."""
    if not raw:
        return None

    value = _SEPARATORS.sub("", to_latin_digits(raw.strip()))

    # پیشوندهای بین‌المللی، از بلندترین به کوتاه‌ترین
    for prefix in ("+98", "0098", "98"):
        if value.startswith(prefix):
            value = value[len(prefix) :]
            break
    else:
        if value.startswith("0"):
            value = value[1:]

    # اکنون باید `9XXXXXXXXX` باشد
    candidate = f"0{value}"
    return candidate if MOBILE_RE.match(candidate) else None


def normalize_email(raw: str | None) -> str | None:
    """کوچک‌سازی و پاک‌سازی ایمیل. ستون CITEXT است، ولی ذخیرهٔ یکدست
    مقایسه در لاگ و گزارش را هم ساده می‌کند."""
    if not raw:
        return None
    # NFKC نویسه‌های عرض‌کامل و شکل‌های جایگزین را یکدست می‌کند.
    value = unicodedata.normalize("NFKC", raw.strip()).lower()
    return value if EMAIL_RE.match(value) else None


def normalize_destination(raw: str, channel: Channel) -> str | None:
    """نرمال‌سازی بر اساس کانال."""
    return normalize_mobile(raw) if channel == "SMS" else normalize_email(raw)


def detect_channel(raw: str) -> Channel:
    """حدس کانال از روی شکل ورودی — کاربر نباید مجبور به انتخاب باشد."""
    return "EMAIL" if "@" in raw else "SMS"


def is_valid_national_id(raw: str | None) -> bool:
    """چک‌دیجیت کد ملی ایران — FR-AUTH-04.

    الگوریتم: مجموع وزنی ۹ رقم اول (وزن ۱۰ تا ۲)، باقی‌ماندهٔ تقسیم بر ۱۱.
    اگر باقی‌مانده < ۲ باشد، رقم کنترل باید برابر آن باشد؛ در غیر این صورت
    برابر ۱۱ منهای باقی‌مانده.
    """
    if not raw:
        return False
    value = _SEPARATORS.sub("", to_latin_digits(raw.strip()))
    if not re.fullmatch(r"\d{10}", value):
        return False
    # ارقام یکسان (مثل ۰۰۰۰۰۰۰۰۰۰) از چک‌دیجیت عبور می‌کنند ولی معتبر نیستند.
    if value == value[0] * 10:
        return False

    checksum = sum(int(value[i]) * (10 - i) for i in range(9))
    remainder = checksum % 11
    control = int(value[9])
    return control == remainder if remainder < 2 else control == 11 - remainder
