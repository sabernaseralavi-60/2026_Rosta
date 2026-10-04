"""حساب مالک در تولید — ورود با موبایل و رمز.

اجرا: ``OWNER_LOGIN=<موبایل 09... یا ایمیل> OWNER_PASSWORD=... python -m silp.scripts.bootstrap_owner``

برخلاف ``seed_master`` (فقط توسعه)، این اسکریپت در هر محیطی کار می‌کند ولی رمز را
از محیط می‌گیرد، نه از کد. اجرای دوباره رمز و نقش‌ها را به‌روز می‌کند.
"""

from __future__ import annotations

import asyncio
import os
import sys

from sqlalchemy import select

from silp.core.permissions import Role, ScopeType
from silp.core.security import hash_password
from silp.db.session import dispose_engine, session_scope
from silp.models.identity import User
from silp.models.profile import Profile
from silp.scripts.seed_profiles import COMPLETED_STEPS
from silp.services import authz

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


async def bootstrap_owner(login: str, password: str) -> bool:
    """خروجی: True اگر تازه ساخته شد."""
    created = False
    async with session_scope() as session:
        by_mobile = login.startswith("09")
        column = User.mobile if by_mobile else User.email
        user = await session.scalar(select(User).where(column == login))
        if user is None:
            user = User(mobile=login) if by_mobile else User(email=login)
            session.add(user)
            created = True
        user.password_hash = hash_password(password)
        user.status = "ACTIVE"
        await session.flush()
        if await session.get(Profile, user.id) is None:
            session.add(
                Profile(
                    user_id=user.id,
                    first_name="مالک",
                    last_name="سامانه",
                    survey_completed_steps=COMPLETED_STEPS,
                )
            )
        for role in ROLES:
            await authz.grant_role(session, user_id=user.id, role=role, scope_type=ScopeType.GLOBAL)
    return created


async def _main() -> int:
    login = os.environ.get("OWNER_LOGIN", "").strip().lower()
    password = os.environ.get("OWNER_PASSWORD", "")
    if not login or len(password) < 12:
        print("OWNER_LOGIN و OWNER_PASSWORD (حداقل ۱۲ نویسه) لازم‌اند.", file=sys.stderr)
        return 1
    try:
        created = await bootstrap_owner(login, password)
    finally:
        await dispose_engine()
    print(f"حساب مالک {login}: {'ساخته شد' if created else 'به‌روز شد'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
