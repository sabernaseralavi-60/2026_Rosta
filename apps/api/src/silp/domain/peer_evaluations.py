"""قواعد ارزیابی همتا — FR-PRJ-08، ADR-0024 برش ب.

خالص است: بدون دیتابیس. سرویس این‌ها را می‌خواند تا آستانهٔ ناشناسی و
قواعد «همهٔ همتاها» یک‌جا بماند.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

RATING_RANGE = (1, 5)

#: میانگینِ کمتر از این تعداد ارزیابی نشان داده نمی‌شود: با یک ارزیابی،
#: «میانگین» همان نظر یک نفر است و ناشناسی از بین می‌رود.
MIN_EVALUATIONS_FOR_AVERAGE = 2

#: منبع امتیاز: خودِ پروژه — هر (ارزیابی‌کننده، پروژه) یک بار امتیاز می‌گیرد،
#: نه به‌ازای هر همتا (تیم ده‌نفره ۴۵ امتیاز رایگان می‌گرفت).
POINT_SOURCE_TYPE = "PROJECT_PEER_EVAL"


@dataclass(frozen=True, slots=True)
class PeerRating:
    evaluatee_id: uuid.UUID
    contribution: int
    reliability: int | None = None


def _in_range(value: int) -> bool:
    low, high = RATING_RANGE
    return low <= value <= high


def validate(ratings: Sequence[PeerRating], peer_ids: Iterable[uuid.UUID]) -> str | None:
    """پیام خطای فارسی، یا `None` اگر ارزیابی کامل و پذیرفتنی است.

    باید دقیقاً یک ردیف برای **هر** عضو فعالِ دیگر باشد: نه کمتر (ناقص ۴۲۲)،
    نه بیشتر، نه تکراری. «هر همتا» شرط امتیاز است، پس نیمه‌کاره ذخیره نمی‌شود.
    """
    expected = set(peer_ids)
    given = [rating.evaluatee_id for rating in ratings]
    if len(given) != len(set(given)):
        return "برای هر هم‌تیمی فقط یک ارزیابی بفرست."
    if not set(given) <= expected:
        return "فقط اعضای فعال دیگر تیم را می‌شود ارزیابی کرد."
    if set(given) != expected:
        return "همهٔ هم‌تیمی‌ها را ارزیابی کن؛ ارزیابی ناقص ثبت نمی‌شود."
    low, high = RATING_RANGE
    for rating in ratings:
        if not _in_range(rating.contribution):
            return f"سهم همکاری عددی از {low} تا {high} است."
        if rating.reliability is not None and not _in_range(rating.reliability):
            return f"قابل‌اعتماد بودن عددی از {low} تا {high} است."
    return None


def average(values: Sequence[int]) -> float | None:
    """میانگین گردشدهٔ یک رقم اعشار؛ `None` اگر ارزیابی برای ناشناس ماندن کم است."""
    if len(values) < MIN_EVALUATIONS_FOR_AVERAGE:
        return None
    return round(sum(values) / len(values), 1)


__all__ = [
    "MIN_EVALUATIONS_FOR_AVERAGE",
    "POINT_SOURCE_TYPE",
    "RATING_RANGE",
    "PeerRating",
    "average",
    "validate",
]
