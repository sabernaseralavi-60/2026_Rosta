"""فهرست دانشجویان درس — منطق خالص، بدون I/O (ADR-0035).

شمارهٔ دانشجویی راز نیست (همکلاسی و دفتر آموزش آن را دارند)؛ پس هرگز
«رمز» نیست و متن خامش هم در دیتابیس نمی‌ماند. فقط HMAC آن نگه داشته می‌شود:
برای تطبیق کافی است و نشت جدول، شماره‌ها را فاش نمی‌کند.
"""

from __future__ import annotations

import hashlib
import hmac
import re

from silp.domain.identity.normalize import to_latin_digits

STUDENT_NO_RE = re.compile(r"^\d{5,15}$")
PASSWORD_MIN_LENGTH = 8

_SEPARATORS = re.compile(r"[\s\-‌‏‎]")


def normalize_student_no(raw: str | None) -> str | None:
    """رقم‌های لاتین و بی‌فاصله، یا None اگر شکل شمارهٔ دانشجویی نباشد."""
    if not raw:
        return None
    value = _SEPARATORS.sub("", to_latin_digits(str(raw).strip()))
    # اکسل عدد را گاهی «۴۰۱۲۳۴۵۶۷.۰» می‌نویسد.
    if value.endswith(".0"):
        value = value[:-2]
    return value if STUDENT_NO_RE.match(value) else None


def digest(value: str, secret: str) -> str:
    """HMAC-SHA256 با کلیدِ مشتق از راز سرور. کلید عوض شود، همهٔ هش‌ها باید بازسازی شوند."""
    key = hashlib.sha256(f"silp-roster-v1:{secret}".encode()).digest()
    return hmac.new(key, value.encode("utf-8"), hashlib.sha256).hexdigest()


def masked_name(first_name: str, last_name: str) -> str:
    """«علی ا.» — پیش از تأیید هویت، نام کامل به حدس‌زننده نشان داده نمی‌شود."""
    first = first_name.strip()
    family = last_name.strip()
    return f"{first} {family[:1]}." if family else first


def password_problem(password: str, *, forbidden_digests: set[str], secret: str) -> str | None:
    """پیام فارسی اگر رمز پذیرفتنی نیست؛ وگرنه None.

    رمز نباید خودِ شمارهٔ دانشجویی یا موبایل باشد: هر دو را دیگران می‌دانند. مقایسه با هش
    انجام می‌شود، چون متن خام شماره‌ها دیگر در دسترس نیست.
    """
    if len(password) < PASSWORD_MIN_LENGTH:
        return f"رمز باید دست‌کم {PASSWORD_MIN_LENGTH} نویسه باشد."
    candidate = to_latin_digits(password.strip())
    if digest(candidate, secret) in forbidden_digests:
        return "رمز نباید شمارهٔ دانشجویی یا موبایل شما باشد."
    if candidate.isdigit() and len(set(candidate)) == 1:
        return "رمز بیش از حد ساده است."
    return None
