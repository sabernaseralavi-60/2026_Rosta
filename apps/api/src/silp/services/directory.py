"""نام نمایشی کاربران — یک کوئری برای یک فهرست، نه یکی به‌ازای هر ردیف.

§5.14 «بدون N+1»: هر endpoint فهرستی که نام عضو، متقاضی یا نویسنده را
نشان می‌دهد، همهٔ شناسه‌ها را یک‌جا به اینجا می‌دهد.

نام نمایشی از `profiles` می‌آید و ممکن است نباشد (کاربری که هنوز نیمرخ
نساخته). در آن حالت `username` جایگزین می‌شود و اگر آن هم نبود، None —
هرگز شمارهٔ موبایل یا ایمیل، که §11.5 آن را داده‌ٔ شخصی می‌داند.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from silp.models.identity import User
from silp.models.profile import Profile


@dataclass(frozen=True, slots=True)
class DisplayName:
    full_name: str | None
    username: str | None


async def display_names(
    session: AsyncSession, user_ids: Iterable[uuid.UUID]
) -> dict[uuid.UUID, DisplayName]:
    unique = {uid for uid in user_ids if uid is not None}
    if not unique:
        return {}
    rows = await session.execute(
        select(User.id, User.username, Profile.first_name, Profile.last_name, Profile.display_name)
        .outerjoin(Profile, Profile.user_id == User.id)
        .where(User.id.in_(unique))
    )
    result: dict[uuid.UUID, DisplayName] = {}
    for user_id, username, first, last, display in rows:
        name = display or (f"{first or ''} {last or ''}".strip() or None)
        result[user_id] = DisplayName(full_name=name, username=username)
    return result


def name_of(names: dict[uuid.UUID, DisplayName], user_id: uuid.UUID | None) -> str | None:
    if user_id is None:
        return None
    entry = names.get(user_id)
    if entry is None:
        return None
    return entry.full_name or entry.username


__all__ = ["DisplayName", "display_names", "name_of"]
