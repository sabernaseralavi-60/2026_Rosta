"""سهم فروشنده — منطق خالص ADR-0025."""

from __future__ import annotations

from decimal import Decimal

import pytest

from silp.domain.ventures import share_of, share_percent_of


@pytest.mark.parametrize(
    ("rewards", "expected"),
    [
        ({"points": 200, "revenue_share_percent": 15}, Decimal("15.00")),
        ({"revenue_share_percent": 12.5}, Decimal("12.50")),
        ({"revenue_share_percent": 0}, Decimal("0.00")),
        ({"revenue_share_percent": 100}, Decimal("100.00")),
        ({"points": 200}, Decimal(0)),
        ({}, Decimal(0)),
        (None, Decimal(0)),
        ({"revenue_share_percent": "15"}, Decimal(0)),  # رشته یعنی فرم غلط پر شده
        ({"revenue_share_percent": True}, Decimal(0)),  # bool زیرکلاس int است
        ({"revenue_share_percent": -5}, Decimal(0)),
        ({"revenue_share_percent": 101}, Decimal(0)),
        ({"revenue_share_percent": float("nan")}, Decimal(0)),
        ({"revenue_share_percent": float("inf")}, Decimal(0)),
    ],
)
def test_share_percent_reads_only_a_sane_number(rewards: object, expected: Decimal) -> None:
    assert share_percent_of(rewards) == expected


def test_share_is_floored_so_shares_never_exceed_the_sale() -> None:
    assert share_of(12_000_000, Decimal("15")) == 1_800_000
    # ۱۵٪ از ۹۹۹ = ۱۴۹٫۸۵ ← ۱۴۹، نه ۱۵۰
    assert share_of(999, Decimal("15")) == 149
    assert share_of(1, Decimal("99.99")) == 0


def test_share_is_zero_for_no_sale_or_no_percent() -> None:
    assert share_of(0, Decimal("15")) == 0
    assert share_of(-5, Decimal("15")) == 0
    assert share_of(1_000_000, Decimal(0)) == 0


def test_share_of_the_maximum_sale_is_exact() -> None:
    top = 1_000_000_000_000  # MAX_SALES_RIAL
    assert share_of(top, Decimal("100")) == top
    assert share_of(top, Decimal("12.5")) == 125_000_000_000
