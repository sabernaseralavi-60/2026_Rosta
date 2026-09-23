"""سرویس توکن — FR-AUTH-03: چرخش اجباری و تشخیص سرقت.

مدل خانواده:

    ورود  ──► T1 (family F)
                │ refresh
                ▼
              T2 (family F, parent T1)   ← T1 باطل می‌شود
                │ refresh
                ▼
              T3 (family F, parent T2)

اگر T1 دوباره استفاده شود، یعنی یا مهاجم آن را دزدیده یا کاربر واقعی
قربانی شده است. در هر دو حالت **کل خانوادهٔ F** باطل می‌شود؛ تشخیص اینکه
کدام طرف مهاجم است ممکن نیست، پس هر دو باید دوباره وارد شوند.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import CursorResult, delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from silp.core.config import Settings
from silp.core.exceptions import InvalidToken, TokenExpired, TokenReuseDetected
from silp.core.logging import get_logger
from silp.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_refresh_token,
)
from silp.models.identity import RefreshToken
from silp.services import events

log = get_logger("silp.token")

REVOKED_ROTATED = "ROTATED"
REVOKED_LOGOUT = "LOGOUT"
REVOKED_REUSE = "REUSE_DETECTED"
REVOKED_MANUAL = "SESSION_REVOKED"
REVOKED_ROLE_CHANGE = "ROLE_CHANGED"

# چرخش توکن باید نقش‌های **فعلی** را بگیرد، نه آنچه هنگام ورود بود.
# اگر نقشی از کاربر گرفته شده، توکن تازه نباید آن را حمل کند.
RoleLoader = Callable[[uuid.UUID], Awaitable[list[str]]]


def _affected(result: Any) -> int:
    """تعداد ردیف‌های تغییرکرده.

    `Session.execute` در تایپ‌ها `Result` برمی‌گرداند ولی برای UPDATE و
    DELETE در عمل `CursorResult` است که `rowcount` دارد.
    """
    if isinstance(result, CursorResult):
        return int(result.rowcount or 0)
    return 0


@dataclass(frozen=True, slots=True)
class TokenPair:
    access_token: str
    refresh_token: str
    token_type: str
    expires_in: int
    session_id: uuid.UUID


class TokenService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings

    # ── صدور ───────────────────────────────────────────────────────────
    async def issue_pair(
        self,
        *,
        user_id: uuid.UUID,
        roles: list[str],
        user_agent: str | None = None,
        ip_address: str | None = None,
        family_id: uuid.UUID | None = None,
        parent_id: uuid.UUID | None = None,
    ) -> TokenPair:
        """صدور جفت توکن. `family_id` تازه یعنی ورود جدید."""
        now = datetime.now(UTC)
        raw_refresh = generate_refresh_token()
        record = RefreshToken(
            user_id=user_id,
            token_hash=hash_refresh_token(raw_refresh),
            family_id=family_id or uuid.uuid4(),
            parent_id=parent_id,
            user_agent=(user_agent or "")[:500] or None,
            ip_address=ip_address,
            expires_at=now + timedelta(days=self.settings.refresh_token_days),
        )
        self.session.add(record)
        await self.session.flush()

        # شناسهٔ رکورد refresh همان شناسهٔ نشست است؛ نشست‌های فعال §5.2
        # با همین شناسه فهرست و قطع می‌شوند.
        access_token, expires_at = create_access_token(
            self.settings,
            user_id=user_id,
            roles=roles,
            session_id=record.id,
        )
        return TokenPair(
            access_token=access_token,
            refresh_token=raw_refresh,
            token_type="Bearer",  # noqa: S106 — نوع طرح، نه راز
            expires_in=int((expires_at - now).total_seconds()),
            session_id=record.id,
        )

    # ── چرخش ───────────────────────────────────────────────────────────
    async def rotate(
        self,
        *,
        raw_refresh: str,
        roles_for: RoleLoader,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> TokenPair:
        """تمدید توکن با چرخش اجباری و تشخیص سرقت."""
        token_hash = hash_refresh_token(raw_refresh)
        record = await self.session.scalar(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )
        if record is None:
            raise InvalidToken

        now = datetime.now(UTC)

        if record.revoked_at is not None:
            # استفادهٔ دوباره از توکن باطل‌شده — کل خانواده می‌سوزد.
            revoked = await self.revoke_family(record.family_id, reason=REVOKED_REUSE)
            log.warning(
                "refresh_token_reuse_detected",
                family_id=str(record.family_id),
                user_id=str(record.user_id),
                revoked_count=revoked,
                previous_reason=record.revoked_reason,
            )
            await events.publish(self.session, events.SessionsRevoked(user_id=record.user_id))
            await self.session.commit()
            raise TokenReuseDetected

        if record.expires_at <= now:
            raise TokenExpired

        # ابطال اتمیک نسخهٔ فعلی. اگر رقابتی رخ دهد و کس دیگری زودتر
        # باطل کرده باشد، این به‌روزرسانی هیچ ردیفی برنمی‌گرداند.
        rotated = await self.session.scalar(
            update(RefreshToken)
            .where(RefreshToken.id == record.id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now, revoked_reason=REVOKED_ROTATED)
            .returning(RefreshToken.id)
        )
        if rotated is None:
            await self.revoke_family(record.family_id, reason=REVOKED_REUSE)
            await self.session.commit()
            raise TokenReuseDetected

        roles = await roles_for(record.user_id)
        pair = await self.issue_pair(
            user_id=record.user_id,
            roles=roles,
            user_agent=user_agent,
            ip_address=ip_address,
            family_id=record.family_id,
            parent_id=record.id,
        )
        await self.session.commit()
        log.info("refresh_rotated", user_id=str(record.user_id), session_id=str(pair.session_id))
        return pair

    # ── ابطال ──────────────────────────────────────────────────────────
    async def revoke(self, *, raw_refresh: str, reason: str = REVOKED_LOGOUT) -> bool:
        """خروج از نشست جاری. خروج از نشستی که وجود ندارد هم موفق است."""
        revoked = await self.session.scalar(
            update(RefreshToken)
            .where(
                RefreshToken.token_hash == hash_refresh_token(raw_refresh),
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=datetime.now(UTC), revoked_reason=reason)
            .returning(RefreshToken.id)
        )
        await self.session.commit()
        return revoked is not None

    async def revoke_session(
        self, *, user_id: uuid.UUID, session_id: uuid.UUID, reason: str = REVOKED_MANUAL
    ) -> bool:
        """قطع یک نشست مشخص — §5.2 `DELETE /auth/sessions/{id}`.

        شرط `user_id` عمدی است: کاربر نباید بتواند نشست دیگری را قطع کند.
        """
        revoked = await self.session.scalar(
            update(RefreshToken)
            .where(
                RefreshToken.id == session_id,
                RefreshToken.user_id == user_id,
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=datetime.now(UTC), revoked_reason=reason)
            .returning(RefreshToken.id)
        )
        await self.session.commit()
        return revoked is not None

    async def revoke_family(self, family_id: uuid.UUID, *, reason: str) -> int:
        """ابطال همهٔ توکن‌های زندهٔ یک خانواده. commit نمی‌کند."""
        result = await self.session.execute(
            update(RefreshToken)
            .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=datetime.now(UTC), revoked_reason=reason)
        )
        return _affected(result)

    async def revoke_all_for_user(self, user_id: uuid.UUID, *, reason: str) -> int:
        """ابطال همهٔ نشست‌های کاربر — تغییر نقش، تعلیق حساب، تغییر رمز."""
        result = await self.session.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=datetime.now(UTC), revoked_reason=reason)
        )
        await self.session.commit()
        return _affected(result)

    # ── فهرست نشست‌ها — §5.2 ───────────────────────────────────────────
    async def active_sessions(self, user_id: uuid.UUID) -> list[RefreshToken]:
        now = datetime.now(UTC)
        result = await self.session.scalars(
            select(RefreshToken)
            .where(
                RefreshToken.user_id == user_id,
                RefreshToken.revoked_at.is_(None),
                RefreshToken.expires_at > now,
            )
            .order_by(RefreshToken.created_at.desc())
        )
        return list(result)

    async def purge_expired(self, *, older_than_days: int = 7) -> int:
        """حذف توکن‌های مدت‌ها منقضی. تاریخچه برای حسابرسی یک هفته می‌ماند."""
        cutoff = datetime.now(UTC) - timedelta(days=older_than_days)
        result = await self.session.execute(
            delete(RefreshToken).where(RefreshToken.expires_at < cutoff)
        )
        await self.session.commit()
        return _affected(result)
