"""تست وضعیت ورود اولیه و تولید نام کاربری — §7.1."""

from __future__ import annotations

import pytest

from silp.domain.identity.onboarding import (
    OnboardingState,
    ProfileSnapshot,
    resolve,
)
from silp.domain.identity.username import (
    RESERVED_USERNAMES,
    is_valid_username,
    pick_username,
    slugify_fa,
)


# ── onboarding_state — قاعدهٔ دقیق §7.1 ────────────────────────────────
def test_missing_profile_requires_basic_info() -> None:
    result = resolve(None)
    assert result.state is OnboardingState.BASIC_INFO_REQUIRED
    assert result.next_route == "/onboarding/basic"
    assert result.is_blocking is True


@pytest.mark.parametrize(
    "profile",
    [
        ProfileSnapshot(first_name=None, last_name="کریمی"),
        ProfileSnapshot(first_name="مریم", last_name=None),
        ProfileSnapshot(first_name="", last_name="کریمی"),
        ProfileSnapshot(first_name="مریم", last_name=""),
    ],
)
def test_partial_name_still_requires_basic_info(profile: ProfileSnapshot) -> None:
    assert resolve(profile).state is OnboardingState.BASIC_INFO_REQUIRED


def test_named_profile_without_survey_requires_survey() -> None:
    result = resolve(ProfileSnapshot("مریم", "کریمی", survey_completed_steps=0))
    assert result.state is OnboardingState.SURVEY_REQUIRED
    assert result.next_route == "/onboarding/survey/1"
    assert result.is_blocking is True


@pytest.mark.parametrize("steps", [1, 2, 3])
def test_partial_survey_is_incomplete_but_not_blocking(steps: int) -> None:
    """§7.1 — کاربر می‌تواند از گام ارزیابی رد شود و وارد شود."""
    result = resolve(ProfileSnapshot("مریم", "کریمی", survey_completed_steps=steps))
    assert result.state is OnboardingState.SURVEY_INCOMPLETE
    assert result.is_blocking is False
    assert result.next_route == "/dashboard"
    assert result.completed_steps == steps


def test_full_survey_is_complete() -> None:
    result = resolve(ProfileSnapshot("مریم", "کریمی", survey_completed_steps=4))
    assert result.state is OnboardingState.COMPLETE
    assert result.completed_steps == 4


@pytest.mark.parametrize("steps", [-3, 99])
def test_out_of_range_step_counts_are_clamped(steps: int) -> None:
    """دادهٔ خراب نباید حالت نامعتبر بسازد."""
    result = resolve(ProfileSnapshot("مریم", "کریمی", survey_completed_steps=steps))
    assert 0 <= result.completed_steps <= 4


# ── slugify و نام کاربری ───────────────────────────────────────────────
@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("مریم کریمی", "marim-karimi"),
        ("امیر", "amir"),
        ("علی", "ali"),  # حرف‌نویسی خودش مصوت دارد، مصوت دوم درج نمی‌شود
        ("ژاله", "zhale"),  # «ه» پایانی صدای e دارد
        ("زهرا", "zahra"),  # «ه» میانی همخوان است
        ("نگار شریفی", "nagar-sharifi"),
    ],
)
def test_transliteration_is_readable_latin(name: str, expected: str) -> None:
    """خروجی باید خوانا باشد، نه صرفاً مجاز: «مریم» نه «mrim»."""
    assert slugify_fa(name) == expected


@pytest.mark.parametrize("name", ["مریم کریمی", "امیر رضایی", "خسرو", "سارا محمدی", "محمدحسین"])
def test_slug_is_url_safe(name: str) -> None:
    slug = slugify_fa(name)
    assert slug
    assert all(c.isalnum() or c == "-" for c in slug)
    assert slug == slug.lower()


def test_transliteration_is_deterministic() -> None:
    """دو بار اجرا باید یک نتیجه بدهد — نام کاربری نباید بین دو درخواست فرق کند."""
    assert slugify_fa("مریم کریمی") == slugify_fa("مریم کریمی")


def test_slug_never_starts_or_ends_with_dash() -> None:
    for name in ["  مریم  ", "-مریم-", "مریم کریمی"]:
        slug = slugify_fa(name)
        assert not slug.startswith("-")
        assert not slug.endswith("-")


def test_empty_name_falls_back_to_user() -> None:
    assert pick_username("", "", is_taken=lambda _: False) == "user"


def test_first_free_candidate_is_chosen() -> None:
    assert pick_username("مریم", "کریمی", is_taken=lambda _: False) == slugify_fa("مریم-کریمی")


def test_collision_appends_numeric_suffix() -> None:
    base = slugify_fa("مریم-کریمی")
    taken = {base, f"{base}-2", f"{base}-3"}
    assert pick_username("مریم", "کریمی", is_taken=taken.__contains__) == f"{base}-4"


def test_reserved_words_are_never_issued() -> None:
    """نام کاربری `admin` مسیر /u/admin را می‌شکند."""
    chosen = pick_username("ad", "min", is_taken=lambda _: False)
    assert chosen not in RESERVED_USERNAMES


def test_generated_username_is_always_valid() -> None:
    for first, last in [("مریم", "کریمی"), ("امیر", "رضایی"), ("", "")]:
        assert is_valid_username(pick_username(first, last, is_taken=lambda _: False))


@pytest.mark.parametrize(
    ("value", "valid"),
    [
        ("maryam-k", True),
        ("a1", False),  # کوتاه‌تر از ۳
        ("-leading", False),
        ("trailing-", False),
        ("Upper", False),
        ("with space", False),
        ("admin", False),
        ("x" * 33, False),
    ],
)
def test_username_validation_rules(value: str, valid: bool) -> None:
    assert is_valid_username(value) is valid
