"""منطق خالص حلقهٔ یادگیری — ADR-0036 §۵–۶. بدون دیتابیس و بدون ساعت.

* **استمرار (Streak)**: روز = روز تقویمی تهران. یک «معافیت» در هر هفته (هفته از شنبه):
  اگر دقیقاً یک روز جا بیفتد و در آن هفته معافیت مصرف نشده باشد، رشته نمی‌شکند.
* **شایستگی (Mastery)**: میانگین متحرک با پیش‌فرض ۰٫۵. با شاهد کم برچسب «کم‌داده»
  می‌خورد تا نقشهٔ مهارت با پنج سؤال ادعای دقیق نکند.
* **استخر**: انتخاب n سؤال با برابرتوزیعی میان مفاهیم، قطعی برای یک دانه (شناسهٔ تلاش).
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Literal

from silp.domain.quiz.shuffle import shuffled_ids

# ایران از شهریور ۱۴۰۱ ساعت تابستانی ندارد؛ آفست ثابت +۰۳:۳۰ است. (پایگاه‌دادهٔ منطقهٔ زمانی
# روی ویندوز نصب نیست و این منطق نباید به آن وابسته شود.)
TEHRAN = timezone(timedelta(hours=3, minutes=30), "Asia/Tehran")

STREAK_MILESTONES: tuple[int, ...] = (7, 30)

#: کمینهٔ شاهد برای اینکه سطح مهارت اعلام شود.
MIN_EVIDENCE = 5
PRIOR_SCORE = 0.5
MIN_ALPHA = 0.15

MasteryLevel = Literal["STRONG", "MEDIUM", "WEAK", "LOW_DATA"]


def tehran_day(moment: datetime) -> date:
    """روز تقویمی تهران برای یک لحظه (بدون وابستگی به منطقهٔ سرور)."""
    aware = moment if moment.tzinfo else moment.replace(tzinfo=UTC)
    return aware.astimezone(TEHRAN).date()


def week_start(day: date) -> date:
    """شنبهٔ همان هفته (هفتهٔ ایرانی از شنبه شروع می‌شود)."""
    return day - timedelta(days=(day.weekday() + 2) % 7)


# ── استمرار ────────────────────────────────────────────────────────────
@dataclass(frozen=True, slots=True)
class StreakState:
    current: int = 0
    longest: int = 0
    started_on: date | None = None
    last_day: date | None = None
    freeze_week: date | None = None


@dataclass(frozen=True, slots=True)
class StreakStep:
    state: StreakState
    #: نقطهٔ عطفی که با همین گام رسیده شد (۷ یا ۳۰)، وگرنه None.
    milestone: int | None
    #: آیا برای پر کردن روز جاافتاده از معافیت استفاده شد.
    froze: bool


def advance_streak(state: StreakState, day: date) -> StreakStep:
    """ثبت یک چالش کامل‌شده در `day`. تکرار همان روز بی‌اثر است."""
    last = state.last_day
    if last is not None and day <= last:
        return StreakStep(state, None, False)

    froze = False
    freeze_week = state.freeze_week
    if last is None:
        current, started = 1, day
    else:
        gap = (day - last).days
        if gap == 1:
            current, started = state.current + 1, state.started_on or day
        elif gap == 2 and freeze_week != week_start(last + timedelta(days=1)):
            # دقیقاً یک روز جا افتاده و معافیت آن هفته مصرف نشده است.
            froze = True
            freeze_week = week_start(last + timedelta(days=1))
            current, started = state.current + 1, state.started_on or day
        else:
            current, started = 1, day

    longest = max(state.longest, current)
    milestone = current if current in STREAK_MILESTONES else None
    return StreakStep(
        replace(
            state,
            current=current,
            longest=longest,
            started_on=started,
            last_day=day,
            freeze_week=freeze_week,
        ),
        milestone,
        froze,
    )


def streak_is_alive(state: StreakState, today: date) -> bool:
    """آیا رشتهٔ فعلی هنوز می‌تواند امروز یا فردا ادامه یابد (برای نمایش به دانشجو)؟"""
    if state.last_day is None or state.current == 0:
        return False
    return (today - state.last_day).days <= 1


# ── شایستگی ────────────────────────────────────────────────────────────
def update_mastery(
    score: float | Decimal, evidence_n: int, correct: Sequence[bool]
) -> tuple[float, int]:
    """به‌روزرسانی پاسخ‌به‌پاسخ؛ خروجی `(امتیاز تازه، شاهد تازه)`.

    گام یادگیری `max(0.15, 1/(n+3))`: پاسخ‌های اول وزن بیشتری دارند ولی پیش‌فرض ۰٫۵ اجازه
    نمی‌دهد یک پاسخ تنها دانشجو را «کاملاً قوی» یا «کاملاً ضعیف» کند.
    """
    value = float(score)
    n = evidence_n
    for outcome in correct:
        alpha = max(MIN_ALPHA, 1.0 / (n + 3))
        value += alpha * ((1.0 if outcome else 0.0) - value)
        n += 1
    return round(min(1.0, max(0.0, value)), 4), n


def mastery_level(score: float | Decimal, evidence_n: int) -> MasteryLevel:
    if evidence_n < MIN_EVIDENCE:
        return "LOW_DATA"
    value = float(score)
    if value >= 0.75:
        return "STRONG"
    if value >= 0.5:
        return "MEDIUM"
    return "WEAK"


# ── استخر ──────────────────────────────────────────────────────────────
def draw_questions(
    items: Sequence[tuple[uuid.UUID, uuid.UUID | None]],
    count: int,
    *,
    seed: uuid.UUID | str,
) -> list[uuid.UUID]:
    """n سؤال از استخر، برابر میان مفاهیم (سؤال بی‌مفهوم یک گروه جداست).

    قطعی برای یک `seed`؛ دو دانشجو (دو دانه) مجموعه‌های متفاوت می‌گیرند. اگر استخر کوچک‌تر
    از `count` باشد همهٔ آن برمی‌گردد.
    """
    if count >= len(items):
        return [item_id for item_id, _ in items]
    groups: dict[str, list[str]] = defaultdict(list)
    for item_id, concept in items:
        groups[str(concept)].append(str(item_id))
    # ترتیب گروه‌ها و درون هر گروه هر دو با دانه درهم می‌شود.
    order = shuffled_ids(list(groups), seed=seed, scope="concepts")
    queues = {
        key: shuffled_ids(members, seed=seed, scope=f"in:{key}") for key, members in groups.items()
    }
    picked: list[str] = []
    while len(picked) < count:
        progressed = False
        for key in order:
            if queues[key] and len(picked) < count:
                picked.append(queues[key].pop(0))
                progressed = True
        if not progressed:
            break
    return [uuid.UUID(value) for value in picked]
