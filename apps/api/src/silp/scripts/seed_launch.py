"""دادهٔ راه‌اندازی تولید — M7-16، §13.3.

اجرا، اولین بار (پس از `alembic upgrade head`):

    python -m silp.scripts.seed_launch --lead-mobile 0913xxxxxxx --admin-mobile 0913xxxxxxx
    python -m silp.scripts.sync_courses          # به مدیر نیاز دارد — همان که بالا ساخته شد
    python -m silp.scripts.seed_launch --lead-mobile 0913xxxxxxx   # ارائهٔ دروس همگام‌شده

`seed` توسعه در تولید عمداً اجرا نمی‌شود (حساب نمونه با کد ثابت ورود). ولی
بانک ۲۵ پروژه، نیم‌سال، طرح اشتراک و ارائه‌ها در تولید هم لازم‌اند، و
**اولین مدیر** تا امروز هیچ راهی برای ساخته شدن نداشت. این اسکریپت همان
بخش امن را جدا می‌کند:

* حساب استاد با شمارهٔ واقعی (نه ۰۹۱۲۰۰۰۰۰۰۲)، نقش استاد، و مدیریت پروژه‌ها؛
* نقش مدیر برای شماره‌های `--admin-mobile`؛
* نیم‌سال، طرح اشتراک، بانک پروژه و ارائهٔ هر درس همگام‌شده؛
* هیچ هفته‌ای منتشر نمی‌شود مگر با `--publish-weeks`.

بی‌اثر در تکرار است. حساب فقط شماره دارد؛ نیمرخ را صاحبش در اولین ورود
کامل می‌کند (ADR-0018).
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from silp.core.config import get_settings
from silp.core.logging import configure_logging
from silp.core.permissions import Role, ScopeType
from silp.db.session import dispose_engine, session_scope
from silp.domain.identity.normalize import normalize_mobile
from silp.scripts.seed_courses import seed_offerings, seed_plans, seed_terms
from silp.scripts.seed_projects import ensure_lead, seed_projects
from silp.scripts.sync_courses import resolve_root
from silp.services import authz


def _mobile(raw: str) -> str:
    mobile = normalize_mobile(raw)
    if mobile is None:
        msg = f"شمارهٔ موبایل نامعتبر: {raw}"
        raise argparse.ArgumentTypeError(msg)
    return mobile


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="دادهٔ راه‌اندازی تولید — M7-16")
    parser.add_argument(
        "--lead-mobile",
        type=_mobile,
        required=True,
        help="شمارهٔ استاد: مدیر پروژه‌های بانک و استاد ارائه‌ها",
    )
    parser.add_argument(
        "--admin-mobile",
        type=_mobile,
        action="append",
        default=[],
        help="شمارهٔ مدیر سامانه؛ برای چند مدیر تکرار کنید",
    )
    parser.add_argument(
        "--publish-weeks",
        type=int,
        default=0,
        help="چند هفتهٔ اول هر ارائه منتشر شود (پیش‌فرض ۰: تصمیم با استاد)",
    )
    parser.add_argument("--courses-root", default=None, help="پوشهٔ Courses (پیش‌فرض: خودکار)")
    return parser.parse_args(argv)


async def run(args: argparse.Namespace) -> dict[str, tuple[int, int]]:
    async with session_scope() as session:
        for mobile in args.admin_mobile:
            admin_id = await ensure_lead(session, mobile)
            await authz.grant_role(
                session, user_id=admin_id, role=Role.ADMIN, scope_type=ScopeType.GLOBAL
            )

        lead_id = await ensure_lead(session, args.lead_mobile)
        for role in (Role.INSTRUCTOR, Role.STUDENT):
            await authz.grant_role(session, user_id=lead_id, role=role, scope_type=ScopeType.GLOBAL)

        terms = await seed_terms(session)
        plans = await seed_plans(session)
        projects = await seed_projects(session, lead_id)
        offerings = await seed_offerings(
            session,
            instructor_id=lead_id,
            courses_root=resolve_root(args.courses_root),
            publish_weeks=max(0, args.publish_weeks),
        )
        await authz.invalidate_roles(lead_id)
    return {"نیم‌سال": terms, "طرح اشتراک": plans, "پروژه": projects, "ارائهٔ درس": offerings}


async def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    settings = get_settings()
    configure_logging(settings.log_level, renderer="console")
    try:
        summary = await run(args)
    finally:
        await dispose_engine()

    print("")
    for label, (created, existing) in summary.items():
        print(f"  {label}: {created} ساخته شد، {existing} از قبل موجود بود.")
    if args.admin_mobile:
        print(f"  مدیر سامانه: {len(args.admin_mobile)} شماره")
    if summary["ارائهٔ درس"] == (0, 0):
        # sync_courses به مدیر نیاز دارد و مدیر را همین اسکریپت می‌سازد؛ پس
        # ترتیب اولین بار: seed_launch ← sync_courses ← seed_launch.
        print(
            "  هیچ درسی همگام نشده: sync_courses را اجرا کنید و سپس دوباره seed_launch.",
            file=sys.stderr,
        )
    print("")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
