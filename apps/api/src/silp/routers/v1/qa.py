"""مسیر پرسش‌وپاسخ درس — FR-EDU-07، ADR-0024 برش ج.

فهرست و ساخت زیر `/offerings/{id}/qa/threads` است (قلمرو ارائه)؛ کار روی یک
پرسش یا پاسخ زیر `/qa`. همه‌جا دسترسی از `QaService.offering_access` می‌آید:
بیرونی ۴۰۴ می‌گیرد، نه ۴۰۳.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, status

from silp.core.permissions import CurrentUser
from silp.models.qa import QaReply, QaThread
from silp.routers.deps import CurrentUserDep, SessionDep
from silp.schemas.common import ErrorResponse, Page, PageParams
from silp.schemas.idea import AuthorOut
from silp.schemas.qa import (
    ReplyIn,
    ReplyOut,
    ResolveIn,
    ThreadDetailOut,
    ThreadFilter,
    ThreadIn,
    ThreadSummaryOut,
)
from silp.services.directory import DisplayName, display_names
from silp.services.qa_service import QaAccess, QaService, ThreadRow

router = APIRouter(prefix="/qa", tags=["qa"])
offering_router = APIRouter(prefix="/offerings/{offering_id}/qa", tags=["qa"])

EXCERPT_LENGTH = 200
_NOT_FOUND: dict[int | str, dict[str, Any]] = {404: {"model": ErrorResponse}}


def get_qa_service(session: SessionDep) -> QaService:
    return QaService(session)


QaServiceDep = Annotated[QaService, Depends(get_qa_service)]


def _excerpt(text: str) -> str:
    cleaned = " ".join(text.split())
    return cleaned if len(cleaned) <= EXCERPT_LENGTH else cleaned[: EXCERPT_LENGTH - 1] + "…"


def _author(user_id: uuid.UUID, names: dict[uuid.UUID, DisplayName]) -> AuthorOut:
    entry = names.get(user_id)
    return AuthorOut(
        id=user_id,
        name=entry.full_name if entry else None,
        username=entry.username if entry else None,
    )


def _summary(
    service: QaService,
    row: ThreadRow,
    access: QaAccess,
    viewer: CurrentUser,
    names: dict[uuid.UUID, DisplayName],
) -> ThreadSummaryOut:
    thread = row.thread
    visible = service.author_visible(thread, access, viewer)
    return ThreadSummaryOut(
        id=thread.id,
        offering_id=thread.offering_id,
        week_number=row.week_number,
        title=thread.title,
        excerpt=_excerpt(thread.body),
        author=_author(thread.author_id, names) if visible else None,
        is_anonymous=thread.is_anonymous,
        is_resolved=thread.is_resolved,
        reply_count=row.reply_count,
        has_official_answer=row.has_official_answer,
        is_mine=thread.author_id == viewer.id,
        created_at=thread.created_at,
    )


def _reply(
    reply: QaReply,
    access: QaAccess,
    viewer: CurrentUser,
    names: dict[uuid.UUID, DisplayName],
    voted: set[uuid.UUID],
) -> ReplyOut:
    mine = reply.author_id == viewer.id
    return ReplyOut(
        id=reply.id,
        thread_id=reply.thread_id,
        body=reply.body,
        author=_author(reply.author_id, names),
        is_official=reply.is_official,
        helpful_count=reply.helpful_count,
        voted_by_me=reply.id in voted,
        is_endorsed=reply.endorsed_at is not None,
        endorsed_at=reply.endorsed_at,
        is_mine=mine,
        can_vote=not mine,
        can_endorse=access.is_manager and not mine and not reply.is_official,
        can_delete=mine or access.is_manager,
        created_at=reply.created_at,
    )


async def _detail(
    service: QaService,
    thread: QaThread,
    access: QaAccess,
    viewer: CurrentUser,
    week_number: int | None,
) -> ThreadDetailOut:
    replies = await service.replies(thread.id)
    names = await display_names(
        service.session, [thread.author_id, *(r.author_id for r in replies)]
    )
    voted = await service.voted_by(viewer.id, [r.id for r in replies])
    mine = thread.author_id == viewer.id
    row = ThreadRow(
        thread,
        week_number,
        len(replies),
        any(r.is_official or r.endorsed_at is not None for r in replies),
    )
    return ThreadDetailOut(
        **_summary(service, row, access, viewer, names).model_dump(),
        body=thread.body,
        replies=[_reply(r, access, viewer, names, voted) for r in replies],
        can_resolve=mine or access.is_manager,
        can_delete=access.is_manager or (mine and all(r.author_id == viewer.id for r in replies)),
        is_manager=access.is_manager,
    )


# ── فهرست و ساخت — قلمرو ارائه ─────────────────────────────────────────
@offering_router.get(
    "/threads",
    response_model=Page[ThreadSummaryOut],
    summary="پرسش‌های درس — بی‌پاسخ اول",
    responses=_NOT_FOUND,
)
async def list_threads(
    offering_id: uuid.UUID,
    service: QaServiceDep,
    current: CurrentUserDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    week_number: Annotated[int | None, Query(ge=1, le=52)] = None,
    filter_: Annotated[ThreadFilter, Query(alias="filter")] = "all",
) -> Page[ThreadSummaryOut]:
    """ADR-0024 بند ۲۰ — `week_number` برگهٔ «پرسش‌وپاسخ» صفحهٔ هفته را می‌سازد."""
    access = await service.offering_access(offering_id, current)
    params = PageParams(page=page, page_size=page_size)
    rows, total = await service.list_threads(
        access,
        current,
        week_number=week_number,
        filter_=filter_,
        offset=params.offset,
        limit=params.page_size,
    )
    names = await display_names(service.session, [r.thread.author_id for r in rows])
    return Page.of(
        [_summary(service, r, access, current, names) for r in rows],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )


@offering_router.post(
    "/threads",
    response_model=ThreadDetailOut,
    status_code=status.HTTP_201_CREATED,
    summary="پرسیدن",
    responses={**_NOT_FOUND, 422: {"model": ErrorResponse}},
)
async def create_thread(
    offering_id: uuid.UUID,
    payload: ThreadIn,
    service: QaServiceDep,
    current: CurrentUserDep,
) -> ThreadDetailOut:
    access = await service.offering_access(offering_id, current)
    thread = await service.create_thread(
        access,
        current,
        title=payload.title,
        body=payload.body,
        week_number=payload.week_number,
        is_anonymous=payload.is_anonymous,
    )
    return await _detail(service, thread, access, current, payload.week_number)


# ── یک پرسش ────────────────────────────────────────────────────────────
@router.get(
    "/threads/{thread_id}",
    response_model=ThreadDetailOut,
    summary="پرسش و پاسخ‌هایش",
    responses=_NOT_FOUND,
)
async def get_thread(
    thread_id: uuid.UUID, service: QaServiceDep, current: CurrentUserDep
) -> ThreadDetailOut:
    thread, access, week_number = await service.thread_access(thread_id, current)
    return await _detail(service, thread, access, current, week_number)


@router.patch(
    "/threads/{thread_id}",
    response_model=ThreadDetailOut,
    summary="حل‌شده کردن پرسش (پرسنده یا استاد)",
    responses={**_NOT_FOUND, 403: {"model": ErrorResponse}},
)
async def resolve_thread(
    thread_id: uuid.UUID, payload: ResolveIn, service: QaServiceDep, current: CurrentUserDep
) -> ThreadDetailOut:
    thread, access, week_number = await service.thread_access(thread_id, current)
    thread = await service.set_resolved(thread, access, current, resolved=payload.is_resolved)
    return await _detail(service, thread, access, current, week_number)


@router.delete(
    "/threads/{thread_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="حذف پرسش (پرسنده تا پیش از اولین پاسخ؛ استاد همیشه)",
    responses={**_NOT_FOUND, 403: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
async def delete_thread(
    thread_id: uuid.UUID, service: QaServiceDep, current: CurrentUserDep
) -> None:
    thread, access, _ = await service.thread_access(thread_id, current)
    await service.delete_thread(thread, access, current)


@router.post(
    "/threads/{thread_id}/replies",
    response_model=ReplyOut,
    status_code=status.HTTP_201_CREATED,
    summary="پاسخ دادن",
    responses={**_NOT_FOUND, 422: {"model": ErrorResponse}},
)
async def post_reply(
    thread_id: uuid.UUID, payload: ReplyIn, service: QaServiceDep, current: CurrentUserDep
) -> ReplyOut:
    thread, access, _ = await service.thread_access(thread_id, current)
    reply = await service.post_reply(thread, access, current, body=payload.body)
    names = await display_names(service.session, [reply.author_id])
    return _reply(reply, access, current, names, set())


# ── یک پاسخ ────────────────────────────────────────────────────────────
async def _reply_out(
    service: QaService, reply: QaReply, access: QaAccess, current: CurrentUser
) -> ReplyOut:
    names = await display_names(service.session, [reply.author_id])
    voted = await service.voted_by(current.id, [reply.id])
    return _reply(reply, access, current, names, voted)


@router.delete(
    "/replies/{reply_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="حذف پاسخ (نویسنده یا استاد) — امتیازش برمی‌گردد",
    responses={**_NOT_FOUND, 403: {"model": ErrorResponse}},
)
async def delete_reply(reply_id: uuid.UUID, service: QaServiceDep, current: CurrentUserDep) -> None:
    reply, _, access = await service.reply_access(reply_id, current)
    await service.delete_reply(reply, access, current)


@router.post(
    "/replies/{reply_id}/vote",
    response_model=ReplyOut,
    summary="رأی «مفید»",
    responses={
        **_NOT_FOUND,
        409: {"model": ErrorResponse, "description": "DUPLICATE_VOTE | پاسخ خودت"},
    },
)
async def vote_reply(
    reply_id: uuid.UUID, service: QaServiceDep, current: CurrentUserDep
) -> ReplyOut:
    reply, _, access = await service.reply_access(reply_id, current)
    reply = await service.vote(reply, current)
    return await _reply_out(service, reply, access, current)


@router.delete(
    "/replies/{reply_id}/vote",
    response_model=ReplyOut,
    summary="پس‌گرفتن رأی — امتیازِ رسیده برنمی‌گردد",
    responses=_NOT_FOUND,
)
async def unvote_reply(
    reply_id: uuid.UUID, service: QaServiceDep, current: CurrentUserDep
) -> ReplyOut:
    reply, _, access = await service.reply_access(reply_id, current)
    reply = await service.unvote(reply, current)
    return await _reply_out(service, reply, access, current)


@router.post(
    "/replies/{reply_id}/endorse",
    response_model=ReplyOut,
    summary="تأیید استاد بر پاسخ دانشجو",
    responses={**_NOT_FOUND, 403: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
async def endorse_reply(
    reply_id: uuid.UUID, service: QaServiceDep, current: CurrentUserDep
) -> ReplyOut:
    reply, _, access = await service.reply_access(reply_id, current)
    reply = await service.endorse(reply, access, current)
    return await _reply_out(service, reply, access, current)


@router.delete(
    "/replies/{reply_id}/endorse",
    response_model=ReplyOut,
    summary="برداشتن تأیید — امتیازش برمی‌گردد",
    responses={**_NOT_FOUND, 403: {"model": ErrorResponse}},
)
async def unendorse_reply(
    reply_id: uuid.UUID, service: QaServiceDep, current: CurrentUserDep
) -> ReplyOut:
    reply, _, access = await service.reply_access(reply_id, current)
    reply = await service.unendorse(reply, access)
    return await _reply_out(service, reply, access, current)
