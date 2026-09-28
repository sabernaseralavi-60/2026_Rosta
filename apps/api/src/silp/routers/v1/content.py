"""مسیرهای عمومی محتوا — ADR-0030.

| مسیر | توضیح |
|------|-------|
| `GET /public/content` | فهرست محتوای منتشرشده با فیلتر نوع، موضوع، درس و جست‌وجو |
| `GET /public/content/{slug}` | یک محتوا؛ متن فقط برای کسی که دسترسی دارد |

احراز هویت اختیاری است: بی‌ورود فقط `PUBLIC` باز است. پاسخ بیننده‌ٔ واردشده هرگز
در کش مشترک نمی‌نشیند، چون `locked` و `body_md` به او وابسته است.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Path, Query, Response

from silp.models.content import CONTENT_KINDS, ContentItem
from silp.routers.deps import OptionalUserDep, SessionDep
from silp.schemas.common import ErrorResponse
from silp.schemas.content import ContentCardOut, ContentDetailOut, ContentListOut, FacetOut
from silp.services.content_service import ACCESS_FA, KIND_FA, ContentService, can_read

CACHE_ANONYMOUS = "public, max-age=60"
CACHE_PRIVATE = "private, no-store"

router = APIRouter(prefix="/public/content", tags=["public"])


def _card(item: ContentItem, *, locked: bool) -> ContentCardOut:
    return ContentCardOut(
        slug=item.slug,
        kind=item.kind,
        kind_fa=KIND_FA[item.kind],
        title_fa=item.title_fa,
        summary=item.summary,
        cover=item.cover,
        access=item.access,
        access_fa=ACCESS_FA[item.access],
        topics=list(item.topics),
        reading_minutes=item.reading_minutes,
        published_at=item.published_at,
        locked=locked,
    )


@router.get("", response_model=ContentListOut, summary="فهرست محتوای منتشرشده")
async def list_content(
    session: SessionDep,
    viewer: OptionalUserDep,
    response: Response,
    kind: Annotated[str | None, Query(pattern="^[A-Z_]+$")] = None,
    topic: Annotated[str | None, Query(max_length=80)] = None,
    course: Annotated[str | None, Query(max_length=80)] = None,
    q: Annotated[str | None, Query(min_length=2, max_length=80)] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    offset: Annotated[int, Query(ge=0, le=10_000)] = 0,
) -> ContentListOut:
    service = ContentService(session)
    if kind is not None and kind not in CONTENT_KINDS:
        kind = None
    items, total = await service.search(
        kind=kind, topic=topic, course=course, q=q, limit=limit, offset=offset
    )
    kinds, topics = await service.facets()
    response.headers["Cache-Control"] = CACHE_PRIVATE if viewer else CACHE_ANONYMOUS
    return ContentListOut(
        items=[_card(i, locked=not can_read(i.access, viewer)) for i in items],
        total=total,
        kinds=[FacetOut(value=k, label=KIND_FA[k], count=n) for k, n in kinds.items()],
        topics=[FacetOut(value=t, label=t, count=n) for t, n in topics.items()],
    )


@router.get(
    "/{slug}",
    response_model=ContentDetailOut,
    summary="یک محتوا",
    responses={404: {"model": ErrorResponse}},
)
async def get_content(
    slug: Annotated[str, Path(min_length=1, max_length=200)],
    session: SessionDep,
    viewer: OptionalUserDep,
    response: Response,
) -> ContentDetailOut:
    service = ContentService(session)
    item = await service.get(slug)
    locked = not can_read(item.access, viewer)
    related = await service.related(item)
    response.headers["Cache-Control"] = CACHE_PRIVATE if viewer else CACHE_ANONYMOUS
    card = _card(item, locked=locked)
    return ContentDetailOut(
        **card.model_dump(),
        skills=list(item.skills),
        course_slug=item.course_slug,
        body_md=None if locked else item.body_md,
        related=[_card(r, locked=not can_read(r.access, viewer)) for r in related],
    )


__all__ = ["router"]
