"""منطق خالص داشبورد — شاخص سلامت پروژه (§7.4) و «قدم بعدی» (FR-DASH-01)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from silp.domain.next_step import NextStep, choose
from silp.domain.project_health import MilestoneState, compute_health

TODAY = date(2026, 10, 1)
NOW = datetime(2026, 10, 1, 8, 0, tzinfo=UTC)


# ── سلامت پروژه ────────────────────────────────────────────────────────
def _health(
    *,
    idle_days: int = 0,
    milestones: list[MilestoneState] | None = None,
    deadline_in: int | None = None,
) -> str:
    return compute_health(
        today=TODAY,
        last_activity_on=TODAY - timedelta(days=idle_days),
        milestones=milestones or [],
        deadline_on=TODAY + timedelta(days=deadline_in) if deadline_in is not None else None,
    ).health


def test_fourteen_idle_days_is_stalled() -> None:
    assert _health(idle_days=14) == "STALLED"
    assert _health(idle_days=13) == "AT_RISK"
    assert _health(idle_days=6) == "HEALTHY"


def test_overdue_unapproved_milestone_is_at_risk() -> None:
    late = MilestoneState(due_on=TODAY - timedelta(days=1), status="IN_PROGRESS")
    done = MilestoneState(due_on=TODAY - timedelta(days=1), status="APPROVED")
    assert _health(milestones=[late]) == "AT_RISK"
    assert _health(milestones=[done]) == "HEALTHY"


def test_close_deadline_with_little_progress_is_at_risk() -> None:
    pending = [MilestoneState(due_on=None, status="PENDING") for _ in range(3)]
    approved = [MilestoneState(due_on=None, status="APPROVED") for _ in range(3)]
    assert _health(milestones=pending, deadline_in=5) == "AT_RISK"
    assert _health(milestones=approved, deadline_in=5) == "HEALTHY"


def test_stalled_wins_over_at_risk_and_explains_itself() -> None:
    verdict = compute_health(
        today=TODAY,
        last_activity_on=TODAY - timedelta(days=20),
        milestones=[MilestoneState(due_on=TODAY - timedelta(days=3), status="PENDING")],
        deadline_on=None,
    )
    assert verdict.health == "STALLED"
    assert verdict.reason == "20 روز بدون فعالیت"


# ── قدم بعدی ───────────────────────────────────────────────────────────
def _step(kind: str, due_in: timedelta | None = None) -> NextStep:
    return NextStep(
        kind=kind,
        title=kind,
        description="",
        href="/",
        due_at=NOW + due_in if due_in is not None else None,
    )


def test_quiz_closing_within_a_day_beats_an_overdue_milestone() -> None:
    chosen = choose(
        [_step("MILESTONE_OVERDUE", -timedelta(days=2)), _step("QUIZ_OPEN", timedelta(hours=5))],
        now=NOW,
    )
    assert chosen is not None and chosen.kind == "QUIZ_OPEN"


def test_overdue_milestone_beats_a_quiz_with_time_left() -> None:
    chosen = choose(
        [_step("QUIZ_OPEN", timedelta(days=4)), _step("MILESTONE_OVERDUE", -timedelta(days=2))],
        now=NOW,
    )
    assert chosen is not None and chosen.kind == "MILESTONE_OVERDUE"


def test_within_a_kind_the_earliest_deadline_wins() -> None:
    first = _step("MILESTONE_DUE", timedelta(days=2))
    later = _step("MILESTONE_DUE", timedelta(days=5))
    assert choose([later, first], now=NOW) is first


def test_profile_before_study_before_exploration() -> None:
    steps = [_step("FIND_PROJECT"), _step("STUDY"), _step("PROFILE_INCOMPLETE")]
    chosen = choose(steps, now=NOW)
    assert chosen is not None and chosen.kind == "PROFILE_INCOMPLETE"


def test_nothing_to_do_is_none() -> None:
    assert choose([], now=NOW) is None
