"""گواهی — FR-PRJ-08، FR-PROF-03، §7.13، ADR-0017. منطق خالص، بدون I/O.

## کد عمومی

`XXXX-XXXX` از الفبای Crockford Base32 (بی `I`، `L`، `O`، `U`) — ۴۰ بیت
تصادفی. کوتاه است تا روی برگهٔ چاپی یا در گفتگوی تلفنی خوانده شود، و
حدس‌ناپذیر است تا کسی با شمردن کدها فهرست دارندگان گواهی را بیرون نکشد.
کاربری که `O` یا `I` تایپ کند، همان `0` و `1` را می‌گیرد.

## چه چیزی گواهی می‌گیرد

| نوع | رویداد | صادرکننده |
|-----|--------|-----------|
| `PROJECT` | بستن پروژه (`ProjectCompleted`) — هر عضو فعال | کسی که پروژه را بست، مگر خود دارنده |
| `RESEARCH_LEVEL` | تأیید سطح (`ResearchReviewed`) | بازبین سطح |
| `COURSE` | نمرهٔ نهایی ≥ ۱۰ (`EnrollmentCompleted`) | استاد ارائه |

نمره روی گواهی درس نمی‌آید: FR-PROF-03 «نمرات درسی هرگز نمایش داده
نمی‌شود» و صفحهٔ راستی‌آزمایی عمومی است.
"""

from __future__ import annotations

import re
import secrets
from decimal import Decimal

from silp.domain.text import to_persian_digits

#: Crockford Base32 — بی حرف‌هایی که با رقم اشتباه می‌شوند.
CODE_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
CODE_GROUP = 4
CODE_PATTERN = re.compile(r"^[0-9A-Z]{4}-[0-9A-Z]{4}$")

#: نمرهٔ قبولی درس در مقیاس ۲۰ — آیین‌نامهٔ آموزشی کارشناسی.
COURSE_PASS_GRADE = Decimal("10")

_CONFUSABLE = str.maketrans({"O": "0", "I": "1", "L": "1"})
_PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def new_code() -> str:
    raw = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_GROUP * 2))
    return f"{raw[:CODE_GROUP]}-{raw[CODE_GROUP:]}"


def normalize_code(value: str) -> str | None:
    """ورودی کاربر به شکل استاندارد؛ ناممکن ⇒ `None`.

    فاصله و خط تیره اختیاری‌اند، حروف کوچک و رقم فارسی پذیرفته می‌شوند.
    """
    cleaned = re.sub(r"[\s\-_\u200c]", "", value.translate(_PERSIAN_DIGITS)).upper()
    cleaned = cleaned.translate(_CONFUSABLE)
    if len(cleaned) != CODE_GROUP * 2 or any(c not in CODE_ALPHABET for c in cleaned):
        return None
    return f"{cleaned[:CODE_GROUP]}-{cleaned[CODE_GROUP:]}"


def project_title(project_title_fa: str) -> str:
    return f"تکمیل پروژهٔ «{project_title_fa}»"


def research_title(level: int, level_title_fa: str) -> str:
    return f"سطح {to_persian_digits(str(level))} مسیر پژوهش — {level_title_fa}"


def course_title(course_title_fa: str) -> str:
    return f"گذراندن درس «{course_title_fa}»"


def course_passed(grade: Decimal | float | None) -> bool:
    return grade is not None and Decimal(str(grade)) >= COURSE_PASS_GRADE


__all__ = [
    "CODE_ALPHABET",
    "CODE_PATTERN",
    "COURSE_PASS_GRADE",
    "course_passed",
    "course_title",
    "new_code",
    "normalize_code",
    "project_title",
    "research_title",
]
