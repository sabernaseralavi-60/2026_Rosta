"""قواعد خالص بانک ایده — FR-IDEA-02، §9.2. بدون I/O.

## رتبه‌بندی با زوال زمانی

```
score = votes / (hours_since_post + 2) ^ 1.5
```

تا ایدهٔ تازه شانس دیده‌شدن داشته باشد. همین فرمول در SQL هم نوشته شده
(`IdeaService._hot_score`)؛ این نسخهٔ پایتونی مرجع تست است و هر دو باید
یکی بمانند.
"""

from __future__ import annotations

from datetime import datetime

from silp.models.idea import IDEA_CATEGORY_TITLE_FA, MAX_TAGS

HOT_OFFSET_HOURS = 2.0
HOT_GRAVITY = 1.5

#: آستانه‌های رأی و قاعدهٔ امتیازشان — §9.2 «یک‌بار».
VOTE_MILESTONES: tuple[tuple[int, str], ...] = ((10, "IDEA_VOTES_10"), (50, "IDEA_VOTES_50"))

TAG_MAX_LENGTH = 30


def hot_score(votes: int, created_at: datetime, now: datetime) -> float:
    hours = max((now - created_at).total_seconds() / 3600.0, 0.0)
    return float(votes / (hours + HOT_OFFSET_HOURS) ** HOT_GRAVITY)


def reached_milestones(vote_count: int) -> list[str]:
    """قواعد آستانه‌ای که این تعداد رأی به آن‌ها رسیده."""
    return [rule for threshold, rule in VOTE_MILESTONES if vote_count >= threshold]


def clean_tags(tags: list[str] | None) -> list[str]:
    """برچسب‌ها: فاصلهٔ اضافه حذف، `#` ابتدایی برداشته، تکراری یکی، حداکثر ۸.

    برچسب خالی یا بلندتر از ۳۰ نویسه نادیده گرفته نمی‌شود — خطاست؛ کاربر
    باید بداند چرا برچسبش ثبت نشد.
    """
    result: list[str] = []
    for raw in tags or []:
        tag = " ".join(raw.strip().lstrip("#").split())
        if not tag:
            continue
        if len(tag) > TAG_MAX_LENGTH:
            msg = f"برچسب «{tag[:20]}…» بلندتر از {TAG_MAX_LENGTH} نویسه است."
            raise ValueError(msg)
        if tag not in result:
            result.append(tag)
    if len(result) > MAX_TAGS:
        msg = f"حداکثر {MAX_TAGS} برچسب."
        raise ValueError(msg)
    return result


def category_title(code: str | None) -> str | None:
    return IDEA_CATEGORY_TITLE_FA.get(code) if code else None


__all__ = [
    "HOT_GRAVITY",
    "HOT_OFFSET_HOURS",
    "VOTE_MILESTONES",
    "category_title",
    "clean_tags",
    "hot_score",
    "reached_milestones",
]
