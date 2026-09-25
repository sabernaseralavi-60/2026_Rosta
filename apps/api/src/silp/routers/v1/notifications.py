"""مسیرهای اعلان — §5.10، FR-MSG-01/02/03، M6.

| مسیر | مرجع |
|------|------|
| `GET /notifications`، `…/unread-count`، `…/{id}/read`، `…/read-all` | §5.10، M6-08 |
| `GET /notifications/stream` | SSE — §5.10، M6-08 |
| `GET/PUT /notifications/preferences` | FR-MSG-02، M6-09 |
| `/notifications/channels/{channel}/…` | پیوند تلگرام و ایتا — M6-06، ADR-0013 |
| `POST /integrations/telegram/webhook` | وب‌هوک ربات — M6-06 |
| `/admin/outbox…`، `/admin/message-templates…` | §7.10، FR-MSG-03، M6-10 |

هر مسیر `/notifications` فقط اعلان‌های **خودِ** کاربر را می‌بیند؛ شناسهٔ
کاربر هرگز از ورودی خوانده نمی‌شود. اعلان دیگری ۴۰۴ است، نه ۴۰۳ (§6.4
قاعدهٔ ۴) — وجودش هم نباید لو برود.
"""

from __future__ import annotations

import hmac
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from fastapi.responses import StreamingResponse

from silp.core.exceptions import NotFound
from silp.core.permissions import CurrentUser, Permission
from silp.core.security import mask_email, mask_mobile
from silp.db.session import get_session_factory
from silp.domain.notifications import catalog
from silp.domain.notifications.push import endpoint_of
from silp.integrations.messaging import enabled_channels
from silp.integrations.messaging.bots import parse_telegram_start
from silp.models.identity import User
from silp.models.messaging import OUTBOX_STATUS_TITLE_FA, MessageTemplate, OutboxMessage
from silp.routers.deps import CurrentUserDep, SessionDep, SettingsDep, require
from silp.schemas.common import ErrorResponse
from silp.schemas.notifications import (
    ChannelConfirmIn,
    ChannelLinkIn,
    ChannelLinkOut,
    ChannelStatusOut,
    Group,
    GroupPreferenceOut,
    NotificationFeedOut,
    NotificationOut,
    OutboxMessageOut,
    OutboxPageOut,
    OutboxStatus,
    PreferencesIn,
    PreferencesOut,
    PushDevicesOut,
    PushSubscriptionIn,
    QuietHoursOut,
    ReadAllOut,
    RetriedOut,
    TemplateOut,
    TemplatePreviewIn,
    TemplatePreviewOut,
    TemplateUpdateIn,
    UnreadCountOut,
)
from silp.services.channel_link_service import LINK_FLOW, ChannelLinkService
from silp.services.notification_service import NotificationService
from silp.services.notification_stream import notification_events
from silp.services.outbox_service import OutboxService
from silp.services.push_service import PushService
from silp.services.template_service import TemplateService

AUTH_ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse, "description": "احراز هویت نشده"}
}

router = APIRouter(prefix="/notifications", tags=["notifications"], responses=AUTH_ERRORS)
integrations_router = APIRouter(prefix="/integrations", tags=["integrations"])
admin_router = APIRouter(prefix="/admin", tags=["admin"], responses=AUTH_ERRORS)

SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    # Nginx پاسخ را بافر نکند — وگرنه اعلان تا پر شدن بافر نمی‌رسد.
    "X-Accel-Buffering": "no",
    "Connection": "keep-alive",
}


# ── مرکز اعلان ─────────────────────────────────────────────────────────
@router.get("", response_model=NotificationFeedOut, summary="فهرست اعلان‌ها (کرسری)")
async def feed(
    user: CurrentUserDep,
    session: SessionDep,
    cursor: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    unread_only: bool = False,
    group: Group | None = None,
) -> NotificationFeedOut:
    items, next_cursor = await NotificationService(session).feed(
        user.id, before=cursor, limit=limit, unread_only=unread_only, group=group
    )
    return NotificationFeedOut(
        items=[NotificationOut.of(n) for n in items],
        next_cursor=str(next_cursor) if next_cursor else None,
    )


@router.get("/unread-count", response_model=UnreadCountOut, summary="شمارندهٔ زنگوله")
async def unread_count(user: CurrentUserDep, session: SessionDep) -> UnreadCountOut:
    return UnreadCountOut(count=await NotificationService(session).unread_count(user.id))


