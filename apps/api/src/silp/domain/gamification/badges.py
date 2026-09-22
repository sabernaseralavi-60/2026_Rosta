"""ارزیاب معیار نشان — PRD §9.5، FR-GAM-03. منطق خالص، بدون I/O.

معیار یک ساختار JSON است (`badges.criteria`) و «واقعیت‌ها» یک عکس از
وضعیت کاربر که سرویس از دیتابیس می‌سازد. این جدایی دو فایده دارد:

۱. هر معیار بدون دیتابیس تست می‌شود.
۲. همان ارزیاب **پیشرفت** را هم برمی‌گرداند، نه فقط «گرفت یا نه» —
   §9.5: «کاربر نشان‌های قفل‌شده را با شرایطشان می‌بیند؛ این خودش یک
   راهنمای مسیر است.» «۳ از ۵» راهنماست، «قفل» نیست.

## انواع معیار

| نوع | کلیدها | معنی |
|-----|--------|------|
| `POINT_THRESHOLD` | `amount`، `category`؟ | مجموع امتیاز (کل یا یک دسته) ≥ مقدار |
| `COUNT` | `entity`، `n`، `kind`؟ / `quartile`؟ | تعداد رخداد ≥ n |
| `STREAK` | `entity`، `n` | بلندترین زنجیرهٔ پیاپی ≥ n |
| `FIRST` | `entity`، `min_value` | دست‌کم یک رخداد با مقدار ≥ min_value |
| `SUM` | `entity`، `min_value` | مجموع مقدارها ≥ min_value |
| `WITHIN_DAYS` | `entity`، `days` | اولین رخداد تا `days` روز پس از ثبت‌نام |
| `COMPOSITE` | `all_of` | همهٔ زیرمعیارها |

واقعیتی که سرویس نمی‌شناسد صفر است، نه خطا: نشان «شهرساز» پیش از ساخت
ماژول شهر هوشمند (M7) قفل می‌ماند، ولی ارزیابی کل نشان‌ها نمی‌شکند.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

CRITERION_TYPES = frozenset(
    {"POINT_THRESHOLD", "COUNT", "STREAK", "FIRST", "SUM", "WITHIN_DAYS", "COMPOSITE"}
)
QUALIFIER_KEYS = ("kind", "quartile")


class InvalidCriteria(ValueError):
    """معیار نشان ساختار درستی ندارد."""


@dataclass(frozen=True, slots=True)
class BadgeFacts:
    """عکس وضعیت یک کاربر — ورودی ارزیاب.

    کلید `counts` نام موجودیت است، یا برای شمارش مقیّد
    `"<موجودیت>:<مقید>"` — مثلاً `PROJECT_COMPLETED:B_RESEARCH`.
    """

    points_by_category: Mapping[str, Decimal] = field(default_factory=dict)
    counts: Mapping[str, int] = field(default_factory=dict)
    streaks: Mapping[str, int] = field(default_factory=dict)
    sums: Mapping[str, Decimal] = field(default_factory=dict)
    maxima: Mapping[str, Decimal] = field(default_factory=dict)
    days_to_first: Mapping[str, int] = field(default_factory=dict)

    @property
    def total_points(self) -> Decimal:
        return sum(self.points_by_category.values(), Decimal(0))


@dataclass(frozen=True, slots=True)
class Progress:
    met: bool
    current: Decimal
    target: Decimal

    @property
    def ratio(self) -> Decimal:
        if self.target <= 0:
            return Decimal(1) if self.met else Decimal(0)
        return min(self.current / self.target, Decimal(1))


def count_key(entity: str, qualifier: str | None = None) -> str:
    return f"{entity}:{qualifier}" if qualifier else entity


def evaluate(criteria: Mapping[str, Any], facts: BadgeFacts) -> Progress:
    """آیا معیار برقرار است، و تا کجا؟"""
    validate(criteria)
    return _evaluate(criteria, facts)


def _evaluate(criteria: Mapping[str, Any], facts: BadgeFacts) -> Progress:
    kind = criteria["type"]
    match kind:
        case "POINT_THRESHOLD":
            target = Decimal(str(criteria["amount"]))
            category = criteria.get("category")
            current = (
                facts.points_by_category.get(category, Decimal(0))
                if category
                else facts.total_points
            )
            return _at_least(current, target)
        case "COUNT":
            qualifier = next((criteria[k] for k in QUALIFIER_KEYS if criteria.get(k)), None)
            current = Decimal(facts.counts.get(count_key(criteria["entity"], qualifier), 0))
            return _at_least(current, Decimal(criteria["n"]))
        case "STREAK":
            current = Decimal(facts.streaks.get(criteria["entity"], 0))
            return _at_least(current, Decimal(criteria["n"]))
        case "FIRST":
            best = facts.maxima.get(criteria["entity"])
            met = best is not None and best >= Decimal(str(criteria["min_value"]))
            return Progress(met=met, current=Decimal(int(met)), target=Decimal(1))
        case "SUM":
            current = facts.sums.get(criteria["entity"], Decimal(0))
            return _at_least(current, Decimal(str(criteria["min_value"])))
        case "WITHIN_DAYS":
            days = facts.days_to_first.get(criteria["entity"])
            met = days is not None and days <= int(criteria["days"])
            return Progress(met=met, current=Decimal(int(met)), target=Decimal(1))
        case "COMPOSITE":
            parts = [_evaluate(child, facts) for child in criteria["all_of"]]
            done = sum(1 for p in parts if p.met)
            return Progress(
                met=done == len(parts), current=Decimal(done), target=Decimal(len(parts))
            )
    raise InvalidCriteria(f"نوع معیار ناشناخته: {kind}")  # pragma: no cover — validate


def _at_least(current: Decimal, target: Decimal) -> Progress:
    return Progress(met=current >= target, current=min(current, target), target=target)


def validate(criteria: Any) -> None:
    """ساختار معیار را بررسی می‌کند — هم برای ارزیابی، هم برای ویرایش مدیر."""
    if not isinstance(criteria, Mapping):
        raise InvalidCriteria("معیار باید یک شیء باشد.")
    kind = criteria.get("type")
    if kind not in CRITERION_TYPES:
        raise InvalidCriteria(f"نوع معیار ناشناخته: {kind}")

    def need(key: str, *types: type) -> Any:
        value = criteria.get(key)
        if value is None or isinstance(value, bool) or not isinstance(value, types):
            raise InvalidCriteria(f"معیار {kind} به «{key}» نیاز دارد.")
        return value

    if kind == "COMPOSITE":
        children = criteria.get("all_of")
        if not isinstance(children, list) or not children:
            raise InvalidCriteria("معیار ترکیبی به فهرست ناخالی «all_of» نیاز دارد.")
        for child in children:
            validate(child)
        return
    if kind == "POINT_THRESHOLD":
        if need("amount", int, float, str) and Decimal(str(criteria["amount"])) <= 0:
            raise InvalidCriteria("آستانهٔ امتیاز باید مثبت باشد.")
        return
    need("entity", str)
    if kind in ("COUNT", "STREAK") and need("n", int) < 1:
        raise InvalidCriteria("«n» باید دست‌کم ۱ باشد.")
    if kind in ("FIRST", "SUM"):
        need("min_value", int, float, str)
    if kind == "WITHIN_DAYS" and need("days", int) < 0:
        raise InvalidCriteria("«days» نمی‌تواند منفی باشد.")


def longest_weekly_streak(weeks: Iterable[date]) -> int:
    """بلندترین زنجیرهٔ هفته‌های پیاپی. ورودی کلید هفته (شنبهٔ محلی) است."""
    ordered = sorted(set(weeks))
    best = 0
    run = 0
    previous: date | None = None
    for week in ordered:
        run = run + 1 if previous is not None and week - previous == timedelta(days=7) else 1
        best = max(best, run)
        previous = week
    return best


__all__ = [
    "CRITERION_TYPES",
    "BadgeFacts",
    "InvalidCriteria",
    "Progress",
    "count_key",
    "evaluate",
    "longest_weekly_streak",
    "validate",
]
