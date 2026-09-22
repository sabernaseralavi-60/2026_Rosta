"""سرویس احراز هویت — FR-AUTH-01/02/03، گردش‌کار §7.1.

این لایه OTP، توکن و ساخت کاربر را به هم می‌دوزد. هیچ منطق رمزنگاری یا
دسترسی مستقیم به HTTP اینجا نیست؛ فقط قواعد کسب‌وکار.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from silp.core import ratelimit
from silp.core.config import Settings
from silp.core.exceptions import AccountSuspended, Unauthenticated
from silp.core.logging import get_logger
from silp.core.permissions import Role, ScopeType
from silp.core.security import verify_password
from silp.domain.identity.normalize import (
    Channel,
    normalize_email,
    normalize_mobile,
)
from silp.domain.identity.onboarding import Onboarding, ProfileSnapshot, resolve
from silp.models.identity import OTPChallenge, User
from silp.models.profile import Profile
from silp.services import authz
from silp.services.otp_service import ChallengeIssued, OTPService, Purpose
from silp.services.token_service import TokenPair, TokenService

log = get_logger("silp.auth")

# FR-AUTH-02 — قفل نرم پس از ۵ تلاش ناموفق در ۱۵ دقیقه.
PASSWORD_ATTEMPT_LIMIT = ratelimit.Limit("login:pw", count=5, window_seconds=900)

# پیام یکسان برای «کاربر نیست» و «رمز غلط» — NFR-02 · Enumeration.
CREDENTIALS_MESSAGE = "نام کاربری یا رمز عبور نادرست است."


@dataclass(frozen=True, slots=True)
class AuthenticatedUser:
    """خروجی ورود موفق — آنچه لایهٔ مسیر برای ساخت پاسخ لازم دارد."""

    user: User
    tokens: TokenPair
    onboarding: Onboarding
    roles: list[str]
    is_new_user: bool


class AuthService:
    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        otp: OTPService,
        tokens: TokenService,
    ) -> None:
        self.session = session
        self.settings = settings
        self.otp = otp
        self.tokens = tokens

    # ── ورود با OTP — FR-AUTH-01 ───────────────────────────────────────
    async def verify_otp_and_login(
        self,
        *,
        challenge_id: str,
        code: str,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> AuthenticatedUser:
        """تأیید کد، ساخت حساب در صورت نیاز، و صدور جفت توکن."""
        challenge = await self.otp.verify(challenge_id=challenge_id, code=code)

        user, is_new = await self._get_or_create_user(challenge)
        if user.status != "ACTIVE":
            raise AccountSuspended

        await self._mark_verified(user, challenge)
        return await self._complete_login(
            user,
            is_new_user=is_new,
            user_agent=user_agent,
            ip_address=ip_address,
        )

    # ── ورود با رمز — FR-AUTH-02 ───────────────────────────────────────
    async def login_with_password(
        self,
        *,
        identifier: str,
        password: str,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> AuthenticatedUser:
        """ورود با (موبایل یا ایمیل) + رمز عبور.

        خطا هرگز افشا نمی‌کند که کاربر وجود دارد یا نه، و در هر دو حالت
        یک بررسی argon2 انجام می‌شود تا زمان پاسخ یکنواخت بماند.
        """
        normalized = normalize_mobile(identifier) or normalize_email(identifier)
        limit_key = normalized or identifier[:64]

        attempt = await ratelimit.check(PASSWORD_ATTEMPT_LIMIT, limit_key)
        if not attempt.allowed:
            raise Unauthenticated(
                "حساب شما موقتاً قفل شده است. چند دقیقه بعد دوباره تلاش کنید.",
                code="ACCOUNT_LOCKED",
                headers={"Retry-After": str(attempt.retry_after)},
            )

        user = await self._find_by_identifier(normalized) if normalized else None
        password_hash = user.password_hash if user else None

        if not verify_password(password, password_hash) or user is None:
            log.info("password_login_failed", identifier_kind=_kind(normalized))
            raise Unauthenticated(CREDENTIALS_MESSAGE, code="INVALID_CREDENTIALS")

        if user.status != "ACTIVE":
            raise AccountSuspended

        # ورود موفق، سهمیهٔ تلاش پاک می‌شود.
        await ratelimit.reset(PASSWORD_ATTEMPT_LIMIT, limit_key)
        return await self._complete_login(
            user, is_new_user=False, user_agent=user_agent, ip_address=ip_address
        )

    # ── تمدید توکن — FR-AUTH-03 ────────────────────────────────────────
    async def refresh(
        self,
        *,
        raw_refresh: str,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> TokenPair:
        async def roles_for(user_id: uuid.UUID) -> list[str]:
            return await authz.role_codes(self.session, user_id)

        return await self.tokens.rotate(
            raw_refresh=raw_refresh,
            roles_for=roles_for,
            user_agent=user_agent,
            ip_address=ip_address,
        )

    async def request_otp(
        self,
        *,
        destination: str,
        channel: Channel,
        purpose: Purpose = "LOGIN",
        ip_address: str | None = None,
    ) -> ChallengeIssued:
        return await self.otp.request(
            raw_destination=destination,
            channel=channel,
            purpose=purpose,
            ip_address=ip_address,
        )

    # ── داخلی ──────────────────────────────────────────────────────────
    async def _find_by_identifier(self, normalized: str) -> User | None:
        column = User.mobile if normalized.startswith("09") else User.email
        user: User | None = await self.session.scalar(
            select(User).where(column == normalized, User.deleted_at.is_(None))
        )
        return user

    async def _get_or_create_user(self, challenge: OTPChallenge) -> tuple[User, bool]:
        """کاربر موجود را برمی‌گرداند یا می‌سازد و نقش STUDENT می‌دهد."""
        destination = challenge.destination
        is_sms = challenge.channel == "SMS"
        column = User.mobile if is_sms else User.email

        user = await self.session.scalar(
            select(User).where(column == destination, User.deleted_at.is_(None))
        )
        if user is not None:
            return user, False

        user = User(
            mobile=destination if is_sms else None,
            email=destination if not is_sms else None,
        )
        self.session.add(user)
        await self.session.flush()

        # FR-AUTH-01 — نقش پیش‌فرض پس از ثبت‌نام.
        await authz.grant_role(
            self.session,
            user_id=user.id,
            role=Role.STUDENT,
            scope_type=ScopeType.GLOBAL,
        )
        log.info("user_registered", user_id=str(user.id), channel=challenge.channel)
        return user, True

    async def _mark_verified(self, user: User, challenge: OTPChallenge) -> None:
        """تأیید موفق OTP یعنی مالکیت آن مقصد ثابت شده است."""
        now = datetime.now(UTC)
        if challenge.channel == "SMS" and user.mobile_verified_at is None:
            user.mobile_verified_at = now
        elif challenge.channel == "EMAIL" and user.email_verified_at is None:
            user.email_verified_at = now

    async def _complete_login(
        self,
        user: User,
        *,
        is_new_user: bool,
        user_agent: str | None,
        ip_address: str | None,
    ) -> AuthenticatedUser:
        user.last_login_at = datetime.now(UTC)
        roles = await authz.role_codes(self.session, user.id)

        pair = await self.tokens.issue_pair(
            user_id=user.id,
            roles=roles,
            user_agent=user_agent,
            ip_address=ip_address,
        )
        await self.session.commit()

        log.info(
            "login_succeeded",
            user_id=str(user.id),
            session_id=str(pair.session_id),
            is_new_user=is_new_user,
        )
        return AuthenticatedUser(
            user=user,
            tokens=pair,
            onboarding=await self.onboarding_for(user),
            roles=roles,
            is_new_user=is_new_user,
        )

    async def onboarding_for(self, user: User) -> Onboarding:
        """وضعیت ورود اولیه — §7.1.

        تصمیم با سرور است، نه کلاینت: نیمرخ خوانده می‌شود و `resolve`
        منطق §7.1 را اعمال می‌کند. کاربری که هنوز نیمرخ ندارد
        `BASIC_INFO_REQUIRED` می‌گیرد و به `/onboarding/basic` می‌رود.
        """
        profile = await self.session.get(Profile, user.id)
        snapshot: ProfileSnapshot | None = (
            None
            if profile is None
            else ProfileSnapshot(
                first_name=profile.first_name,
                last_name=profile.last_name,
                survey_completed_steps=profile.survey_completed_steps,
            )
        )
        return resolve(snapshot)


def _kind(normalized: str | None) -> str:
    if normalized is None:
        return "unknown"
    return "mobile" if normalized.startswith("09") else "email"
