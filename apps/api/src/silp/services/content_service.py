"""خواندن محتوای منتشرشده — ADR-0030.

نوشتن محتوا اینجا نیست: مسیر نوشتن `silp.vault.publisher` است (Vault ← نمایه).

**دسترسی** (تا آمدن عضویت، ADR-0030):

| سطح | چه کسی می‌خواند |
|-----|------------------|
| PUBLIC | همه |
| REGISTERED | هر کاربر واردشده |
| STUDENT | دانشجو و کادر آموزشی |
| MEMBER، PREMIUM | فقط کادر آموزشی و مدیر — تا پیاده‌شدن عضویت، بستهٔ پولی وجود ندارد |

متن یک محتوای قفل‌شده هرگز از سرور بیرون نمی‌رود؛ فقط عنوان و خلاصه.
"""

from __future__ import annotations

from typing import Final

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from silp.core.exceptions import NotFound
from silp.core.permissions import CurrentUser, Role
from silp.models.content import ContentItem

KIND_FA: Final[dict[str, str]] = {
    "ARTICLE": "مقالهٔ آموزشی",
    "BOOK_SUMMARY": "خلاصهٔ کتاب",
    "PAPER_SUMMARY": "خلاصهٔ مقاله",
    "EXAMPLE": "مثال حل‌شده",
    "CASE_STUDY": "مطالعهٔ موردی",
    "DATASET_NOTE": "راهنمای داده",
}
ACCESS_FA: Final[dict[str, str]] = {
    "PUBLIC": "عمومی",
    "REGISTERED": "با حساب رایگان",
    "STUDENT": "دانشجویان",
    "MEMBER": "اعضا",
    "PREMIUM": "ویژه",
}
_STAFF: Final = frozenset({Role.INSTRUCTOR, Role.COORDINATOR, Role.ADMIN})


def can_read(access: str, viewer: CurrentUser | None) -> bool:
    if access == "PUBLIC":
        return True
    if viewer is None:
        return False
    roles = {grant.role for grant in viewer.grants}
    if access == "REGISTERED":
        return True
    if access == "STUDENT":
        return Role.STUDENT in roles or bool(roles & _STAFF)
    return bool(roles & _STAFF)


class ContentService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def search(
        self,
        *,
        kind: str | None = None,
        topic: str | None = None,
        course: str | None = None,
        q: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[ContentItem], int]:
        conditions = [ContentItem.status == "PUBLISHED"]
        if kind:
            conditions.append(ContentItem.kind == kind)
        if topic:
            conditions.append(ContentItem.topics.contains([topic]))
        if course:
            conditions.append(ContentItem.course_slug == course)
        if q:
            pattern = f"%{q.strip()}%"
            conditions.append(
                or_(
                    func.fa_normalize(ContentItem.title_fa).ilike(func.fa_normalize(pattern)),
                    func.fa_normalize(ContentItem.summary).ilike(func.fa_normalize(pattern)),
                )
            )
        total = await self.session.scalar(
            select(func.count()).select_from(ContentItem).where(*conditions)
        )
        rows = await self.session.scalars(
            select(ContentItem)
            .where(*conditions)
            .order_by(ContentItem.published_at.desc(), ContentItem.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(rows), int(total or 0)

    async def facets(self) -> tuple[dict[str, int], dict[str, int]]:
        """شمار هر نوع و هر موضوع در محتوای منتشرشده — برای فیلترهای صفحه."""
        kinds = dict(
            (
                await self.session.execute(
                    select(ContentItem.kind, func.count())
                    .where(ContentItem.status == "PUBLISHED")
                    .group_by(ContentItem.kind)
                )
            )
            .tuples()
            .all()
        )
        unnested = (
            select(func.unnest(ContentItem.topics).label("topic"))
            .where(ContentItem.status == "PUBLISHED")
            .subquery()
        )
        topics = dict(
            (
                await self.session.execute(
                    select(unnested.c.topic, func.count())
                    .group_by(unnested.c.topic)
                    .order_by(func.count().desc(), unnested.c.topic)
                    .limit(30)
                )
            )
            .tuples()
            .all()
        )
        return kinds, topics

    async def get(self, slug: str) -> ContentItem:
        item = await self.session.scalar(
            select(ContentItem).where(ContentItem.slug == slug, ContentItem.status == "PUBLISHED")
        )
        if item is None:
            raise NotFound("این محتوا پیدا نشد.")
        return item

    async def related(self, item: ContentItem, limit: int = 3) -> list[ContentItem]:
        conditions = [ContentItem.status == "PUBLISHED", ContentItem.id != item.id]
        if item.topics:
            conditions.append(ContentItem.topics.overlap(item.topics))
        else:
            conditions.append(ContentItem.kind == item.kind)
        rows = await self.session.scalars(
            select(ContentItem)
            .where(*conditions)
            .order_by(ContentItem.published_at.desc())
            .limit(limit)
        )
        return list(rows)


__all__ = ["ACCESS_FA", "KIND_FA", "ContentService", "can_read"]