@router.post("/{notification_id}/read", response_model=NotificationOut, summary="علامت خوانده‌شده")
async def mark_read(
    notification_id: uuid.UUID, user: CurrentUserDep, session: SessionDep
) -> NotificationOut:
    notification = await NotificationService(session).mark_read(user.id, notification_id)
    return NotificationOut.of(notification)


@router.post("/read-all", response_model=ReadAllOut, summary="همه را خوانده‌شده کن")
async def mark_all_read(user: CurrentUserDep, session: SessionDep) -> ReadAllOut:
    return ReadAllOut(updated=await NotificationService(session).mark_all_read(user.id))


@router.get(
    "/stream",
    summary="جریان بی‌درنگ اعلان (SSE)",
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {}}}},
)
async def stream(user: CurrentUserDep) -> StreamingResponse:
    """رویدادها: `unread` با `{count}`، و `notification` با یک اعلان کامل.

    پس از ۱۰ دقیقه بسته می‌شود؛ کلاینت با توکن تازه دوباره وصل می‌شود.
    """
    events = notification_events(user.id, open_session=get_session_factory())
    return StreamingResponse(events, media_type="text/event-stream", headers=SSE_HEADERS)


# ── ترجیحات — FR-MSG-02 ────────────────────────────────────────────────
async def _preferences_out(
    session: SessionDep, settings: SettingsDep, user_id: uuid.UUID
) -> PreferencesOut:
    service = NotificationService(session, settings)
    groups = await service.preferences(user_id)
    enabled = set(enabled_channels(settings))
    user = await session.get(User, user_id)
    links = await ChannelLinkService(session, settings).links(user_id)
    now = datetime.now(UTC)

    devices = await PushService(session, settings).count(user_id)
    channels: list[ChannelStatusOut] = []
    for channel in ("SMS", "EMAIL", "PUSH", *catalog.LINKABLE_CHANNELS):
        link = links.get(channel)
        if channel == "SMS":
            linked, masked = bool(user and user.mobile), mask_mobile(user.mobile if user else None)
        elif channel == "PUSH":
            linked, masked = devices > 0, None
        elif channel == "EMAIL":
            verified = bool(user and user.email and user.email_verified_at)
            linked, masked = verified, mask_email(user.email) if verified and user else None
        else:
            linked = bool(link and link.is_linked)
            masked = _mask_chat(link.address) if link and link.is_linked else None
        channels.append(
            ChannelStatusOut(
                channel=channel,
                title_fa=catalog.CHANNEL_TITLE_FA[channel],
                available=channel in enabled,
                requires_link=channel in catalog.LINKABLE_CHANNELS,
                linked=linked,
                address_masked=masked,
                link_flow=LINK_FLOW.get(channel),
                pending_link=bool(
                    link
                    and link.link_code_hash
                    and link.link_expires_at
                    and link.link_expires_at > now
                ),
                devices=devices if channel == "PUSH" else 0,
            )
        )
    return PreferencesOut(
        groups=[
            GroupPreferenceOut(
                group=group,
                title_fa=catalog.GROUP_TITLE_FA[group],
                description_fa=catalog.GROUP_DESCRIPTION_FA[group],
                channels=[c for c in chosen if c == "IN_APP" or c in enabled],
            )
            for group, chosen in groups.items()
        ],
        channels=channels,
        quiet_hours=QuietHoursOut(start=settings.quiet_hours_start, end=settings.quiet_hours_end),
        push_public_key=(settings.vapid_public_key or None) if "PUSH" in enabled else None,
    )


def _mask_chat(address: str | None) -> str | None:
    if not address:
        return None
    if address.startswith("@"):
        return address
    return f"…{address[-4:]}" if len(address) > 4 else address


@router.get("/preferences", response_model=PreferencesOut, summary="تنظیمات کانال")
async def get_preferences(
    user: CurrentUserDep, session: SessionDep, settings: SettingsDep
) -> PreferencesOut:
    return await _preferences_out(session, settings, user.id)


@router.put("/preferences", response_model=PreferencesOut, summary="ذخیرهٔ تنظیمات کانال")
async def put_preferences(
    body: PreferencesIn, user: CurrentUserDep, session: SessionDep, settings: SettingsDep
) -> PreferencesOut:
    choices = {group: list(channels) for group, channels in body.groups.items()}
    await NotificationService(session, settings).set_preferences(user.id, choices)
    return await _preferences_out(session, settings, user.id)


