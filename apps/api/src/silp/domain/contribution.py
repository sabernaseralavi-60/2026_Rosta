"""تحلیل مشارکت تیمی — FR-PRJ-08، ADR-0026. منطق خالص، بدون دیتابیس.

سهم هر عضو میانگینِ وزنیِ سهم‌های او در چهار «بُعد» است، نه جمعِ شمارها:
پیام‌های بی‌شمار فقط می‌توانند سهمِ عضو را در بُعد گفتگو ببرند و اثرشان از
وزن همان بُعد بیشتر نمی‌شود.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

DELIVERABLES = "DELIVERABLES"
VERIFIED_ACTIVITY = "VERIFIED_ACTIVITY"
TASKS = "TASKS"
DISCUSSION = "DISCUSSION"

#: ترتیب نمایش = ترتیب اهمیت. وزن‌ها ثابت دامنه‌اند، نه ستون (ADR-0026 بند ۱).
WEIGHTS: dict[str, float] = {
    DELIVERABLES: 0.40,
    VERIFIED_ACTIVITY: 0.25,
    TASKS: 0.20,
    DISCUSSION: 0.15,
}

DIMENSION_TITLE_FA: dict[str, str] = {
    DELIVERABLES: "تحویل‌دادنی تأییدشده",
    VERIFIED_ACTIVITY: "فعالیت و فروش تأییدشده",
    TASKS: "وظیفهٔ انجام‌شده",
    DISCUSSION: "پیام در گفتگوی تیم",
}

DIMENSIONS = tuple(WEIGHTS)


@dataclass(frozen=True, slots=True)
class MemberCounts:
    """شمارهای خام یک عضو: کد بُعد ← تعداد. بُعدِ غایب یعنی صفر."""

    user_id: uuid.UUID
    counts: Mapping[str, int]
    #: عضو هنوز در تیم است؛ `LEFT`/`REMOVED` در سهم می‌مانند ولی «ساکت» حساب نمی‌شوند.
    is_active: bool = True


@dataclass(frozen=True, slots=True)
class DimensionShare:
    dimension: str
    count: int
    share_percent: float | None


@dataclass(frozen=True, slots=True)
class MemberShare:
    user_id: uuid.UUID
    #: `None` وقتی هیچ بُعدی در کل تیم داده ندارد.
    share_percent: float | None
    signals: list[DimensionShare]
    #: عضو فعالی که در هیچ بُعد چیزی ندارد — واقعیتِ «ثبت نشده»، نه اتهام.
    is_silent: bool


@dataclass(frozen=True, slots=True)
class Analysis:
    #: وزن مؤثر هر بُعد پس از بهنجارسازی؛ بُعدِ کل‌تیم‌صفر نیست.
    effective_weights: dict[str, float]
    team_totals: dict[str, int]
    members: list[MemberShare]


def _percent(fraction: float) -> float:
    return round(fraction * 100, 1)


def analyse(members: Sequence[MemberCounts]) -> Analysis:
    """سهم هر عضو. مرتب: بیشترین سهم اول، بی‌سهم (`None`) آخر."""
    totals = {d: sum(max(m.counts.get(d, 0), 0) for m in members) for d in DIMENSIONS}
    live = [d for d in DIMENSIONS if totals[d] > 0]
    weight_sum = sum(WEIGHTS[d] for d in live)
    effective = {d: WEIGHTS[d] / weight_sum for d in live} if live else {}

    shares: list[MemberShare] = []
    for member in members:
        signals = [
            DimensionShare(
                dimension=d,
                count=max(member.counts.get(d, 0), 0),
                share_percent=(
                    _percent(max(member.counts.get(d, 0), 0) / totals[d]) if totals[d] else None
                ),
            )
            for d in DIMENSIONS
        ]
        overall = (
            _percent(sum(effective[d] * max(member.counts.get(d, 0), 0) / totals[d] for d in live))
            if live
            else None
        )
        silent = member.is_active and all(s.count == 0 for s in signals)
        shares.append(MemberShare(member.user_id, overall, signals, silent))

    shares.sort(key=lambda s: (s.share_percent is None, -(s.share_percent or 0.0)))
    return Analysis(effective_weights=effective, team_totals=totals, members=shares)


__all__ = [
    "DELIVERABLES",
    "DIMENSIONS",
    "DIMENSION_TITLE_FA",
    "DISCUSSION",
    "TASKS",
    "VERIFIED_ACTIVITY",
    "WEIGHTS",
    "Analysis",
    "DimensionShare",
    "MemberCounts",
    "MemberShare",
    "analyse",
]
