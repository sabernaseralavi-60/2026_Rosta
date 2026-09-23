"""جستجوی سراسری ⌘K — §3.7، M7-13، ADR-0017.

«جستجوی یکپارچه در: دروس، پروژه‌ها، ایده‌ها، افراد، منابع.» هر گروه همان
قاعدهٔ دیده‌شدنی را دارد که فهرست خودش — جستجو راه میان‌بری به چیزی
نیست که کاربر در فهرستش نمی‌بیند:

| گروه | دیده می‌شود |
|------|-------------|
| درس | درس فعال |
| پروژه | منتشرشده (نه پیش‌نویس، نه لغوشده) — و پروژه‌های خودم با هر وضعیت |
| ایده | بایگانی‌نشده |
| کسب‌وکار | بسته‌نشده |
| موضوع پژوهشی | وضعیت‌های عمومی بانک موضوع |
| فرد | فقط نیمرخ عمومی (FR-PROF-03) |
| منبع | مادهٔ منتشرشدهٔ کتابخانهٔ درس فعال — فقط عنوان؛ دروازهٔ اشتراک سر جایش است |

همه با `fa_normalize` روی ستون تولیدشده یا عبارت نرمال‌شده مقایسه
می‌شوند، پس «ي» و «ی» یا «ك» و «ک» فرقی نمی‌کنند. «دستورات» (ثبت ایده،
رفتن به داشبورد) در کلاینت‌اند: فهرست ثابتی‌اند که به نقش بستگی دارند،
نه به داده.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from silp.core.permissions import CurrentUser
from silp.domain.research import PUBLIC_TOPIC_STATUSES
from silp.models.education import Course, CourseMaterial
from silp.models.idea import Idea
from silp.models.identity import User
from silp.models.profile import Profile
from silp.models.project import KIND_TITLE_FA, Project, Team, TeamMember
from silp.models.research import ResearchTopic
from silp.models.venture import Venture

MIN_QUERY_LENGTH = 2
PER_GROUP = 5

GROUP_TITLE_FA: dict[str, str] = {
    "COURSE": "دروس",
    "PROJECT": "پروژه‌ها",
    "IDEA": "ایده‌ها",
    "VENTURE": "کسب‌وکارها",
    "TOPIC": "موضوع‌های پژوهشی",
    "PERSON": "افراد",
    "MATERIAL": "منابع",
}


@dataclass(frozen=True, slots=True)
class Hit:
    id: uuid.UUID
    title: str
    subtitle: str | None
    href: str


@dataclass(frozen=True, slots=True)
class Group:
    kind: str
    title_fa: str
    items: list[Hit]


class SearchService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def search(
        self, q: str, viewer: CurrentUser, *, per_group: int = PER_GROUP
    ) -> list[Group]:
        cleaned = q.strip()
        if len(cleaned) < MIN_QUERY_LENGTH:
            return []
        needle = func.concat("%", func.fa_normalize(cleaned), "%")
        groups = [
            ("COURSE", await self._courses(needle, per_group)),
            ("PROJECT", await self._projects(needle, viewer, per_group)),
            ("IDEA", await self._ideas(needle, per_group)),
            ("VENTURE", await self._ventures(needle, per_group)),
            ("TOPIC", await self._topics(needle, per_group)),
            ("PERSON", await self._people(needle, per_group)),
            ("MATERIAL", await self._materials(needle, per_group)),
        ]
        return [Group(kind, GROUP_TITLE_FA[kind], hits) for kind, hits in groups if hits]

    async def _courses(self, needle: ColumnElement[str], limit: int) -> list[Hit]:
        rows = await self.session.scalars(
            select(Course)
            .where(
                Course.deleted_at.is_(None),
                Course.is_active.is_(True),
                Course.title_norm.like(needle),
            )
            .order_by(Course.title_fa)
            .limit(limit)
        )
        return [Hit(c.id, c.title_fa, c.code, f"/library/{c.slug}") for c in rows]

    async def _projects(
        self, needle: ColumnElement[str], viewer: CurrentUser, limit: int
    ) -> list[Hit]:
        mine = (
            select(Team.project_id)
            .join(TeamMember, TeamMember.team_id == Team.id)
            .where(TeamMember.user_id == viewer.id, TeamMember.status == "ACTIVE")
        )
        visible = or_(
            Project.status.not_in(("DRAFT", "CANCELLED")),
            Project.lead_id == viewer.id,
            Project.id.in_(mine),
        )
        rows = await self.session.scalars(
            select(Project)
            .where(Project.deleted_at.is_(None), visible, Project.search_norm.like(needle))
            .order_by(Project.status == "COMPLETED", Project.created_at.desc())
            .limit(limit)
        )
        return [
            Hit(p.id, p.title_fa, KIND_TITLE_FA.get(p.kind, p.kind), f"/projects/{p.id}")
            for p in rows
        ]

    async def _ideas(self, needle: ColumnElement[str], limit: int) -> list[Hit]:
        rows = await self.session.scalars(
            select(Idea)
            .where(
                Idea.deleted_at.is_(None),
                Idea.status != "ARCHIVED",
                Idea.search_norm.like(needle),
            )
            .order_by(Idea.vote_count.desc(), Idea.created_at.desc())
            .limit(limit)
        )
        return [Hit(i.id, i.title, None, f"/ideas/{i.id}") for i in rows]

    async def _ventures(self, needle: ColumnElement[str], limit: int) -> list[Hit]:
        rows = await self.session.scalars(
            select(Venture)
            .where(
                Venture.deleted_at.is_(None),
                Venture.stage != "CLOSED",
                Venture.search_norm.like(needle),
            )
            .order_by(Venture.stage_changed_at.desc())
            .limit(limit)
        )
        return [Hit(v.id, v.name, v.pitch, f"/ventures/{v.id}") for v in rows]

    async def _topics(self, needle: ColumnElement[str], limit: int) -> list[Hit]:
        rows = await self.session.scalars(
            select(ResearchTopic)
            .where(
                ResearchTopic.status.in_(PUBLIC_TOPIC_STATUSES),
                ResearchTopic.search_norm.like(needle),
            )
            .order_by(ResearchTopic.status == "OPEN", ResearchTopic.created_at.desc())
            .limit(limit)
        )
        return [Hit(t.id, t.title, None, f"/research/topics/{t.id}") for t in rows]

    async def _people(self, needle: ColumnElement[str], limit: int) -> list[Hit]:
        name = func.fa_normalize(
            func.concat_ws(" ", Profile.first_name, Profile.last_name, Profile.display_name)
        )
        rows = await self.session.execute(
            select(
                User.id,
                User.username,
                Profile.first_name,
                Profile.last_name,
                Profile.display_name,
                Profile.field_of_study,
            )
            .join(Profile, Profile.user_id == User.id)
            .where(
                Profile.is_public.is_(True),
                User.deleted_at.is_(None),
                User.status == "ACTIVE",
                User.username.is_not(None),
                or_(name.like(needle), User.username.like(needle)),
            )
            .order_by(Profile.first_name, Profile.last_name)
            .limit(limit)
        )
        return [
            Hit(uid, display or f"{first} {last}".strip(), field, f"/u/{username}")
            for uid, username, first, last, display, field in rows
        ]

    async def _materials(self, needle: ColumnElement[str], limit: int) -> list[Hit]:
        rows = await self.session.execute(
            select(CourseMaterial, Course.slug, Course.title_fa)
            .join(Course, Course.id == CourseMaterial.course_id)
            .where(
                CourseMaterial.deleted_at.is_(None),
                CourseMaterial.status == "PUBLISHED",
                Course.deleted_at.is_(None),
                Course.is_active.is_(True),
                CourseMaterial.title_norm.like(needle),
            )
            .order_by(CourseMaterial.title_fa)
            .limit(limit)
        )
        return [
            Hit(material.id, material.title_fa, course_title, f"/library/{slug}")
            for material, slug, course_title in rows
        ]


__all__ = ["GROUP_TITLE_FA", "MIN_QUERY_LENGTH", "Group", "Hit", "SearchService"]
