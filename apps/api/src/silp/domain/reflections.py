"""قواعد بازتاب پایان پروژه — FR-PRJ-08، ADR-0024.

خالص است: بدون دیتابیس. سرویس این‌ها را می‌خواند تا آستانه یک‌جا بماند
و بی‌مهاجرت عوض شود (قید دیتابیس فقط «خالی نباشد» را می‌گوید).
"""

from __future__ import annotations

from dataclasses import dataclass

#: ۱۵ امتیاز برای «خوب بود» یعنی امتیاز رایگان (§9.8). ۳۰ نویسه یک جملهٔ
#: کامل است، نه یک مانع.
MIN_LEARNED_CHARS = 30
MAX_FIELD_CHARS = 4000
SATISFACTION_RANGE = (1, 5)

#: منبع امتیاز: خودِ پروژه — هر (کاربر، پروژه) یک بازتاب دارد.
POINT_SOURCE_TYPE = "PROJECT_REFLECTION"


@dataclass(frozen=True, slots=True)
class ReflectionDraft:
    learned: str
    challenges: str | None = None
    would_do_differently: str | None = None
    satisfaction: int | None = None


def clean(text: str | None) -> str | None:
    """فاصلهٔ اضافی را می‌برد؛ رشتهٔ تهی `None` است."""
    stripped = (text or "").strip()
    return stripped or None


def validate(draft: ReflectionDraft) -> str | None:
    """پیام خطای فارسی، یا `None` اگر بازتاب پذیرفتنی است."""
    learned = clean(draft.learned)
    if learned is None:
        return "بنویس در این پروژه چه آموختی."
    if len(learned) < MIN_LEARNED_CHARS:
        return f"«چه آموختم» دست‌کم {MIN_LEARNED_CHARS} نویسه (یک جملهٔ کامل) باشد."
    for value in (learned, draft.challenges, draft.would_do_differently):
        if value is not None and len(value.strip()) > MAX_FIELD_CHARS:
            return f"هر بخش حداکثر {MAX_FIELD_CHARS} نویسه است."
    low, high = SATISFACTION_RANGE
    if draft.satisfaction is not None and not low <= draft.satisfaction <= high:
        return f"رضایت عددی از {low} تا {high} است."
    return None


__all__ = [
    "MAX_FIELD_CHARS",
    "MIN_LEARNED_CHARS",
    "POINT_SOURCE_TYPE",
    "ReflectionDraft",
    "clean",
    "validate",
]
