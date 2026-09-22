"""داده‌های اولیهٔ توسعه — §14.8.

اجرا: ``make seed`` یا ``python -m silp.scripts.seed``

اسکریپت **بی‌اثر در تکرار** است: اجرای دوباره حساب تکراری نمی‌سازد.
حساب‌های نمونه فقط در ``ENVIRONMENT=development`` ساخته می‌شوند؛ در تولید
اسکریپت با خطا خارج می‌شود، نه اینکه بی‌صدا هیچ کاری نکند.
"""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import select

from silp.core.config import get_settings
from silp.core.logging import configure_logging, get_logger
from silp.core.permissions import Role, ScopeType
from silp.db.session import dispose_engine, session_scope
from silp.models.identity import User
from silp.scripts.seed_profiles import seed_profiles
from silp.scripts.seed_projects import ensure_lead, seed_projects
from silp.services import authz

log = get_logger("silp.seed")

# §14.8 — (موبایل، نقش، شرح نیمرخ)
DEV_ACCOUNTS: tuple[tuple[str, Role, str], ...] = (
    ("09120000001", Role.ADMIN, "مدیر سامانه"),
    ("09120000002", Role.INSTRUCTOR, "استاد، مدیر ۴ ارائه"),
    ("09120000003", Role.TA, "دستیار آموزشی"),
    ("09120000010", Role.STUDENT, "پرسونای مریم: مهارت نرم‌افزاری متوسط، هدف نمره"),
    ("09120000011", Role.STUDENT, "پرسونای امیر: R و آمار قوی، هدف مقاله"),
    ("09120000012", Role.STUDENT, "پرسونای سارا: محتوا و فروش، موتور دارد، هدف درآمد"),
    ("09120000013", Role.STUDENT, "نیمرخ خالی — برای تست حالت ورود اولیه"),
    ("09120000020", Role.PUBLIC_LEARNER, "کاربر عمومی غیردانشجو"),
)


async def seed_dev_accounts() -> tuple[int, int]:
    """ساخت حساب‌های نمونه. خروجی: (ساخته‌شده، از قبل موجود)."""
    created = 0
    existing = 0

    async with session_scope() as session:
        for mobile, role, note in DEV_ACCOUNTS:
            user = await session.scalar(select(User).where(User.mobile == mobile))
            if user is None:
                user = User(mobile=mobile)
                session.add(user)
                await session.flush()
                created += 1
                log.info("seed_user_created", mobile=mobile, role=role.value, note=note)
            else:
                existing += 1

            # اعطای نقش بی‌اثر در تکرار است (ON CONFLICT DO NOTHING).
            await authz.grant_role(
                session,
                user_id=user.id,
                role=role,
                scope_type=ScopeType.GLOBAL,
            )
            # دانشجو علاوه بر نقش تخصصی، نقش پایه را هم دارد.
            if role in (Role.INSTRUCTOR, Role.TA):
                await authz.grant_role(
                    session, user_id=user.id, role=Role.STUDENT, scope_type=ScopeType.GLOBAL
                )

    return created, existing


INSTRUCTOR_MOBILE = "09120000002"


async def seed_content() -> tuple[tuple[int, int], tuple[int, int]]:
    """نیمرخ پرسوناها و بانک پروژهٔ §14.5.

    ترتیب مهم است: پروژه‌ها به حساب استاد به‌عنوان مدیر نیاز دارند، و
    نیمرخ‌ها به وجود کاربر.
    """
    async with session_scope() as session:
        profiles = await seed_profiles(session)
        lead_id = await ensure_lead(session, INSTRUCTOR_MOBILE)
        projects = await seed_projects(session, lead_id)
    return profiles, projects


async def main() -> int:
    settings = get_settings()
    configure_logging(settings.log_level, renderer="console")

    if settings.is_production:
        print("داده‌های نمونه در محیط تولید ساخته نمی‌شوند.", file=sys.stderr)
        return 1

    try:
        created, existing = await seed_dev_accounts()
        (p_created, p_existing), (j_created, j_existing) = await seed_content()
    finally:
        await dispose_engine()

    print("")
    print(f"  حساب‌های نمونه: {created} ساخته شد، {existing} از قبل موجود بود.")
    print(f"  نیمرخ‌ها:       {p_created} ساخته شد، {p_existing} از قبل موجود بود.")
    print(f"  پروژه‌ها:       {j_created} ساخته شد، {j_existing} از قبل موجود بود.")
    if settings.dev_fixed_otp:
        print(f"  کد ورود در محیط توسعه: {settings.dev_fixed_otp}")
    print("  نمونه: 09120000010 (دانشجو) · 09120000001 (مدیر)")
    print("")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
