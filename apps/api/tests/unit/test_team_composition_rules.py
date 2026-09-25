"""پیشنهاد ترکیب تیم — منطق خالص FR-TEAM-04 (ADR-0027). بدون دیتابیس."""

from __future__ import annotations

import uuid

from silp.domain.team_composition import MAX_SEATS, suggest_compositions
from silp.domain.teams import Candidate, Need

GIS, SUMO, PY = (uuid.UUID(int=n) for n in (101, 102, 103))
NEEDS = [
    Need(skill_id=GIS, title_fa="GIS", min_level=3, weight=3),
    Need(skill_id=SUMO, title_fa="SUMO", min_level=3, weight=2),
    Need(skill_id=PY, title_fa="پایتون", min_level=3, weight=1),
]


def person(n: int, **skills: int) -> Candidate:
    ids = {"gis": GIS, "sumo": SUMO, "py": PY}
    return Candidate(user_id=uuid.UUID(int=n), skills={ids[k]: v for k, v in skills.items()})


def members(composition) -> list[int]:  # type: ignore[no-untyped-def]
    return [p.user_id.int for p in composition.picks]


def test_second_pick_covers_what_the_first_left_open() -> None:
    """هدف اصلی: دو نفر GIS-بلد پشت هم نمی‌آیند وقتی SUMO خالی است."""
    pool = [person(1, gis=4), person(2, gis=5), person(3, sumo=4)]
    best = suggest_compositions(pool, NEEDS, seats=2)[0]
    assert sorted(members(best)) == [1, 3] or sorted(members(best)) == [2, 3]
    assert {c.title_fa for p in best.picks for c in p.covers} == {"GIS", "SUMO"}


def test_coverage_is_weighted_and_reports_uncovered() -> None:
    pool = [person(1, gis=4), person(3, sumo=4)]
    best = suggest_compositions(pool, NEEDS, seats=2)[0]
    assert best.coverage_percent == 83.3  # (3+2)/6
    assert [n.title_fa for n in best.uncovered] == ["پایتون"]


def test_heavier_gap_is_taken_first() -> None:
    pool = [person(1, sumo=4), person(2, gis=4)]
    best = suggest_compositions(pool, NEEDS, seats=1)[0]
    assert members(best) == [2]
    assert best.coverage_percent == 50.0


def test_never_adds_a_member_who_covers_nothing_new() -> None:
    pool = [person(1, gis=4, sumo=4, py=4), person(2, gis=5), person(3)]
    (only,) = suggest_compositions(pool, NEEDS, seats=5, alternatives=1)
    assert members(only) == [1]
    assert only.coverage_percent == 100.0
    assert only.uncovered == ()


def test_alternatives_differ_and_are_ordered_by_coverage() -> None:
    pool = [person(1, gis=4), person(2, gis=4, sumo=3), person(3, sumo=4)]
    result = suggest_compositions(pool, NEEDS, seats=2)
    sets = [frozenset(members(c)) for c in result]
    assert len(set(sets)) == len(sets)
    coverage = [c.coverage_percent for c in result]
    assert coverage == sorted(coverage, reverse=True)
    assert result[0].coverage_percent == 83.3


def test_below_the_required_level_does_not_count_as_coverage() -> None:
    assert suggest_compositions([person(1, gis=2)], NEEDS, seats=3) == []


def test_no_gaps_or_no_candidates_gives_nothing() -> None:
    assert suggest_compositions([person(1, gis=5)], [], seats=3) == []
    assert suggest_compositions([], NEEDS, seats=3) == []


def test_zero_total_weight_is_treated_as_no_gaps() -> None:
    zero = [Need(skill_id=GIS, title_fa="GIS", min_level=3, weight=0)]
    assert suggest_compositions([person(1, gis=5)], zero, seats=2) == []


def test_seats_are_clamped_and_result_is_deterministic() -> None:
    pool = [person(n, gis=4) for n in range(1, 9)]
    first = suggest_compositions(pool, NEEDS, seats=99)
    second = suggest_compositions(list(reversed(pool)), NEEDS, seats=99)
    assert all(len(c.picks) <= MAX_SEATS for c in first)
    assert [members(c) for c in first] == [members(c) for c in second]


def test_reason_names_only_newly_covered_skills() -> None:
    pool = [person(1, gis=4, sumo=4), person(2, gis=5, py=4)]
    best = suggest_compositions(pool, NEEDS, seats=2, alternatives=1)[0]
    second = best.picks[1]
    assert [c.title_fa for c in second.covers] == ["پایتون"]
    assert "GIS" not in second.reason
