"""جستجوی سراسری ⌘K — §3.7، M7-13، ADR-0017.

`GET /search?q=…` — گروه‌بندی‌شده، حداکثر پنج نتیجه در هر گروه. نیازمند
ورود است: پالت ⌘K در پوستهٔ اپلیکیشن است و «پروژه‌های من» به کاربر بستگی
دارد. پرس‌وجوی کوتاه‌تر از دو نویسه فهرست خالی می‌گیرد، نه خطا — پالت با
هر ضربهٔ کلید درخواست می‌فرستد.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel

from silp.routers.deps import CurrentUserDep, SessionDep
from silp.schemas.common import ErrorResponse
from silp.services.search_service import SearchService

router = APIRouter(
    prefix="/search",
    tags=["search"],
    responses={401: {"model": ErrorResponse, "description": "احراز هویت نشده"}},
)


class SearchHitOut(BaseModel):
    id: uuid.UUID
    title: str
    subtitle: str | None
    href: str


class SearchGroupOut(BaseModel):
    kind: str
    title_fa: str
    items: list[SearchHitOut]


class SearchOut(BaseModel):
    q: str
    groups: list[SearchGroupOut]


@router.get("", response_model=SearchOut, summary="جستجوی سراسری")
async def search(
    current: CurrentUserDep,
    session: SessionDep,
    q: Annotated[str, Query(max_length=100)] = "",
    per_group: Annotated[int, Query(ge=1, le=10)] = 5,
) -> SearchOut:
    groups = await SearchService(session).search(q, current, per_group=per_group)
    return SearchOut(
        q=q,
        groups=[
            SearchGroupOut(
                kind=g.kind,
                title_fa=g.title_fa,
                items=[
                    SearchHitOut(id=h.id, title=h.title, subtitle=h.subtitle, href=h.href)
                    for h in g.items
                ],
            )
            for g in groups
        ],
    )


__all__ = ["router"]
