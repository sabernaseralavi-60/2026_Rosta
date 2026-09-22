"""فرمول‌های امتیاز — PRD §9.2 و §9.3. منطق خالص، بدون I/O.

هر تابع اینجا یک **ضریب** برمی‌گرداند، نه امتیاز نهایی:
`amount = rule.base_points × multiplier`. ضریب در دفتر کل عکس گرفته
می‌شود (`point_entries.multiplier`، ADR-0012) تا بازمحاسبه با قاعدهٔ
جدید (§9.9) ممکن باشد — «۲۴ امتیاز» نمی‌گوید «۳۰ × ۰٫۸» بوده است.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, date, datetime, time, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

#: وقت محلی ایران. ایران از ۱۴۰۱ ساعت تابستانی ندارد، پس اختلاف ثابت
#: است و به پایگاه‌دادهٔ منطقهٔ زمانی (`tzdata`، که روی ویندوز جدا نصب
#: می‌شود) نیازی نیست. «روز» سقف روزانه و «ساعت» نشان شب‌زنده‌دار از این
#: می‌خوانند — نیمه‌شب UTC ساعت ۳:۳۰ بامداد تهران است.
LOCAL_TZ = timezone(timedelta(hours=3, minutes=30), name="Asia/Tehran")

MULTIPLIER_QUANTUM = Decimal("0.0001")
AMOUNT_QUANTUM = Decimal("0.01")
#: سقف ستون `NUMERIC(6,2)`.
MAX_AMOUNT = Decimal("9999.99")

# ── نگاشت نوع پروژه به دسته — §9.2 ─────────────────────────────────────
PROJECT_KIND_CATEGORY: dict[str, str] = {
    "A_VENTURE": "STARTUP",
    "B_RESEARCH": "RESEARCH",
    "C_PROBLEM": "LEARNING",
    "D_PERSONAL": "LEARNING",
}

# ── ضرایب تعدیل — §9.3 ─────────────────────────────────────────────────
LATE_FACTOR = Decimal("0.70")
EARLY_FACTOR = Decimal("1.05")
EARLY_DAYS = 3
CHANGES_REQUESTED_FACTOR = Decimal("0.85")
HIGH_QUALITY_FACTOR = Decimal("1.20")
HIGH_QUALITY_RUBRIC = Decimal("4.5")
RUBRIC_MAX = Decimal(5)

#: §9.8 — پروژهٔ شخصی خودتأییدی، نصف امتیاز تکمیل.
PERSONAL_PROJECT_FACTOR = Decimal("0.5")

#: §9.2 — «قبولی» وقتی آزمون `passing_score` ندارد (ADR-0012).
DEFAULT_PASS_RATIO = Decimal("0.5")

#: §9.2 `ATTENDANCE_STREAK` — «۴ جلسهٔ متوالی بدون غیبت».
ATTENDANCE_STREAK_LENGTH = 4
#: وضعیت‌هایی که زنجیرهٔ حضور را ادامه می‌دهند. تأخیر غیبت نیست؛
#: `EXCUSED` هم غیبت است، فقط موجه — «حضور کامل» با آن کامل نمی‌شود.
STREAK_STATUSES = frozenset({"PRESENT", "LATE"})


def quantize_multiplier(value: Decimal) -> Decimal:
    return value.quantize(MULTIPLIER_QUANTUM, rounding=ROUND_HALF_UP)


def amount_of(base_points: Decimal, multiplier: Decimal) -> Decimal:
    """امتیاز یک ردیف: پایه × ضریب، گرد و محدود به ستون."""
    raw = (base_points * multiplier).quantize(AMOUNT_QUANTUM, rounding=ROUND_HALF_UP)
    return min(raw, MAX_AMOUNT)


def category_for_project(kind: str) -> str:
    return PROJECT_KIND_CATEGORY.get(kind, "LEARNING")


def difficulty_factor(difficulty: int) -> Decimal:
    """`0.7 + 0.15 × difficulty` — سطح ۱: ۰٫۸۵ تا سطح ۵: ۱٫۴۵."""
    level = min(max(difficulty, 1), 5)
    return Decimal("0.7") + Decimal("0.15") * level


def project_completion_multiplier(*, kind: str, difficulty: int) -> Decimal:
    factor = difficulty_factor(difficulty)
    if kind == "D_PERSONAL":
        factor *= PERSONAL_PROJECT_FACTOR
    return quantize_multiplier(factor)


def rubric_average(rubric_scores: Mapping[str, Any] | None) -> Decimal | None:
    """میانگین معیارهای عددی روبریک، از ۵. مقدار غیرعددی نادیده گرفته می‌شود."""
    if not rubric_scores:
        return None
    values: list[Decimal] = []
    for value in rubric_scores.values():
        if isinstance(value, bool) or not isinstance(value, int | float | Decimal | str):
            continue
        try:
            number = Decimal(str(value))
        except ArithmeticError:
            continue
        if Decimal(0) <= number <= RUBRIC_MAX:
            values.append(number)
    if not values:
        return None
    return sum(values, Decimal(0)) / len(values)


def adjustment_factors(
    *,
    is_late: bool,
    submitted_on: date,
    due_on: date | None,
    had_changes_requested: bool,
    rubric_scores: Mapping[str, Any] | None,
) -> list[tuple[str, Decimal]]:
    """ضرایب §9.3 که بر این تحویل اعمال می‌شوند، با برچسب فارسی.

    «دیر» از `deliverables.is_late` می‌آید، نه از مقایسهٔ دوبارهٔ تاریخ‌ها:
    آن ستون عکس لحظهٔ ارسال است و جابه‌جا کردن مهلت پس از تحویل نباید
    گذشته را بازنویسی کند (ADR-0006). دیر و زود با هم جمع نمی‌شوند.
    """
    factors: list[tuple[str, Decimal]] = []
    if is_late:
        factors.append(("تحویل با تأخیر", LATE_FACTOR))
    elif due_on is not None and (due_on - submitted_on).days >= EARLY_DAYS:
        factors.append(("تحویل زودهنگام", EARLY_FACTOR))
    if had_changes_requested:
        factors.append(("نیاز به اصلاح", CHANGES_REQUESTED_FACTOR))
    average = rubric_average(rubric_scores)
    if average is not None and average >= HIGH_QUALITY_RUBRIC:
        factors.append(("کیفیت بالا", HIGH_QUALITY_FACTOR))
    return factors


def milestone_multiplier(points: Decimal, factors: Iterable[tuple[str, Decimal]]) -> Decimal:
    """`milestone.points × Π ضرایب` — قاعدهٔ `MILESTONE_APPROVED` پایهٔ ۱ دارد."""
    result = Decimal(points)
    for _, factor in factors:
        result *= factor
    return quantize_multiplier(result)


def factors_note(factors: Sequence[tuple[str, Decimal]]) -> str | None:
    """شرح ضرایب برای ستون `note` — دانشجو باید بداند چرا ۷۰ شد، نه ۱۰۰."""
    if not factors:
        return None
    return "، ".join(f"{label} ×{factor.normalize()}" for label, factor in factors)


# ── آزمون — §9.2 و §7.12 ───────────────────────────────────────────────
def score_ratio(score: Decimal, total: Decimal) -> Decimal:
    if total <= 0:
        return Decimal(0)
    ratio = min(max(score / total, Decimal(0)), Decimal(1))
    return quantize_multiplier(ratio)


def passed(score: Decimal, total: Decimal, passing_score: Decimal | None) -> bool:
    if total <= 0:
        return False
    if passing_score is not None:
        return score >= passing_score
    return score >= total * DEFAULT_PASS_RATIO


# ── حضور — §9.2 ────────────────────────────────────────────────────────
def streak_completions(statuses: Sequence[str | None]) -> list[int]:
    """اندیس جلساتی که یک زنجیرهٔ کامل ۴تایی را می‌بندند.

    `statuses` به ترتیب تاریخ جلسه است و `None` یعنی برای این دانشجو
    ثبتی نشده — که غیبت حساب می‌شود. هر جلسه فقط در یک زنجیره شمرده
    می‌شود: هشت حضور پیاپی دو پاداش است، نه پنج.
    """
    completions: list[int] = []
    run = 0
    for index, status in enumerate(statuses):
        if status in STREAK_STATUSES:
            run += 1
            if run == ATTENDANCE_STREAK_LENGTH:
                completions.append(index)
                run = 0
        else:
            run = 0
    return completions


# ── زمان محلی و پنجره‌های سقف ──────────────────────────────────────────
def local_day_start(now: datetime) -> datetime:
    local = now.astimezone(LOCAL_TZ)
    return datetime.combine(local.date(), time.min, tzinfo=LOCAL_TZ).astimezone(UTC)


def local_week_start(now: datetime) -> datetime:
    """آغاز هفتهٔ محلی — شنبه، مثل تقویم ایران."""
    local = now.astimezone(LOCAL_TZ)
    # weekday(): دوشنبه=۰ … شنبه=۵ ⇒ فاصله تا شنبهٔ گذشته.
    days_since_saturday = (local.weekday() - 5) % 7
    saturday = local.date() - timedelta(days=days_since_saturday)
    return datetime.combine(saturday, time.min, tzinfo=LOCAL_TZ).astimezone(UTC)


def week_key(moment: datetime) -> date:
    """شنبهٔ محلی هفته‌ای که `moment` در آن است — کلید زنجیرهٔ هفتگی."""
    return local_week_start(moment).astimezone(LOCAL_TZ).date()


def is_night(moment: datetime) -> bool:
    """۲۳ تا ۴ بامداد به وقت تهران — نشان `NIGHT_OWL`."""
    hour = moment.astimezone(LOCAL_TZ).hour
    return hour >= 23 or hour < 4


__all__ = [
    "ATTENDANCE_STREAK_LENGTH",
    "LOCAL_TZ",
    "PROJECT_KIND_CATEGORY",
    "adjustment_factors",
    "amount_of",
    "category_for_project",
    "difficulty_factor",
    "factors_note",
    "is_night",
    "local_day_start",
    "local_week_start",
    "milestone_multiplier",
    "passed",
    "project_completion_multiplier",
    "quantize_multiplier",
    "rubric_average",
    "score_ratio",
    "streak_completions",
    "week_key",
]
