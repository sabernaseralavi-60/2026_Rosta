"""تست عملیات رمزنگاری — NFR-01، FR-AUTH-01/03."""

from __future__ import annotations

import uuid
from datetime import timedelta

import jwt
import pytest

from silp.core.exceptions import InvalidToken, TokenExpired
from silp.core.security import (
    create_access_token,
    decode_access_token,
    generate_otp,
    generate_refresh_token,
    hash_otp,
    hash_password,
    hash_refresh_token,
    mask_email,
    mask_mobile,
    verify_otp,
    verify_password,
)


# ── رمز عبور — argon2id ────────────────────────────────────────────────
def test_password_hash_is_not_reversible() -> None:
    password = "یک-رمز-قوی-1404"
    digest = hash_password(password)
    assert password not in digest
    assert digest.startswith("$argon2id$")


def test_password_verification_round_trips() -> None:
    password = "correct horse battery staple"
    assert verify_password(password, hash_password(password)) is True
    assert verify_password("wrong", hash_password(password)) is False


def test_same_password_gets_different_hashes() -> None:
    """نمک تصادفی است؛ دو هش یکسان یعنی نمک ثابت."""
    assert hash_password("same") != hash_password("same")


def test_missing_hash_is_rejected_not_accepted() -> None:
    """کاربر بدون رمز (فقط OTP) نباید با رمز خالی وارد شود."""
    assert verify_password("anything", None) is False
    assert verify_password("anything", "") is False


# ── OTP — bcrypt، FR-AUTH-01 ───────────────────────────────────────────
@pytest.mark.parametrize("length", [4, 5, 6, 7, 8])
def test_otp_has_requested_length(length: int) -> None:
    code = generate_otp(length)
    assert len(code) == length
    assert code.isdigit()


def test_otp_keeps_leading_zeros() -> None:
    """کد `012345` شش‌رقمی است، نه پنج‌رقمی."""
    codes = {generate_otp(6) for _ in range(200)}
    assert all(len(c) == 6 for c in codes)


def test_otp_hash_verifies_and_rejects() -> None:
    code = "482913"
    digest = hash_otp(code)
    assert code not in digest
    assert verify_otp(code, digest) is True
    assert verify_otp("482914", digest) is False


def test_malformed_otp_hash_does_not_raise() -> None:
    assert verify_otp("123456", "not-a-bcrypt-hash") is False


# ── Refresh token — FR-AUTH-03 ─────────────────────────────────────────
def test_refresh_token_has_256_bits_of_entropy() -> None:
    token = generate_refresh_token()
    # token_urlsafe(32) حدود ۴۳ نویسه می‌دهد
    assert len(token) >= 40
    assert len({generate_refresh_token() for _ in range(100)}) == 100


def test_refresh_hash_is_deterministic_sha256() -> None:
    token = generate_refresh_token()
    assert hash_refresh_token(token) == hash_refresh_token(token)
    assert len(hash_refresh_token(token)) == 64


# ── JWT — FR-AUTH-03 ───────────────────────────────────────────────────
def test_access_token_round_trips(settings) -> None:  # type: ignore[no-untyped-def]
    user_id, session_id = uuid.uuid4(), uuid.uuid4()
    token, expires_at = create_access_token(
        settings, user_id=user_id, roles=["STUDENT"], session_id=session_id
    )
    claims = decode_access_token(settings, token)

    assert claims["sub"] == str(user_id)
    assert claims["sid"] == str(session_id)
    assert claims["roles"] == ["STUDENT"]
    assert claims["typ"] == "access"
    assert "jti" in claims
    assert expires_at.tzinfo is not None


def test_expired_access_token_is_rejected(settings) -> None:  # type: ignore[no-untyped-def]
    token, _ = create_access_token(
        settings,
        user_id=uuid.uuid4(),
        roles=[],
        session_id=uuid.uuid4(),
        expires_in=timedelta(seconds=-10),
    )
    with pytest.raises(TokenExpired):
        decode_access_token(settings, token)


def test_token_signed_with_other_key_is_rejected(settings) -> None:  # type: ignore[no-untyped-def]
    forged = jwt.encode(
        {"sub": str(uuid.uuid4()), "jti": "x", "exp": 9_999_999_999, "typ": "access"},
        "a-different-secret-entirely-but-long-enough-for-hs256",
        algorithm="HS256",
    )
    with pytest.raises(InvalidToken):
        decode_access_token(settings, forged)


def test_token_without_required_claims_is_rejected(settings) -> None:  # type: ignore[no-untyped-def]
    incomplete = jwt.encode(
        {"exp": 9_999_999_999, "typ": "access"},
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    with pytest.raises(InvalidToken):
        decode_access_token(settings, incomplete)


def test_impersonation_token_lifetime_is_capped(settings) -> None:  # type: ignore[no-untyped-def]
    """§6.5 — عمر توکن جعل هویت حداکثر ۳۰ دقیقه است."""
    _, expires_at = create_access_token(
        settings,
        user_id=uuid.uuid4(),
        roles=["STUDENT"],
        session_id=uuid.uuid4(),
        act_as=uuid.uuid4(),
        expires_in=timedelta(hours=8),
    )
    from datetime import UTC, datetime

    assert expires_at - datetime.now(UTC) <= timedelta(minutes=30, seconds=1)


# ── پوشاندن اطلاعات تماس — NFR-01 ──────────────────────────────────────
def test_mobile_is_masked() -> None:
    assert mask_mobile("09121234567") == "0912***4567"


def test_email_is_masked() -> None:
    assert mask_email("maryam@example.com") == "m***m@example.com"
    assert mask_email("ab@example.com") == "a***@example.com"


def test_masking_handles_missing_values() -> None:
    assert mask_mobile(None) is None
    assert mask_email(None) is None
