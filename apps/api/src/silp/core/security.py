"""عملیات رمزنگاری — NFR-01، NFR-02، FR-AUTH-01/02/03.

| داده         | الگوریتم                                          |
|--------------|---------------------------------------------------|
| رمز عبور     | argon2id (time=3, memory=64MiB, parallelism=4)     |
| OTP          | bcrypt                                             |
| refresh token| sha256 (توکن خودش ۲۵۶ بیت آنتروپی دارد)            |

هیچ مقایسهٔ حساسی با `==` انجام نمی‌شود؛ همه با `compare_digest` یا تابع
verify کتابخانه که خودش زمان‌ثابت است.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import bcrypt
import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from silp.core.config import Settings
from silp.core.exceptions import InvalidToken, TokenExpired

# ── رمز عبور — argon2id، پارامترهای NFR-01 ─────────────────────────────
_password_hasher = PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=4,
    hash_len=32,
    salt_len=16,
)


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    """تأیید رمز. در برابر کاربر ناموجود هم یک هش ساختگی بررسی می‌شود تا
    زمان پاسخ یکنواخت بماند و وجود حساب افشا نشود (NFR-02 · Enumeration)."""
    if not password_hash:
        _password_hasher.hash(password)  # مصرف زمان معادل
        return False
    try:
        return _password_hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    try:
        return _password_hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True


# ── OTP — bcrypt، FR-AUTH-01 ───────────────────────────────────────────
def generate_otp(length: int = 6) -> str:
    """کد عددی با آنتروپی رمزنگاری‌شده. صفرهای ابتدایی حفظ می‌شوند."""
    upper = 10**length
    return str(secrets.randbelow(upper)).zfill(length)


def hash_otp(code: str) -> str:
    return bcrypt.hashpw(code.encode("utf-8"), bcrypt.gensalt(rounds=10)).decode("utf-8")


def verify_otp(code: str, code_hash: str) -> bool:
    try:
        return bcrypt.checkpw(code.encode("utf-8"), code_hash.encode("utf-8"))
    except ValueError:
        return False


# ── Refresh token — sha256، FR-AUTH-03 ─────────────────────────────────
REFRESH_TOKEN_BYTES = 32  # ۲۵۶ بیت


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(REFRESH_TOKEN_BYTES)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def tokens_match(a: str, b: str) -> bool:
    return hmac.compare_digest(a, b)


# ── JWT — access token، FR-AUTH-03 ─────────────────────────────────────
TokenType = Literal["access", "impersonation"]


def create_access_token(
    settings: Settings,
    *,
    user_id: uuid.UUID,
    roles: list[str],
    session_id: uuid.UUID,
    act_as: uuid.UUID | None = None,
    expires_in: timedelta | None = None,
) -> tuple[str, datetime]:
    """صدور access token. مقدار بازگشتی: (توکن، زمان انقضا).

    `act_as` فقط برای جعل هویت پشتیبانی است (§6.5) و عمر کوتاه‌تری می‌گیرد.
    """
    now = datetime.now(UTC)
    lifetime = expires_in or timedelta(minutes=settings.access_token_minutes)
    if act_as is not None:
        lifetime = min(lifetime, timedelta(minutes=30))
    expires_at = now + lifetime

    payload: dict[str, Any] = {
        "sub": str(user_id),
        "roles": roles,
        "sid": str(session_id),
        "jti": str(uuid.uuid4()),
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
        "typ": "access",
    }
    if act_as is not None:
        payload["act_as"] = str(act_as)

    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return token, expires_at


def decode_access_token(settings: Settings, token: str) -> dict[str, Any]:
    """رمزگشایی و اعتبارسنجی. خطای صریح برمی‌گرداند، نه None."""
    try:
        claims: dict[str, Any] = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "sub", "jti"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenExpired from exc
    except jwt.InvalidTokenError as exc:
        raise InvalidToken from exc

    if claims.get("typ") != "access":
        raise InvalidToken
    return claims


# ── پوشاندن داده‌های تماس — NFR-01 ─────────────────────────────────────
def mask_mobile(mobile: str | None) -> str | None:
    """`09121234567` → `0912***4567`"""
    if not mobile or len(mobile) < 8:
        return mobile
    return f"{mobile[:4]}***{mobile[-4:]}"


def mask_email(email: str | None) -> str | None:
    """`maryam@example.com` → `m***m@example.com`"""
    if not email or "@" not in email:
        return email
    local, _, domain = email.partition("@")
    if len(local) <= 2:
        return f"{local[0]}***@{domain}"
    return f"{local[0]}***{local[-1]}@{domain}"
