"""سرویس OTP — FR-AUTH-01.

معیارهای پذیرش که اینجا اعمال می‌شوند:

* کد شش‌رقمی با اعتبار ۱۲۰ ثانیه، ذخیره‌شده به‌صورت bcrypt (نه متن ساده).
* بیش از ۳ درخواست در ۱۰ دقیقه برای یک شماره ⇒ ۴۲۹ با زمان انتظار.
* سه پاسخ اشتباه متوالی ⇒ چالش باطل و کد جدید لازم است.
* در محیط توسعه، OTP در لاگ چاپ و پیامک ارسال نمی‌شود.

نکتهٔ همزمانی: افزایش `attempts` با یک `UPDATE ... RETURNING` شرطی انجام
می‌شود، نه خواندن-سپس-نوشتن. دو درخواست هم‌زمان نمی‌توانند شمارنده را دور بزنند.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy import CursorResult, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from silp.core import ratelimit
from silp.core.config import Settings
from silp.core.exceptions import (
    InvalidDestination,
    OTPExpired,
    OTPInvalid,
    OTPRateLimited,
    OTPTooManyAttempts,
)
from silp.core.logging import get_logger
from silp.core.security import generate_otp, hash_otp, mask_email, mask_mobile, verify_otp
from silp.domain.identity.normalize import Channel, normalize_destination
from silp.integrations.sms import SMSSender
from silp.models.identity import OTPChallenge

log = get_logger("silp.otp")

Purpose = Literal["LOGIN", "VERIFY_EMAIL", "VERIFY_MOBILE", "RESET_PASSWORD"]


@dataclass(frozen=True, slots=True)
class ChallengeIssued:
    challenge_id: str
    expires_in: int
    resend_after: int
    masked_destination: str


def mask(destination: str, channel: Channel) -> str:
    masked = mask_mobile(destination) if channel == "SMS" else mask_email(destination)
    return masked or destination


def _identity(destination: str) -> str:
    """کلید محدودیت نرخ. مقصد هش می‌شود تا شمارهٔ خام در Redis ننشیند."""
    return hashlib.sha256(destination.encode("utf-8")).hexdigest()[:32]


class OTPService:
    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        sms: SMSSender,
    ) -> None:
        self.session = session
        self.settings = settings
        self.sms = sms

    # ── درخواست کد ─────────────────────────────────────────────────────
    async def request(
        self,
        *,
        raw_destination: str,
        channel: Channel,
        purpose: Purpose = "LOGIN",
        ip_address: str | None = None,
    ) -> ChallengeIssued:
        destination = normalize_destination(raw_destination, channel)
        if destination is None:
            raise InvalidDestination

        await self._enforce_rate_limits(destination, ip_address)

        code = self._code_for(destination)
        now = datetime.now(UTC)
        expires_at = now + timedelta(seconds=self.settings.otp_ttl_seconds)

        # چالش‌های باز قبلی برای همین مقصد و هدف باطل می‌شوند، وگرنه کد
        # قدیمی تا انقضا معتبر می‌ماند و پنجرهٔ حمله را باز نگه می‌دارد.
        await self._invalidate_open_challenges(destination, purpose)

        challenge = OTPChallenge(
            channel=channel,
            destination=destination,
            code_hash=hash_otp(code),
            purpose=purpose,
            max_attempts=self.settings.otp_max_attempts,
            expires_at=expires_at,
            ip_address=ip_address,
        )
        self.session.add(challenge)
        await self.session.flush()

        await self._deliver(destination, code, channel)
        await self.session.commit()

        log.info(
            "otp_requested",
            challenge_id=str(challenge.id),
            channel=channel,
            purpose=purpose,
            destination=mask(destination, channel),
        )
        return ChallengeIssued(
            challenge_id=str(challenge.id),
            expires_in=self.settings.otp_ttl_seconds,
            resend_after=self.settings.otp_resend_after_seconds,
            masked_destination=mask(destination, channel),
        )

    # ── تأیید کد ───────────────────────────────────────────────────────
    async def verify(self, *, challenge_id: str, code: str) -> OTPChallenge:
        """در موفقیت، چالش مصرف‌شده را برمی‌گرداند. در شکست، خطا می‌دهد.

        ترتیب بررسی‌ها عمدی است: اول انقضا، بعد سقف تلاش، بعد خود کد.
        کاربری که کدش منقضی شده نباید سهمیهٔ تلاشش مصرف شود.
        """
        challenge = await self._load(challenge_id)
        now = datetime.now(UTC)

        if challenge.consumed_at is not None:
            # چالش مصرف‌شده مثل کد نادرست پاسخ می‌گیرد تا اطلاعاتی لو نرود.
            raise OTPInvalid
        if challenge.expires_at <= now:
            raise OTPExpired
        if challenge.attempts >= challenge.max_attempts:
            raise OTPTooManyAttempts

        if not verify_otp(code, challenge.code_hash):
            attempts = await self._record_failed_attempt(challenge)
            log.info(
                "otp_failed",
                challenge_id=challenge_id,
                attempts=attempts,
                max_attempts=challenge.max_attempts,
            )
            if attempts >= challenge.max_attempts:
                raise OTPTooManyAttempts
            raise OTPInvalid

        consumed = await self._consume(challenge, now)
        if consumed is None:
            # درخواست هم‌زمان دیگری زودتر همین چالش را مصرف کرده است.
            raise OTPInvalid

        log.info("otp_verified", challenge_id=challenge_id, purpose=challenge.purpose)
        return challenge

    # ── داخلی ──────────────────────────────────────────────────────────
    def _code_for(self, destination: str) -> str:
        """کد ثابت در همهٔ محیط‌های غیرتولیدی — §14.8.

        شرط «غیرتولیدی» است، نه «توسعه»: تست یکپارچه هم باید کد را از پیش
        بداند، وگرنه هر تست ورود باید از آداپتور پیامک بخواندش. نشت به
        تولید ممکن نیست، چون `_production_hardening` در §12.7 خالی بودن
        `DEV_FIXED_OTP` را در تولید الزامی کرده است.
        """
        if not self.settings.is_production and self.settings.dev_fixed_otp:
            return self.settings.dev_fixed_otp
        return generate_otp(self.settings.otp_length)

    async def _enforce_rate_limits(self, destination: str, ip_address: str | None) -> None:
        dest_limit = ratelimit.otp_per_destination(self.settings.otp_per_destination_per_10min)
        result = await ratelimit.check(dest_limit, _identity(destination))
        if not result.allowed:
            raise OTPRateLimited(retry_after=result.retry_after)

        if ip_address:
            ip_limit = ratelimit.otp_per_ip(self.settings.otp_per_ip_per_hour)
            ip_result = await ratelimit.check(ip_limit, ip_address)
            if not ip_result.allowed:
                raise OTPRateLimited(retry_after=ip_result.retry_after)

    async def _invalidate_open_challenges(self, destination: str, purpose: Purpose) -> None:
        await self.session.execute(
            update(OTPChallenge)
            .where(
                OTPChallenge.destination == destination,
                OTPChallenge.purpose == purpose,
                OTPChallenge.consumed_at.is_(None),
            )
            .values(consumed_at=text("now()"))
        )

    async def _deliver(self, destination: str, code: str, channel: Channel) -> None:
        if channel == "SMS":
            await self.sms.send_otp(destination, code, template=self.settings.sms_otp_template)
        else:
            # آداپتور ایمیل در M6-05 می‌آید. تا آن زمان در توسعه لاگ کافی است.
            log.warning(
                "otp_email_channel_not_implemented",
                destination=mask(destination, channel),
                dev_otp_code=code if not self.settings.is_production else None,
            )

    async def _load(self, challenge_id: str) -> OTPChallenge:
        challenge = await self.session.scalar(
            select(OTPChallenge).where(OTPChallenge.id == challenge_id)
        )
        if challenge is None:
            # شناسهٔ ناموجود از کد نادرست قابل تفکیک نیست — عمدی.
            raise OTPInvalid
        return challenge

    async def _record_failed_attempt(self, challenge: OTPChallenge) -> int:
        """افزایش اتمیک شمارنده. مقدار جدید برگردانده می‌شود."""
        attempts = await self.session.scalar(
            update(OTPChallenge)
            .where(
                OTPChallenge.id == challenge.id,
                OTPChallenge.attempts < OTPChallenge.max_attempts,
            )
            .values(attempts=OTPChallenge.attempts + 1)
            .returning(OTPChallenge.attempts)
        )
        await self.session.commit()
        return int(attempts) if attempts is not None else challenge.max_attempts

    async def _consume(self, challenge: OTPChallenge, now: datetime) -> datetime | None:
        """مصرف اتمیک. اگر کس دیگری زودتر مصرف کرده باشد None برمی‌گردد."""
        consumed_at = await self.session.scalar(
            update(OTPChallenge)
            .where(
                OTPChallenge.id == challenge.id,
                OTPChallenge.consumed_at.is_(None),
                OTPChallenge.expires_at > now,
            )
            .values(consumed_at=now)
            .returning(OTPChallenge.consumed_at)
        )
        if consumed_at is not None:
            challenge.consumed_at = consumed_at
        return consumed_at

    # ── پاک‌سازی — NFR-01: حذف فیزیکی پس از ۲۴ ساعت ────────────────────
    async def purge_expired(self, *, older_than_hours: int = 24) -> int:
        cutoff = datetime.now(UTC) - timedelta(hours=older_than_hours)
        result = await self.session.execute(
            text("DELETE FROM otp_challenges WHERE created_at < :cutoff"),
            {"cutoff": cutoff},
        )
        await self.session.commit()
        return int(result.rowcount or 0) if isinstance(result, CursorResult) else 0
