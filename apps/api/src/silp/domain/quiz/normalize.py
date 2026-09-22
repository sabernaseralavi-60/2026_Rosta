"""نرمال‌سازی پاسخ کوتاه فارسی — منطق خالص، بدون I/O.

وظیفهٔ نقشهٔ راه: M4-09. مرجع: FR-QUIZ-03.

مسئله ساده به‌نظر می‌رسد و نیست. دانشجو «مدل خطی تعمیم‌یافته» را به این
شکل‌ها می‌نویسد و هر شش تا یک پاسخ‌اند:

    مدل خطی تعمیم‌یافته · مدل خطي تعميم يافته · مدل  خطی تعمیم یافته
    مُدل خطی تعمیم‌یافته · مدل خطی تعمیم‌یافته  · Model خطی…

اگر تطبیق خام باشد، پنج تای اول غلط حساب می‌شوند — و این یعنی نمرهٔ
اشتباه برای دانشجویی که پاسخ را بلد بود. برای همین تطبیق **روی شکل
نرمال‌شده** انجام می‌شود، نه روی متن خام.

## نسبت با `fa_normalize()` دیتابیس

همان قواعد §4.0 و [ADR-0003] است، با یک تفاوت عمدی: اینجا ارقام هم
یکدست می‌شوند («۱۲» ≡ «12»). در جستجو این لازم نبود چون هر دو شکل در
ستون ذخیره‌شده می‌مانند، ولی در تصحیح، «۱۲ متر» و «12 متر» یک پاسخ‌اند
و رد کردن یکی از آن‌ها صرفاً تنبیهِ صفحه‌کلید است.

تابع SQL برای **جستجو**ست و این یکی برای **تصحیح**؛ یکی کردنشان یعنی
یکی از دو کار بد انجام شود. تست `test_python_and_sql_normalizers_agree`
نگه می‌دارد که در آنچه مشترک است واگرا نشوند.
"""

from __future__ import annotations

import re
import unicodedata

# ── نگاشت عربی → فارسی، نویسه‌به‌نویسه هم‌طول (ADR-0003 مسئلهٔ ۱) ───────
# طول دو رشته باید برابر بماند؛ اگر کسی نویسه‌ای افزود و جفتش را نه،
# `str.maketrans` خودش خطا می‌دهد — که بهتر از نگاشت بی‌صدای غلط است.
_ARABIC_SOURCE = "يكةأإآؤئىۀ"
_PERSIAN_TARGET = "یکهاااوییه"

_PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
_ARABIC_DIGITS = "٠١٢٣٤٥٦٧٨٩"
_LATIN_DIGITS = "0123456789"

_CHAR_MAP = str.maketrans(
    _ARABIC_SOURCE + _PERSIAN_DIGITS + _ARABIC_DIGITS,
    _PERSIAN_TARGET + _LATIN_DIGITS * 2,
)

# اعراب و کشیده: U+064B تا U+0670. **حذف** می‌شوند، نه جایگزین با فاصله،
# وگرنه «مُحَمَّد» به «م ح م د» تبدیل می‌شود (ADR-0003 مسئلهٔ ۲).
_DIACRITICS = re.compile("[ً-ٰ]+")

# نیم‌فاصله و علائم جهت: به فاصله تبدیل می‌شوند، چون **بین** واژه‌اند.
_ZERO_WIDTH = re.compile("[​-‏﻿]+")

_WHITESPACE = re.compile(r"\s+")

# نشانه‌گذاری پایانی که معنای پاسخ را عوض نمی‌کند: «پواسون.» ≡ «پواسون»
_TRAILING_PUNCT = re.compile(r"[.،؛:!?؟\s]+$")


def normalize_answer(raw: str | None) -> str:
    """شکل نرمال یک پاسخ کوتاه.

    ترتیب مراحل اهمیت دارد: NFKC اول می‌آید تا نویسه‌های عرض‌کامل و
    شکل‌های جایگزین (ﻲ، ﮐ) پیش از نگاشت به شکل پایه برسند.
    """
    if not raw:
        return ""

    value = unicodedata.normalize("NFKC", raw)
    value = value.translate(_CHAR_MAP)
    value = _DIACRITICS.sub("", value)
    value = _ZERO_WIDTH.sub(" ", value)
    value = _WHITESPACE.sub(" ", value).strip()
    value = _TRAILING_PUNCT.sub("", value)
    return value.lower()


def answers_match(given: str | None, accepted: str, *, case_sensitive: bool = False) -> bool:
    """آیا پاسخ دانشجو با یک پاسخ پذیرفته یکی است؟

    `case_sensitive` فقط روی حروف لاتین اثر دارد — فارسی حرف بزرگ و کوچک
    ندارد. وقتی استاد آن را روشن می‌کند (مثلاً نام یک تابع R)، تنها
    مرحلهٔ کوچک‌سازی کنار می‌رود؛ بقیهٔ نرمال‌سازی سر جایش می‌ماند، چون
    «حساس به بزرگی و کوچکی» یعنی همین، نه «حساس به اعراب و نیم‌فاصله».
    """
    if case_sensitive:
        return _normalize_preserving_case(given) == _normalize_preserving_case(accepted)
    return normalize_answer(given) == normalize_answer(accepted)


def _normalize_preserving_case(raw: str | None) -> str:
    if not raw:
        return ""
    value = unicodedata.normalize("NFKC", raw)
    value = value.translate(_CHAR_MAP)
    value = _DIACRITICS.sub("", value)
    value = _ZERO_WIDTH.sub(" ", value)
    value = _WHITESPACE.sub(" ", value).strip()
    return _TRAILING_PUNCT.sub("", value)


__all__ = ["answers_match", "normalize_answer"]