# ── اشتراک Push وب — ADR-0029 ───────────────────────────────────────────
@router.post(
    "/push/subscriptions",
    response_model=PushDevicesOut,
    summary="ثبت اشتراک Push این مرورگر",
)
async def push_subscribe(
    body: PushSubscriptionIn,
    request: Request,
    user: CurrentUserDep,
    session: SessionDep,
    settings: SettingsDep,
) -> PushDevicesOut:
    devices = await PushService(session, settings).subscribe(
        user.id,
        endpoint=body.endpoint,
        p256dh=body.keys.p256dh,
        auth=body.keys.auth,
        user_agent=request.headers.get("user-agent"),
    )
    return PushDevicesOut(devices=devices)


@router.delete(
    "/push/subscriptions",
    response_model=PushDevicesOut,
    summary="برداشتن اشتراک Push این مرورگر",
)
async def push_unsubscribe(
    endpoint: Annotated[str, Query(min_length=1, max_length=2048)],
    user: CurrentUserDep,
    session: SessionDep,
    settings: SettingsDep,
) -> PushDevicesOut:
    return PushDevicesOut(
        devices=await PushService(session, settings).unsubscribe(user.id, endpoint)
    )


# ── پیوند پیام‌رسان ────────────────────────────────────────────────────
@router.post(
    "/channels/{channel}/link",
    response_model=ChannelLinkOut,
    summary="شروع اتصال تلگرام یا ایتا",
)
async def start_link(
    channel: str,
    body: ChannelLinkIn,
    user: CurrentUserDep,
    session: SessionDep,
    settings: SettingsDep,
) -> ChannelLinkOut:
    started = await ChannelLinkService(session, settings).start(
        user.id, channel.upper(), address=body.address
    )
    return ChannelLinkOut(
        channel=started.channel,
        flow=started.flow,
        expires_at=started.expires_at,
        deep_link=started.deep_link,
    )


@router.post(
    "/channels/{channel}/confirm",
    response_model=PreferencesOut,
    summary="تأیید اتصال ایتا با کد",
)
async def confirm_link(
    channel: str,
    body: ChannelConfirmIn,
    user: CurrentUserDep,
    session: SessionDep,
    settings: SettingsDep,
) -> PreferencesOut:
    await ChannelLinkService(session, settings).confirm(user.id, channel.upper(), body.code)
    return await _preferences_out(session, settings, user.id)


@router.delete("/channels/{channel}", status_code=204, summary="قطع اتصال پیام‌رسان")
async def unlink(
    channel: str, user: CurrentUserDep, session: SessionDep, settings: SettingsDep
) -> Response:
    await ChannelLinkService(session, settings).unlink(user.id, channel.upper())
    return Response(status_code=204)


# ── وب‌هوک تلگرام ──────────────────────────────────────────────────────
@integrations_router.post("/telegram/webhook", include_in_schema=False)
async def telegram_webhook(
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    secret: Annotated[str | None, Header(alias="X-Telegram-Bot-Api-Secret-Token")] = None,
) -> dict[str, Any]:
    """`/start <token>` ⇒ پیوند. پاسخ همیشه ۲۰۰ است، مگر رمز نادرست.

    پاسخ وب‌هوک می‌تواند خودش یک فراخوان Bot API باشد (`method`)؛ پس پیام
    «پیوند منقضی شد» بی‌هیچ درخواست بیرونی از داخل درخواست فرستاده می‌شود.
    """
    expected = settings.telegram_webhook_secret
    if settings.telegram_provider == "disabled" or not expected:
        raise NotFound
    if not secret or not hmac.compare_digest(secret, expected):
        raise NotFound
    try:
        update = await request.json()
    except ValueError:
        return {"ok": True}
    parsed = parse_telegram_start(update) if isinstance(update, dict) else None
    if parsed is None:
        return {"ok": True}
    chat_id, token = parsed
    row = await ChannelLinkService(session, settings).bind_telegram(chat_id=chat_id, token=token)
    if row is None:
        return {
            "method": "sendMessage",
            "chat_id": chat_id,
            "text": "این پیوند منقضی یا نامعتبر است. از تنظیمات اعلان در سابِر دوباره بساز.",
        }
    return {"ok": True}


