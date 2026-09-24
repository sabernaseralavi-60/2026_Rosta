"""پروژه‌های تحت نظارت و صف واحد بررسی — PRD §3.5، ADR-0022.

«همهٔ تحویل‌دادنی‌های همهٔ ارائه‌ها در یک صف، نه پراکنده در ده صفحه.»

## چه پروژه‌ای «تحت نظارت» است

پروژه‌ای که استاد **مدیرش** است، یا `offering_id`اش یکی از ارائه‌های
استاد است. همان تعریفی که شمارندهٔ «تحویل منتظر» در داشبورد
(`TeachDashboardService`) به کار می‌برد — تا عددی که استاد در داشبورد
می‌بیند، همان طول صفی باشد که با یک کلیک باز می‌شود. تعریف یک‌جاست:
`supervision_scope`.

«ارائه‌های استاد» را فراخوان می‌دهد و از اعطاهای **تازه** می‌آید، نه از JWT؛
دستیار (`TA`) در آن نیست چون مجوز بررسی ندارد و صفی که نمی‌تواند در آن
کاری کند فقط ۴۰۳ می‌سازد.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from silp.models.delivery import Deliverable, Milestone
from silp.models.education import Course, CourseOffering
from silp.models.project import Project, Team, TeamMember
from silp.services.directory import display_names, name_of

OPEN_DELIVERABLE_STATUSES = ("SUBMITTED", "UNDER_REVIEW")
#: بیش از این در یک پاسخ نمی‌آید؛ صفی که از این بلندتر است، خودش نشانهٔ مشکل است
#: و `total` آن را می‌گوید.
MAX_QUEUE_ROWS = 200
EXCERPT_CHARS = 240

# «متوقف» پیش از «در خطر» و آن پیش از «سالم» — ترتیب حروف الفبا این را نمی‌دهد.
_HEALTH_RANK = case(
    (Project.health == "STALLED", 0),
    (Project.health == "AT_RISK", 1),
    else_=2,
)
# پروژه‌های جاری بالا؛ بسته‌شده‌ها و پیش‌نویس‌ها پایین.
_STATUS_RANK = case(
    (Project.status == "IN_PROGRESS", 0),
    (Project.status == "OPEN", 1),
    (Project.status == "PAUSED", 2),
    (Project.status == "DRAFT", 3),
    else_=4,
)


def supervision_scope(user_id: uuid.UUID, offering_ids: Iterable[uuid.UUID]) -> ColumnElement[bool]:
    """پروژه‌ای که کاربر مدیرش است یا در ارائه‌ای است که او استادش است."""
    return or_(Project.lead_id == user_id, Project.offering_id.in_(list(offering_ids)))


@dataclass(frozen=True, slots=True)
class SupervisedProject:
    project: Project
    course_title_fa: str | None
    lead_name: str | None
    active_members: int
    milestones_total: int
    milestones_approved: int
    milestones_overdue: int
    open_deliverables: int
    oldest_open_days: int | None
    days_inactive: int


@dataclass(frozen=True, slots=True)
class ReviewItem:
    deliverable_id: uuid.UUID
    project_id: uuid.UUID
    project_title_fa: str
    course_title_fa: str | None
    milestone_id: uuid.UUID
    milestone_title_fa: str
    submitter_id: uuid.UUID
    submitter_name: str | None
    version: int
    status: str
    is_late: bool
    submitted_at: datetime
    days_waiting: int
    excerpt: str | None
    link_count: int


@dataclass(frozen=True, slots=True)
class ReviewQueue:
    total: int
    oldest_days: int | None
    items: list[ReviewItem]


def _days_since(moment: datetime | None, now: datetime) -> int | None:
    if moment is None:
        return None
    return max((now - moment).days, 0)


def _excerpt(body: str | None) -> str | None:
    text = " ".join((body or "").split())
    if not text:
        return None
    return text if len(text) <= EXCERPT_CHARS else text[: EXCERPT_CHARS - 1] + "…"


class TeachProjectsService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def projects(
        self,
        user_id: uuid.UUID,
        offering_ids: Iterable[uuid.UUID],
        *,
        today: date | None = None,
        now: datetime | None = None,
    ) -> list[SupervisedProject]:
        """پروژه‌های تحت نظارت، «متوقف» و «در خطر» بالاتر از «سالم»."""
        now = now or datetime.now(UTC)
        today = today or now.date()
        rows = list(
            await self.session.execute(
                select(Project, Course.title_fa)
                .outerjoin(CourseOffering, CourseOffering.id == Project.offering_id)
                .outerjoin(Course, Course.id == CourseOffering.course_id)
                .where(
                    Project.deleted_at.is_(None),
                    Project.status != "CANCELLED",
                    supervision_scope(user_id, offering_ids),
                )
                .order_by(_STATUS_RANK, _HEALTH_RANK, Project.last_activity_at, Project.id)
            )
        )
        if not rows:
            return []
        ids = [p.id for p, _ in rows]

        member_rows = (
            await self.session.execute(
                select(Team.project_id, func.count(TeamMember.id))
                .join(TeamMember, TeamMember.team_id == Team.id)
                .where(Team.project_id.in_(ids), TeamMember.status == "ACTIVE")
                .group_by(Team.project_id)
            )
        ).tuples()
        members = dict(member_rows.all())
        milestones: dict[uuid.UUID, tuple[int, int, int]] = {}
        for pid, total, approved, overdue in (
            await self.session.execute(
                select(
                    Milestone.project_id,
                    func.count(),
                    func.count().filter(Milestone.status == "APPROVED"),
                    func.count().filter(
                        Milestone.status != "APPROVED",
                        Milestone.due_on.is_not(None),
                        Milestone.due_on < today,
                    ),
                )
                .where(Milestone.project_id.in_(ids))
                .group_by(Milestone.project_id)
            )
        ).tuples():
            milestones[pid] = (total, approved, overdue)
        pending: dict[uuid.UUID, tuple[int, datetime | None]] = {}
        for pid, count, first_at in (
            await self.session.execute(
                select(Milestone.project_id, func.count(), func.min(Deliverable.submitted_at))
                .select_from(Deliverable)
                .join(Milestone, Milestone.id == Deliverable.milestone_id)
                .where(
                    Milestone.project_id.in_(ids),
                    Deliverable.status.in_(OPEN_DELIVERABLE_STATUSES),
                )
                .group_by(Milestone.project_id)
            )
        ).tuples():
            pending[pid] = (count, first_at)

        names = await display_names(self.session, [p.lead_id for p, _ in rows])
        result: list[SupervisedProject] = []
        for project, course_title in rows:
            total, approved, overdue = milestones.get(project.id, (0, 0, 0))
            open_count, oldest = pending.get(project.id, (0, None))
            result.append(
                SupervisedProject(
                    project=project,
                    course_title_fa=course_title,
                    lead_name=name_of(names, project.lead_id),
                    active_members=members.get(project.id, 0),
                    milestones_total=total,
                    milestones_approved=approved,
                    milestones_overdue=overdue,
                    open_deliverables=open_count,
                    oldest_open_days=_days_since(oldest, now),
                    days_inactive=_days_since(project.last_activity_at, now) or 0,
                )
            )
        return result

    async def review_queue(
        self,
        user_id: uuid.UUID,
        offering_ids: Iterable[uuid.UUID],
        *,
        now: datetime | None = None,
    ) -> ReviewQueue:
        """تحویل‌های منتظر بررسی، قدیمی‌ترین اول — کسی که بیشتر منتظر مانده."""
        now = now or datetime.now(UTC)
        scope = (
            Project.deleted_at.is_(None),
            Project.status != "CANCELLED",
            Deliverable.status.in_(OPEN_DELIVERABLE_STATUSES),
            supervision_scope(user_id, offering_ids),
        )
        total, oldest = (
            await self.session.execute(
                select(func.count(Deliverable.id), func.min(Deliverable.submitted_at))
                .join(Milestone, Milestone.id == Deliverable.milestone_id)
                .join(Project, Project.id == Milestone.project_id)
                .where(*scope)
            )
        ).one()
        rows = list(
            await self.session.execute(
                select(
                    Deliverable.id,
                    Deliverable.submitter_id,
                    Deliverable.version,
                    Deliverable.status,
                    Deliverable.is_late,
                    Deliverable.submitted_at,
                    Deliverable.body,
                    func.coalesce(func.cardinality(Deliverable.links), 0),
                    Milestone.id,
                    Milestone.title_fa,
                    Project.id,
                    Project.title_fa,
                    Course.title_fa,
                )
                .join(Milestone, Milestone.id == Deliverable.milestone_id)
                .join(Project, Project.id == Milestone.project_id)
                .outerjoin(CourseOffering, CourseOffering.id == Project.offering_id)
                .outerjoin(Course, Course.id == CourseOffering.course_id)
                .where(*scope)
                .order_by(Deliverable.submitted_at, Deliverable.id)
                .limit(MAX_QUEUE_ROWS)
            )
        )
        names = await display_names(self.session, [r[1] for r in rows])
        items = [
            ReviewItem(
                deliverable_id=did,
                project_id=pid,
                project_title_fa=ptitle,
                course_title_fa=ctitle,
                milestone_id=mid,
                milestone_title_fa=mtitle,
                submitter_id=sid,
                submitter_name=name_of(names, sid),
                version=version,
                status=status,
                is_late=is_late,
                submitted_at=submitted_at,
                days_waiting=_days_since(submitted_at, now) or 0,
                excerpt=_excerpt(body),
                link_count=links,
            )
            for (
                did,
                sid,
                version,
                status,
                is_late,
                submitted_at,
                body,
                links,
                mid,
                mtitle,
                pid,
                ptitle,
                ctitle,
            ) in rows
        ]
        return ReviewQueue(total=total or 0, oldest_days=_days_since(oldest, now), items=items)


__all__ = [
    "MAX_QUEUE_ROWS",
    "ReviewItem",
    "ReviewQueue",
    "SupervisedProject",
    "TeachProjectsService",
    "supervision_scope",
]
