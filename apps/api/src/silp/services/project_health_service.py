"""به‌روزرسانی شبانهٔ شاخص سلامت پروژه — PRD §7.4، FR-PRJ-07، M5-12.

قاعده در `silp.domain.project_health` است؛ اینجا فقط پروژه‌ها خوانده و
نتیجه نوشته می‌شود. فقط ستونی که واقعاً عوض شده نوشته می‌شود، تا
`updated_at` پروژه‌ای که سلامتش همان دیروز است، هر شب بی‌دلیل تازه نشود.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from silp.core.logging import get_logger
from silp.domain.gamification.formulas import LOCAL_TZ
from silp.domain.project_health import MilestoneState, compute_health
from silp.models.delivery import Milestone
from silp.models.project import Project

log = get_logger("silp.project_health")


class ProjectHealthService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def recompute(self, *, today: date | None = None) -> int:
        """خروجی: تعداد پروژه‌هایی که سلامتشان عوض شد. بی‌اثر در تکرار."""
        day = today or datetime.now(UTC).astimezone(LOCAL_TZ).date()
        projects = list(
            await self.session.scalars(
                select(Project)
                .where(Project.status == "IN_PROGRESS", Project.deleted_at.is_(None))
                .with_for_update(skip_locked=True)
            )
        )
        if not projects:
            return 0

        milestones: dict[object, list[MilestoneState]] = defaultdict(list)
        for m in await self.session.scalars(
            select(Milestone).where(Milestone.project_id.in_([p.id for p in projects]))
        ):
            milestones[m.project_id].append(
                MilestoneState(due_on=m.due_on, status=m.status, is_required=m.is_required)
            )

        changed = 0
        for project in projects:
            verdict = compute_health(
                today=day,
                last_activity_on=project.last_activity_at.astimezone(LOCAL_TZ).date(),
                milestones=milestones[project.id],
                deadline_on=project.deadline_on,
            )
            if verdict.health != project.health:
                log.info(
                    "project_health_changed",
                    project_id=str(project.id),
                    before=project.health,
                    after=verdict.health,
                    reason=verdict.reason,
                )
                project.health = verdict.health
                changed += 1
        await self.session.commit()
        return changed


__all__ = ["ProjectHealthService"]
