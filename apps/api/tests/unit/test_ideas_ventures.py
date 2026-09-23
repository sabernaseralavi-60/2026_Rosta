"""بانک ایده و کارآفرینی — منطق خالص (M7). بدون دیتابیس."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from silp.core.permissions import CurrentUser, Permission, Role, RoleGrant, ScopeType
from silp.domain import ideas, ventures


# ── ایده ───────────────────────────────────────────────────────────────
def test_hot_score_prefers_fresh_ideas_with_equal_votes() -> None:
    now = datetime(2026, 9, 23, tzinfo=UTC)
    fresh = ideas.hot_score(10, now - timedelta(hours=1), now)
    stale = ideas.hot_score(10, now - timedelta(days=3), now)
    assert fresh > stale


def test_hot_score_matches_the_prd_formula() -> None:
    """FR-IDEA-02: `votes / (hours + 2) ^ 1.5`."""
    now = datetime(2026, 9, 23, tzinfo=UTC)
    assert ideas.hot_score(8, now - timedelta(hours=2), now) == pytest.approx(8 / 4**1.5)


def test_hot_score_of_a_future_timestamp_does_not_explode() -> None:
    now = datetime(2026, 9, 23, tzinfo=UTC)
    assert ideas.hot_score(3, now + timedelta(minutes=5), now) == pytest.approx(3 / 2**1.5)


@pytest.mark.parametrize(
    ("votes", "expected"),
    [(0, []), (9, []), (10, ["IDEA_VOTES_10"]), (50, ["IDEA_VOTES_10", "IDEA_VOTES_50"])],
)
def test_vote_milestones(votes: int, expected: list[str]) -> None:
    assert ideas.reached_milestones(votes) == expected


def test_clean_tags_trims_dedupes_and_strips_hash() -> None:
    assert ideas.clean_tags(["  #حمل‌ونقل ", "حمل‌ونقل", "", "  هوش   مصنوعی "]) == [
        "حمل‌ونقل",
        "هوش مصنوعی",
    ]


def test_clean_tags_rejects_long_or_too_many() -> None:
    with pytest.raises(ValueError, match="بلندتر"):
        ideas.clean_tags(["ا" * 31])
    with pytest.raises(ValueError, match="حداکثر"):
        ideas.clean_tags([f"برچسب{i}" for i in range(9)])


# ── مرحلهٔ بلوغ — §7.7 ─────────────────────────────────────────────────
def test_idea_stage_needs_all_four_profile_fields() -> None:
    partial = ventures.VentureFacts(filled_fields=frozenset({"description", "problem"}))
    readiness = ventures.readiness("IDEA", partial)
    assert readiness.next_stage == "VALIDATION"
    assert not readiness.ready
    assert len(readiness.missing) == 2

    full = ventures.VentureFacts(
        filled_fields=frozenset({"description", "problem", "target_market", "revenue_model"})
    )
    assert ventures.readiness("IDEA", full).ready


def test_validation_needs_ten_verified_contacts() -> None:
    assert not ventures.readiness("VALIDATION", ventures.VentureFacts(verified_contacts=9)).ready
    ready = ventures.readiness("VALIDATION", ventures.VentureFacts(verified_contacts=12))
    assert ready.ready
    # پیشرفت به هدف محدود است — «۱۲ از ۱۰» در رابط کاربری بی‌معناست.
    assert ready.criteria[0].current == 10


def test_mvp_needs_an_approved_code_or_media_deliverable() -> None:
    facts = ventures.VentureFacts(approved_mvp_deliverables=1)
    assert ventures.readiness("MVP", facts).next_stage == "FIRST_REVENUE"
    assert ventures.readiness("MVP", facts).ready
    assert not ventures.readiness("MVP", ventures.VentureFacts()).ready


def test_growth_threshold_is_strictly_greater() -> None:
    at = ventures.VentureFacts(verified_sales_rial=1000, growth_threshold_rial=1000)
    over = ventures.VentureFacts(verified_sales_rial=1001, growth_threshold_rial=1000)
    assert not ventures.readiness("FIRST_REVENUE", at).ready
    assert ventures.readiness("FIRST_REVENUE", over).ready


@pytest.mark.parametrize("stage", ["GROWTH", "PAUSED", "CLOSED"])
def test_no_next_stage_after_growth_or_outside_growth(stage: str) -> None:
    readiness = ventures.readiness(stage, ventures.VentureFacts())
    assert readiness.next_stage is None
    assert not readiness.ready


def test_stage_number_is_the_stage_up_multiplier() -> None:
    assert [ventures.stage_number(s) for s in ("VALIDATION", "MVP", "FIRST_REVENUE", "GROWTH")] == [
        1,
        2,
        3,
        4,
    ]


# ── ضریب شاخص — §9.2 `STARTUP` ─────────────────────────────────────────
def test_sales_amount_multiplier_is_one_point_per_half_million_toman() -> None:
    assert ventures.metric_multiplier("SALES_AMOUNT", 12_000_000, per_row_cap=None) == Decimal(
        "2.4"
    )


def test_sales_amount_multiplier_caps_at_200() -> None:
    assert ventures.metric_multiplier("SALES_AMOUNT", 10**11, per_row_cap=None) == Decimal(200)


def test_capped_counts_use_the_daily_cap_per_row() -> None:
    """«۵۰ تماس» در یک ردیف، ۲۰ تماس حساب می‌شود — سقف روزانهٔ قاعده."""
    assert ventures.metric_multiplier("CALLS", 50, per_row_cap=20) == Decimal(20)
    assert ventures.metric_multiplier("CALLS", 7, per_row_cap=20) == Decimal(7)


def test_uncapped_counts_are_bounded() -> None:
    assert ventures.metric_multiplier("LEADS", 5000, per_row_cap=None) == Decimal(
        ventures.UNCAPPED_COUNT_LIMIT
    )


def test_every_metric_has_a_point_rule() -> None:
    from silp.models.venture import METRIC_KINDS

    assert set(ventures.METRIC_RULES) == set(METRIC_KINDS)


# ── مجوزها ─────────────────────────────────────────────────────────────
def _user(*grants: RoleGrant) -> CurrentUser:
    return CurrentUser(id=uuid.uuid4(), session_id=uuid.uuid4(), grants=grants)


def test_offering_instructor_may_promote_ideas() -> None:
    """ایده به ارائه‌ای تعلق ندارد؛ استاد هر ارائه‌ای داور ایده است."""
    instructor = _user(RoleGrant(Role.INSTRUCTOR, ScopeType.OFFERING, uuid.uuid4()))
    assert instructor.has_permission(Permission.IDEA_PROMOTE)
    assert not _user(RoleGrant(Role.STUDENT)).has_permission(Permission.IDEA_PROMOTE)


def test_project_lead_verifies_metrics_only_in_own_project() -> None:
    own, other = uuid.uuid4(), uuid.uuid4()
    lead = _user(RoleGrant(Role.PROJECT_LEAD, ScopeType.PROJECT, own))
    assert lead.has_permission(Permission.PROJECT_METRIC_VERIFY, own)
    assert not lead.has_permission(Permission.PROJECT_METRIC_VERIFY, other)
    # مدیر پروژه داور شاخص کسب‌وکار نیست.
    assert not lead.has_permission(Permission.VENTURE_METRIC_VERIFY)


def test_students_cannot_verify_venture_metrics() -> None:
    assert not _user(RoleGrant(Role.STUDENT)).has_permission(Permission.VENTURE_METRIC_VERIFY)
    assert _user(RoleGrant(Role.MENTOR)).has_permission(Permission.VENTURE_METRIC_VERIFY)
