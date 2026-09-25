"""قواعد پرسش‌وپاسخ درس — FR-EDU-07، ADR-0024 برش ج.

خالص است: بدون دیتابیس. سرویس و شنوندهٔ امتیاز آستانه‌ها را از اینجا می‌خوانند
تا یک‌جا بمانند و بی‌مهاجرت عوض شوند.
"""

from __future__ import annotations

from silp.models.qa import (
    BODY_MAX,
    REPLY_MIN,
    THREAD_BODY_MIN,
    TITLE_MAX,
    TITLE_MIN,
)

#: منبع امتیاز هر دو قاعده: خودِ پاسخ. هر پاسخ هر قاعده را حداکثر یک‌بار می‌گیرد.
POINT_SOURCE_TYPE = "QA_REPLY"
HELPFUL_RULE = "QA_ANSWER_HELPFUL"
OFFICIAL_RULE = "QA_ANSWER_OFFICIAL_MATCH"
RULES: tuple[str, ...] = (HELPFUL_RULE, OFFICIAL_RULE)

#: «≥۳ رأی مفید» — جدول §9.2. رأی خودِ نویسنده، استاد و دستیار به این عدد نمی‌رسد.
HELPFUL_VOTES_REQUIRED = 3

THREAD_FILTERS: tuple[str, ...] = ("all", "unanswered", "unresolved", "mine")


def clean_title(title: str) -> str:
    """فاصله‌های پیاپی یکی می‌شوند: عنوان یک خط است."""
    return " ".join(title.split())


def validate_thread(title: str, body: str) -> str | None:
    """پیام خطای فارسی، یا `None` اگر پرسش پذیرفتنی است. ورودی‌ها پاک‌شده‌اند."""
    if not TITLE_MIN <= len(title) <= TITLE_MAX:
        return f"عنوان پرسش باید بین {TITLE_MIN} تا {TITLE_MAX} نویسه باشد."
    if not THREAD_BODY_MIN <= len(body) <= BODY_MAX:
        return f"شرح پرسش باید بین {THREAD_BODY_MIN} تا {BODY_MAX} نویسه باشد."
    return None


def validate_reply(body: str) -> str | None:
    if not REPLY_MIN <= len(body) <= BODY_MAX:
        return f"پاسخ باید بین {REPLY_MIN} تا {BODY_MAX} نویسه باشد."
    return None


def helpful_earned(*, endorsed: bool, student_votes: int) -> bool:
    """شرط `QA_ANSWER_HELPFUL` — «≥۳ رأی مفید **یا** تأیید استاد»."""
    return endorsed or student_votes >= HELPFUL_VOTES_REQUIRED


def rules_earned(*, endorsed: bool, student_votes: int) -> tuple[str, ...]:
    """قاعده‌هایی که پاسخِ یک دانشجو الان باید داشته باشد.

    ***افزایشی است:*** پاسخ تأییدشده هر دو را می‌گیرد، چون شرط ردیف اول صریحاً
    «یا تأیید استاد» را دارد (ADR-0024 بند ۱۶).
    """
    earned: list[str] = []
    if helpful_earned(endorsed=endorsed, student_votes=student_votes):
        earned.append(HELPFUL_RULE)
    if endorsed:
        earned.append(OFFICIAL_RULE)
    return tuple(earned)


__all__ = [
    "HELPFUL_RULE",
    "HELPFUL_VOTES_REQUIRED",
    "OFFICIAL_RULE",
    "POINT_SOURCE_TYPE",
    "RULES",
    "THREAD_FILTERS",
    "clean_title",
    "helpful_earned",
    "rules_earned",
    "validate_reply",
    "validate_thread",
]
