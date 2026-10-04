"""حساب آزمون مالک سامانه — فقط توسعه.

اجرا: ``python -m silp.scripts.seed_master``

یک کاربر با نام کاربری ``saber`` و رمز ``33`` و همهٔ نقش‌های عملیاتی می‌سازد تا مالک
بتواند از هر در عبور کند و بازخورد بدهد. در ``ENVIRONMENT`` غیر از ``development``
با خطا خارج می‌شود. ورود با نام کاربری هم فقط در توسعه فعال است.
"""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import select

from silp.core.config import get_settings
from silp.core.permissions import Role, ScopeType
from silp.core.security import hash_password
from silp.db.session import dispose_engine, session_scope
from silp.models.identity import User
from silp.models.profile import Profile
from silp.scripts.seed_profiles import COMPLETED_STEPS
from silp.services import authz

USERNAME = "saber"
PASSWORD = "33"  # noqa: S105 — حساب آزمون، فقط توسعه
MOBILE = "09120000099"
ROLES = (
    Role.STUDENT,
    Role.PROJECT_LEAD,
    Role.MENTOR,
    Role.TA,
    Role.INSTRUCTOR,
    Role.COORDINATOR,
    Role.SUPPORT,
    Role.ADMIN,
)


async def seed_master() -> bool:
    """خروجی: True اگر تازه ساخته شد."""
    created = False
    async with session_scope() as session:
        user = await session.scalar(select(User).where(User.username == USERNAME))
        if user is None:
            user = User(username=USERNAME, mobile=MOBILE)
            session.add(user)
            created = True
        user.password_hash = hash_password(PASSWORD)
        user.status = "ACTIVE"
        await session.flush()
        if await session.get(Profile, user.id) is None:
            # نیمرخ کامل، تا ورود مالک به صفحهٔ ثبت‌نام اولیه نرود.
            session.add(
                Profile(
                    user_id=user.id,
                    first_name="صابر",
                    last_name="مالک",
                    survey_completed_steps=COMPLETED_STEPS,
                )
            )
        for role in ROLES:
            await authz.grant_role(session, user_id=user.id, role=role, scope_type=ScopeType.GLOBAL)
    return created


async def _main() -> int:
    if not get_settings().is_development:
        print("seed_master فقط در ENVIRONMENT=development اجرا می‌شود.", file=sys.stderr)
        return 1
    try:
        created = await seed_master()
    finally:
        await dispose_engine()
    print(f"حساب {USERNAME}: {'ساخته شد' if created else 'به‌روز شد'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
