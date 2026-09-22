"""شاخص سلامت پروژه — PRD §7.4، FR-PRJ-07، M5-12. منطق خالص.

```
days_inactive ≥ 14                                  ⇒ STALLED
مرحلهٔ از مهلت گذشتهٔ تأییدنشده یا days_inactive ≥ 7 ⇒ AT_RISK
≤ ۷ روز تا پایان پروژه و پیشرفت < ۷۰٪               ⇒ AT_RISK
در غیر این صورت                                     ⇒ HEALTHY
```

فقط پروژه‌های `IN_PROGRESS` ارزیابی می‌شوند (سرویس انتخاب می‌کند):
پروژهٔ `PAUSED` شاخصش فریز است (§7.4 «فریز شاخص سلامت») و پروژهٔ `OPEN`
هنوز تیم ندارد که «فعالیت» داشته باشد — ۱۴ روز انتظار برای درخواست‌دهنده،
«متوقف» نیست.

`today` آرگومان است، نه ساعت سیستم: همان قاعدهٔ ماژول‌های دامنه‌ای
دیگر، تا تست بدون جابه‌جایی ساعت ممکن باشد.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

STALLED_AFTER_DAYS = 14
AT_RISK_AFTER_DAYS = 7
DEADLINE_WINDOW_DAYS = 7
DEADLINE_PROGRESS_FLOOR = Decimal("0.7")

HEALTH_TITLE_FA: dict[str, str] = {
    "HEALTHY": "سالم",
    "AT_RISK": "در خطر",
    "STALLED": "متوقف",
}


@dataclass(frozen=True, slots=True)
class MilestoneState:
    due_on: date | None
    status: str
    is_required: bool = True


@dataclass(frozen=True, slots=True)
class HealthVerdict:
    health: str
    reason: str | None
    days_inactive: int


def progress_ratio(milestones: Sequence[MilestoneState]) -> Decimal:
    required = [m for m in milestones if m.is_required]
    if not required:
        return Decimal(1)
    approved = sum(1 for m in required if m.status == "APPROVED")
    return Decimal(approved) / Decimal(len(required))


def compute_health(
    *,
    today: date,
    last_activity_on: date,
    milestones: Sequence[MilestoneState],
    deadline_on: date | None,
) -> HealthVerdict:
    days_inactive = max((today - last_activity_on).days, 0)

    if days_inactive >= STALLED_AFTER_DAYS:
        return HealthVerdict("STALLED", f"{days_inactive} روز بدون فعالیت", days_inactive)

    overdue = sum(
        1
        for m in milestones
        if m.due_on is not None and m.due_on < today and m.status != "APPROVED"
    )
    if overdue:
        return HealthVerdict("AT_RISK", f"{overdue} مرحلهٔ عقب‌افتاده", days_inactive)
    if days_inactive >= AT_RISK_AFTER_DAYS:
        return HealthVerdict("AT_RISK", f"{days_inactive} روز بدون فعالیت", days_inactive)
    if (
        deadline_on is not None
        and (deadline_on - today).days <= DEADLINE_WINDOW_DAYS
        and progress_ratio(milestones) < DEADLINE_PROGRESS_FLOOR
    ):
        return HealthVerdict("AT_RISK", "مهلت پروژه نزدیک است و پیشرفت کم", days_inactive)
    return HealthVerdict("HEALTHY", None, days_inactive)


__all__ = [
    "HEALTH_TITLE_FA",
    "HealthVerdict",
    "MilestoneState",
    "compute_health",
    "progress_ratio",
]
