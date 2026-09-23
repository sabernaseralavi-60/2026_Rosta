"""مسیر /ideas — §5.8، FR-IDEA-01/02/03.

فهرست و صفحهٔ ایده عمومی‌اند (§3.2 «بانک ایده عمومی»)؛ رأی، نظر و ثبت
ورود می‌خواهند. نام نویسندهٔ ایدهٔ ناشناس در هیچ پاسخی نیست جز برای خودش.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from silp.core.permissions import CurrentUser
from silp.domain.ideas import category_title
from silp.models.idea import IDEA_CATEGORY_TITLE_FA, Idea, IdeaComment
from silp.routers.deps import CurrentUserDep, OptionalUserDep, SessionDep
from silp.schemas.common import ErrorResponse, Page, PageParams
from silp.schemas.idea import (
    ArchiveIn,
    AuthorOut,
    CategoryOut,
    CommentIn,
    CommentOut,
    IdeaCategory,
    IdeaDetailOut,
    IdeaIn,
    IdeaSort,
    IdeaStatus,
    IdeaSummaryOut,
    PromoteIn,
    PromotionOut,
    VoteOut,
)
from silp.services.directory import DisplayName, display_names
from silp.services.idea_service import IdeaDraft, IdeaService

router = APIRouter(prefix="/ideas", tags=["ideas"])

EXCERPT_LENGTH = 220


def get_idea_service(session: SessionDep) -> IdeaService:
    return IdeaService(session)


IdeaServiceDep = Annotated[IdeaService, Depends(get_idea_service)]


def _excerpt(text: str) -> str:
    cleaned = " ".join(text.split())
    return cleaned if len(cleaned) <= EXCERPT_LENGTH else cleaned[: EXCERPT_LENGTH - 1] + "…"


def _author(
    idea: Idea, names: dict[uuid.UUID, DisplayName], viewer: CurrentUser | None
) -> AuthorOut | None:
    if idea.is_anonymous and (viewer is None or viewer.id != idea.author_id):
        return None
    entry = names.get(idea.author_id)
    return AuthorOut(
        id=idea.author_id,
        name=entry.full_name if entry else None,
        username=entry.username if entry else None,
    )


def _summary(
    idea: Idea,
    names: dict[uuid.UUID, DisplayName],
    viewer: CurrentUser | None,
    voted: set[uuid.UUID],
) -> IdeaSummaryOut:
    return IdeaSummaryOut(
        id=idea.id,
        title=idea.title,
        excerpt=_excerpt(idea.body),
        category=idea.category,
        category_fa=category_title(idea.category),
        tags=list(idea.tags),
        status=idea.status,
        is_anonymous=idea.is_anonymous,
        author=_author(idea, names, viewer),
        vote_count=idea.vote_count,
        comment_count=idea.comment_count,
        voted_by_me=idea.id in voted,
        is_mine=viewer is not None and viewer.id == idea.author_id,
        promoted_to_type=idea.promoted_to_type,
        promoted_to_id=idea.promoted_to_id,
        created_at=idea.created_at,
    )


def _draft(payload: IdeaIn) -> IdeaDraft:
    return IdeaDraft(
        title=payload.title,
        body=payload.body,
        problem=payload.problem,
        category=payload.category,
        tags=payload.tags,
        is_anonymous=payload.is_anonymous,
    )


async def _detail(service: IdeaService, idea: Idea, viewer: CurrentUser | None) -> IdeaDetailOut:
    comments = await service.comments(idea.id)
    names = await display_names(service.session, [idea.author_id, *(c.author_id for c in comments)])
    voted = await service.voted_by(viewer.id, [idea.id]) if viewer else set()
    can_moderate = viewer is not None and await service.can_moderate(viewer)
    can_promote = viewer is not None and idea.status == "OPEN" and await service.can_promote(viewer)
    base = _summary(idea, names, viewer, voted)
    return IdeaDetailOut(
        **base.model_dump(),
        body=idea.body,
        problem=idea.problem,
        archived_reason=idea.archived_reason,
        promoted_at=idea.promoted_at,
        comments=[_comment(c, names, viewer, can_moderate) for c in comments],
        can_edit=viewer is not None and viewer.id == idea.author_id and idea.status == "OPEN",
        can_promote=can_promote,
        can_moderate=can_moderate,
    )


def _comment(
    comment: IdeaComment,
    names: dict[uuid.UUID, DisplayName],
    viewer: CurrentUser | None,
    can_moderate: bool,
) -> CommentOut:
    deleted = comment.deleted_at is not None
    mine = viewer is not None and viewer.id == comment.author_id
    entry = names.get(comment.author_id)
    return CommentOut(
        id=comment.id,
        parent_id=comment.parent_id,
        body=None if deleted else comment.body,
        author=None
        if deleted
        else AuthorOut(
            id=comment.author_id,
            name=entry.full_name if entry else None,
            username=entry.username if entry else None,
        ),
        is_deleted=deleted,
        is_mine=mine and not deleted,
        can_delete=not deleted and (mine or can_moderate),
        created_at=comment.created_at,
    )


@router.get("/categories", response_model=list[CategoryOut], summary="دسته‌های ایده")
async def categories() -> list[CategoryOut]:
    return [
        CategoryOut(code=code, title_fa=title) for code, title in IDEA_CATEGORY_TITLE_FA.items()
    ]


@router.get("", response_model=Page[IdeaSummaryOut], summary="بانک ایده")
async def list_ideas(
    service: IdeaServiceDep,
    viewer: OptionalUserDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    q: Annotated[str | None, Query(max_length=100)] = None,
    category: Annotated[IdeaCategory | None, Query()] = None,
    tag: Annotated[str | None, Query(max_length=30)] = None,
    status_filter: Annotated[IdeaStatus | None, Query(alias="status")] = "OPEN",
    mine: Annotated[bool, Query()] = False,
    sort: Annotated[IdeaSort, Query()] = "hot",
) -> Page[IdeaSummaryOut]:
    """FR-IDEA-01/02 — «داغ» با زوال زمانی، «تازه»، یا «پررأی».

    `mine=true` ایده‌های خود کاربر را با هر وضعیتی می‌دهد، حتی بایگانی‌شده.
    """
    params = PageParams(page=page, page_size=page_size)
    author_id = viewer.id if (mine and viewer is not None) else None
    if mine and viewer is None:
        return Page.of([], total=0, page=params.page, page_size=params.page_size)
    stmt = service.list_query(
        q=q,
        category=category,
        tag=tag,
        status=None if status_filter == "ARCHIVED" else status_filter,
        author_id=author_id,
        sort=sort,
    )
    ideas, total = await service.page(stmt, offset=params.offset, limit=params.page_size)
    names = await display_names(service.session, [i.author_id for i in ideas])
    voted = await service.voted_by(viewer.id, [i.id for i in ideas]) if viewer else set()
    return Page.of(
        [_summary(i, names, viewer, voted) for i in ideas],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )


@router.post(
    "",
    response_model=IdeaDetailOut,
    status_code=status.HTTP_201_CREATED,
    summary="ثبت ایده",
    responses={401: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
async def create_idea(
    payload: IdeaIn, service: IdeaServiceDep, current: CurrentUserDep
) -> IdeaDetailOut:
    idea = await service.create(actor=current, draft=_draft(payload))
    return await _detail(service, idea, current)


@router.get(
    "/{idea_id}",
    response_model=IdeaDetailOut,
    summary="جزئیات ایده و نظرها",
    responses={404: {"model": ErrorResponse}},
)
async def get_idea(
    idea_id: uuid.UUID, service: IdeaServiceDep, viewer: OptionalUserDep
) -> IdeaDetailOut:
    idea = await service.get_visible(idea_id, viewer)
    return await _detail(service, idea, viewer)


@router.patch("/{idea_id}", response_model=IdeaDetailOut, summary="ویرایش ایده (نویسنده)")
async def update_idea(
    idea_id: uuid.UUID, payload: IdeaIn, service: IdeaServiceDep, current: CurrentUserDep
) -> IdeaDetailOut:
    idea = await service.get_visible(idea_id, current)
    idea = await service.update(idea=idea, actor=current, draft=_draft(payload))
    return await _detail(service, idea, current)


@router.delete(
    "/{idea_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="حذف ایده (نویسنده)",
)
async def delete_idea(idea_id: uuid.UUID, service: IdeaServiceDep, current: CurrentUserDep) -> None:
    idea = await service.get_visible(idea_id, current)
    await service.delete(idea=idea, actor=current)


@router.post("/{idea_id}/archive", response_model=IdeaDetailOut, summary="بایگانی (ناظر)")
async def archive_idea(
    idea_id: uuid.UUID, payload: ArchiveIn, service: IdeaServiceDep, current: CurrentUserDep
) -> IdeaDetailOut:
    idea = await service.get_visible(idea_id, current)
    idea = await service.archive(idea=idea, actor=current, reason=payload.reason)
    return await _detail(service, idea, current)


@router.post(
    "/{idea_id}/vote",
    response_model=VoteOut,
    summary="رأی مثبت",
    responses={409: {"model": ErrorResponse}},
)
async def vote(idea_id: uuid.UUID, service: IdeaServiceDep, current: CurrentUserDep) -> VoteOut:
    idea = await service.get_visible(idea_id, current)
    idea = await service.vote(idea=idea, actor=current)
    return VoteOut(idea_id=idea.id, vote_count=idea.vote_count, voted_by_me=True)


@router.delete("/{idea_id}/vote", response_model=VoteOut, summary="پس گرفتن رأی")
async def unvote(idea_id: uuid.UUID, service: IdeaServiceDep, current: CurrentUserDep) -> VoteOut:
    idea = await service.get_visible(idea_id, current)
    idea = await service.unvote(idea=idea, actor=current)
    return VoteOut(idea_id=idea.id, vote_count=idea.vote_count, voted_by_me=False)


@router.post(
    "/{idea_id}/comments",
    response_model=CommentOut,
    status_code=status.HTTP_201_CREATED,
    summary="نظر یا پاسخ",
)
async def add_comment(
    idea_id: uuid.UUID, payload: CommentIn, service: IdeaServiceDep, current: CurrentUserDep
) -> CommentOut:
    idea = await service.get_visible(idea_id, current)
    comment = await service.add_comment(
        idea=idea, actor=current, body=payload.body, parent_id=payload.parent_id
    )
    names = await display_names(service.session, [current.id])
    return _comment(comment, names, current, can_moderate=False)


@router.delete(
    "/comments/{comment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="حذف نظر",
)
async def delete_comment(
    comment_id: uuid.UUID, service: IdeaServiceDep, current: CurrentUserDep
) -> None:
    await service.delete_comment(comment_id=comment_id, actor=current)


@router.post(
    "/{idea_id}/promote",
    response_model=PromotionOut,
    summary="ارتقا به پروژه یا کسب‌وکار",
    responses={403: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
async def promote(
    idea_id: uuid.UUID, payload: PromoteIn, service: IdeaServiceDep, current: CurrentUserDep
) -> PromotionOut:
    """§7.8 — مجوز `idea.promote`. پروژه `DRAFT` می‌ماند تا استاد کاملش کند."""
    idea = await service.get_visible(idea_id, current)
    result = await service.promote(
        idea=idea,
        actor=current,
        target=payload.target,
        project_kind=payload.project_kind,
        expected_output=payload.expected_output,
    )
    href = (
        f"/projects/{result.target_id}"
        if result.target_type == "PROJECT"
        else f"/ventures/{result.target_id}"
    )
    return PromotionOut(
        target_type=result.target_type,
        target_id=result.target_id,
        href=href,
    )
