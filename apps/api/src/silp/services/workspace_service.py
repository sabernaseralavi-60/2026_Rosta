"""تختهٔ وظایف و گفتگوی تیمی — FR-PRJ-06، M2-10.

عمداً ساده: سه ستون وظیفه و یک نخ یک‌سطحی. چت بی‌درنگ در فاز ۱ نیست
(§02) و تختهٔ وظایف هم جریان کاری قابل تنظیم ندارد — هر دو را می‌شود
بعداً اضافه کرد، ولی نمی‌شود پیچیدگی زودهنگام را پس گرفت.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from silp.core.exceptions import Conflict, NotFound, NotTeamMember, ValidationFailed
from silp.core.permissions import CurrentUser
from silp.models.delivery import TASK_STATUSES, Milestone, ProjectMessage, ProjectTask
from silp.models.project import Project
from silp.services.project_service import ProjectService

MAX_TASK_TITLE = 200
MAX_MESSAGE_LENGTH = 4000
DEFAULT_MESSAGE_PAGE = 50


@dataclass(slots=True)
class TaskDraft:
    title: str
    description: str | None = None
    assignee_id: uuid.UUID | None = None
    milestone_id: uuid.UUID | None = None
    due_on: date | None = None
    status: str = "TODO"
    sort_order: int = 0


def _now() -> datetime:
    return datetime.now(UTC)


class WorkspaceService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.projects = ProjectService(session)

    # ── وظایف ──────────────────────────────────────────────────────────
    async def tasks(self, project_id: uuid.UUID) -> list[ProjectTask]:
        rows = await self.session.scalars(
            select(ProjectTask)
            .where(ProjectTask.project_id == project_id)
            .order_by(ProjectTask.status, ProjectTask.sort_order, ProjectTask.created_at)
        )
        return list(rows)

    async def require_task(self, task_id: uuid.UUID, project_id: uuid.UUID) -> ProjectTask:
        task = await self.session.get(ProjectTask, task_id)
        if task is None or task.project_id != project_id:
            raise NotFound("این وظیفه پیدا نشد.")
        return task

    async def create_task(
        self, *, project: Project, actor: CurrentUser, draft: TaskDraft
    ) -> ProjectTask:
        await self._require_member(project, actor)
        _validate_task(draft)
        await self._validate_assignee(project, draft.assignee_id)
        await self._validate_milestone(project, draft.milestone_id)

        task = ProjectTask(
            project_id=project.id,
            milestone_id=draft.milestone_id,
            title=draft.title.strip(),
            description=(draft.description or "").strip() or None,
            assignee_id=draft.assignee_id,
            status=draft.status,
            due_on=draft.due_on,
            sort_order=draft.sort_order,
            created_by=actor.id,
        )
        self.session.add(task)
        project.last_activity_at = _now()
        await self.session.commit()
        return task

    async def update_task(
        self, *, project: Project, actor: CurrentUser, task: ProjectTask, draft: TaskDraft
    ) -> ProjectTask:
        """هر عضو تیم می‌تواند هر وظیفه را جابه‌جا کند.

        تختهٔ تیمی است، نه صندوق شخصی؛ قفل کردن وظیفه روی مسئولش یعنی
        کسی که کار را تمام کرده ولی مسئولش نیست، نمی‌تواند علامت بزند.
        """
        await self._require_member(project, actor)
        _validate_task(draft)
        await self._validate_assignee(project, draft.assignee_id)
        await self._validate_milestone(project, draft.milestone_id)

        task.title = draft.title.strip()
        task.description = (draft.description or "").strip() or None
        task.assignee_id = draft.assignee_id
        task.milestone_id = draft.milestone_id
        task.status = draft.status
        task.due_on = draft.due_on
        task.sort_order = draft.sort_order
        project.last_activity_at = _now()
        await self.session.commit()
        return task

    async def delete_task(self, *, project: Project, actor: CurrentUser, task: ProjectTask) -> None:
        await self._require_member(project, actor)
        await self.session.delete(task)
        project.last_activity_at = _now()
        await self.session.commit()

    # ── گفتگو ──────────────────────────────────────────────────────────
    async def messages(
        self, project_id: uuid.UUID, *, limit: int = DEFAULT_MESSAGE_PAGE
    ) -> list[ProjectMessage]:
        rows = await self.session.scalars(
            select(ProjectMessage)
            .where(ProjectMessage.project_id == project_id, ProjectMessage.deleted_at.is_(None))
            # شناسه هم در مرتب‌سازی می‌آید: `now()` در یک تراکنش ثابت
            # است، پس چند پیامِ یک درخواست `created_at` یکسان می‌گیرند و
            # بدون این، ترتیبشان دلبخواهی می‌شود. `uuidv7` زمان‌ترتیب است.
            .order_by(ProjectMessage.created_at.desc(), ProjectMessage.id.desc())
            .limit(limit)
        )
        return list(reversed(list(rows)))

    async def post_message(
        self,
        *,
        project: Project,
        actor: CurrentUser,
        body: str,
        parent_id: uuid.UUID | None = None,
        file_id: uuid.UUID | None = None,
    ) -> ProjectMessage:
        await self._require_member(project, actor)
        text = body.strip()
        if not text:
            raise ValidationFailed("پیام خالی فرستاده نمی‌شود.")
        if len(text) > MAX_MESSAGE_LENGTH:
            raise ValidationFailed(f"پیام حداکثر {MAX_MESSAGE_LENGTH} نویسه است.")

        if parent_id is not None:
            parent = await self.session.get(ProjectMessage, parent_id)
            if parent is None or parent.project_id != project.id or parent.deleted_at:
                raise NotFound("پیامی که به آن پاسخ داده‌اید پیدا نشد.")
            if parent.parent_id is not None:
                # §4.6 — نخ فقط یک سطح عمق دارد.
                raise Conflict("پاسخ به پاسخ ممکن نیست؛ زیر پیام اصلی بنویسید.")

        message = ProjectMessage(
            project_id=project.id,
            parent_id=parent_id,
            author_id=actor.id,
            body=text,
            file_id=file_id,
        )
        self.session.add(message)
        project.last_activity_at = _now()
        await self.session.commit()
        return message

    async def delete_message(
        self, *, project: Project, actor: CurrentUser, message_id: uuid.UUID
    ) -> None:
        message = await self.session.get(ProjectMessage, message_id)
        if message is None or message.project_id != project.id or message.deleted_at:
            raise NotFound("پیام پیدا نشد.")
        if message.author_id != actor.id and actor.id != project.lead_id:
            raise NotFound("پیام پیدا نشد.")
        message.deleted_at = _now()
        await self.session.commit()

    # ── درونی ──────────────────────────────────────────────────────────
    async def _require_member(self, project: Project, actor: CurrentUser) -> None:
        if await self.projects.membership(project.id, actor.id) is None:
            raise NotTeamMember

    async def _validate_assignee(self, project: Project, assignee_id: uuid.UUID | None) -> None:
        if assignee_id is None:
            return
        if await self.projects.membership(project.id, assignee_id) is None:
            raise ValidationFailed("مسئول وظیفه باید عضو فعال تیم باشد.")

    async def _validate_milestone(self, project: Project, milestone_id: uuid.UUID | None) -> None:
        if milestone_id is None:
            return
        milestone = await self.session.get(Milestone, milestone_id)
        if milestone is None or milestone.project_id != project.id:
            raise NotFound("این مرحله در پروژه تعریف نشده است.")


def _validate_task(draft: TaskDraft) -> None:
    if not draft.title.strip():
        raise ValidationFailed("عنوان وظیفه را خالی نگذارید.")
    if len(draft.title.strip()) > MAX_TASK_TITLE:
        raise ValidationFailed(f"عنوان وظیفه حداکثر {MAX_TASK_TITLE} نویسه است.")
    if draft.status not in TASK_STATUSES:
        raise ValidationFailed("وضعیت وظیفه معتبر نیست.")


__all__ = ["DEFAULT_MESSAGE_PAGE", "MAX_MESSAGE_LENGTH", "TaskDraft", "WorkspaceService"]
