"""ورود دانشجوی درس با موبایل + شمارهٔ دانشجویی — ADR-0035.

سه گام، هر کدام یک تابع:

1. `lookup`   — موبایل و شمارهٔ دانشجویی؛ پاسخ «شما فلانی هستید؟» با نام پوشیده.
2. `confirm`  — تأیید هویت؛ کد شش‌رقمی به **ایمیلِ ثبت‌شده در فهرست** می‌رود.
3. `complete` — کد + رمز تازه؛ حساب ساخته (یا به حساب قبلی وصل) و دانشجو در درس‌ها ثبت‌نام می‌شود.

چرا شمارهٔ دانشجویی رمز نیست: همکلاسی و دفتر آموزش آن را دارند. تنها چیزی که
حساب را می‌دهد، دسترسی به ایمیل دانشگاهی ثبت‌شده در فهرست است. شمارهٔ دانشجویی
فقط «پیدا کردن ردیف» است و متن خامش جایی نمی‌ماند (فقط HMAC).

commit صریح در همین لایه است (قرارداد `db/session.py`)، جز در موفقیتِ `complete`:
آنجا مسیر بلافاصله توکن صادر می‌کند و همان commit همه‌چیز را ثبت می‌کند.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from silp.core import ratelimit
from silp.core.config import Settings
from silp.core.exceptions import (
    EmailUnavailable,
    OTPExpired,
    OTPInvalid,
    OTPTooManyAttempts,
    RateLimited,
    RosterAccountConflict,
    RosterClaimClosed,
    RosterNoEmail,
    RosterNotFound,
    WeakPassword,
)
from silp.core.logging import get_logger
from silp.core.permissions import Role, ScopeType
from silp.core.security import generate_otp, hash_otp, hash_password, mask_email, verify_otp
from silp.domain.identity import roster as rules
from silp.domain.identity.normalize import normalize_mobile
from silp.integrations.messaging import channel_sender
from silp.integrations.messaging.base import OutgoingMessage
from silp.models.education import Course, CourseOffering, Enrollment
from silp.models.identity import User
from silp.models.profile import Profile
from silp.models.roster import RosterClaim, RosterEntry
from silp.services import authz, events
from silp.services.profile_service import ProfileService

log = get_logger("silp.roster")

LOOKUP_IP = ratelimit.Limit("roster:lookup:ip", count=20, window_seconds=3600)
LOOKUP_MOBILE = ratelimit.Limit("roster:lookup:mobile", count=10, window_seconds=3600)
#: سقف مستقل از Redis: اگر Redis نبود، حدس‌زدنِ شمارهٔ دانشجویی آزاد نمی‌شود.
CLAIMS_PER_NUMBER_PER_HOUR = 10
CLAIM_TTL = timedelta(minutes=30)
CODE_TTL = timedelta(minutes=10)
CODE_RESEND_AFTER = timedelta(seconds=60)
MAX_CODE_ATTEMPTS = 5
MAX_CODE_SENDS = 3


@dataclass(frozen=True, slots=True)
class LookupResult:
    claim_id: uuid.UUID
    display_name: str
    has_email: bool


@dataclass(frozen=True, slots=True)
class ConfirmResult:
    cancelled: bool
    masked_email: str | None
    expires_in: int
    resend_after: int


@dataclass(frozen=True, slots=True)
class CompleteResult:
    user: User
    #: نادرست = دانشجوی برگشتی (حساب داشت؛ درس‌های تازه‌ اضافه شد و رمزش عوض شد).
    is_new_user: bool
    courses: list[str]


def _now() -> datetime:
    return datetime.now(UTC)


class RosterService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings

    # ── ۱. پیدا کردن ردیف ──────────────────────────────────────────────
    async def lookup(self, *, mobile: str, student_no: str, ip: str | None) -> LookupResult:
        normalized_mobile = normalize_mobile(mobile)
        number = rules.normalize_student_no(student_no)
        if normalized_mobile is None or number is None:
            # قالب نادرست از «در فهرست نیست» قابل تفکیک نیست — عمدی.
            raise RosterNotFound
        number_hash = rules.digest(number, self.settings.secret_key)

        await self._enforce_lookup_limits(normalized_mobile, number_hash, ip)

        entries = list(
            await self.session.scalars(
                select(RosterEntry)
                .where(RosterEntry.student_no_hash == number_hash)
                .order_by(RosterEntry.created_at, RosterEntry.id)
            )
        )
        if not entries:
            raise RosterNotFound

        email = next((e.email for e in entries if e.email), None)
        claim = RosterClaim(
            student_no_hash=number_hash,
            mobile=normalized_mobile,
            email=email,
            ip_address=ip,
            expires_at=_now() + CLAIM_TTL,
        )
        self.session.add(claim)
        await self.session.commit()
        first = entries[0]
        log.info("roster_lookup_matched", claim_id=str(claim.id), has_email=bool(email))
        return LookupResult(
            claim_id=claim.id,
            display_name=rules.masked_name(first.first_name, first.last_name),
            has_email=bool(email),
        )

    async def _enforce_lookup_limits(self, mobile: str, number_hash: str, ip: str | None) -> None:
        checks = [(LOOKUP_MOBILE, mobile)]
        if ip:
            checks.append((LOOKUP_IP, ip))
        for limit, identity in checks:
            result = await ratelimit.check(limit, identity)
            if not result.allowed:
                raise RateLimited(retry_after=result.retry_after)
        recent = await self.session.scalar(
            select(func.count())
            .select_from(RosterClaim)
            .where(
                RosterClaim.student_no_hash == number_hash,
                RosterClaim.created_at > _now() - timedelta(hours=1),
            )
        )
        if (recent or 0) >= CLAIMS_PER_NUMBER_PER_HOUR:
            raise RateLimited(retry_after=3600)

    # ── ۲. تأیید هویت و ارسال کد ───────────────────────────────────────
    async def confirm(self, *, claim_id: uuid.UUID, accept: bool) -> ConfirmResult:
        claim = await self._open_claim(claim_id, {"AWAITING_CONFIRM", "AWAITING_CODE"})
        if not accept:
            claim.status = "CANCELLED"
            await self.session.commit()
            return ConfirmResult(cancelled=True, masked_email=None, expires_in=0, resend_after=0)
        if not claim.email:
            claim.status = "CANCELLED"
            await self.session.commit()
            raise RosterNoEmail

        await self._resolve_owner(claim)  # پیش از فرستادن ایمیل، تعارض حساب را بگو
        now = _now()
        if claim.status == "AWAITING_CODE" and claim.code_expires_at is not None:
            sent_at = claim.code_expires_at - CODE_TTL
            wait = sent_at + CODE_RESEND_AFTER - now
            if wait > timedelta(0):
                raise RateLimited(retry_after=int(wait.total_seconds()) + 1)
        if claim.code_sends >= MAX_CODE_SENDS:
            raise RateLimited(retry_after=int(CODE_TTL.total_seconds()))

        code = self._code()
        await self._send_code(claim.email, code)

        claim.code_hash = hash_otp(code)
        claim.code_expires_at = now + CODE_TTL
        claim.code_attempts = 0
        claim.code_sends += 1
        claim.status = "AWAITING_CODE"
        await self.session.commit()
        log.info("roster_code_sent", claim_id=str(claim.id), sends=claim.code_sends)
        return ConfirmResult(
            cancelled=False,
            masked_email=mask_email(claim.email),
            expires_in=int(CODE_TTL.total_seconds()),
            resend_after=int(CODE_RESEND_AFTER.total_seconds()),
        )

    def _code(self) -> str:
        """کد ثابت فقط در غیرتولید؛ `_production_hardening` در تولید خالی‌بودنش را الزام می‌کند."""
        if not self.settings.is_production and self.settings.dev_fixed_otp:
            return self.settings.dev_fixed_otp
        return generate_otp(self.settings.otp_length)

    async def _send_code(self, email: str, code: str) -> None:
        sender = channel_sender(self.settings, "EMAIL")
        if sender is None:
            raise EmailUnavailable
        result = await sender.send(
            OutgoingMessage(
                channel="EMAIL",
                recipient=email,
                subject="کد تأیید ورود به سامانهٔ سابِر",
                body=(
                    f"کد تأیید شما: {code}\n"
                    f"این کد {int(CODE_TTL.total_seconds() // 60)} دقیقه اعتبار دارد.\n\n"
                    "اگر شما درخواست ورود نداده‌اید، این نامه را نادیده بگیرید؛ "
                    "بدون این کد کسی به حساب شما وارد نمی‌شود."
                ),
            )
        )
        if not result.delivered:
            log.warning("roster_code_send_failed", error=result.error)
            raise EmailUnavailable

    # ── ۳. کد + رمز تازه ───────────────────────────────────────────────
    async def complete(self, *, claim_id: uuid.UUID, code: str, password: str) -> CompleteResult:
        claim = await self._open_claim(claim_id, {"AWAITING_CODE"})

        problem = rules.password_problem(
            password,
            forbidden_digests={
                claim.student_no_hash,
                rules.digest(claim.mobile, self.settings.secret_key),
            },
            secret=self.settings.secret_key,
        )
        if problem:
            raise WeakPassword(problem)

        now = _now()
        if claim.code_hash is None or claim.code_expires_at is None or claim.code_expires_at <= now:
            raise OTPExpired
        if claim.code_attempts >= MAX_CODE_ATTEMPTS:
            claim.status = "CANCELLED"
            await self.session.commit()
            raise OTPTooManyAttempts
        if not verify_otp(code, claim.code_hash):
            claim.code_attempts += 1
            if claim.code_attempts >= MAX_CODE_ATTEMPTS:
                claim.status = "CANCELLED"
            await self.session.commit()
            raise OTPTooManyAttempts if claim.status == "CANCELLED" else OTPInvalid

        owner = await self._resolve_owner(claim)
        entries = list(
            await self.session.scalars(
                select(RosterEntry)
                .where(RosterEntry.student_no_hash == claim.student_no_hash)
                .with_for_update()
            )
        )
        is_new = owner is None
        user = owner if owner is not None else await self._create_user(claim, entries)
        # دانشجوی برگشتی هم رمز تازه می‌گیرد: دسترسی به ایمیل ثبت‌شده، بازیابی حساب است.
        user.password_hash = hash_password(password)

        courses = await self._attach(user, entries, claim, now)
        claim.status = "DONE"
        claim.code_hash = None
        await self.session.flush()
        if is_new:
            await events.publish(self.session, events.UserRegistered(user_id=user.id))
        log.info("roster_claim_done", user_id=str(user.id), new=is_new, courses=len(courses))
        return CompleteResult(user=user, is_new_user=is_new, courses=courses)

    # ── داخلی ──────────────────────────────────────────────────────────
    async def _open_claim(self, claim_id: uuid.UUID, allowed: set[str]) -> RosterClaim:
        claim = await self.session.scalar(
            select(RosterClaim).where(RosterClaim.id == claim_id).with_for_update()
        )
        if claim is None or claim.status not in allowed or claim.expires_at <= _now():
            raise RosterClaimClosed
        return claim

    async def _resolve_owner(self, claim: RosterClaim) -> User | None:
        """حسابِ صاحبِ این هویت، یا None اگر باید حساب تازه ساخت؛ تعارض را خطا می‌دهد.

        * ردیفی از همین شماره پیش‌تر به حسابی وصل شده ⇒ دانشجوی برگشتی. فقط اگر همان
          موبایل باشد (وگرنه کسی که کد ایمیل دارد، حساب را به شمارهٔ دیگری می‌برد).
        * موبایل مالِ حسابی است که به این ردیف وصل نیست ⇒ تعارض. ما نمی‌دانیم آن حساب
          مالِ همین آدم است؛ دست نمی‌زنیم.
        * ایمیل مالِ حساب دیگری است ⇒ تعارض.
        """
        linked = await self.session.scalar(
            select(User)
            .join(RosterEntry, RosterEntry.user_id == User.id)
            .where(RosterEntry.student_no_hash == claim.student_no_hash, User.deleted_at.is_(None))
            .limit(1)
        )
        by_mobile = await self.session.scalar(
            select(User).where(User.mobile == claim.mobile, User.deleted_at.is_(None))
        )
        if linked is not None:
            if linked.mobile != claim.mobile:
                raise RosterAccountConflict
            if linked.status != "ACTIVE":
                raise RosterAccountConflict
            return linked
        if by_mobile is not None:
            raise RosterAccountConflict
        by_email = await self.session.scalar(
            select(User.id).where(User.email == claim.email, User.deleted_at.is_(None))
        )
        if by_email is not None:
            raise RosterAccountConflict
        return None

    async def _create_user(self, claim: RosterClaim, entries: list[RosterEntry]) -> User:
        now = _now()
        user = User(mobile=claim.mobile, email=claim.email, email_verified_at=now)
        self.session.add(user)
        await self.session.flush()
        first = entries[0]
        self.session.add(
            Profile(user_id=user.id, first_name=first.first_name, last_name=first.last_name)
        )
        await self.session.flush()
        await ProfileService(self.session).ensure_username(
            user.id, first.first_name, first.last_name
        )
        await authz.grant_role(
            self.session, user_id=user.id, role=Role.STUDENT, scope_type=ScopeType.GLOBAL
        )
        return user

    async def _attach(
        self, user: User, entries: list[RosterEntry], claim: RosterClaim, now: datetime
    ) -> list[str]:
        """ردیف‌ها را به کاربر می‌بندد و او را در همهٔ درس‌های فهرست ثبت‌نام می‌کند.

        ظرفیت و تأیید ثبت‌نام نادیده گرفته می‌شود: فهرست را استاد خودش ساخته و
        حاضربودنِ اسم در آن، خودش تأیید است.
        """
        titles: list[str] = []
        for entry in entries:
            if entry.user_id is None:
                entry.user_id = user.id
                entry.claimed_at = now
            enrollment = await self.session.scalar(
                select(Enrollment).where(
                    Enrollment.offering_id == entry.offering_id,
                    Enrollment.student_id == user.id,
                )
            )
            if enrollment is None:
                self.session.add(
                    Enrollment(
                        offering_id=entry.offering_id,
                        student_id=user.id,
                        status="ACTIVE",
                        decided_at=now,
                    )
                )
            elif enrollment.status not in ("ACTIVE", "COMPLETED"):
                enrollment.status = "ACTIVE"
                enrollment.enrolled_at = now
                enrollment.decided_at = now
            title = await self.session.scalar(
                select(Course.title_fa)
                .join(CourseOffering, CourseOffering.course_id == Course.id)
                .where(CourseOffering.id == entry.offering_id)
            )
            if title:
                titles.append(title)
        return titles
