"""قواعد تحلیل مشارکت — ADR-0026. خالص، بدون دیتابیس."""

from __future__ import annotations

import uuid

import pytest

from silp.domain import contribution as rules
from silp.domain.contribution import MemberCounts

A, B, C = (uuid.uuid4() for _ in range(3))


def _by_user(analysis: rules.Analysis) -> dict[uuid.UUID, rules.MemberShare]:
    return {m.user_id: m for m in analysis.members}


def test_weights_sum_to_one() -> None:
    assert sum(rules.WEIGHTS.values()) == pytest.approx(1.0)


def test_shares_of_a_full_team_add_up_to_a_hundred() -> None:
    analysis = rules.analyse(
        [
            MemberCounts(A, {rules.DELIVERABLES: 3, rules.TASKS: 4, rules.DISCUSSION: 10}),
            MemberCounts(B, {rules.DELIVERABLES: 1, rules.TASKS: 4, rules.DISCUSSION: 5}),
            MemberCounts(C, {rules.DELIVERABLES: 2, rules.VERIFIED_ACTIVITY: 7}),
        ]
    )
    total = sum(m.share_percent or 0 for m in analysis.members)
    assert total == pytest.approx(100, abs=0.3), "گردکردن یک رقم اعشار"


def test_a_dimension_nobody_has_is_dropped_and_weights_renormalise() -> None:
    analysis = rules.analyse(
        [
            MemberCounts(A, {rules.DELIVERABLES: 1, rules.DISCUSSION: 1}),
            MemberCounts(B, {rules.DELIVERABLES: 1, rules.DISCUSSION: 1}),
        ]
    )
    assert set(analysis.effective_weights) == {rules.DELIVERABLES, rules.DISCUSSION}
    assert sum(analysis.effective_weights.values()) == pytest.approx(1.0)
    assert analysis.effective_weights[rules.DELIVERABLES] == pytest.approx(0.40 / 0.55)
    assert [m.share_percent for m in analysis.members] == [50.0, 50.0]


def test_a_team_with_nothing_recorded_has_no_share_at_all() -> None:
    analysis = rules.analyse([MemberCounts(A, {}), MemberCounts(B, {})])
    assert analysis.effective_weights == {}
    assert [m.share_percent for m in analysis.members] == [None, None], "نه «۰٪ برای همه»"
    assert all(s.share_percent is None for m in analysis.members for s in m.signals)


def test_endless_chatter_is_capped_by_the_weight_of_its_own_dimension() -> None:
    """۵۰۰ پیام در برابر یک تحویل تأییدشده: پیام‌دهنده از وزن *مؤثر* گفتگو بالاتر نمی‌رود.

    فقط دو بُعد داده دارند، پس وزن‌ها بهنجار می‌شوند: ۰٫۱۵ ÷ ۰٫۵۵ ≈ ۲۷٫۳٪.
    """
    analysis = rules.analyse(
        [
            MemberCounts(A, {rules.DELIVERABLES: 1}),
            MemberCounts(B, {rules.DISCUSSION: 500}),
        ]
    )
    shares = _by_user(analysis)
    assert shares[B].share_percent == pytest.approx(100 * 0.15 / 0.55, abs=0.1)
    assert shares[A].share_percent == pytest.approx(100 * 0.40 / 0.55, abs=0.1)
    assert shares[B].share_percent < 100 * analysis.effective_weights[rules.DISCUSSION] + 0.1


def test_with_all_four_dimensions_chatter_never_passes_fifteen_percent() -> None:
    analysis = rules.analyse(
        [
            MemberCounts(A, {rules.DELIVERABLES: 1, rules.VERIFIED_ACTIVITY: 1, rules.TASKS: 1}),
            MemberCounts(B, {rules.DISCUSSION: 10_000}),
        ]
    )
    assert _by_user(analysis)[B].share_percent == pytest.approx(15.0)


def test_the_top_share_comes_first_and_nothing_recorded_comes_last() -> None:
    analysis = rules.analyse(
        [
            MemberCounts(A, {}),
            MemberCounts(B, {rules.TASKS: 1}),
            MemberCounts(C, {rules.TASKS: 3}),
        ]
    )
    assert [m.user_id for m in analysis.members] == [C, B, A]


def test_ties_keep_the_input_order() -> None:
    analysis = rules.analyse([MemberCounts(A, {rules.TASKS: 2}), MemberCounts(B, {rules.TASKS: 2})])
    assert [m.user_id for m in analysis.members] == [A, B]


def test_an_active_member_with_nothing_is_silent_but_one_who_left_is_not() -> None:
    analysis = rules.analyse(
        [
            MemberCounts(A, {rules.TASKS: 1}),
            MemberCounts(B, {}),
            MemberCounts(C, {}, is_active=False),
        ]
    )
    shares = _by_user(analysis)
    assert shares[A].is_silent is False
    assert shares[B].is_silent is True
    assert shares[C].is_silent is False, "کسی که رفته «ساکت» نیست؛ فقط رفته است"


def test_a_member_who_left_keeps_their_share_of_the_team() -> None:
    analysis = rules.analyse(
        [
            MemberCounts(A, {rules.TASKS: 3}),
            MemberCounts(B, {rules.TASKS: 1}, is_active=False),
        ]
    )
    assert _by_user(analysis)[A].share_percent == 75.0
    assert _by_user(analysis)[B].share_percent == 25.0


def test_every_member_gets_every_dimension_in_display_order() -> None:
    analysis = rules.analyse([MemberCounts(A, {rules.TASKS: 1})])
    assert [s.dimension for s in analysis.members[0].signals] == list(rules.DIMENSIONS)
    assert analysis.members[0].signals[2].share_percent == 100.0
    assert analysis.members[0].signals[0].share_percent is None, "کل تیم در این بُعد صفر است"


def test_a_solo_team_is_one_hundred_percent() -> None:
    analysis = rules.analyse([MemberCounts(A, {rules.DELIVERABLES: 2, rules.DISCUSSION: 1})])
    assert analysis.members[0].share_percent == 100.0


def test_negative_counts_are_ignored() -> None:
    analysis = rules.analyse(
        [MemberCounts(A, {rules.TASKS: -5}), MemberCounts(B, {rules.TASKS: 2})]
    )
    assert analysis.team_totals[rules.TASKS] == 2
    assert _by_user(analysis)[A].share_percent == 0.0
