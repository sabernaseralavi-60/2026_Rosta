"""قواعد ارزیابی همتا — ADR-0024. خالص، بدون دیتابیس."""

from __future__ import annotations

import uuid

import pytest

from silp.domain import peer_evaluations as rules
from silp.domain.peer_evaluations import PeerRating

A, B, C = (uuid.uuid4() for _ in range(3))


def test_a_rating_for_every_peer_is_accepted() -> None:
    ratings = [PeerRating(A, 4, 5), PeerRating(B, 1)]
    assert rules.validate(ratings, [A, B]) is None
    assert rules.validate(list(reversed(ratings)), [A, B]) is None, "ترتیب مهم نیست"


def test_a_missing_peer_makes_it_incomplete() -> None:
    message = rules.validate([PeerRating(A, 4)], [A, B])
    assert message is not None and "ناقص" in message


def test_someone_who_is_not_a_peer_is_refused() -> None:
    assert rules.validate([PeerRating(A, 4), PeerRating(C, 4)], [A]) is not None
    assert rules.validate([PeerRating(C, 4)], []) is not None


def test_a_duplicate_is_refused_even_when_everyone_is_covered() -> None:
    assert (
        rules.validate([PeerRating(A, 4), PeerRating(A, 2), PeerRating(B, 3)], [A, B]) is not None
    )


@pytest.mark.parametrize("value", [0, 6, -1])
def test_out_of_range_is_refused(value: int) -> None:
    assert rules.validate([PeerRating(A, value)], [A]) is not None
    assert rules.validate([PeerRating(A, 3, value)], [A]) is not None


@pytest.mark.parametrize("value", [1, 5])
def test_the_edges_of_the_range_are_accepted(value: int) -> None:
    assert rules.validate([PeerRating(A, value, value)], [A]) is None


def test_an_average_needs_enough_opinions_to_stay_anonymous() -> None:
    assert rules.average([]) is None
    assert rules.average([5]) is None
    assert rules.average([3, 4]) == 3.5
    assert rules.average([5, 4, 4]) == 4.3
