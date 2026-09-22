"""حل نقش‌ها و بررسی مجوز با پشتوانهٔ دیتابیس — §6.4.

کش نقش در Redis با TTL ۶۰ ثانیه. تغییر نقش، کش را فوراً باطل می‌کند.
در نبود Redis همه چیز کار می‌کند، فقط هر درخواست یک کوئری بیشتر می‌زند
(NFR-11: کش اختیاری است، نه حیاتی).
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from silp.core.logging import get_logger
from silp.core.permissions import (
    CurrentUser,
    Permission,
    Role,
    RoleGrant,
    ScopeType,
)
from silp.core.redis import ROLES_TTL_SECONDS, get_redis, key_roles
from silp.models.identity import UserRole

log = get_logger("silp.authz")


async def load_grants(session: AsyncSession, user_id: uuid.UUID) -> tuple[RoleGrant, ...]:
    """خواندن اعطاهای نقش فعال از دیتابیس — بدون کش."""
    now = datetime.now(UTC)
    rows = await session.scalars(
        select(UserRole).where(
            UserRole.user_id == user_id,
            (UserRole.expires_at.is_(None)) | (UserRole.expires_at > now),
        )
    )
    grants: list[RoleGrant] = []
    for row in rows:
        if row.role_code not in Role.__members__:
            # نقشی که در کد نیست یعنی دیتابیس از کد جلوتر است — نادیده
            # گرفته می‌شود، ولی بی‌صدا نه.
            log.warning("unknown_role_code", role_code=row.role_code, user_id=str(user_id))
            continue
        grants.append(
            RoleGrant(
                role=Role(row.role_code),
                scope_type=ScopeType(row.scope_type),
                scope_id=row.scope_id,
            )
        )
    return tuple(grants)


def _serialize(grants: tuple[RoleGrant, ...]) -> str:
    return json.dumps(
        [
            {
                "role": g.role.value,
                "scope_type": g.scope_type.value,
                "scope_id": str(g.scope_id) if g.scope_id else None,
            }
            for g in grants
        ],
        ensure_ascii=False,
    )


def _deserialize(payload: str) -> tuple[RoleGrant, ...]:
    return tuple(
        RoleGrant(
            role=Role(item["role"]),
            scope_type=ScopeType(item["scope_type"]),
            scope_id=uuid.UUID(item["scope_id"]) if item["scope_id"] else None,
        )
        for item in json.loads(payload)
    )


async def get_grants(session: AsyncSession, user_id: uuid.UUID) -> tuple[RoleGrant, ...]:
    """اعطاهای نقش، با کش ۶۰ ثانیه‌ای."""
    cache_key = key_roles(str(user_id))
    redis = get_redis()

    try:
        cached = await redis.get(cache_key)
        if cached:
            return _deserialize(cached)
    except (RedisError, ValueError, KeyError) as exc:
        # کش خراب یا در دسترس نیست — مسیر اصلی ادامه می‌دهد.
        log.warning("role_cache_read_failed", error=str(exc))

    grants = await load_grants(session, user_id)

    try:
        await redis.setex(cache_key, ROLES_TTL_SECONDS, _serialize(grants))
    except RedisError as exc:
        log.warning("role_cache_write_failed", error=str(exc))

    return grants


async def invalidate_roles(user_id: uuid.UUID) -> None:
    """ابطال فوری کش پس از تغییر نقش — §6.4 قاعدهٔ ۵."""
    try:
        await get_redis().delete(key_roles(str(user_id)))
    except RedisError as exc:
        log.warning("role_cache_invalidate_failed", user_id=str(user_id), error=str(exc))


async def role_codes(session: AsyncSession, user_id: uuid.UUID) -> list[str]:
    """فهرست کد نقش‌ها — برای گنجاندن در JWT."""
    return sorted({g.role.value for g in await get_grants(session, user_id)})


async def has_permission(
    session: AsyncSession,
    user: CurrentUser,
    permission: Permission,
    scope_id: uuid.UUID | None = None,
) -> bool:
    """بررسی مجوز با اعطاهای تازه.

    اعطاهای داخل `CurrentUser` از JWT می‌آیند و تا ۱۵ دقیقه کهنه‌اند. برای
    مجوزهای قلمرودار، قلمرو در توکن نیست و باید از منبع خوانده شود.
    """
    grants = await get_grants(session, user.id)
    fresh = CurrentUser(
        id=user.id,
        session_id=user.session_id,
        grants=grants,
        impersonated_by=user.impersonated_by,
    )
    return fresh.has_permission(permission, scope_id)


async def grant_role(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    role: Role,
    scope_type: ScopeType = ScopeType.GLOBAL,
    scope_id: uuid.UUID | None = None,
    granted_by: uuid.UUID | None = None,
) -> UserRole | None:
    """اعطای نقش. اگر همین اعطا وجود داشته باشد، None برمی‌گردد.

    درج با `ON CONFLICT DO NOTHING` انجام می‌شود تا دو درخواست هم‌زمان
    خطای یکتایی ندهند؛ یکتایی با ایندکس عبارتی uq_user_roles_grant تضمین
    می‌شود، که نمی‌توان آن را با index_elements نام برد.
    """
    stmt = (
        insert(UserRole)
        .values(
            user_id=user_id,
            role_code=role.value,
            scope_type=scope_type.value,
            scope_id=scope_id,
            granted_by=granted_by,
        )
        .on_conflict_do_nothing()
        .returning(UserRole)
    )
    created = await session.scalar(stmt)
    await invalidate_roles(user_id)
    return created
