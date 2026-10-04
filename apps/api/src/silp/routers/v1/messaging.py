"""گفت‌وگوی استاد–دانشجو — ADR-0036.

| مسیر | توضیح |
|------|-------|
| `GET /messaging/inbox` | گفت‌وگوهای کاربر (مستقیم‌ها + کانال درس) با شمارندهٔ خوانده‌نشده |
| `GET /messaging/unread` | جمع خوانده‌نشده‌ها (نشان کنار منو) |
| `GET/POST /messaging/conversations/{id}/messages` | خواندن و نوشتن |
| `POST /messaging/conversations/{id}/read` | علامت «خوانده شد» |
| `DELETE /messaging/messages/{id}` | حذف نرم (فرستنده یا کادر) |
| `GET /messaging/offerings/{id}/threads` | کادر: همهٔ دانشجویان ارائه و وضعیت گفت‌وگو |
| `POST /messaging/offerings/{id}/threads/{student_id}` | کادر: باز کردن گفت‌وگوی مستقیم |
| `POST /messaging/offerings/{id}/send` | کادر: «به همه» (کانال) یا «به منتخب» (پیام خصوصی) |

دسترسی در سرویس بررسی می‌شود؛ غیرعضو ۴۰۴ می‌گیرد، نه ۴۰۳.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from silp.core.permissions import CurrentUser, Permission
from silp.routers.deps import CurrentUserDep, MessagingServiceDep, offering_from_path, require
from silp.schemas.common import ErrorResponse
from silp.schemas.messaging import (
    AudienceIn,
    ConversationOut,
    ConversationRefOut,
    MessageIn,
    MessageOut,
    SendResultOut,
    ThreadOut,
    UnreadOut,
)

router = APIRouter(prefix="/messaging", tags=["messaging"])

_R: dict[int | str, dict[str, object]] = {
    404: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
}
StaffDep = Annotated[
    CurrentUser,
    Depends(require(Permission.ANNOUNCEMENT_PUBLISH, scope=offering_from_path)),
]


@router.get("/inbox", response_model=list[ConversationOut], summary="گفت‌وگوهای من")
async def inbox(svc: MessagingServiceDep, user: CurrentUserDep) -> list[ConversationOut]:
    return [ConversationOut(**vars(s)) for s in await svc.inbox(user)]


@router.get("/unread", response_model=UnreadOut, summary="جمع پیام‌های خوانده‌نشده")
async def unread(svc: MessagingServiceDep, user: CurrentUserDep) -> UnreadOut:
    return UnreadOut(unread=await svc.unread_total(user))


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=list[MessageOut],
    summary="پیام‌های یک گفت‌وگو (قدیمی‌تر ⇒ تازه‌تر)",
    responses=_R,
)
async def list_messages(
    conversation_id: uuid.UUID,
    svc: MessagingServiceDep,
    user: CurrentUserDep,
    before: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[MessageOut]:
    rows = await svc.messages(user, conversation_id, before=before, limit=limit)
    return [MessageOut(**vars(m)) for m in rows]


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=MessageOut,
    status_code=status.HTTP_201_CREATED,
    summary="ارسال پیام",
    responses=_R,
)
async def send_message(
    conversation_id: uuid.UUID,
    payload: MessageIn,
    svc: MessagingServiceDep,
    user: CurrentUserDep,
) -> MessageOut:
    message = await svc.send(user, conversation_id, payload.body, reply_to_id=payload.reply_to_id)
    return MessageOut(
        id=message.id,
        sender_id=message.sender_id,
        sender_name="",
        mine=True,
        from_staff=False,
        body=message.body,
        reply_to_id=message.reply_to_id,
        created_at=message.created_at,
        deleted=False,
    )


@router.post(
    "/conversations/{conversation_id}/read",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="علامت‌گذاری به‌عنوان خوانده‌شده",
    responses=_R,
)
async def mark_read(
    conversation_id: uuid.UUID, svc: MessagingServiceDep, user: CurrentUserDep
) -> Response:
    await svc.mark_read(user, conversation_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/messages/{message_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="حذف نرم پیام",
    responses=_R,
)
async def delete_message(
    message_id: uuid.UUID, svc: MessagingServiceDep, user: CurrentUserDep
) -> Response:
    await svc.delete_message(user, message_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/offerings/{offering_id}/threads",
    response_model=list[ThreadOut],
    summary="کادر: دانشجویان ارائه و وضعیت گفت‌وگوی هرکدام",
    responses=_R,
)
async def threads(
    offering_id: uuid.UUID, svc: MessagingServiceDep, actor: StaffDep
) -> list[ThreadOut]:
    return [ThreadOut(**vars(t)) for t in await svc.threads(actor, offering_id)]


@router.post(
    "/offerings/{offering_id}/threads/{student_id}",
    response_model=ConversationRefOut,
    summary="کادر: باز کردن (یا برگرداندن) گفت‌وگوی مستقیم با یک دانشجو",
    responses=_R,
)
async def open_thread(
    offering_id: uuid.UUID, student_id: uuid.UUID, svc: MessagingServiceDep, actor: StaffDep
) -> ConversationRefOut:
    conv = await svc.open_direct(actor, offering_id, student_id)
    return ConversationRefOut(id=conv.id)


@router.post(
    "/offerings/{offering_id}/channel",
    response_model=ConversationRefOut,
    summary="کادر: کانال درس",
    responses=_R,
)
async def open_channel(
    offering_id: uuid.UUID, svc: MessagingServiceDep, actor: StaffDep
) -> ConversationRefOut:
    conv = await svc.channel_for(actor, offering_id)
    return ConversationRefOut(id=conv.id)


@router.post(
    "/offerings/{offering_id}/send",
    response_model=SendResultOut,
    summary="کادر: ارسال به همه (کانال درس) یا به دانشجویان منتخب (پیام خصوصی)",
    responses=_R,
)
async def send_to_audience(
    offering_id: uuid.UUID, payload: AudienceIn, svc: MessagingServiceDep, actor: StaffDep
) -> SendResultOut:
    result = await svc.send_to_audience(
        actor,
        offering_id,
        audience=payload.audience,
        student_ids=payload.student_ids,
        body=payload.body,
    )
    return SendResultOut(sent=result.sent, skipped_no_account=result.skipped_no_account)
