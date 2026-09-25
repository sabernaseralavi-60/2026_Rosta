"""بازتاب پایان پروژه — FR-PRJ-08، ADR-0024.

بازتاب سند است، نه پیش‌نویس: یک‌بار برای هر (پروژه، عضو) و بی‌ویرایش.
خصوصی است — فقط نویسنده‌اش می‌بیند (بخش «چه سخت بود» ممکن است دربارهٔ
هم‌تیمی‌ها باشد؛ مدیر و استاد هم آن را نمی‌خوانند).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from silp.core.exceptions import Conflict, NotTeamMember, ValidationFailed
from silp.core.permissions import CurrentUser
from silp.domain import reflections as rules
from silp.domain.reflections import ReflectionDraft
from silp.models.delivery import ProjectReflection
from silp.models.project import Project
from silp.services import events
from silp.services.points_service import PointsService
from silp.services.project_service import ProjectService

RULE_CODE = "REFLECTION_SUBMITTED"


@dataclass(frozen=True, slots=True)
class ReflectionState:
    """آنچه فرم برای نشان دادن خودش لازم دارد — یک فراخوانی، نه سه‌تا."""

    can_submit: bool
    reason: str | None
    reflection: ProjectReflection | None
    points: Decimal | None


class ReflectionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.projects = ProjectService(session)

    async def state(self, *, project: Project, actor: CurrentUser) -> ReflectionState:
        """وضعیت بازتاب خودِ کاربر. غیرعضو ۴۰۳ می‌گیرد (مثل بقیهٔ فضای کاری)."""
        await self._require_member(project, actor)
        existing = await self.session.get(ProjectReflection, (project.id, actor.id))
        points = await self._reward()
        if existing is not None:
            return ReflectionState(False, "بازتاب این پروژه را نوشته‌ای.", existing, points)
        if project.status != "COMPLETED":
            return ReflectionState(False, "بازتاب پس از بسته شدن پروژه نوشته می‌شود.", None, points)
        return ReflectionState(True, None, None, points)

    async def submit(
        self, *, project: Project, actor: CurrentUser, draft: ReflectionDraft
    ) -> ProjectReflection:
        await self._require_member(project, actor)
        if project.status != "COMPLETED":
            raise Conflict("بازتاب پس از بسته شدن پروژه نوشته می‌شود.")
        problem = rules.validate(draft)
        if problem is not None:
            raise ValidationFailed(problem)
        if await self.session.get(ProjectReflection, (project.id, actor.id)) is not None:
            raise Conflict("بازتاب این پروژه را قبلاً نوشته‌ای.")

        reflection = ProjectReflection(
            project_id=project.id,
            user_id=actor.id,
            learned=rules.clean(draft.learned) or "",
            challenges=rules.clean(draft.challenges),
            would_do_differently=rules.clean(draft.would_do_differently),
            satisfaction=draft.satisfaction,
        )
        try:
            async with self.session.begin_nested():
                self.session.add(reflection)
                await self.session.flush()
        except IntegrityError:
            # دو کلیک هم‌زمان: کلید اصلی دومی را رد می‌کند.
            raise Conflict("بازتاب این پروژه را قبلاً نوشته‌ای.") from None
        await events.publish(
            self.session, events.ReflectionSubmitted(project_id=project.id, user_id=actor.id)
        )
        await self.session.commit()
        return reflection

    # ── درونی ──────────────────────────────────────────────────────────
    async def _require_member(self, project: Project, actor: CurrentUser) -> None:
        if await self.projects.membership(project.id, actor.id) is None:
            raise NotTeamMember

    async def _reward(self) -> Decimal | None:
        """امتیاز فعلی قاعده — مدیر آن را عوض می‌کند، پس ثابت در کد نمی‌گذاریم."""
        rule = await PointsService(self.session).rule(RULE_CODE)
        return rule.base_points if rule is not None and rule.is_active else None


__all__ = ["RULE_CODE", "ReflectionService", "ReflectionState"]
