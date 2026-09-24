"""بانک پروژهٔ راه‌اندازی — §14.5 و §13.3، M7-16.

قواعد «راهنمای نوشتن ۱۹ پروژهٔ باقی‌مانده» و آزمون پوشش پنج پرسونا. بانک
داده است و داده بی‌صدا خراب می‌شود: پروژه‌ای که «موقتاً» خودرو را الزامی
کند، از پیشنهاد بیست دانشجو بیرون می‌رود و هیچ تستی نمی‌شکند — مگر این.
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime

import pytest

from silp.content.project_bank import PROJECTS, SOFTWARE_SKILLS, VEHICLE_ASSETS
from silp.domain.recommendation.scorer import score_project
from silp.models.delivery import OUTPUT_KINDS
from silp.scripts.check_coverage import (
    PERSONAS,
    REQUIRED_MATCHES,
    coverage,
    project_spec,
)

# §14.3 و §14.1–۱۴.۲ — کدهای مجاز
SKILLS = {
    "EXCEL", "PYTHON", "R", "GIS", "STATISTICS", "WRITING", "MARKETING_SKILL",
    "GRAPHIC_DESIGN", "AI_TOOLS", "ENGLISH", "SUMO", "AIMSUN", "AUTOCAD", "POWERBI",
    "WEB_DEV", "MODELING", "PRESENTATION",
}  # fmt: skip
ASSETS = {"LAPTOP", "POWERFUL_PC", "SERVER", "FAST_INTERNET", "CAR", "PICKUP",
          "MOTORCYCLE", "CAMERA", "WORKSPACE"}  # fmt: skip
INTERESTS = {"RESEARCH", "PROGRAMMING", "MARKETING", "SALES", "GRAPHIC", "CONTENT",
             "PROJECT_MGMT", "DATA_ANALYSIS", "TRANSPORT", "AGRICULTURE", "COMMERCE",
             "URBAN"}  # fmt: skip


def test_launch_bank_has_twenty_five_projects() -> None:
    """§13.3 — «سامانه‌ای با ۳ پروژه، شکست‌خورده است.»"""
    assert len(PROJECTS) >= 25
    assert len({p.slug for p in PROJECTS}) == len(PROJECTS)


def test_kind_distribution_matches_the_guide() -> None:
    kinds = Counter(p.kind for p in PROJECTS)
    assert kinds == {"A_VENTURE": 8, "B_RESEARCH": 6, "C_PROBLEM": 8, "D_PERSONAL": 3}


def test_entry_level_projects() -> None:
    assert sum(p.difficulty <= 2 for p in PROJECTS) >= 6


def test_projects_without_software_skills() -> None:
    assert sum(not ({s.code for s in p.skills} & SOFTWARE_SKILLS) for p in PROJECTS) >= 5


def test_projects_without_a_mandatory_vehicle() -> None:
    needs_vehicle = [
        p.slug for p in PROJECTS if any(a.mandatory and a.code in VEHICLE_ASSETS for a in p.assets)
    ]
    assert len(PROJECTS) - len(needs_vehicle) >= 20, needs_vehicle


def test_solo_and_low_commitment_projects() -> None:
    assert sum(p.team_size_min == 1 for p in PROJECTS) >= 6
    assert sum(p.time_commitment_hpw <= 5 for p in PROJECTS) >= 5


@pytest.mark.parametrize("seed", PROJECTS, ids=lambda p: p.slug)
def test_every_project_is_well_formed(seed) -> None:  # type: ignore[no-untyped-def]
    assert {s.code for s in seed.skills} <= SKILLS
    assert {a.code for a in seed.assets} <= ASSETS
    assert set(seed.interests) <= INTERESTS
    assert 1 <= seed.difficulty <= 5
    assert 1 <= seed.team_size_min <= seed.team_size_max
    assert seed.work_style in {"SOLO", "TEAM", "EITHER"}
    # پروژهٔ تک‌نفره سبک «تیمی» ندارد، و پروژهٔ «فقط تیمی» تک‌نفره شروع نمی‌شود.
    if seed.team_size_max == 1:
        assert seed.work_style == "SOLO"
    if seed.work_style == "TEAM":
        assert seed.team_size_min >= 2

    if seed.workflow:
        assert not seed.milestones
        return
    # §14.5 P-01 — جمع امتیاز مراحل همان پاداش اعلام‌شده است.
    assert len(seed.milestones) >= 3
    assert sum(m.points for m in seed.milestones) == seed.rewards["points"]
    assert all(m.output_kind in OUTPUT_KINDS for m in seed.milestones)


def test_every_persona_gets_three_strong_matches() -> None:
    """§14.5 «آزمون پوشش» — همان عددی که `check_coverage` چاپ می‌کند."""
    result = coverage()
    for persona in PERSONAS:
        assert len(result[persona.key]) >= REQUIRED_MATCHES, persona.title_fa


@pytest.mark.parametrize(
    ("persona_key", "kind"),
    [("amir", "B_RESEARCH"), ("sara", "A_VENTURE"), ("maryam", "C_PROBLEM")],
)
def test_each_persona_sees_their_own_kind_first(persona_key: str, kind: str) -> None:
    """§01 — پیامد طراحی هر پرسونا: سه پیشنهاد اولش از نوع خودش است.

    آستانهٔ ۷۰ به‌تنهایی سست است (بیشتر بانک از آن می‌گذرد)؛ ترتیب چیزی است
    که دانشجو واقعاً می‌بیند.
    """
    persona = next(p for p in PERSONAS if p.key == persona_key)
    ctx = persona.context()
    now = datetime(2026, 9, 23, tzinfo=UTC)
    ranked = sorted(
        ((score_project(ctx, project_spec(seed), now=now), seed) for seed in PROJECTS),
        key=lambda pair: -pair[0].score,
    )
    top = [seed.kind for match, seed in ranked if not match.is_excluded][:3]
    assert top == [kind] * 3
