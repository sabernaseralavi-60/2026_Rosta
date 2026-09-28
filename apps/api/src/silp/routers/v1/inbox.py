"""صندوق درخواست‌های ورودی، داشبورد مالک و پیگیری مشتری — ADR-0032.

| مسیر | دسترسی |
|------|--------|
| `GET /admin/owner/overview` | `intake.manage` |
| `GET /admin/intake` | `intake.manage` — فهرست با فیلتر نوع، وضعیت، جست‌وجو |
| `GET /admin/intake/{id}` | `intake.manage` — با یادداشت خصوصی و تاریخچه |
| `PATCH /admin/intake/{id}` | `intake.manage` — وضعیت و یادداشت‌ها؛ حسابرسی می‌شود |
| `GET /me/requests` | واردشده — درخواست‌های خودم |
| `POST /public/track` | بی‌ورود — کد و راه تماس؛ بدون متن درخواست |
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from silp.core.permissions import CurrentUser, Permission
from silp.models.intake import IntakeEvent, IntakeRequest
from silp.routers.deps import ClientIPDep, CurrentUserDep, SessionDep, require
from silp.schemas.common import ErrorResponse
from silp.schemas.inbox import (
    EventOut,
    InboxDetailOut,
    InboxItemOut,
    InboxPageOut,
    InboxUpdateIn,
    MyRequestOut,
    OverviewOut,
    RequestTrackIn,
    RequestTrackOut,
)
from silp.services.client_request_service import ClientRequestService
from silp.services.inbox_service import InboxService, is_stale

_ERRORS: dict[int | str, dict[str, object]] = {
    401: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
}

admin_router = APIRouter(prefix="/admin", tags=["admin"], responses=_ERRORS)
me_router = APIRouter(prefix="/me", tags=["me"], responses=_ERRORS)
public_router = APIRouter(prefix="/public", tags=["public"], responses=_ERRORS)

OwnerDep = Annotated[CurrentUser, Depends(require(Permission.INTAKE_MANAGE))]


def _events(events: list[IntakeEvent]) -> list[EventOut]:
    return [
        EventOut(
            id=e.id,
            from_status=e.from_status,
            to_status=e.to_status,
            public_note=e.public_note,
            created_at=e.created_at,
        )
        for e in events
    ]


def _item(request: IntakeRequest, person_code: str | None) -> InboxItemOut:
    return InboxItemOut(
        id=request.id,
        kind=request.kind,
        tracking_code=request.tracking_code,
        status=request.status,
        contact_name=request.contact_name,
        contact_mobile=request.contact_mobile,
        contact_email=request.contact_email,
        organization=request.organization,
        need_type=request.need_type,
        services=list(request.services),
        summary=request.summary,
        person_code=person_code,
        created_at=request.created_at,
        updated_at=request.updated_at,
        stale=is_stale(request),
    )


def _detail(
    request: IntakeRequest, person_code: str | None, events: list[IntakeEvent]
) -> InboxDetailOut:
    return InboxDetailOut(
        **_item(request, person_code).model_dump(),
        payload=dict(request.payload),
        owner_note=request.owner_note,
        events=_events(events),
    )


# ── مالک ───────────────────────────────────────────────────────────────
@admin_router.get("/owner/overview", response_model=OverviewOut, summary="داشبورد مالک")
async def overview(session: SessionDep, _: OwnerDep, response: Response) -> OverviewOut:
    response.headers["Cache-Control"] = "no-store"
    data = await InboxService(session).overview()
    follow_up = [_item(r, code) for r, code in data.pop("follow_up")]
    return OverviewOut(**data, follow_up=follow_up)


@admin_router.get("/intake", response_model=InboxPageOut, summary="صندوق درخواست‌های ورودی")
async def list_intake(
    session: SessionDep,
    _: OwnerDep,
    response: Response,
    kind: Annotated[str | None, Query(pattern="^(INTAKE|COLLABORATION)$")] = None,
    status: Annotated[
        str | None, Query(pattern="^(NEW|IN_REVIEW|ACCEPTED|DECLINED|ARCHIVED)$")
    ] = None,
    q: Annotated[str | None, Query(min_length=2, max_length=80)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
    offset: Annotated[int, Query(ge=0, le=100_000)] = 0,
) -> InboxPageOut:
    response.headers["Cache-Control"] = "no-store"
    rows, total, counts = await InboxService(session).page(
        kind=kind, status=status, q=q, limit=limit, offset=offset
    )
    return InboxPageOut(items=[_item(r, c) for r, c in rows], total=total, counts=counts)


@admin_router.get("/intake/{request_id}", response_model=InboxDetailOut, summary="یک درخواست")
async def get_intake(
    request_id: uuid.UUID, session: SessionDep, _: OwnerDep, response: Response
) -> InboxDetailOut:
    response.headers["Cache-Control"] = "no-store"
    (request, code), events = await InboxService(session).get(request_id)
    return _detail(request, code, events)


@admin_router.patch("/intake/{request_id}", response_model=InboxDetailOut, summary="رسیدگی")
async def update_intake(
    request_id: uuid.UUID, payload: InboxUpdateIn, session: SessionDep, owner: OwnerDep
) -> InboxDetailOut:
    (request, code), events = await InboxService(session).update(request_id, payload, actor=owner)
    detail = _detail(request, code, events)
    await session.commit()
    return detail


# ── مشتری واردشده ──────────────────────────────────────────────────────
@me_router.get("/requests", response_model=list[MyRequestOut], summary="درخواست‌های من")
async def my_requests(
    session: SessionDep, current: CurrentUserDep, response: Response
) -> list[MyRequestOut]:
    response.headers["Cache-Control"] = "private, no-store"
    pairs = await ClientRequestService(session).mine(current.id)
    return [
        MyRequestOut(
            tracking_code=r.tracking_code,
            kind=r.kind,
            status=r.status,
            need_type=r.need_type,
            services=list(r.services),
            summary=r.summary,
            created_at=r.created_at,
            updated_at=r.updated_at,
            events=_events(events),
        )
        for r, events in pairs
    ]


# ── مشتری بی‌ورود ──────────────────────────────────────────────────────
@public_router.post("/track", response_model=RequestTrackOut, summary="پیگیری با کد و راه تماس")
async def track(
    payload: RequestTrackIn, session: SessionDep, ip: ClientIPDep, response: Response
) -> RequestTrackOut:
    response.headers["Cache-Control"] = "no-store"
    request, events = await ClientRequestService(session).track(
        payload.tracking_code, payload.contact, ip=ip
    )
    return RequestTrackOut(
        tracking_code=request.tracking_code,
        kind=request.kind,
        status=request.status,
        need_type=request.need_type,
        created_at=request.created_at,
        updated_at=request.updated_at,
        events=_events(events),
    )


__all__ = ["admin_router", "me_router", "public_router"]
