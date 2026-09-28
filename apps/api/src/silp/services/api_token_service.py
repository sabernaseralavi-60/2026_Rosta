"""ساخت، تأیید و ابطال توکن دسترسی برنامه‌ای — ADR-0031.

* توکن `silp_pat_<۴۳ نویسه>` است و **فقط یک‌بار** برمی‌گردد؛ دیتابیس `sha256` دارد.
* `authenticate` هیچ‌وقت نمی‌گوید *چرا* رد شد (ناشناخته / ابطال‌شده / منقضی): هر سه
  یک `InvalidToken` است تا کسی توکن‌های باطل را از نادرست تشخیص ندهد.
* توکن سقفِ مجوز را پایین می‌آورد، نه بالا: مجوزِ لحظهٔ صاحب‌توکن هم لازم است.
  ادمینی که نقشش گرفته شد، توکنش همان لحظه بی‌اثر می‌شود.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from silp.core.exceptions import InvalidToken, PermissionDenied, ValidationFailed
from silp.core.permissions import CurrentUser
from silp.models.api_token import TOKEN_PREFIX, TOKEN_SCOPES, ApiToken
from silp.models.identity import User
from silp.services import authz

#: هر بار `last_used_at` را نمی‌نویسیم: یک `push` چند درخواست است و هر نوشتن یک commit.
LAST_USED_GRANULARITY = timedelta(minutes=5)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_token() -> str:
    return TOKEN_PREFIX + secrets.token_urlsafe(32)


class ApiTokenService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        user_id: uuid.UUID,
        *,
        name: str,
        scopes: list[str],
        expires_in_days: int | None = None,
    ) -> tuple[ApiToken, str]:
        """ردیف و متن توکن. متن را جای دیگری نمی‌توان دوباره دید."""
        name = name.strip()
        if not 1 <= len(name) <= 80:
            raise ValidationFailed("نام توکن ۱ تا ۸۰ نویسه باشد.")
        unknown = sorted(set(scopes) - set(TOKEN_SCOPES))
        if not scopes or unknown:
            raise ValidationFailed(
                f"دامنهٔ نامعتبر: {', '.join(unknown) or '—'}. مجاز: {', '.join(TOKEN_SCOPES)}"
            )
        user = await self.session.get(User, user_id)
        if user is None or not user.is_active:
            raise ValidationFailed("کاربر پیدا نشد یا فعال نیست.")
        raw = generate_token()
        row = ApiToken(
            user_id=user_id,
            name=name,
            token_hash=hash_token(raw),
            token_hint=raw[: len(TOKEN_PREFIX) + 4],
            scopes=sorted(set(scopes)),
            expires_at=(datetime.now(UTC) + timedelta(days=expires_in_days))
            if expires_in_days
            else None,
        )
        self.session.add(row)
        await self.session.flush()
        return row, raw

    async def list_for(self, user_id: uuid.UUID) -> list[ApiToken]:
        stmt = select(ApiToken).where(ApiToken.user_id == user_id).order_by(ApiToken.id.desc())
        return list(await self.session.scalars(stmt))

    async def revoke(self, token_id: uuid.UUID, *, user_id: uuid.UUID) -> bool:
        row = await self.session.get(ApiToken, token_id)
        if row is None or row.user_id != user_id:
            return False
        if row.revoked_at is None:
            row.revoked_at = datetime.now(UTC)
        await self.session.flush()
        return True

    async def authenticate(self, raw: str, *, scope: str) -> tuple[ApiToken, CurrentUser]:
        """توکن ← صاحبش. هر شکستی `InvalidToken`؛ دامنهٔ کم `PermissionDenied`."""
        if not raw.startswith(TOKEN_PREFIX):
            raise InvalidToken
        row = await self.session.scalar(
            select(ApiToken).where(ApiToken.token_hash == hash_token(raw))
        )
        now = datetime.now(UTC)
        if (
            row is None
            or row.revoked_at is not None
            or (row.expires_at is not None and row.expires_at <= now)
        ):
            raise InvalidToken
        user = await self.session.get(User, row.user_id)
        if user is None or user.deleted_at is not None or not user.is_active:
            raise InvalidToken
        if scope not in row.scopes:
            raise PermissionDenied("این توکن اجازهٔ این کار را ندارد.", code="TOKEN_SCOPE")
        if row.last_used_at is None or now - row.last_used_at >= LAST_USED_GRANULARITY:
            row.last_used_at = now
        grants = await authz.get_grants(self.session, user.id)
        return row, CurrentUser(id=user.id, session_id=row.id, grants=grants)


__all__ = ["ApiTokenService", "generate_token", "hash_token"]
