"""پیشنهاد خودکار ترکیب تیم — FR-TEAM-04، §8.14، ADR-0027. منطق خالص.

پوشش وزنی حریصانه: در هر گام نامزدی برگزیده می‌شود که وزنِ **کمبودهای هنوز
پوشانده‌نشده** را که به حد لازم می‌رساند بیشینه کند. «پوشش» دوتایی است (سطح
کافی دارد یا نه)؛ `complement()` فقط تساوی را می‌شکند.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from silp.domain import teams
from silp.domain.teams import Candidate, CoveredSkill, Need
from silp.domain.text import join_fa, to_persian_digits

MAX_SEATS = 5
ALTERNATIVES = 3
MAX_SCORE = 100.0
MAX_REASON_SKILLS = 3


@dataclass(frozen=True, slots=True)
class Pick:
    """یک عضو پیشنهادی و مهارت‌هایی که **تازه** به تیم می‌آورد."""

    user_id: uuid.UUID
    covers: tuple[CoveredSkill, ...]
    reason: str


@dataclass(frozen=True, slots=True)
class Composition:
    picks: tuple[Pick, ...]
    #: درصد وزنیِ کمبودهایی که این ترکیب می‌پوشاند (۰ تا ۱۰۰).
    coverage_percent: float
    uncovered: tuple[Need, ...]
    #: مجموع مکملیت اعضا نسبت به کمبودهایی که هنگام انتخاب باقی بود — فقط برای ترتیب.
    tie_score: float = 0.0


def _covers(candidate: Candidate, need: Need) -> bool:
    return candidate.skills.get(need.skill_id, 0) >= need.min_level


def _gain(candidate: Candidate, remaining: Sequence[Need]) -> int:
    return sum(max(n.weight, 0) for n in remaining if _covers(candidate, n))


def _key(
    candidate: Candidate, remaining: Sequence[Need], commitment_hpw: int | None
) -> tuple[int, float, str]:
    """کلید مرتب‌سازی (بزرگ‌تر بهتر): پوشش تازه، مکملیت، سپس شناسه برای قطعیت."""
    comp = teams.complement(candidate, remaining, commitment_hpw=commitment_hpw)
    return (_gain(candidate, remaining), comp.score if comp else 0.0, str(candidate.user_id))


def _ranked(
    pool: Sequence[Candidate], remaining: Sequence[Need], commitment_hpw: int | None
) -> list[Candidate]:
    """نامزدهایی که چیزی می‌پوشانند، از بهترین به بدترین (تساوی با شناسهٔ کوچک‌تر)."""
    keyed = [(_key(c, remaining, commitment_hpw), c) for c in pool if _gain(c, remaining) > 0]
    keyed.sort(key=lambda pair: (-pair[0][0], -pair[0][1], pair[0][2]))
    return [c for _, c in keyed]


def _pick_reason(covers: Sequence[CoveredSkill]) -> str:
    titles = [c.title_fa for c in covers[:MAX_REASON_SKILLS]]
    rest = len(covers) - len(titles)
    tail = f" و {to_persian_digits(str(rest))} مهارت دیگر" if rest else ""
    return f"{join_fa(titles)}{tail} را می‌آورد که تا اینجا در تیم نیست."


def _greedy(
    pool: Sequence[Candidate],
    gaps: Sequence[Need],
    seats: int,
    commitment_hpw: int | None,
    first: Candidate | None,
) -> Composition:
    remaining = list(gaps)
    chosen: list[Candidate] = []
    picks: list[Pick] = []
    tie = 0.0
    while len(chosen) < seats and remaining:
        if first is not None and not chosen:
            best: Candidate | None = first
        else:
            taken = {c.user_id for c in chosen}
            ranked = _ranked([c for c in pool if c.user_id not in taken], remaining, commitment_hpw)
            best = ranked[0] if ranked else None
        if best is None:
            break
        newly = [n for n in remaining if _covers(best, n)]
        if not newly:
            break
        comp = teams.complement(best, remaining, commitment_hpw=commitment_hpw)
        tie += comp.score if comp else 0.0
        covers = tuple(
            CoveredSkill(
                title_fa=n.title_fa,
                level=best.skills[n.skill_id],
                verified=n.skill_id in best.verified_skills,
            )
            for n in sorted(newly, key=lambda n: (-n.weight, n.title_fa))
        )
        picks.append(Pick(user_id=best.user_id, covers=covers, reason=_pick_reason(covers)))
        chosen.append(best)
        remaining = [n for n in remaining if not _covers(best, n)]

    total = sum(max(n.weight, 0) for n in gaps)
    left = sum(max(n.weight, 0) for n in remaining)
    coverage = round((total - left) / total * MAX_SCORE, 1) if total > 0 else 0.0
    return Composition(
        picks=tuple(picks),
        coverage_percent=coverage,
        uncovered=tuple(remaining),
        tie_score=round(tie, 1),
    )


def suggest_compositions(
    pool: Sequence[Candidate],
    gaps: Sequence[Need],
    *,
    seats: int,
    commitment_hpw: int | None = None,
    alternatives: int = ALTERNATIVES,
) -> list[Composition]:
    """ترکیب‌های پیشنهادی، بهترین اول. خالی اگر کمبودی نیست یا هیچ‌کس چیزی نمی‌پوشاند."""
    seats = max(1, min(seats, MAX_SEATS))
    if not gaps or sum(max(n.weight, 0) for n in gaps) <= 0:
        return []

    starters = _ranked(pool, gaps, commitment_hpw)[: max(1, alternatives)]
    seen: set[frozenset[uuid.UUID]] = set()
    result: list[Composition] = []
    for starter in starters:
        composition = _greedy(pool, gaps, seats, commitment_hpw, starter)
        members = frozenset(p.user_id for p in composition.picks)
        if not members or members in seen:
            continue
        seen.add(members)
        result.append(composition)
    result.sort(key=lambda c: (-c.coverage_percent, len(c.picks), -c.tie_score))
    return result


__all__ = ["ALTERNATIVES", "MAX_SEATS", "Composition", "Pick", "suggest_compositions"]
