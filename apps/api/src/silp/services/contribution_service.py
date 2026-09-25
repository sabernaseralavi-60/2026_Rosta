"""تحلیل مشارکت تیمی — FR-PRJ-08، ADR-0026.

فقط می‌خواند: چهار `GROUP BY` روی جدول‌های موجود و هیچ نوشتنی، امتیازی یا
اعلانی. قاعدهٔ سهم در `silp.domain.contribution` است؛ اینجا فقط دید و شمارش.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from silp.core.exceptions import Conflict, NotTeamMember
from silp.core.permissions import CurrentUser, Permission
from silp.domain import contribution as rules
from silp.models.delivery import Deliverable, Milestone, ProjectMessage, ProjectTask
from silp.models.project import Project, TeamMember
from silp.models.venture import VentureMetric
from silp.services import authz
from silp.services.directory import display_names, name_of
from silp.services.project_service import ProjectService

TEAM = "TEAM"
SELF = "SELF"


@dataclass(frozen=True, slots=True)
class ContributionMember:
    user_id: uuid.UUID
    full_name: str | None
    status: str
    is_lead: bool
    joined_at: datetime
    left_at: datetime | None
    share: rules.MemberShare


@dataclass(frozen=True, slots=True)
class ContributionReport:
    scope: str
    effective_weights: dict[str, float]
    #: فقط برای `TEAM`؛ عضو عادی جمع کل تیم را نمی‌بیند (ADR-0026 بند ۵).
    team_totals: dict[str, int]
    members: list[ContributionMember]


class ContributionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.projects = ProjectService(session)

    async def report(self, *, project: Project, actor: CurrentUser) -> ContributionReport:
        membership = await self.projects.membership(project.id, actor.id)
        oversight = (membership is not None and membership.is_lead) or await authz.has_permission(
            self.session, actor, Permission.PROJECT_CLOSE, project.id
        )
        if membership is None and not oversight:
            raise NotTeamMember
        if project.status in ("DRAFT", "OPEN"):
            raise Conflict("پروژه هنوز تیمی ندارد؛ تحلیل مشارکت پس از شروع پروژه در دسترس است.")

        # کسی که رفته و برگشته چند ردیف دارد؛ آخرین عضویت او را نمایندگی می‌کند
        # و شمارهایش دوبار در جمع تیم نمی‌آید.
        rows = {m.user_id: m for m in await self.projects.members(project.id)}
        counts = await self._counts(project.id)
        analysis = rules.analyse(
            [
                rules.MemberCounts(
                    user_id=m.user_id,
                    counts={d: counts[d].get(m.user_id, 0) for d in rules.DIMENSIONS},
                    is_active=m.status == "ACTIVE",
                )
                for m in rows.values()
            ]
        )
        by_user = {share.user_id: share for share in analysis.members}
        names = await display_names(self.session, list(rows))

        visible = [uid for uid in by_user if oversight or uid == actor.id]
        return ContributionReport(
            scope=TEAM if oversight else SELF,
            effective_weights=analysis.effective_weights,
            team_totals=analysis.team_totals if oversight else {},
            members=[_member(rows[uid], name_of(names, uid), by_user[uid]) for uid in visible],
        )

    async def _counts(self, project_id: uuid.UUID) -> dict[str, dict[uuid.UUID, int]]:
        """کد بُعد ← (کاربر ← شمار). هر بُعد یک پرس‌وجوی تجمیعی."""
        s = self.session
        approved = await s.execute(
            select(Deliverable.submitter_id, func.count())
            .join(Milestone, Milestone.id == Deliverable.milestone_id)
            .where(Milestone.project_id == project_id, Deliverable.status == "APPROVED")
            .group_by(Deliverable.submitter_id)
        )
        verified = await s.execute(
            select(VentureMetric.user_id, func.count())
            .where(VentureMetric.project_id == project_id, VentureMetric.status == "VERIFIED")
            .group_by(VentureMetric.user_id)
        )
        done = await s.execute(
            select(ProjectTask.assignee_id, func.count())
            .where(
                ProjectTask.project_id == project_id,
                ProjectTask.status == "DONE",
                ProjectTask.assignee_id.is_not(None),
            )
            .group_by(ProjectTask.assignee_id)
        )
        posted = await s.execute(
            select(ProjectMessage.author_id, func.count())
            .where(ProjectMessage.project_id == project_id, ProjectMessage.deleted_at.is_(None))
            .group_by(ProjectMessage.author_id)
        )
        return {
            rules.DELIVERABLES: dict(approved.tuples().all()),
            rules.VERIFIED_ACTIVITY: dict(verified.tuples().all()),
            rules.TASKS: {uid: n for uid, n in done.tuples().all() if uid is not None},
            rules.DISCUSSION: dict(posted.tuples().all()),
        }


def _member(row: TeamMember, full_name: str | None, share: rules.MemberShare) -> ContributionMember:
    return ContributionMember(
        user_id=row.user_id,
        full_name=full_name,
        status=row.status,
        is_lead=row.is_lead,
        joined_at=row.joined_at,
        left_at=row.left_at,
        share=share,
    )


__all__ = ["SELF", "TEAM", "ContributionMember", "ContributionReport", "ContributionService"]
