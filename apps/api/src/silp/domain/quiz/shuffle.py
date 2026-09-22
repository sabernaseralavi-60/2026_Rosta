"""درهم‌سازی قطعی سؤال و گزینه — منطق خالص. FR-QUIZ-02، §7.3 قاعدهٔ ۴.

دو نیاز که با هم در تنش‌اند:

۱. ترتیب هر دانشجو باید **متفاوت** باشد (نگاه‌کردن به مانیتور بغلی).
۲. ترتیب همان دانشجو باید با رفرش صفحه **تغییر نکند**.

## چرا `random.shuffle` نه

`random.Random(seed).shuffle` قطعی است ولی تضمینِ نسخه‌ای ندارد:
الگوریتم Mersenne Twister ثابت است، اما ترتیبی که `shuffle` از آن
می‌سازد جزء API پایدار CPython نیست. ارتقای پایتون وسط یک نیم‌سال
می‌تواند ترتیب گزینه‌ها را عوض کند — و چون ترتیبِ گزینه ذخیره **نمی‌شود**
(برخلاف `question_order`)، دانشجویی که وسط آزمون صفحه را رفرش کند،
گزینه‌ها را جابه‌جا می‌بیند و پاسخ ذخیره‌شده‌اش روی گزینهٔ دیگری می‌نشیند.

به‌جایش کلید مرتب‌سازی از `sha256(attempt_id | question_id | item_id)`
گرفته می‌شود: تابعی مشخص، مستقل از نسخهٔ پایتون، و قابل بازتولید در هر
زبانی. همان ورودی، همیشه همان ترتیب.

`question_order` با این حال ذخیره می‌شود (§4.5): اگر استاد وسط آزمون
سؤالی بیفزاید، ترتیبِ ذخیره‌شده دست‌نخورده می‌ماند و تلاش‌های در جریان
تکان نمی‌خورند.
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Sequence


def _sort_key(*parts: str) -> bytes:
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).digest()
    return digest


def shuffled_ids(
    ids: Sequence[uuid.UUID | str],
    *,
    seed: uuid.UUID | str,
    scope: str = "",
) -> list[str]:
    """ترتیب قطعیِ درهم برای یک فهرست شناسه.

    `scope` شناسهٔ سؤال است وقتی گزینه‌ها درهم می‌شوند؛ بدون آن، همهٔ
    سؤال‌های یک تلاش گزینه‌هایشان را به یک الگو جابه‌جا می‌کردند.
    """
    seed_text = str(seed)
    return sorted((str(i) for i in ids), key=lambda item: _sort_key(seed_text, scope, item))


def question_order(
    question_ids: Sequence[uuid.UUID],
    *,
    attempt_id: uuid.UUID,
    shuffle: bool,
) -> list[uuid.UUID]:
    """ترتیب سؤال‌های یک تلاش — در لحظهٔ شروع تولید و ذخیره می‌شود."""
    if not shuffle:
        return list(question_ids)
    ordered = shuffled_ids(question_ids, seed=attempt_id)
    return [uuid.UUID(value) for value in ordered]


def option_order(
    option_ids: Sequence[str],
    *,
    attempt_id: uuid.UUID,
    question_id: uuid.UUID | str,
    shuffle: bool,
) -> tuple[str, ...]:
    """ترتیب گزینه‌های یک سؤال در یک تلاش — ذخیره نمی‌شود، بازمحاسبه می‌شود."""
    if not shuffle:
        return tuple(option_ids)
    return tuple(shuffled_ids(option_ids, seed=attempt_id, scope=str(question_id)))


__all__ = ["option_order", "question_order", "shuffled_ids"]
