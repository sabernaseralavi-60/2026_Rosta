"""تولید نام کاربری — PRD §7.1. منطق خالص، بدون I/O.

نام کاربری برای آدرس نیمرخ عمومی (/u/{username}) لازم است و خودکار ساخته
می‌شود. حرف‌نویسی فارسی به لاتین با نگاشت سفارشی انجام می‌گیرد، چون
حرف‌نویس‌های عمومی «خ» را «kh» نمی‌کنند و «ی» پایانی را می‌خورند.
"""

from __future__ import annotations

import re
import secrets
from collections.abc import Callable, Iterator

MAX_BASE_LENGTH = 28
MAX_NUMERIC_SUFFIX = 99
RANDOM_SUFFIX_DIGITS = 4

# §7.1 — کلمات رزرو. نام کاربری نباید با مسیرهای سامانه تداخل کند.
RESERVED_USERNAMES: frozenset[str] = frozenset(
    {
        "admin",
        "api",
        "teach",
        "me",
        "u",
        "login",
        "verify",
        "settings",
        "projects",
        "courses",
        "ideas",
        "teams",
        "dashboard",
        "null",
        "undefined",
        # افزوده بر سند: بقیهٔ مسیرهای سطح‌اول §3
        "about",
        "research",
        "ventures",
        "notifications",
        "onboarding",
        "quiz",
        "public",
        "static",
        "assets",
        "health",
        "support",
        "silp",
    }
)

# نگاشت حرف‌نویسی فارسی به لاتین. ترتیب مهم نیست چون تک‌نویسه است.
_TRANSLITERATION: dict[str, str] = {
    "ا": "a",
    "آ": "a",
    "أ": "a",
    "إ": "a",
    "ء": "",
    "ب": "b",
    "پ": "p",
    "ت": "t",
    "ث": "s",
    "ج": "j",
    "چ": "ch",
    "ح": "h",
    "خ": "kh",
    "د": "d",
    "ذ": "z",
    "ر": "r",
    "ز": "z",
    "ژ": "zh",
    "س": "s",
    "ش": "sh",
    "ص": "s",
    "ض": "z",
    "ط": "t",
    "ظ": "z",
    "ع": "a",
    "غ": "gh",
    "ف": "f",
    "ق": "gh",
    "ک": "k",
    "ك": "k",
    "گ": "g",
    "ل": "l",
    "م": "m",
    "ن": "n",
    "و": "o",
    "ه": "h",
    "ة": "h",
    "ی": "i",
    "ي": "i",
    "ى": "i",
    "‌": "-",  # نیم‌فاصله مرز کلمه است
    " ": "-",
    "_": "-",
}

# حروفی که خودشان صدای بلند می‌دهند؛ بین این‌ها و همسایه‌شان مصوت
# درج نمی‌شود. «ه» اینجا نیست چون در میان واژه همخوان است («زهرا»)؛
# حالت پایانی‌اش جداگانه مدیریت می‌شود.
_VOWEL_LETTERS = frozenset("اآأإوی يىء")
_WORD_BREAKS = ("", " ", "‌", "_", "-")

# اعراب و کشیده پیش از حرف‌نویسی حذف می‌شوند.
_DIACRITICS = re.compile(r"[ً-ٰ]")
_NON_SLUG = re.compile(r"[^a-z0-9-]")
_DASH_RUN = re.compile(r"-{2,}")

DEFAULT_SHORT_VOWEL = "a"


def _is_consonant(ch: str) -> bool:
    return ch in _TRANSLITERATION and ch not in _VOWEL_LETTERS and ch not in " _‌"


def _is_final_heh(ch: str, nxt: str) -> bool:
    """«ه» در پایان واژه، نه در میان آن."""
    return ch == "ه" and nxt in _WORD_BREAKS


