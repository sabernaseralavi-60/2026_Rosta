"""فضای کاری پروژه — مرحله، تحویل‌دادنی، تختهٔ وظایف و گفتگو.

مرجع: §5.7، FR-PRJ-05، FR-PRJ-06، §7.6.

هر چیزی که اینجاست فقط برای عضو تیم (یا سرپرست پروژه) دیده می‌شود.
بررسی دسترسی دو لایه است: `require(...)` در مسیر و بررسی عضویت در
سرویس — §6.4 قاعدهٔ ۲.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from silp.core.permissions import CurrentUser, Permission
from silp.models.delivery import (
    DELIVERABLE_STATUS_TITLE_FA,
    MILESTONE_STATUS_TITLE_FA,
    OUTPUT_KIND_TITLE_FA,
    TASK_STATUS_TITLE_FA,
    Deliverable,
    Milestone,
    ProjectMessage,
    ProjectTask,
)
from silp.models.file import File
from silp.routers.deps import (
    CurrentUserDep,
    DeliveryServiceDep,
    FileServiceDep,
    ProjectServiceDep,
    SessionDep,
    WorkspaceServiceDep,
    project_from_path,
    project_of_deliverable,
    project_of_milestone,
    require,
)
from silp.schemas.common import ErrorResponse
from silp.schemas.delivery import (
    DeliverableIn,
    DeliverableOut,
    MessageIn,
    MessageOut,
    MilestoneIn,
    MilestoneOut,
    ReviewIn,
    ReviewOut,
    TaskIn,
    TaskOut,
)
from silp.schemas.file import FileOut
from silp.services.delivery_service import MilestoneDraft
from silp.services.directory import display_names, name_of
from silp.services.workspace_service import DEFAULT_MESSAGE_PAGE, TaskDraft

router = APIRouter(prefix="/projects", tags=["projects"])
milestone_router = APIRouter(prefix="/milestones", tags=["projects"])
deliverable_router = APIRouter(prefix="/deliverables", tags=["projects"])


# ── تبدیل ──────────────────────────────────────────────────────────────
def _milestone_out(
    milestone: Milestone,
    *,
    my_deliverable: DeliverableOut | None = None,
    deliverable_count: int = 0,
) -> MilestoneOut:
    return MilestoneOut(
        id=milestone.id,
        project_id=milestone.project_id,
        title_fa=milestone.title_fa,
        description=milestone.description,
        sort_order=milestone.sort_order,
        due_on=milestone.due_on,
        points=float(milestone.points),
        is_required=milestone.is_required,
        output_kind=milestone.output_kind,
        output_kind_fa=(
            OUTPUT_KIND_TITLE_FA.get(milestone.output_kind) if milestone.output_kind else None
        ),
        checklist=[str(item) for item in milestone.checklist],
        status=milestone.status,
        status_fa=MILESTONE_STATUS_TITLE_FA.get(milestone.status, milestone.status),
        approved_at=milestone.approved_at,
        my_deliverable=my_deliverable,
        deliverable_count=deliverable_count,
    )


def _deliverable_out(
    deliverable: Deliverable,
    *,
    submitter_name: str | None = None,
    files: list[FileOut] | None = None,
) -> DeliverableOut:
    return DeliverableOut(
        id=deliverable.id,
        milestone_id=deliverable.milestone_id,
        submitter_id=deliverable.submitter_id,
        submitter_name=submitter_name,
        version=deliverable.version,
        body=deliverable.body,
        links=list(deliverable.links),
        status=deliverable.status,
        status_fa=DELIVERABLE_STATUS_TITLE_FA.get(deliverable.status, deliverable.status),
        is_late=deliverable.is_late,
        score=float(deliverable.score) if deliverable.score is not None else None,
        feedback=deliverable.feedback,
        rubric_scores=deliverable.rubric_scores,
        reviewed_by=deliverable.reviewed_by,
        reviewed_at=deliverable.reviewed_at,
        submitted_at=deliverable.submitted_at,
        files=files or [],
    )


async def _files_of(
    session: AsyncSession, deliverable_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[FileOut]]:
    """پیوست‌های چند تحویل‌دادنی در یک کوئری — §5.14."""
    if not deliverable_ids:
        return {}
    from silp.models.delivery import DeliverableFile

    rows = await session.execute(
        select(DeliverableFile.deliverable_id, File)
        .join(File, File.id == DeliverableFile.file_id)
        .where(
            DeliverableFile.deliverable_id.in_(deliverable_ids),
            File.deleted_at.is_(None),
        )
    )
    grouped: dict[uuid.UUID, list[FileOut]] = {}
    for deliverable_id, file in rows:
        grouped.setdefault(deliverable_id, []).append(FileOut.model_validate(file))
    return grouped


async def _deliverables_out(session: AsyncSession, rows: list[Deliverable]) -> list[DeliverableOut]:
    if not rows:
        return []
    names = await display_names(session, [r.submitter_id for r in rows])
    files = await _files_of(session, [r.id for r in rows])
    return [
        _deliverable_out(
            r, submitter_name=name_of(names, r.submitter_id), files=files.get(r.id, [])
        )
        for r in rows
    ]


# ── مرحله — FR-PRJ-05 ──────────────────────────────────────────────────
@router.get(
    "/{project_id}/milestones",
    response_model=list[MilestoneOut],
    summary="مراحل پروژه",
    responses={403: {"model": ErrorResponse}},
)
async def list_milestones(
    project_id: uuid.UUID,
    current: CurrentUserDep,
    projects: ProjectServiceDep,
    delivery: DeliveryServiceDep,
    session: SessionDep,
) -> list[MilestoneOut]:
    """مراحل به‌همراه «تحویل من» برای هر مرحله.

    «تحویل من» آخرین نسخهٔ خود کاربر است، نه نسخهٔ همهٔ اعضا: دانشجو
    باید وضعیت کار خودش را ببیند، و مدیر پروژه صف بررسی جداگانه دارد.
    """
    await projects.require_member(project_id, current)
    milestones = await delivery.milestones(project_id)
    if not milestones:
        return []

    ids = [m.id for m in milestones]
    count_rows = await session.execute(
        select(Deliverable.milestone_id, func.count())
        .where(Deliverable.milestone_id.in_(ids))
        .group_by(Deliverable.milestone_id)
    )
    counts = dict(count_rows.tuples().all())
    mine = list(
        await session.scalars(
            select(Deliverable)
            .where(
                Deliverable.milestone_id.in_(ids),
                Deliverable.submitter_id == current.id,
            )
            .order_by(Deliverable.milestone_id, Deliverable.version)
        )
    )
    latest: dict[uuid.UUID, Deliverable] = {d.milestone_id: d for d in mine}
    presented = await _deliverables_out(session, list(latest.values()))
    by_milestone = {d.milestone_id: d for d in presented}

    return [
        _milestone_out(
            m,
            my_deliverable=by_milestone.get(m.id),
            deliverable_count=int(counts.get(m.id, 0)),
        )
        for m in milestones
    ]


@router.post(
    "/{project_id}/milestones",
    response_model=MilestoneOut,
    status_code=status.HTTP_201_CREATED,
    summary="تعریف مرحله",
    responses={403: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
async def create_milestone(
    project_id: uuid.UUID,
    payload: MilestoneIn,
    projects: ProjectServiceDep,
    delivery: DeliveryServiceDep,
    current: Annotated[
        CurrentUser,
        Depends(require(Permission.PROJECT_MILESTONE_MANAGE, scope=project_from_path)),
    ],
) -> MilestoneOut:
    milestone = await delivery.create_milestone(
        project=await projects.require(project_id),
        actor=current,
        draft=_milestone_draft(payload),
    )
    return _milestone_out(milestone)


@milestone_router.patch(
    "/{milestone_id}",
    response_model=MilestoneOut,
    summary="ویرایش مرحله",
    responses={403: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
async def update_milestone(
    milestone_id: uuid.UUID,
    payload: MilestoneIn,
    projects: ProjectServiceDep,
    delivery: DeliveryServiceDep,
    current: Annotated[
        CurrentUser,
        Depends(require(Permission.PROJECT_MILESTONE_MANAGE, scope=project_of_milestone)),
    ],
) -> MilestoneOut:
    milestone = await delivery.require_milestone(milestone_id)
    project = await projects.require(milestone.project_id)
    milestone = await delivery.update_milestone(
        milestone=milestone, project=project, actor=current, draft=_milestone_draft(payload)
    )
    return _milestone_out(milestone)


@milestone_router.delete(
    "/{milestone_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="حذف مرحله",
    responses={403: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
async def delete_milestone(
    milestone_id: uuid.UUID,
    projects: ProjectServiceDep,
    delivery: DeliveryServiceDep,
    _: Annotated[
        CurrentUser,
        Depends(require(Permission.PROJECT_MILESTONE_MANAGE, scope=project_of_milestone)),
    ],
) -> None:
    milestone = await delivery.require_milestone(milestone_id)
    project = await projects.require(milestone.project_id)
    await delivery.delete_milestone(milestone=milestone, project=project)


# ── تحویل‌دادنی — §7.6 ─────────────────────────────────────────────────
@milestone_router.get(
    "/{milestone_id}/deliverables",
    response_model=list[DeliverableOut],
    summary="تاریخچهٔ نسخه‌های یک مرحله",
    responses={403: {"model": ErrorResponse}},
)
async def list_deliverables(
    milestone_id: uuid.UUID,
    current: CurrentUserDep,
    delivery: DeliveryServiceDep,
    projects: ProjectServiceDep,
    session: SessionDep,
) -> list[DeliverableOut]:
    milestone = await delivery.require_milestone(milestone_id)
    await projects.require_member(milestone.project_id, current)
    rows = await delivery.deliverables(milestone_id)
    return await _deliverables_out(session, rows)


@milestone_router.post(
    "/{milestone_id}/deliverables",
    response_model=DeliverableOut,
    status_code=status.HTTP_201_CREATED,
    summary="ارسال تحویل‌دادنی",
    responses={
        403: {"model": ErrorResponse, "description": "NOT_TEAM_MEMBER"},
        409: {"model": ErrorResponse, "description": "MILESTONE_NOT_OPEN"},
    },
)
async def submit_deliverable(
    milestone_id: uuid.UUID,
    payload: DeliverableIn,
    delivery: DeliveryServiceDep,
    projects: ProjectServiceDep,
    files: FileServiceDep,
    session: SessionDep,
    current: Annotated[
        CurrentUser, Depends(require(Permission.DELIVERABLE_SUBMIT, scope=project_of_milestone))
    ],
) -> DeliverableOut:
    """§7.6 — هر ارسال یک نسخهٔ تازه است؛ نسخهٔ قبلی دست‌نخورده می‌ماند."""
    milestone = await delivery.require_milestone(milestone_id)
    project = await projects.require(milestone.project_id)
    # فایل‌ها پیش از ساخت ردیف بررسی می‌شوند: تحویل‌دادنی با پیوست
    # نامعتبر نباید اصلاً ساخته شود.
    attachments = await files.load_attachable(list(payload.file_ids), owner_id=current.id)

    deliverable = await delivery.submit(
        milestone=milestone,
        project=project,
        actor=current,
        body=payload.body,
        links=list(payload.links),
        file_ids=[f.id for f in attachments],
    )
    names = await display_names(session, [deliverable.submitter_id])
    return _deliverable_out(
        deliverable,
        submitter_name=name_of(names, deliverable.submitter_id),
        files=[FileOut.model_validate(f) for f in attachments],
    )


@deliverable_router.post(
    "/{deliverable_id}/review",
    response_model=ReviewOut,
    summary="بررسی و بازخورد",
    responses={403: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
async def review_deliverable(
    deliverable_id: uuid.UUID,
    payload: ReviewIn,
    delivery: DeliveryServiceDep,
    session: SessionDep,
    current: Annotated[
        CurrentUser, Depends(require(Permission.DELIVERABLE_REVIEW, scope=project_of_deliverable))
    ],
) -> ReviewOut:
    """§7.6 — «اصلاح کن» و «رد» بدون بازخورد متنی پذیرفته نمی‌شوند."""
    deliverable = await delivery.require_deliverable(deliverable_id)
    outcome = await delivery.review(
        deliverable=deliverable,
        actor=current,
        decision=payload.decision,
        feedback=payload.feedback,
        score=payload.score,
        rubric_scores=payload.rubric_scores,
    )
    presented = await _deliverables_out(session, [outcome.deliverable])
    return ReviewOut(
        deliverable=presented[0],
        milestone=_milestone_out(outcome.milestone),
        project_ready_to_close=outcome.project_ready_to_close,
    )


@router.get(
    "/{project_id}/review-queue",
    response_model=list[DeliverableOut],
    summary="صف بررسی پروژه",
    responses={403: {"model": ErrorResponse}},
)
async def review_queue(
    project_id: uuid.UUID,
    delivery: DeliveryServiceDep,
    session: SessionDep,
    _: Annotated[
        CurrentUser, Depends(require(Permission.DELIVERABLE_REVIEW, scope=project_from_path))
    ],
) -> list[DeliverableOut]:
    rows = await delivery.review_queue(project_id)
    return await _deliverables_out(session, rows)


# ── تختهٔ وظایف — FR-PRJ-06 ────────────────────────────────────────────
def _task_out(task: ProjectTask, *, assignee_name: str | None = None) -> TaskOut:
    return TaskOut(
        id=task.id,
        project_id=task.project_id,
        milestone_id=task.milestone_id,
        title=task.title,
        description=task.description,
        assignee_id=task.assignee_id,
        assignee_name=assignee_name,
        status=task.status,
        status_fa=TASK_STATUS_TITLE_FA.get(task.status, task.status),
        due_on=task.due_on,
        sort_order=task.sort_order,
        created_at=task.created_at,
    )


def _task_draft(payload: TaskIn) -> TaskDraft:
    return TaskDraft(
        title=payload.title,
        description=payload.description,
        assignee_id=payload.assignee_id,
        milestone_id=payload.milestone_id,
        due_on=payload.due_on,
        status=payload.status,
        sort_order=payload.sort_order,
    )


def _milestone_draft(payload: MilestoneIn) -> MilestoneDraft:
    return MilestoneDraft(
        title_fa=payload.title_fa,
        description=payload.description,
        sort_order=payload.sort_order,
        due_on=payload.due_on,
        points=payload.points,
        is_required=payload.is_required,
        output_kind=payload.output_kind,
        checklist=list(payload.checklist),
    )


@router.get(
    "/{project_id}/tasks",
    response_model=list[TaskOut],
    summary="تختهٔ وظایف",
    responses={403: {"model": ErrorResponse}},
)
async def list_tasks(
    project_id: uuid.UUID,
    current: CurrentUserDep,
    projects: ProjectServiceDep,
    workspace: WorkspaceServiceDep,
    session: SessionDep,
) -> list[TaskOut]:
    await projects.require_member(project_id, current)
    rows = await workspace.tasks(project_id)
    names = await display_names(session, [t.assignee_id for t in rows if t.assignee_id])
    return [_task_out(t, assignee_name=name_of(names, t.assignee_id)) for t in rows]


@router.post(
    "/{project_id}/tasks",
    response_model=TaskOut,
    status_code=status.HTTP_201_CREATED,
    summary="افزودن وظیفه",
    responses={403: {"model": ErrorResponse}},
)
async def create_task(
    project_id: uuid.UUID,
    payload: TaskIn,
    current: CurrentUserDep,
    projects: ProjectServiceDep,
    workspace: WorkspaceServiceDep,
) -> TaskOut:
    task = await workspace.create_task(
        project=await projects.require(project_id), actor=current, draft=_task_draft(payload)
    )
    return _task_out(task)


@router.patch(
    "/{project_id}/tasks/{task_id}",
    response_model=TaskOut,
    summary="ویرایش وظیفه",
    responses={403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
async def update_task(
    project_id: uuid.UUID,
    task_id: uuid.UUID,
    payload: TaskIn,
    current: CurrentUserDep,
    projects: ProjectServiceDep,
    workspace: WorkspaceServiceDep,
) -> TaskOut:
    project = await projects.require(project_id)
    task = await workspace.require_task(task_id, project_id)
    task = await workspace.update_task(
        project=project, actor=current, task=task, draft=_task_draft(payload)
    )
    return _task_out(task)


@router.delete(
    "/{project_id}/tasks/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="حذف وظیفه",
    responses={403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
async def delete_task(
    project_id: uuid.UUID,
    task_id: uuid.UUID,
    current: CurrentUserDep,
    projects: ProjectServiceDep,
    workspace: WorkspaceServiceDep,
) -> None:
    project = await projects.require(project_id)
    task = await workspace.require_task(task_id, project_id)
    await workspace.delete_task(project=project, actor=current, task=task)


# ── گفتگو — FR-PRJ-06 ──────────────────────────────────────────────────
def _message_out(message: ProjectMessage, *, author_name: str | None = None) -> MessageOut:
    return MessageOut(
        id=message.id,
        parent_id=message.parent_id,
        author_id=message.author_id,
        author_name=author_name,
        body=message.body,
        file_id=message.file_id,
        created_at=message.created_at,
        edited_at=message.edited_at,
    )


@router.get(
    "/{project_id}/discussion",
    response_model=list[MessageOut],
    summary="گفتگوی تیمی",
    responses={403: {"model": ErrorResponse}},
)
async def list_messages(
    project_id: uuid.UUID,
    current: CurrentUserDep,
    projects: ProjectServiceDep,
    workspace: WorkspaceServiceDep,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=200)] = DEFAULT_MESSAGE_PAGE,
) -> list[MessageOut]:
    await projects.require_member(project_id, current)
    rows = await workspace.messages(project_id, limit=limit)
    names = await display_names(session, [m.author_id for m in rows])
    return [_message_out(m, author_name=name_of(names, m.author_id)) for m in rows]


@router.post(
    "/{project_id}/discussion",
    response_model=MessageOut,
    status_code=status.HTTP_201_CREATED,
    summary="ارسال پیام",
    responses={403: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
async def post_message(
    project_id: uuid.UUID,
    payload: MessageIn,
    current: CurrentUserDep,
    projects: ProjectServiceDep,
    workspace: WorkspaceServiceDep,
    files: FileServiceDep,
    session: SessionDep,
) -> MessageOut:
    project = await projects.require(project_id)
    if payload.file_id is not None:
        await files.load_attachable([payload.file_id], owner_id=current.id)
    message = await workspace.post_message(
        project=project,
        actor=current,
        body=payload.body,
        parent_id=payload.parent_id,
        file_id=payload.file_id,
    )
    names = await display_names(session, [message.author_id])
    return _message_out(message, author_name=name_of(names, message.author_id))


@router.delete(
    "/{project_id}/discussion/{message_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="حذف پیام",
    responses={404: {"model": ErrorResponse}},
)
async def delete_message(
    project_id: uuid.UUID,
    message_id: uuid.UUID,
    current: CurrentUserDep,
    projects: ProjectServiceDep,
    workspace: WorkspaceServiceDep,
) -> None:
    project = await projects.require(project_id)
    await workspace.delete_message(project=project, actor=current, message_id=message_id)


__all__ = ["deliverable_router", "milestone_router", "router"]
