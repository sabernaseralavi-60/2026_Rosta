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
from silp.models.education import CourseOffering
from silp.models.identity import UserRole
from silp.models.project import Project, Team, TeamMember

log = get_logger("silp.authz")


async def load_stored_grants(session: AsyncSession, user_id: uuid.UUID) -> tuple[RoleGrant, ...]:
    """اعطاهای ثبت‌شده در `user_roles` — بدون نقش‌های مشتق."""
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


async def load_derived_grants(session: AsyncSession, user_id: uuid.UUID) -> tuple[RoleGrant, ...]:
    """§6.1 — `PROJECT_LEAD` و `PROJECT_MEMBER` در `user_roles` ذخیره نمی‌شوند.

    دو منبع دارند و هر دو لازم‌اند:

    * **عضویت فعال در تیم** — عضو عادی `PROJECT_MEMBER` و عضو `is_lead`
      نقش `PROJECT_LEAD` می‌گیرد.
    * **`projects.lead_id`** — پروژهٔ `DRAFT` هنوز تیم ندارد (§7.12 تیم
      هنگام انتشار ساخته می‌شود)، پس سازنده تا لحظهٔ انتشار از راه تیم
      هیچ نقشی نمی‌گیرد و نمی‌تواند پروژهٔ خودش را منتشر کند.

    عضو `LEFT` یا `REMOVED` نقشی نمی‌گیرد: ایندکس یکتای
    `idx_team_member_active` تضمین می‌کند هر کاربر حداکثر یک عضویت فعال
    در هر تیم دارد.
    """
    member_rows = await session.execute(
        select(Team.project_id, TeamMember.is_lead)
        .join(TeamMember, TeamMember.team_id == Team.id)
        .where(
            TeamMember.user_id == user_id,
            TeamMember.status == "ACTIVE",
            Team.project_id.is_not(None),
        )
    )
    grants: list[RoleGrant] = [
        RoleGrant(
            role=Role.PROJECT_LEAD if is_lead else Role.PROJECT_MEMBER,
            scope_type=ScopeType.PROJECT,
            scope_id=project_id,
        )
        for project_id, is_lead in member_rows
    ]

    lead_project_ids = await session.scalars(
        select(Project.id).where(Project.lead_id == user_id, Project.deleted_at.is_(None))
    )
    known = {g.scope_id for g in grants if g.role is Role.PROJECT_LEAD}
    grants.extend(
        RoleGrant(role=Role.PROJECT_LEAD, scope_type=ScopeType.PROJECT, scope_id=project_id)
        for project_id in lead_project_ids
        if project_id not in known
    )

    # §6.1 — `INSTRUCTOR` قلمروش ارائه است: «اختیار کامل روی ارائهٔ خود».
    # منبع حقیقت `course_offerings.instructor_id` است، نه یک ردیف دستی
    # در `user_roles`. بدون این، استادی که ارائه‌اش را تازه ساخته باید
    # منتظر بماند تا مدیر نقشش را در همان قلمرو ثبت کند — و مدیری که
    # عجله دارد، نقش را سراسری می‌دهد و در عمل همهٔ دروس را باز می‌کند.
    offering_ids = await session.scalars(
        select(CourseOffering.id).where(
            CourseOffering.instructor_id == user_id, CourseOffering.deleted_at.is_(None)
        )
    )
    grants.extend(
        RoleGrant(role=Role.INSTRUCTOR, scope_type=ScopeType.OFFERING, scope_id=offering_id)
        for offering_id in offering_ids
    )
    return tuple(grants)


async def load_grants(session: AsyncSession, user_id: uuid.UUID) -> tuple[RoleGrant, ...]:
    """همهٔ اعطاهای مؤثر کاربر — ثبت‌شده و مشتق. بدون کش."""
    stored = await load_stored_grants(session, user_id)
    derived = await load_derived_grants(session, user_id)
    grants = stored + derived
    return grants + await load_supervision_grants(session, grants)


async def load_supervision_grants(
    session: AsyncSession, grants: tuple[RoleGrant, ...]
) -> tuple[RoleGrant, ...]:
    """§3.5 — استادِ یک ارائه، پروژه‌های همان ارائه را هم اداره می‌کند (ADR-0022).

    `DELIVERABLE_REVIEW` و هم‌خانواده‌هایش قلمرو **پروژه** دارند ولی نقش استاد
    قلمرو **ارائه**؛ بی این پل، `covers(project_id)` برای استاد هرگز درست
    نبود و او تحویل پروژهٔ ارائهٔ خودش را نمی‌توانست بررسی کند، مگر با نقش
    سراسری (که همهٔ ارائه‌ها را باز می‌کند).

    فقط `INSTRUCTOR` — چه رسمی (`instructor_id`)، چه ثبت‌شدهٔ قلمرودار. دستیار
    (`TA`) پروژه‌ای نمی‌گیرد: ماتریس مجوز پروژه‌ای برایش چیزی ندارد و اعطای
    بی‌مصرف فقط `admin/users` را شلوغ می‌کند.
    """
    offering_ids = {
        g.scope_id
        for g in grants
        if g.role is Role.INSTRUCTOR and g.scope_type is ScopeType.OFFERING and g.scope_id
    }
    if not offering_ids:
        return ()
    project_ids = await session.scalars(
        select(Project.id).where(
            Project.offering_id.in_(offering_ids), Project.deleted_at.is_(None)
        )
    )
    return tuple(
        RoleGrant(role=Role.INSTRUCTOR, scope_type=ScopeType.PROJECT, scope_id=project_id)
        for project_id in project_ids
    )


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
    expires_at: datetime | None = None,
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
            expires_at=expires_at,
        )
        .on_conflict_do_nothing()
        .returning(UserRole)
    )
    created = await session.scalar(stmt)
    await invalidate_roles(user_id)
    return created
