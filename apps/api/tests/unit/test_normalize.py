"""تست نرمال‌سازی مقصد — FR-AUTH-01."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from silp.domain.identity.normalize import (
    detect_channel,
    is_valid_national_id,
    normalize_email,
    normalize_mobile,
    to_latin_digits,
)

CANONICAL = "09121234567"


@pytest.mark.parametrize(
    "raw",
    [
        "09121234567",
        "+989121234567",
        "00989121234567",
        "989121234567",
        "9121234567",
        "0912 123 4567",
        "0912-123-4567",
        "۰۹۱۲۱۲۳۴۵۶۷",  # ارقام فارسی
        "٠٩١٢١٢٣٤٥٦٧",  # ارقام عربی-هندی
        "  09121234567  ",
        "(0912) 123-4567",
    ],
)
def test_every_input_shape_reaches_one_stored_value(raw: str) -> None:
    """یک نفر نباید به خاطر شکل نوشتن شماره، دو حساب بگیرد."""
    assert normalize_mobile(raw) == CANONICAL


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "0812345678",  # پیش‌شمارهٔ نامعتبر
        "091212345678",  # یک رقم اضافه
        "0912123456",  # یک رقم کم
        "not-a-number",
        "+1 555 123 4567",
        "0000000000",
    ],
)
def test_invalid_mobile_is_rejected(raw: str) -> None:
    assert normalize_mobile(raw) is None


def test_none_mobile_is_none() -> None:
    assert normalize_mobile(None) is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Maryam@Example.COM", "maryam@example.com"),
        ("  s@example.ir  ", "s@example.ir"),
        ("a.b+tag@sub.domain.ac.ir", "a.b+tag@sub.domain.ac.ir"),
    ],
)
def test_email_is_normalized(raw: str, expected: str) -> None:
    assert normalize_email(raw) == expected


@pytest.mark.parametrize("raw", ["", "no-at-sign", "a@b", "@example.com", "a@@b.com"])
def test_invalid_email_is_rejected(raw: str) -> None:
    assert normalize_email(raw) is None


def test_channel_is_detected_from_shape() -> None:
    assert detect_channel("09121234567") == "SMS"
    assert detect_channel("s@example.com") == "EMAIL"


@given(st.text(alphabet="0123456789", min_size=1, max_size=20))
def test_latin_digits_are_unchanged(value: str) -> None:
    assert to_latin_digits(value) == value


@given(st.integers(min_value=0, max_value=9_999_999_999))
def test_normalization_is_idempotent(number: int) -> None:
    """نرمال‌سازی دوباره نباید نتیجه را عوض کند."""
    raw = f"09{number:09d}"[:11]
    once = normalize_mobile(raw)
    if once is not None:
        assert normalize_mobile(once) == once


# ── کد ملی — FR-AUTH-04 ────────────────────────────────────────────────
@pytest.mark.parametrize("value", ["0499370899", "0084575948", "0790419904"])
def test_valid_national_ids_pass(value: str) -> None:
    assert is_valid_national_id(value) is True


@pytest.mark.parametrize(
    "value",
    [
        "0499370898",  # رقم کنترل غلط
        "1111111111",  # ارقام یکسان
        "123",
        "",
        None,
        "abcdefghij",
    ],
)
def test_invalid_national_ids_fail(value: str | None) -> None:
    assert is_valid_national_id(value) is False
