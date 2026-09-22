"""پیگیری پیشرفت مطالعه — FR-EDU-04.

قاعده‌های سند، دقیقاً:

* PDF: باز کردن ⇒ `IN_PROGRESS`. علامت‌گذاری دستی ⇒ `COMPLETED`.
* ویدئو: تماشای ≥ ۹۰٪ ⇒ `COMPLETED` **خودکار**.

آستانهٔ ۹۰٪ اینجا یک ثابت نام‌دار است، نه عددی پراکنده در چند فایل:
تیتراژ پایانی را کسی تماشا نمی‌کند و «۱۰۰٪ یا هیچ» یعنی هیچ ویدئویی
هرگز تکمیل‌شده نشود.

پیشرفت هرگز **پس نمی‌رود**: منبعی که یک‌بار `COMPLETED` شده، با یک
گزارش ۴۰ درصدی بعدی (مثلاً چون کاربر ویدئو را دوباره از اول دید)
ناتمام نمی‌شود.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from silp.core.exceptions import NotFound, ValidationFailed
from silp.models.education import Resource, ResourceProgress

# FR-EDU-04 — «تماشای ≥ ۹۰٪ ⇒ COMPLETED خودکار».
VIDEO_COMPLETE_PERCENT = 90

PERCENT_MIN = 0
PERCENT_MAX = 100


class ProgressService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def record(
        self,
        *,
        user_id: uuid.UUID,
        resource_id: uuid.UUID,
        percent: float | None = None,
        position_sec: int | None = None,
        completed: bool | None = None,
    ) -> ResourceProgress:
        """ثبت پیشرفت — §5.5 `POST /resources/{id}/progress`.

        سه ورودی اختیاری‌اند و با هم کار می‌کنند: کلاینت ویدئو `percent`
        و `position_sec` می‌فرستد، خوانندهٔ PDF فقط صدا زدن بدون آرگومان
        (یعنی «بازش کردم»)، و دکمهٔ «خواندم» `completed=true`.
        """
        resource = await self.session.get(Resource, resource_id)
        if resource is None:
            raise NotFound("این منبع پیدا نشد.")
        if percent is not None and not PERCENT_MIN <= percent <= PERCENT_MAX:
            raise ValidationFailed("درصد پیشرفت باید بین ۰ تا ۱۰۰ باشد.")
        if position_sec is not None and position_sec < 0:
            raise ValidationFailed("موقعیت پخش نمی‌تواند منفی باشد.")

        now = _now()
        current = await self.session.get(ResourceProgress, (user_id, resource_id))

        previous_percent = float(current.percent or 0) if current else 0.0
        was_completed = current is not None and current.status == "COMPLETED"

        new_percent = (
            max(previous_percent, float(percent)) if percent is not None else previous_percent
        )
        is_complete = was_completed or bool(completed)
        # ویدئو خودش تمام می‌شود؛ بقیه با دکمهٔ صریح.
        if resource.kind == "VIDEO" and new_percent >= VIDEO_COMPLETE_PERCENT:
            is_complete = True
        if is_complete:
            new_percent = max(new_percent, float(PERCENT_MAX))

        status = "COMPLETED" if is_complete else "IN_PROGRESS"

        values = {
            "user_id": user_id,
            "resource_id": resource_id,
            "status": status,
            "percent": Decimal(str(round(new_percent, 2))),
            "position_sec": position_sec
            if position_sec is not None
            else (current.position_sec if current else None),
            "first_opened_at": current.first_opened_at
            if current and current.first_opened_at
            else now,
            "completed_at": (current.completed_at if current and current.completed_at else now)
            if is_complete
            else None,
        }

        await self.session.execute(
            insert(ResourceProgress)
            .values(**values)
            .on_conflict_do_update(
                index_elements=["user_id", "resource_id"],
                set_={
                    "status": values["status"],
                    "percent": values["percent"],
                    "position_sec": values["position_sec"],
                    "first_opened_at": values["first_opened_at"],
                    "completed_at": values["completed_at"],
                },
            )
        )
        await self.session.commit()

        refreshed = await self.session.get(
            ResourceProgress, (user_id, resource_id), populate_existing=True
        )
        if refreshed is None:  # pragma: no cover — درج بالا تضمینش می‌کند
            raise NotFound("ثبت پیشرفت انجام نشد.")
        return refreshed

    async def for_resources(
        self, user_id: uuid.UUID, resource_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, ResourceProgress]:
        if not resource_ids:
            return {}
        rows = await self.session.scalars(
            select(ResourceProgress).where(
                ResourceProgress.user_id == user_id,
                ResourceProgress.resource_id.in_(resource_ids),
            )
        )
        return {row.resource_id: row for row in rows}


def _now() -> datetime:
    return datetime.now(UTC)


__all__ = ["VIDEO_COMPLETE_PERCENT", "ProgressService"]
