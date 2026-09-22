"""«قدم بعدی تو» — PRD FR-DASH-01، M5-10. منطق خالص.

داشبورد **یک** اقدام را بزرگ نشان می‌دهد، نه فهرستی از ده کار. دانشجویی
که ده کار می‌بیند، هیچ‌کدام را شروع نمی‌کند. سرویس همهٔ نامزدها را جمع
می‌کند و این ماژول مهم‌ترین را برمی‌گزیند.

## ترتیب اولویت

| رتبه | نوع | چرا اینجا |
|------|-----|-----------|
| ۱ | آزمونی که کمتر از ۲۴ ساعت تا بسته شدنش مانده | فردا دیگر نمی‌شود |
| ۲ | مرحلهٔ پروژهٔ عقب‌افتاده | هر روز تأخیر هزینه دارد (ضریب ۰٫۷، §9.3) |
| ۳ | آزمون باز | هنوز وقت هست، ولی پنجره دارد |
| ۴ | مرحله‌ای که تا ۷ روز دیگر مهلت دارد | — |
| ۵ | نیمرخ ناقص | بدون آن پیشنهاد پروژه‌ای نیست |
| ۶ | منبع خوانده‌نشدهٔ هفتهٔ جاری | کار همیشگی، بی‌مهلت |
| ۷ | هنوز پروژه‌ای نداری | §11 «هر دانشجو حداقل یک پروژه» |
| ۸ | هنوز درسی نداری | — |

در هر رتبه، آنکه مهلتش زودتر است جلوتر است.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta

URGENT_QUIZ_WINDOW = timedelta(hours=24)

NEXT_STEP_KINDS = (
    "QUIZ_OPEN",
    "MILESTONE_OVERDUE",
    "MILESTONE_DUE",
    "PROFILE_INCOMPLETE",
    "STUDY",
    "FIND_PROJECT",
    "ENROLL",
)

_BASE_RANK: dict[str, int] = {
    "MILESTONE_OVERDUE": 2,
    "QUIZ_OPEN": 3,
    "MILESTONE_DUE": 4,
    "PROFILE_INCOMPLETE": 5,
    "STUDY": 6,
    "FIND_PROJECT": 7,
    "ENROLL": 8,
}


@dataclass(frozen=True, slots=True)
class NextStep:
    kind: str
    title: str
    description: str
    href: str
    due_at: datetime | None = None


def rank(step: NextStep, *, now: datetime) -> int:
    if (
        step.kind == "QUIZ_OPEN"
        and step.due_at is not None
        and step.due_at - now <= URGENT_QUIZ_WINDOW
    ):
        return 1
    return _BASE_RANK.get(step.kind, 99)


def choose(candidates: Iterable[NextStep], *, now: datetime) -> NextStep | None:
    ordered = sorted(
        candidates,
        key=lambda s: (rank(s, now=now), s.due_at is None, s.due_at or now),
    )
    return ordered[0] if ordered else None


__all__ = ["NEXT_STEP_KINDS", "URGENT_QUIZ_WINDOW", "NextStep", "choose", "rank"]