def slugify_fa(value: str) -> str:
    """حرف‌نویسی فارسی به لاتین و تبدیل به slug مجاز در URL.

    خط فارسی مصوت کوتاه نمی‌نویسد، پس حرف‌نویسی ساده «مریم» را «mrim»
    می‌کند که نه خوانا است و نه چیزی که §7.1 انتظار دارد. برای همین بین
    دو همخوان پشت‌سرهم یک «a» درج می‌شود: «مریم» ← «marim»، «کریمی» ←
    «karimi».

    این یک حدس است، نه آوانگاری دقیق — آوانگاری دقیق بدون واژه‌نامه ممکن
    نیست. کاربر می‌تواند نام کاربری را یک‌بار تغییر دهد (§7.1)، پس تقریب
    خوانا از دقت ناممکن بهتر است. دو درج پشت‌سرهم انجام نمی‌شود تا
    واژه‌های پرهمخوان («خسرو») به رشته‌ای کشدار تبدیل نشوند.
    """
    cleaned = _DIACRITICS.sub("", value.strip().lower())

    pieces: list[str] = []
    just_inserted = False
    for index, ch in enumerate(cleaned):
        nxt = cleaned[index + 1] if index + 1 < len(cleaned) else ""
        after_nxt = cleaned[index + 2] if index + 2 < len(cleaned) else ""
        # «ه» پایانی در فارسی صدای «e» دارد، نه «h»: «ژاله» ← «zhale».
        if _is_final_heh(ch, nxt):
            piece = "e"
        else:
            piece = _TRANSLITERATION.get(ch, ch)
        pieces.append(piece)

        # اگر حرف‌نویسی خودش به مصوت ختم شده، درج مصوت دوباره زائد است:
        # «علی» باید «ali» شود، نه «aali».
        ends_in_vowel = bool(piece) and piece[-1] in "aeio"
        # پیش از «ه» پایانی مصوت درج نمی‌شود، وگرنه «ژاله» می‌شود «zhalae».
        next_is_final_heh = _is_final_heh(nxt, after_nxt)
        if (
            not just_inserted
            and not ends_in_vowel
            and not next_is_final_heh
            and _is_consonant(ch)
            and _is_consonant(nxt)
        ):
            pieces.append(DEFAULT_SHORT_VOWEL)
            just_inserted = True
        else:
            just_inserted = False

    out = _NON_SLUG.sub("-", "".join(pieces))
    out = _DASH_RUN.sub("-", out).strip("-")
    return out


def candidates(first: str, last: str) -> Iterator[str]:
    """دنبالهٔ نامزدهای نام کاربری، به ترتیب اولویت.

    ابتدا پایه، سپس ``-2`` تا ``-99``، و در نهایت پسوند تصادفی ۴ رقمی.
    دنباله بی‌پایان نیست ولی عملاً تمام نمی‌شود.
    """
    base = slugify_fa(f"{first}-{last}")[:MAX_BASE_LENGTH].strip("-") or "user"

    # نام پایه اگر رزرو باشد، هرگز به‌تنهایی پیشنهاد نمی‌شود.
    if base not in RESERVED_USERNAMES:
        yield base

    for n in range(2, MAX_NUMERIC_SUFFIX + 1):
        yield f"{base}-{n}"

    while True:
        suffix = secrets.randbelow(10**RANDOM_SUFFIX_DIGITS)
        yield f"{base}-{suffix:0{RANDOM_SUFFIX_DIGITS}d}"


def pick_username(
    first: str,
    last: str,
    *,
    is_taken: Callable[[str], bool],
    max_tries: int = 120,
) -> str:
    """اولین نامزد آزاد را برمی‌گرداند.

    ``is_taken`` تنها نقطهٔ تماس با دنیای بیرون است و از بیرون تزریق می‌شود،
    تا این تابع بدون دیتابیس تست شود.
    """
    for attempt, candidate in enumerate(candidates(first, last)):
        if attempt >= max_tries:
            break
        if candidate in RESERVED_USERNAMES:
            continue
        if not is_taken(candidate):
            return candidate

    # عملاً غیرقابل دسترسی؛ اگر رسیدیم، نام کاملاً تصادفی بهتر از خطاست.
    return f"user-{secrets.token_hex(4)}"


def is_valid_username(value: str) -> bool:
    """اعتبارسنجی نام کاربری انتخابی کاربر."""
    if not (3 <= len(value) <= 32):
        return False
    if value in RESERVED_USERNAMES:
        return False
    return bool(re.fullmatch(r"[a-z0-9]([a-z0-9-]*[a-z0-9])?", value))
