"""نام کاربری برای کاربرانی که پیش از M7 نیمرخ ساخته‌اند — ADR-0014.

اجرا::

    python -m silp.scripts.backfill_usernames

تا M7 تابع `pick_username` (§7.1) هرگز فراخوانی نمی‌شد و هیچ کاربری نام
کاربری نداشت. از M7 نام کاربری هنگام ثبت نام نیمرخ ساخته می‌شود؛ این
اسکریپت همان را برای کاربران قدیمی انجام می‌دهد.

**بی‌اثر در تکرار است:** فقط کاربرانی را می‌بیند که نام کاربری ندارند، و
نام کاربری موجود هرگز عوض نمی‌شود.
"""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import select

from silp.core.config import get_settings
from silp.core.logging import configure_logging, get_logger
from silp.db.session import dispose_engine, session_scope
from silp.models.identity import User
from silp.models.profile import Profile
from silp.services.profile_service import ProfileService

log = get_logger("silp.backfill")


async def backfill() -> int:
    async with session_scope() as session:
        rows = list(
            await session.execute(
                select(Profile.user_id, Profile.first_name, Profile.last_name)
                .join(User, User.id == Profile.user_id)
                .where(User.username.is_(None), User.deleted_at.is_(None))
                .order_by(User.created_at)
            )
        )
        service = ProfileService(session)
        for user_id, first, last in rows:
            # یکی‌یکی و با flush: نامزد بعدی باید نام تازه‌گرفته‌شدهٔ قبلی را ببیند.
            await service.ensure_username(user_id, first, last)
            await session.flush()
        await session.commit()
        return len(rows)


async def main() -> int:
    configure_logging(get_settings().log_level, renderer="console")
    try:
        count = await backfill()
    finally:
        await dispose_engine()
    print(f"انجام شد — {count} کاربر نام کاربری گرفت.")
    log.info("usernames_backfilled", users=count)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