# ── مدیریت — /admin ────────────────────────────────────────────────────
def _outbox_out(message: OutboxMessage) -> OutboxMessageOut:
    if message.channel == "SMS":
        masked = mask_mobile(message.recipient) or ""
    elif message.channel == "EMAIL":
        masked = mask_email(message.recipient) or ""
    elif message.channel == "PUSH":
        # اشتراک کلید رمزنگاری دارد؛ فقط میزبان سرویس Push دیده می‌شود.
        masked = urlsplit(endpoint_of(message.recipient) or "").hostname or "—"
    else:
        masked = _mask_chat(message.recipient) or ""
    return OutboxMessageOut(
        id=message.id,
        channel=message.channel,
        recipient_masked=masked,
        template=message.template,
        priority=message.priority,
        status=message.status,
        status_fa=OUTBOX_STATUS_TITLE_FA[message.status],
        attempts=message.attempts,
        next_attempt_at=message.next_attempt_at,
        last_error=message.last_error,
        user_id=message.user_id,
        notification_id=message.notification_id,
        created_at=message.created_at,
        sent_at=message.sent_at,
    )


@admin_router.get("/outbox", response_model=OutboxPageOut, summary="صف ارسال — §7.10")
async def outbox(
    _: Annotated[CurrentUser, Depends(require(Permission.OUTBOX_VIEW))],
    session: SessionDep,
    status: OutboxStatus | None = None,
    channel: str | None = None,
    user_id: uuid.UUID | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> OutboxPageOut:
    service = OutboxService(session)
    rows, total = await service.listing(
        status=status, channel=channel, user_id=user_id, page=page, page_size=page_size
    )
    return OutboxPageOut(
        items=[_outbox_out(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
        has_next=page * page_size < total,
        counts=await service.counts(),
    )


@admin_router.post(
    "/outbox/{message_id}/retry", response_model=OutboxMessageOut, summary="تلاش دوباره"
)
async def retry_message(
    message_id: uuid.UUID,
    _: Annotated[CurrentUser, Depends(require(Permission.OUTBOX_RETRY))],
    session: SessionDep,
) -> OutboxMessageOut:
    return _outbox_out(await OutboxService(session).retry(message_id))


@admin_router.post(
    "/outbox/retry-dead", response_model=RetriedOut, summary="همهٔ پیام‌های DEAD به صف"
)
async def retry_dead(
    _: Annotated[CurrentUser, Depends(require(Permission.OUTBOX_RETRY))],
    session: SessionDep,
    channel: str | None = None,
) -> RetriedOut:
    return RetriedOut(retried=await OutboxService(session).retry_all_dead(channel=channel))


def _template_out(row: MessageTemplate) -> TemplateOut:
    kind = catalog.KINDS.get(row.code)
    return TemplateOut(
        code=row.code,
        channel=row.channel,
        kind_title_fa=kind.title_fa if kind else None,
        subject=row.subject,
        body=row.body,
        variables=list(row.variables),
        is_active=row.is_active,
        updated_at=row.updated_at,
    )


@admin_router.get(
    "/message-templates", response_model=list[TemplateOut], summary="الگوهای پیام — FR-MSG-03"
)
async def templates(
    _: Annotated[CurrentUser, Depends(require(Permission.MESSAGE_TEMPLATE_EDIT))],
    session: SessionDep,
) -> list[TemplateOut]:
    return [_template_out(row) for row in await TemplateService(session).all()]


@admin_router.put(
    "/message-templates/{code}/{channel}",
    response_model=TemplateOut,
    summary="ساخت یا ویرایش الگو",
)
async def put_template(
    code: str,
    channel: str,
    body: TemplateUpdateIn,
    user: Annotated[CurrentUser, Depends(require(Permission.MESSAGE_TEMPLATE_EDIT))],
    session: SessionDep,
) -> TemplateOut:
    row = await TemplateService(session).update(
        code=code,
        channel=channel.upper(),
        subject=body.subject,
        body=body.body,
        is_active=body.is_active,
        actor_id=user.id,
    )
    return _template_out(row)


@admin_router.post(
    "/message-templates/preview",
    response_model=TemplatePreviewOut,
    summary="پیش‌نمایش پیش از ذخیره",
)
async def preview_template(
    body: TemplatePreviewIn,
    _: Annotated[CurrentUser, Depends(require(Permission.MESSAGE_TEMPLATE_EDIT))],
    session: SessionDep,
) -> TemplatePreviewOut:
    rendered, parts = TemplateService(session).preview(
        code=body.code,
        channel=body.channel,
        subject=body.subject,
        body=body.body,
        values=body.values,
    )
    return TemplatePreviewOut(
        subject=rendered.subject, body=rendered.body, length=len(rendered.body), sms_parts=parts
    )


__all__ = ["admin_router", "integrations_router", "router"]
