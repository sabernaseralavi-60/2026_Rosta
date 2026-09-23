"""پژوهش و تیم — منطق خالص M7 بخش ب (ADR-0015). بدون دیتابیس."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest

from silp.domain import research as rules
from silp.domain import teams

TODAY = date(2026, 9, 23)


# ── شاهد تحویل سطح ─────────────────────────────────────────────────────
def _submit(level: int, **overrides: object) -> tuple[dict[str, object], list[str]]:
    base: dict[str, object] = {
        "summary": "خلاصهٔ تحویل با جزئیات کافی برای بازبین، بیش از سی نویسه.",
        "links": ["https://example.org/matrix.xlsx"],
        "file_count": 0,
        "evidence": {
            "source_count": 24,
            "gap_summary": "هیچ پژوهشی ایمنی عابر پیاده را در تقاطع‌های بی‌چراغ شهرهای"
            " متوسط ایران با دادهٔ تصادف و حجم تردد با هم نسنجیده است.",
        },
    }
    base.update(overrides)
    return rules.validate_submission(level, today=TODAY, **base)  # type: ignore[arg-type]


def test_level_one_accepts_complete_evidence() -> None:
    cleaned, problems = _submit(1)
    assert problems == []
    assert cleaned["source_count"] == 24


def test_level_one_reports_every_gap_at_once() -> None:
    """مثل معیار خروج §7.7 — همهٔ کمبودها یک‌جا، نه یکی‌یکی."""
    _, problems = _submit(1, links=[], evidence={"source_count": 12})
    assert len(problems) == 3
    assert any("۲۰" in p or "20" in p for p in problems)


def test_unknown_evidence_and_bad_links_are_rejected() -> None:
    _, problems = _submit(1, links=["ftp://x"], evidence={"source_count": 20, "extra": 1})
    assert any("پیوند نامعتبر" in p for p in problems)
    assert any("ناشناخته" in p for p in problems)


def test_future_dates_are_refused() -> None:
    _, problems = rules.validate_submission(
        3,
        summary="پیش‌نویس کامل مقاله برای کنفرانس ملی حمل‌ونقل ارسال شد.",
        links=["https://example.org/draft.pdf"],
        file_count=0,
        evidence={"venue": "کنفرانس ملی حمل‌ونقل", "submitted_on": "2026-12-01"},
        today=TODAY,
    )
    assert any("آینده" in p for p in problems)


@pytest.mark.parametrize(
    ("statuses", "expected"),
    [
        ({}, ["AVAILABLE", "LOCKED", "LOCKED", "LOCKED"]),
        ({1: "SUBMITTED"}, ["SUBMITTED", "LOCKED", "LOCKED", "LOCKED"]),
        ({1: "APPROVED", 2: "IN_PROGRESS"}, ["APPROVED", "IN_PROGRESS", "LOCKED", "LOCKED"]),
    ],
)
def test_level_state_unlocks_one_step_at_a_time(
    statuses: dict[int, str], expected: list[str]
) -> None:
    assert [rules.level_state(n, statuses) for n in rules.LEVELS] == expected


def test_current_level_is_none_when_all_approved() -> None:
    assert rules.current_level({n: "APPROVED" for n in rules.LEVELS}) is None
    assert rules.current_level({1: "APPROVED"}) == 2


# ── خروجی پژوهشی ───────────────────────────────────────────────────────
def test_published_journal_earns_every_stage_with_quartile_factor() -> None:
    awards = dict(rules.output_awards("JOURNAL", "PUBLISHED", "Q1"))
    assert awards == {
        "OUTPUT_SUBMITTED": Decimal(1),
        "OUTPUT_ACCEPTED": Decimal("2.0"),
        "OUTPUT_PUBLISHED": Decimal(1),
    }


def test_conference_ignores_quartile_and_thesis_is_unscored() -> None:
    assert dict(rules.output_awards("CONFERENCE", "ACCEPTED", "Q1"))["OUTPUT_ACCEPTED"] == 1
    assert rules.output_awards("THESIS", "PUBLISHED", None) == []


def test_review_is_needed_only_when_points_would_change() -> None:
    verified = {"verified_stage": "SUBMITTED", "verified_quartile": None}
    # «در داوری» پس از «ارسال‌شده» امتیاز را عوض نمی‌کند.
    assert not rules.needs_review(kind="JOURNAL", status="UNDER_REVIEW", quartile="Q2", **verified)
    assert rules.needs_review(kind="JOURNAL", status="ACCEPTED", quartile="Q2", **verified)
    # چارک دیگر پس از پذیرش تأییدشده — ضریب عوض می‌شود.
    assert rules.needs_review(
        kind="JOURNAL",
        status="ACCEPTED",
        quartile="Q1",
        verified_stage="ACCEPTED",
        verified_quartile="Q2",
    )
    # پایان‌نامه هرگز صف بازبین را پر نمی‌کند.
    assert not rules.needs_review(
        kind="THESIS",
        status="PUBLISHED",
        quartile=None,
        verified_stage=None,
        verified_quartile=None,
    )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://doi.org/10.1016/j.aap.2024.107512", "10.1016/j.aap.2024.107512"),
        ("doi:10.1109/ITSC.2023.1", "10.1109/ITSC.2023.1"),
        ("  ", None),
    ],
)
def test_doi_is_normalized(raw: str, expected: str | None) -> None:
    assert rules.normalize_doi(raw) == expected


def test_doi_format() -> None:
    assert rules.is_doi("10.1016/j.aap.2024.107512")
    assert not rules.is_doi("1016/abc")


# ── هم‌تیمی مکمل — §8.14 ───────────────────────────────────────────────
GIS, PY, R = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
NEEDS = [
    teams.Need(GIS, "GIS", 4, weight=2),
    teams.Need(PY, "Python", 3),
    teams.Need(R, "R", 3),
]


def _candidate(**overrides: object) -> teams.Candidate:
    base: dict[str, object] = {"user_id": uuid.uuid4(), "skills": {GIS: 4}}
    base.update(overrides)
    return teams.Candidate(**base)  # type: ignore[arg-type]


def test_gaps_are_needs_nobody_in_the_team_covers() -> None:
    gaps = teams.team_gaps(NEEDS, {PY: 5, R: 2})
    assert [g.title_fa for g in gaps] == ["GIS", "R"]
    assert teams.team_gaps(NEEDS, {GIS: 4, PY: 3, R: 3}) == []


def test_no_gaps_means_no_complement_score() -> None:
    assert teams.complement(_candidate(), []) is None


def test_complement_rewards_the_missing_skill_and_explains_it() -> None:
    gaps = teams.team_gaps(NEEDS, {PY: 5, R: 3})
    result = teams.complement(_candidate(), gaps)
    assert result is not None
    assert result.score == 100.0
    assert result.reason == "مهارت GIS را در سطح ۴ دارد که هیچ‌کس در تیم ندارد."


def test_complement_is_weighted_and_stays_within_bounds() -> None:
    gaps = teams.team_gaps(NEEDS, {})
    only_r = teams.complement(_candidate(skills={R: 5}), gaps)
    only_gis = teams.complement(_candidate(skills={GIS: 5}), gaps)
    assert only_r is not None and only_gis is not None
    assert only_gis.score > only_r.score  # GIS وزن ۲ دارد
    boosted = teams.complement(
        _candidate(
            skills={GIS: 5, PY: 5, R: 5},
            completed_projects=4,
            shares_course=True,
        ),
        gaps,
    )
    assert boosted is not None and boosted.score == 100.0


def test_availability_softens_but_never_hides() -> None:
    assert teams.availability_factor(None, 10) == 1.0
    assert teams.availability_factor(8, 10) == 1.0
    assert teams.availability_factor(1, 10) == teams.AVAILABILITY_FLOOR


def test_completion_rate_needs_a_sample() -> None:
    assert _candidate(completed_projects=1).completion_rate is None
    assert _candidate(completed_projects=3, dropped_projects=1).completion_rate == 0.75


def test_partial_match_says_how_close() -> None:
    gaps = teams.team_gaps(NEEDS, {PY: 5, R: 5})
    result = teams.complement(_candidate(skills={GIS: 2}), gaps)
    assert result is not None
    assert "نزدیک" in result.reason


def test_without_a_project_we_show_where_they_are_stronger() -> None:
    titles = {GIS: "GIS", PY: "Python", R: "R"}
    stronger = teams.stronger_skills(_candidate(skills={GIS: 4, PY: 2, R: 5}), {R: 4}, titles)
    assert [s.title_fa for s in stronger] == ["GIS"]
    assert teams.stronger_reason(stronger) == "در GIS از تو قوی‌تر است."
    assert teams.stronger_reason([]) is None
