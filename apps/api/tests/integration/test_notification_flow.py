"""اعلان — M6، تعریف انجام‌شدهٔ §13.

«تأیید تحویل‌دادنی ⇒ اعلان داخلی + پیامک، و اگر پیامک شکست بخورد، خودکار
تلاش مجدد می‌شود.»

PostgreSQL واقعی لازم است: بی‌اثری کارهای زمان‌بندی‌شده یک ایندکس یکتای
جزئی است، برداشتن پیام از صف `FOR UPDATE SKIP LOCKED` است، و مرکز اعلان
با کرسری روی uuidv7 صفحه‌بندی می‌شود.

همهٔ کانال‌ها در محیط تست حافظه‌ای‌اند (`tests/conftest.py`)؛ فیکسچر
`channels` همان آداپتورهایی را می‌دهد که صف به آن‌ها می‌فرستد.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select, update
from tests.integration.helpers import auth, grant_role, login, me
from tests.integration.test_project_lifecycle import (
    LEAD_MOBILE,
    STUDENT_MOBILE,
    _actor,
    _published_project,
    _team_of_two,
)
from tests.integration.test_quiz_flow import SINGLE_PAYLOAD, _add_question, _publish, _scene

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

ADMIN_MOBILE = "09121229901"
WEBHOOK_SECRET = "test-telegram-webhook-secret"


# ── کمکی‌ها ────────────────────────────────────────────────────────────
async def _feed(client: Any, token: str, **params: Any) -> dict[str, Any]:
    response = await client.get("/api/v1/notifications", headers=auth(token), params=params)
    assert response.status_code == 200, response.text
    return dict(response.json())


async def _kinds(client: Any, token: str) -> list[str]:
    return [item["kind"] for item in (await _feed(client, token, limit=50))["items"]]


async def _outbox(session: Any, user_id: str | uuid.UUID, template: str | None = None) -> list[Any]:
    from silp.models.messaging import OutboxMessage

    query = select(OutboxMessage).where(OutboxMessage.user_id == uuid.UUID(str(user_id)))
    if template is not None:
        query = query.where(OutboxMessage.template == template)
    return list(await session.scalars(query.order_by(OutboxMessage.created_at)))


def _dispatcher(session: Any) -> Any:
    from silp.services.outbox_service import OutboxService

    return OutboxService(session)


async def _approved_deliverable(client: Any, session: Any) -> dict[str, Any]:
    """تیم دونفره؛ عضو تحویل می‌دهد و مدیر تأیید می‌کند."""
    lead_token, student_token, project_id, milestone_id = await _team_of_two(client, session)
    submitted = await client.post(
        f"/api/v1/milestones/{milestone_id}/deliverables",
        headers=auth(student_token),
        json={"body": "گزارش ده مصاحبه"},
    )
    assert submitted.status_code == 201, submitted.text
    reviewed = await client.post(
        f"/api/v1/deliverables/{submitted.json()['id']}/review",
        headers=auth(lead_token),
        json={"decision": "APPROVED", "score": 45},
    )
    assert reviewed.status_code == 200, reviewed.text
    student = await me(client, student_token)
    return {
        "lead_token": lead_token,
        "student_token": student_token,
        "student_id": student["id"],
        "project_id": project_id,
    }


async def _admin(client: Any, session: Any) -> str:
    token = await login(client, ADMIN_MOBILE)
    await grant_role(session, (await me(client, token))["id"], "ADMIN")
    return await login(client, ADMIN_MOBILE)


# ── تعریف انجام‌شده ─────────────────────────────────────────────────────
async def test_approval_notifies_in_app_and_by_sms(client, db_session, channels) -> None:  # type: ignore[no-untyped-def]
    scene = await _approved_deliverable(client, db_session)

    feed = (await _feed(client, scene["student_token"]))["items"]
    approved = next(i for i in feed if i["kind"] == "DELIVERABLE_APPROVED")
    assert approved["group"] == "PROJECT"
    assert approved["priority"] == "IMPORTANT"
    assert "امتیاز گرفتی" in approved["body"]
    assert approved["action_url"] == f"/projects/{scene['project_id']}/workspace"

    # مدیر هم «تحویل تازه» گرفت؛ ولی تأیید کار خودش را اعلان نمی‌گیرد.
    lead_kinds = await _kinds(client, scene["lead_token"])
    assert "DELIVERABLE_SUBMITTED" in lead_kinds
    assert "DELIVERABLE_APPROVED" not in lead_kinds

    [sms] = await _outbox(db_session, scene["student_id"], "DELIVERABLE_APPROVED")
    assert sms.channel == "SMS" and sms.status == "QUEUED"

    stats = await _dispatcher(db_session).dispatch()
    assert stats.sent >= 1
    await db_session.refresh(sms)
    assert sms.status == "SENT" and sms.sent_at is not None
    delivered = [m for m in channels["SMS"].sent if "تأیید شد" in m.body]
    assert delivered and delivered[0].recipient == STUDENT_MOBILE


async def test_failed_sms_is_retried_with_backoff(client, db_session, channels) -> None:  # type: ignore[no-untyped-def]
    scene = await _approved_deliverable(client, db_session)
    [sms] = await _outbox(db_session, scene["student_id"], "DELIVERABLE_APPROVED")
    # بقیهٔ پیام‌های صف (پذیرش درخواست) کنار می‌روند تا شکست دقیقاً به این پیام بخورد.
    from silp.models.messaging import OutboxMessage

    await db_session.execute(
        update(OutboxMessage)
        .where(OutboxMessage.id != sms.id)
        .values(status="SENT", sent_at=datetime.now(UTC))
    )

    channels["SMS"].fail_next(1, error="کاوه‌نگار 500")
    before = datetime.now(UTC)
    stats = await _dispatcher(db_session).dispatch()
    assert stats.failed == 1
    await db_session.refresh(sms)
    assert sms.status == "FAILED" and sms.attempts == 1
    assert sms.last_error == "کاوه‌نگار 500"
    # ۲¹ × ۳۰ ثانیه ± ۱۰٪
    assert before + timedelta(seconds=50) < sms.next_attempt_at < before + timedelta(seconds=70)

    # پیش از موعد برداشته نمی‌شود …
    assert (await _dispatcher(db_session).dispatch()).claimed == 0
    # … و پس از آن فرستاده می‌شود.
    stats = await _dispatcher(db_session).dispatch(now=datetime.now(UTC) + timedelta(minutes=2))
    await db_session.refresh(sms)
    assert sms.status == "SENT" and sms.attempts == 2 and sms.last_error is None


async def test_permanent_failure_goes_dead_and_alerts_admins(client, db_session, channels) -> None:  # type: ignore[no-untyped-def]
    admin_token = await _admin(client, db_session)
    scene = await _approved_deliverable(client, db_session)
    from silp.models.messaging import OutboxMessage

    [sms] = await _outbox(db_session, scene["student_id"], "DELIVERABLE_APPROVED")
    await db_session.execute(
        update(OutboxMessage)
        .where(OutboxMessage.id != sms.id)
        .values(status="SENT", sent_at=datetime.now(UTC))
    )
    channels["SMS"].fail_next(1, permanent=True, error="کاوه‌نگار 411")

    stats = await _dispatcher(db_session).dispatch()
    assert stats.dead == 1
    await db_session.refresh(sms)
    assert sms.status == "DEAD" and sms.attempts == 1

    feed = (await _feed(client, admin_token))["items"]
    alert = next(i for i in feed if i["kind"] == "OUTBOX_DEAD")
    assert "۱" in alert["body"]

    # §7.10 — «پیام DEAD به‌صورت دستی قابل تلاش مجدد است».
    listing = await client.get(
        "/api/v1/admin/outbox", headers=auth(admin_token), params={"status": "DEAD"}
    )
    assert listing.status_code == 200, listing.text
    body = listing.json()
    assert body["counts"]["DEAD"] >= 1
    row = next(i for i in body["items"] if i["id"] == str(sms.id))
    assert row["recipient_masked"] == "0912***0002"
    assert row["status_fa"] == "ارسال نشد"

    student_try = await client.post(
        f"/api/v1/admin/outbox/{sms.id}/retry", headers=auth(scene["student_token"])
    )
    assert student_try.status_code == 403

    retried = await client.post(f"/api/v1/admin/outbox/{sms.id}/retry", headers=auth(admin_token))
    assert retried.status_code == 200, retried.text
    assert retried.json()["status"] == "QUEUED" and retried.json()["attempts"] == 0
    await _dispatcher(db_session).dispatch()
    await db_session.refresh(sms)
    assert sms.status == "SENT"


async def test_fifth_failure_is_dead(client, db_session, channels) -> None:  # type: ignore[no-untyped-def]
    from silp.models.messaging import OutboxMessage

    token = await login(client, "09121229911")
    user_id = (await me(client, token))["id"]
    message = OutboxMessage(
        channel="SMS",
        recipient="09121229911",
        template="SESSIONS_REVOKED",
        payload={"values": {"name": "", "link": ""}},
        user_id=uuid.UUID(user_id),
        priority="URGENT",
        attempts=4,
        status="FAILED",
        next_attempt_at=datetime.now(UTC) - timedelta(seconds=1),
    )
    db_session.add(message)
    await db_session.flush()
    await db_session.execute(
        update(OutboxMessage)
        .where(OutboxMessage.id != message.id)
        .values(status="SENT", sent_at=datetime.now(UTC))
    )

    channels["SMS"].fail_next(1)
    stats = await _dispatcher(db_session).dispatch()
    assert stats.dead == 1
    await db_session.refresh(message)
    assert message.status == "DEAD" and message.attempts == 5


async def test_expired_lease_is_reclaimed(client, db_session, channels) -> None:  # type: ignore[no-untyped-def]
    """کارگری که وسط ارسال مُرد، پیام را برای همیشه در SENDING جا نمی‌گذارد."""
    from silp.models.messaging import OutboxMessage

    token = await login(client, "09121229912")
    user_id = (await me(client, token))["id"]
    await db_session.execute(update(OutboxMessage).values(status="SENT", sent_at=datetime.now(UTC)))
    stuck = OutboxMessage(
        channel="SMS",
        recipient="09121229912",
        template="SESSIONS_REVOKED",
        payload={"values": {"name": "", "link": ""}},
        user_id=uuid.UUID(user_id),
        status="SENDING",
        attempts=1,
        next_attempt_at=datetime.now(UTC) + timedelta(minutes=3),
    )
    db_session.add(stuck)
    await db_session.flush()

    assert (await _dispatcher(db_session).dispatch()).claimed == 0  # اجاره هنوز باقی است
    stats = await _dispatcher(db_session).dispatch(now=datetime.now(UTC) + timedelta(minutes=4))
    assert stats.sent == 1
    await db_session.refresh(stuck)
    assert stuck.status == "SENT" and stuck.attempts == 2


async def test_one_broken_channel_does_not_stop_the_others(client, db_session, channels) -> None:  # type: ignore[no-untyped-def]
    """FR-MSG-02 — تلگرامِ فیلترشده، پیامک همان اعلان را متوقف نمی‌کند."""
    from silp.models.messaging import OutboxMessage, UserChannel
    from silp.services.notification_service import NotificationService

    token = await login(client, "09121229913")
    user_id = uuid.UUID((await me(client, token))["id"])
    db_session.add(
        UserChannel(
            user_id=user_id, channel="TELEGRAM", address="777", verified_at=datetime.now(UTC)
        )
    )
    await db_session.flush()
    await db_session.execute(update(OutboxMessage).values(status="SENT", sent_at=datetime.now(UTC)))

    # URGENT ⇒ پیامک و پیام‌رسان پیوندشده، بدون توجه به ترجیح (FR-EDU-06).
    await NotificationService(db_session).notify("SESSIONS_REVOKED", [user_id])
    rows = {m.channel: m for m in await _outbox(db_session, user_id, "SESSIONS_REVOKED")}
    assert set(rows) == {"SMS", "TELEGRAM"}

    channels["TELEGRAM"].fail_next(1, error="telegram: ConnectTimeout")
    await _dispatcher(db_session).dispatch()
    for row in rows.values():
        await db_session.refresh(row)
    assert rows["SMS"].status == "SENT"
    assert rows["TELEGRAM"].status == "FAILED"
    assert channels["SMS"].sent[-1].recipient == "09121229913"


# ── مرکز اعلان — FR-MSG-01 ─────────────────────────────────────────────
async def test_feed_pages_counts_and_marks_read(client, db_session) -> None:  # type: ignore[no-untyped-def]
    from silp.services.notification_service import NotificationService

    token = await login(client, "09121229921")
    other = await login(client, "09121229922")
    user_id = uuid.UUID((await me(client, token))["id"])
    service = NotificationService(db_session)
    for badge in ("شروع سریع", "پیوسته", "پژوهشگر"):
        await service.notify("BADGE_AWARDED", [user_id], {"badge": badge}, action_url="/me/badges")

    first = await _feed(client, token, limit=2, group="SOCIAL")
    assert [i["body"] for i in first["items"]] == [
        "نشان «پژوهشگر» را گرفتی!",
        "نشان «پیوسته» را گرفتی!",
    ]
    assert first["next_cursor"]
    second = await _feed(client, token, limit=2, group="SOCIAL", cursor=first["next_cursor"])
    assert [i["body"] for i in second["items"]] == ["نشان «شروع سریع» را گرفتی!"]
    assert second["next_cursor"] is None

    count = await client.get("/api/v1/notifications/unread-count", headers=auth(token))
    before = count.json()["count"]
    assert before >= 3
    assert (await me(client, token))["unread_notifications"] == before

    target = first["items"][0]["id"]
    # اعلان دیگری ۴۰۴ است، نه ۴۰۳ — وجودش لو نمی‌رود (§6.4 قاعدهٔ ۴).
    foreign = await client.post(f"/api/v1/notifications/{target}/read", headers=auth(other))
    assert foreign.status_code == 404

    read = await client.post(f"/api/v1/notifications/{target}/read", headers=auth(token))
    assert read.status_code == 200 and read.json()["is_read"] is True
    count = await client.get("/api/v1/notifications/unread-count", headers=auth(token))
    assert count.json()["count"] == before - 1
    unread_only = await _feed(client, token, unread_only="true", group="SOCIAL")
    assert target not in [i["id"] for i in unread_only["items"]]

    cleared = await client.post("/api/v1/notifications/read-all", headers=auth(token))
    assert cleared.json()["updated"] == before - 1
    count = await client.get("/api/v1/notifications/unread-count", headers=auth(token))
    assert count.json()["count"] == 0


async def test_welcome_on_first_login_only(client, db_session) -> None:  # type: ignore[no-untyped-def]
    token = await login(client, "09121229923")
    assert (await _kinds(client, token)).count("WELCOME") == 1
    token = await login(client, "09121229923")
    assert (await _kinds(client, token)).count("WELCOME") == 1


async def test_dedup_key_makes_repeats_harmless(client, db_session) -> None:  # type: ignore[no-untyped-def]
    from silp.services.notification_service import NotificationService

    token = await login(client, "09121229924")
    user_id = uuid.UUID((await me(client, token))["id"])
    service = NotificationService(db_session)
    first = await service.notify("BADGE_AWARDED", [user_id], {"badge": "الف"}, dedup_key="BADGE:A")
    again = await service.notify("BADGE_AWARDED", [user_id], {"badge": "الف"}, dedup_key="BADGE:A")
    assert len(first) == 1 and again == []


async def test_external_action_urls_are_refused(client, db_session) -> None:  # type: ignore[no-untyped-def]
    from silp.services.notification_service import NotificationService

    token = await login(client, "09121229925")
    user_id = uuid.UUID((await me(client, token))["id"])
    for url in ("https://evil.example", "//evil.example/x"):
        with pytest.raises(ValueError, match="مسیر داخلی"):
            await NotificationService(db_session).notify(
                "BADGE_AWARDED", [user_id], {"badge": "x"}, action_url=url
            )


# ── ترجیحات — FR-MSG-02 ────────────────────────────────────────────────
async def test_preferences_default_and_update(client, db_session) -> None:  # type: ignore[no-untyped-def]
    from silp.services.notification_service import NotificationService

    token = await login(client, "09121229931")
    user_id = uuid.UUID((await me(client, token))["id"])

    response = await client.get("/api/v1/notifications/preferences", headers=auth(token))
    assert response.status_code == 200, response.text
    prefs = response.json()
    groups = {g["group"]: g["channels"] for g in prefs["groups"]}
    assert groups["PROJECT"] == ["IN_APP", "SMS"]
    assert groups["COURSE"] == ["IN_APP", "EMAIL"]
    channels = {c["channel"]: c for c in prefs["channels"]}
    assert channels["SMS"]["linked"] and channels["SMS"]["address_masked"] == "0912***9931"
    assert channels["TELEGRAM"]["available"] and not channels["TELEGRAM"]["linked"]
    assert channels["TELEGRAM"]["link_flow"] == "DEEP_LINK"
    assert channels["EITAA"]["link_flow"] == "CODE"
    assert prefs["quiet_hours"] == {"start": 0, "end": 0}

    response = await client.put(
        "/api/v1/notifications/preferences",
        headers=auth(token),
        json={"groups": {"PROJECT": ["EMAIL"]}},
    )
    assert response.status_code == 200, response.text
    groups = {g["group"]: g["channels"] for g in response.json()["groups"]}
    assert groups["PROJECT"] == ["IN_APP", "EMAIL"]  # مرکز اعلان خاموش‌شدنی نیست
    assert groups["COURSE"] == ["IN_APP", "EMAIL"]  # دست‌نخورده

    # پیامک خاموش شد ⇒ پذیرش درخواست پیامک نمی‌شود. ایمیل تأییدشده ندارد ⇒ هیچ.
    await NotificationService(db_session).notify(
        "APPLICATION_ACCEPTED", [user_id], {"project": "پروژه"}
    )
    assert await _outbox(db_session, user_id, "APPLICATION_ACCEPTED") == []

    refused = await client.put(
        "/api/v1/notifications/preferences",
        headers=auth(token),
        json={"groups": {"PROJECT": ["WHATSAPP"]}},
    )
    assert refused.status_code == 422
    assert "واتساپ" in refused.json()["error"]["message"]


async def test_low_value_kinds_never_go_by_sms(client, db_session) -> None:  # type: ignore[no-untyped-def]
    """ADR-0013 — کاربر پیامک را برای «نشان» روشن کرده، ولی نشان پیامک نمی‌شود."""
    from silp.services.notification_service import NotificationService

    token = await login(client, "09121229932")
    user_id = uuid.UUID((await me(client, token))["id"])
    await client.put(
        "/api/v1/notifications/preferences",
        headers=auth(token),
        json={"groups": {"SOCIAL": ["SMS"]}},
    )
    await NotificationService(db_session).notify("BADGE_AWARDED", [user_id], {"badge": "x"})
    assert await _outbox(db_session, user_id, "BADGE_AWARDED") == []


async def test_quiet_hours_defer_all_but_urgent(client, db_session) -> None:  # type: ignore[no-untyped-def]
    from silp.core.config import get_settings
    from silp.domain.gamification.formulas import LOCAL_TZ
    from silp.services.notification_service import NotificationService

    settings = get_settings().model_copy(update={"quiet_hours_start": 23, "quiet_hours_end": 8})
    service = NotificationService(db_session, settings)
    night = datetime(2026, 10, 1, 23, 30, tzinfo=LOCAL_TZ)
    assert service.first_attempt_at(night, "IMPORTANT") == datetime(
        2026, 10, 2, 8, 0, tzinfo=LOCAL_TZ
    )
    assert service.first_attempt_at(night, "URGENT") == night


# ── پیوند پیام‌رسان ────────────────────────────────────────────────────
async def test_telegram_deep_link_and_webhook(client, db_session) -> None:  # type: ignore[no-untyped-def]
    token = await login(client, "09121229941")
    user_id = (await me(client, token))["id"]

    started = await client.post(
        "/api/v1/notifications/channels/telegram/link", headers=auth(token), json={}
    )
    assert started.status_code == 200, started.text
    link = started.json()
    assert link["flow"] == "DEEP_LINK"
    match = re.fullmatch(r"https://t\.me/silp_test_bot\?start=([A-Za-z0-9_-]+)", link["deep_link"])
    assert match
    start_token = match.group(1)

    update_body = {
        "message": {"chat": {"id": 555001, "type": "private"}, "text": f"/start {start_token}"}
    }
    forged = await client.post(
        "/api/v1/integrations/telegram/webhook",
        json=update_body,
        headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"},
    )
    assert forged.status_code == 404

    hook = await client.post(
        "/api/v1/integrations/telegram/webhook",
        json=update_body,
        headers={"X-Telegram-Bot-Api-Secret-Token": WEBHOOK_SECRET},
    )
    assert hook.status_code == 200 and hook.json() == {"ok": True}

    prefs = (await client.get("/api/v1/notifications/preferences", headers=auth(token))).json()
    telegram = next(c for c in prefs["channels"] if c["channel"] == "TELEGRAM")
    assert telegram["linked"] and telegram["address_masked"] == "…5001"
    assert all("TELEGRAM" in g["channels"] for g in prefs["groups"])

    assert "CHANNEL_LINKED" in await _kinds(client, token)
    confirmation = await _outbox(db_session, user_id, "CHANNEL_LINKED")
    assert [m.channel for m in confirmation] == ["TELEGRAM"]
    assert confirmation[0].recipient == "555001"

    # توکن یک‌بارمصرف است؛ بار دوم ربات می‌گوید پیوند نامعتبر است.
    replay = await client.post(
        "/api/v1/integrations/telegram/webhook",
        json=update_body,
        headers={"X-Telegram-Bot-Api-Secret-Token": WEBHOOK_SECRET},
    )
    assert replay.json()["method"] == "sendMessage"

    gone = await client.delete("/api/v1/notifications/channels/telegram", headers=auth(token))
    assert gone.status_code == 204


async def test_telegram_group_chat_cannot_link(client, db_session) -> None:  # type: ignore[no-untyped-def]
    token = await login(client, "09121229942")
    link = (
        await client.post(
            "/api/v1/notifications/channels/telegram/link", headers=auth(token), json={}
        )
    ).json()
    start_token = link["deep_link"].rsplit("=", 1)[1]
    hook = await client.post(
        "/api/v1/integrations/telegram/webhook",
        json={"message": {"chat": {"id": -100, "type": "group"}, "text": f"/start {start_token}"}},
        headers={"X-Telegram-Bot-Api-Secret-Token": WEBHOOK_SECRET},
    )
    assert hook.json() == {"ok": True}
    prefs = (await client.get("/api/v1/notifications/preferences", headers=auth(token))).json()
    assert not next(c for c in prefs["channels"] if c["channel"] == "TELEGRAM")["linked"]


async def test_eitaa_is_linked_by_code(client, db_session, channels) -> None:  # type: ignore[no-untyped-def]
    token = await login(client, "09121229943")

    bad = await client.post(
        "/api/v1/notifications/channels/eitaa/link", headers=auth(token), json={"address": "ab"}
    )
    assert bad.status_code == 422

    started = await client.post(
        "/api/v1/notifications/channels/eitaa/link",
        headers=auth(token),
        json={"address": "@maryam_k"},
    )
    assert started.status_code == 200, started.text
    assert started.json()["flow"] == "CODE"

    await _dispatcher(db_session).dispatch()
    sent = [m for m in channels["EITAA"].sent if m.recipient == "@maryam_k"]
    assert sent, "کد تأیید به ایتا نرفت"
    code = re.search(r"\d{6}", sent[-1].body)
    assert code

    wrong = await client.post(
        "/api/v1/notifications/channels/eitaa/confirm",
        headers=auth(token),
        json={"code": "000000" if code.group() != "000000" else "111111"},
    )
    assert wrong.status_code == 422 and wrong.json()["error"]["code"] == "LINK_CODE_INVALID"

    confirmed = await client.post(
        "/api/v1/notifications/channels/eitaa/confirm",
        headers=auth(token),
        json={"code": code.group()},
    )
    assert confirmed.status_code == 200, confirmed.text
    eitaa = next(c for c in confirmed.json()["channels"] if c["channel"] == "EITAA")
    assert eitaa["linked"] and eitaa["address_masked"] == "@maryam_k"


async def test_link_requests_are_rate_limited(client, db_session) -> None:  # type: ignore[no-untyped-def]
    token = await login(client, "09121229944")
    for _ in range(3):
        ok = await client.post(
            "/api/v1/notifications/channels/telegram/link", headers=auth(token), json={}
        )
        assert ok.status_code == 200
    limited = await client.post(
        "/api/v1/notifications/channels/telegram/link", headers=auth(token), json={}
    )
    assert limited.status_code == 429


# ── رویدادهای دامنه ────────────────────────────────────────────────────
async def test_application_submission_and_rejection(client, db_session) -> None:  # type: ignore[no-untyped-def]
    lead_token, _ = await _actor(client, db_session, LEAD_MOBILE)
    student_token, _ = await _actor(client, db_session, STUDENT_MOBILE, first_name="زهرا")
    project_id = await _published_project(client, db_session, lead_token)

    applied = await client.post(
        f"/api/v1/projects/{project_id}/applications",
        headers=auth(student_token),
        json={"motivation": "انگیزه‌نامهٔ کاملاً معتبر برای این پروژه."},
    )
    assert applied.status_code == 201, applied.text
    submitted = next(
        i
        for i in (await _feed(client, lead_token))["items"]
        if i["kind"] == "APPLICATION_SUBMITTED"
    )
    assert "زهرا" in submitted["body"]
    assert submitted["action_url"] == f"/projects/{project_id}/applications"

    await client.post(
        f"/api/v1/applications/{applied.json()['id']}/decide",
        headers=auth(lead_token),
        json={"decision": "REJECTED", "note": "ظرفیت تیم پر شد."},
    )
    rejected = next(
        i
        for i in (await _feed(client, student_token))["items"]
        if i["kind"] == "APPLICATION_REJECTED"
    )
    assert rejected["body"].endswith("ظرفیت تیم پر شد.")


async def test_urgent_announcement_forces_sms(client, db_session) -> None:  # type: ignore[no-untyped-def]
    """FR-EDU-06 — درس پیش‌فرضاً پیامک ندارد، ولی اعلان URGENT پیامک می‌شود."""
    scene = await _scene(client, db_session)
    offering_id = scene["offering"].id

    for priority in ("NORMAL", "URGENT"):
        response = await client.post(
            f"/api/v1/teach/offerings/{offering_id}/announcements",
            headers=auth(scene["instructor_token"]),
            json={
                "title": f"اعلان {priority}",
                "body": "جلسهٔ فردا در آزمایشگاه است.",
                "priority": priority,
            },
        )
        assert response.status_code == 201, response.text

    feed = (await _feed(client, scene["student_token"]))["items"]
    posted = {i["priority"]: i for i in feed if i["kind"] == "ANNOUNCEMENT_POSTED"}
    assert set(posted) == {"NORMAL", "URGENT"}
    assert posted["URGENT"]["title"] == "ایمنی راه: اعلان URGENT"

    sms = [
        m
        for m in await _outbox(db_session, scene["student_id"], "ANNOUNCEMENT_POSTED")
        if m.channel == "SMS"
    ]
    assert [m.priority for m in sms] == ["URGENT"]
    # نویسنده اعلان خودش را نمی‌گیرد.
    assert "ANNOUNCEMENT_POSTED" not in await _kinds(client, scene["instructor_token"])


async def test_week_and_quiz_publication_notify_the_class(client, db_session) -> None:  # type: ignore[no-untyped-def]
    from silp.models.education import CourseWeek

    scene = await _scene(client, db_session)
    offering_id = scene["offering"].id
    response = await client.put(
        f"/api/v1/teach/offerings/{offering_id}/weeks",
        headers=auth(scene["instructor_token"]),
        json={"week_number": 4, "title_fa": "تحلیل تقاضای سفر"},
    )
    assert response.status_code == 200, response.text
    week_id = await db_session.scalar(
        select(CourseWeek.id).where(
            CourseWeek.offering_id == offering_id, CourseWeek.week_number == 4
        )
    )
    for _ in range(2):  # بازانتشار دوباره خبر نمی‌کند
        published = await client.post(
            f"/api/v1/teach/weeks/{week_id}/publish",
            headers=auth(scene["instructor_token"]),
            json={},
        )
        assert published.status_code == 200, published.text

    await _add_question(client, scene, kind="SINGLE_CHOICE", payload=SINGLE_PAYLOAD)
    await _publish(client, scene)

    feed = (await _feed(client, scene["student_token"]))["items"]
    weeks = [i for i in feed if i["kind"] == "WEEK_PUBLISHED"]
    assert len(weeks) == 1
    assert weeks[0]["title"] == "هفتهٔ ۴ «ایمنی راه» منتشر شد"
    assert weeks[0]["action_url"] == f"/courses/{offering_id}/weeks/4"
    opened = next(i for i in feed if i["kind"] == "QUIZ_OPENED")
    assert "مهلت:" in opened["body"] and "ساعت" in opened["body"]
    assert "WEEK_PUBLISHED" not in await _kinds(client, scene["instructor_token"])


async def test_token_reuse_notifies_the_owner(client, db_session) -> None:  # type: ignore[no-untyped-def]
    mobile = "09121229951"
    challenge = await client.post(
        "/api/v1/auth/otp/request", json={"destination": mobile, "channel": "SMS"}
    )
    verified = await client.post(
        "/api/v1/auth/otp/verify",
        json={"challenge_id": challenge.json()["challenge_id"], "code": "111111"},
    )
    refresh = verified.json()["refresh_token"]
    user_id = verified.json()["user"]["id"]
    assert (
        await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    ).status_code == 200
    reused = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert reused.status_code == 401

    rows = await _outbox(db_session, user_id, "SESSIONS_REVOKED")
    assert [m.channel for m in rows] == ["SMS"]
    assert rows[0].priority == "URGENT"


# ── یادآوری و خلاصه — §7.11 ────────────────────────────────────────────
async def test_deadline_reminders_are_idempotent(client, db_session) -> None:  # type: ignore[no-untyped-def]
    from silp.domain.gamification.formulas import LOCAL_TZ
    from silp.models.delivery import Milestone
    from silp.services.reminder_service import ReminderService

    lead_token, student_token, _, milestone_id = await _team_of_two(client, db_session)
    today = datetime.now(UTC).astimezone(LOCAL_TZ).date()
    await db_session.execute(
        update(Milestone)
        .where(Milestone.id == uuid.UUID(milestone_id))
        .values(due_on=today + timedelta(days=3))
    )

    first = await ReminderService(db_session).send_deadline_reminders()
    assert first.milestones == 2  # مدیر و عضو
    again = await ReminderService(db_session).send_deadline_reminders()
    assert again.milestones == 0

    reminder = next(
        i for i in (await _feed(client, student_token))["items"] if i["kind"] == "DEADLINE_REMINDER"
    )
    assert reminder["title"].startswith("۳ روز تا مهلت")


async def test_quiz_closing_reminder_skips_those_who_took_it(client, db_session) -> None:  # type: ignore[no-untyped-def]
    from silp.domain.gamification.formulas import LOCAL_TZ
    from silp.services.reminder_service import ReminderService

    # یادآور بر اساس «روز» تهران است، نه ۲۴ ساعت: «اکنون + ۲۵ ساعت» پس از
    # ساعت ۲۳ تهران دو روز تقویمی جلوتر می‌افتد و یادآور «یک روز مانده» نمی‌گیرد.
    # ظهر فردای تهران در هر ساعتی از شبانه‌روز «یک روز مانده» است.
    local_now = datetime.now(LOCAL_TZ)
    tomorrow_noon = (local_now + timedelta(days=1)).replace(hour=12, minute=0, second=0)
    scene = await _scene(client, db_session, closes_delta=tomorrow_noon - local_now)
    await _add_question(client, scene, kind="SINGLE_CHOICE", payload=SINGLE_PAYLOAD)
    await _publish(client, scene)

    stats = await ReminderService(db_session).send_deadline_reminders()
    assert stats.quizzes == 1
    assert "QUIZ_CLOSING" in await _kinds(client, scene["student_token"])
    assert (await ReminderService(db_session).send_deadline_reminders()).quizzes == 0


async def test_weekly_digest_for_students_and_teachers(client, db_session) -> None:  # type: ignore[no-untyped-def]
    from silp.models.education import Enrollment
    from silp.services.reminder_service import ReminderService

    scene = await _scene(client, db_session)
    outsider = await login(client, "09121229961")
    db_session.add(
        Enrollment(
            offering_id=scene["offering"].id,
            student_id=uuid.UUID((await me(client, outsider))["id"]),
            status="PENDING",
        )
    )
    await db_session.flush()

    stats = await ReminderService(db_session).weekly_digest()
    assert stats.teachers >= 1
    teacher = next(
        i
        for i in (await _feed(client, scene["instructor_token"]))["items"]
        if i["kind"] == "WEEKLY_DIGEST_TEACHER"
    )
    assert "۱ درخواست ثبت‌نام" in teacher["body"]
    student_digest = [
        i
        for i in (await _feed(client, scene["student_token"]))["items"]
        if i["kind"] == "WEEKLY_DIGEST"
    ]
    assert len(student_digest) == 1  # دانشجوی ثبت‌نام‌شده خوانده‌نشده دارد (خوش‌آمد)

    again = await ReminderService(db_session).weekly_digest()
    assert again.students == 0 and again.teachers == 0


# ── الگوها — FR-MSG-03 ─────────────────────────────────────────────────
async def test_template_admin_validates_previews_and_applies_at_dispatch(  # type: ignore[no-untyped-def]
    client, db_session, channels
) -> None:
    from silp.models.messaging import OutboxMessage
    from silp.services.notification_service import NotificationService

    admin_token = await _admin(client, db_session)
    student_token = await login(client, "09121229971")
    student_id = uuid.UUID((await me(client, student_token))["id"])

    listing = await client.get("/api/v1/admin/message-templates", headers=auth(admin_token))
    assert listing.status_code == 200
    assert any(t["code"] == "WELCOME" and t["channel"] == "IN_APP" for t in listing.json())
    assert (
        await client.get("/api/v1/admin/message-templates", headers=auth(student_token))
    ).status_code == 403

    bad = await client.put(
        "/api/v1/admin/message-templates/SESSIONS_REVOKED/SMS",
        headers=auth(admin_token),
        json={"body": "سلام {{nmae}}"},
    )
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "TEMPLATE_INVALID"

    off = await client.put(
        "/api/v1/admin/message-templates/WELCOME/IN_APP",
        headers=auth(admin_token),
        json={"subject": "خوش آمدی", "body": "سلام", "is_active": False},
    )
    assert off.status_code == 422

    preview = await client.post(
        "/api/v1/admin/message-templates/preview",
        headers=auth(admin_token),
        json={
            "code": "DEADLINE_REMINDER",
            "channel": "SMS",
            "body": "مهلت «{{milestone}}» {{days}} روز",
        },
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["body"] == "مهلت «گزارش مرور ادبیات» ۳ روز"
    assert preview.json()["sms_parts"] == 1

    await db_session.execute(update(OutboxMessage).values(status="SENT", sent_at=datetime.now(UTC)))
    await NotificationService(db_session).notify("SESSIONS_REVOKED", [student_id])
    edited = await client.put(
        "/api/v1/admin/message-templates/SESSIONS_REVOKED/SMS",
        headers=auth(admin_token),
        json={"body": "سابِر: نشست‌هایت بسته شد، {{name}}."},
    )
    assert edited.status_code == 200, edited.text
    # پیامی که پیش از ویرایش در صف رفت، متن تازه را می‌برد — رندر هنگام ارسال است.
    await _dispatcher(db_session).dispatch()
    assert channels["SMS"].sent[-1].body == "سابِر: نشست‌هایت بسته شد، ."


# ── SSE — §5.10 ────────────────────────────────────────────────────────
async def test_stream_emits_count_then_new_notifications(client, db_session) -> None:  # type: ignore[no-untyped-def]
    from silp.services.notification_service import NotificationService
    from silp.services.notification_stream import notification_events

    token = await login(client, "09121229981")
    user_id = uuid.UUID((await me(client, token))["id"])

    @asynccontextmanager
    async def same_session() -> AsyncIterator[Any]:
        yield db_session

    stream = notification_events(
        user_id, open_session=same_session, poll_seconds=0.01, max_seconds=5, use_redis=False
    )
    assert await anext(stream) == "retry: 5000\n\n"
    first = await anext(stream)
    assert first.startswith("event: unread\n") and '"count":1' in first  # خوش‌آمد

    await NotificationService(db_session).notify("BADGE_AWARDED", [user_id], {"badge": "شروع سریع"})
    chunks = []
    for _ in range(20):
        chunk = await anext(stream)
        chunks.append(chunk)
        if chunk.startswith("event: unread"):
            break
    await stream.aclose()
    notification = next(c for c in chunks if c.startswith("event: notification"))
    assert "نشان «شروع سریع» را گرفتی!" in notification
    assert '"count":2' in chunks[-1]


async def test_stream_requires_a_token(client) -> None:  # type: ignore[no-untyped-def]
    response = await client.get("/api/v1/notifications/stream")
    assert response.status_code == 401


# ── رویدادهای بیشتر ────────────────────────────────────────────────────
async def test_enrollment_request_and_decision(client, db_session) -> None:  # type: ignore[no-untyped-def]
    """§7.2 — `→ PENDING` ⇒ اعلان به استاد؛ تصمیم ⇒ اعلان به دانشجو."""
    scene = await _scene(client, db_session)
    scene["offering"].requires_approval = True
    await db_session.flush()
    newcomer = await login(client, "09121229991")

    enrolled = await client.post(
        f"/api/v1/offerings/{scene['offering'].id}/enroll", headers=auth(newcomer), json={}
    )
    assert enrolled.status_code == 201, enrolled.text
    assert enrolled.json()["status"] == "PENDING"
    request = next(
        i
        for i in (await _feed(client, scene["instructor_token"]))["items"]
        if i["kind"] == "ENROLLMENT_REQUESTED"
    )
    assert "ایمنی راه" in request["body"]

    decided = await client.post(
        f"/api/v1/teach/enrollments/{enrolled.json()['id']}/decide",
        headers=auth(scene["instructor_token"]),
        json={"approve": True},
    )
    assert decided.status_code == 200, decided.text
    approved = next(
        i for i in (await _feed(client, newcomer))["items"] if i["kind"] == "ENROLLMENT_APPROVED"
    )
    assert approved["action_url"] == f"/courses/{scene['offering'].id}"


async def test_manual_grading_announces_the_result(client, db_session) -> None:  # type: ignore[no-untyped-def]
    """تصحیح خودکار اعلان ندارد؛ تصحیح تشریحی به دست استاد دارد."""
    from tests.integration.test_quiz_flow import ESSAY_PAYLOAD, _answer, _start

    scene = await _scene(client, db_session)
    q1 = await _add_question(
        client, scene, kind="SINGLE_CHOICE", payload=SINGLE_PAYLOAD, points="2"
    )
    q2 = await _add_question(
        client, scene, kind="ESSAY", payload=ESSAY_PAYLOAD, points="5", body="تشریحی"
    )
    await _publish(client, scene)
    started = await _start(client, scene)
    await _answer(client, scene, started, q1, {"selected": ["b"]})
    await _answer(client, scene, started, q2, {"text": "پاسخ من دربارهٔ ایمنی راه."})
    await client.post(
        f"/api/v1/attempts/{started['attempt_id']}/submit",
        headers=auth(scene["student_token"]),
        json={"confirm_unanswered": 0},
    )
    assert "QUIZ_RESULT" not in await _kinds(client, scene["student_token"])

    graded = await client.put(
        f"/api/v1/teach/quizzes/{scene['quiz_id']}/attempts/{started['attempt_id']}/answers/{q2}",
        headers=auth(scene["instructor_token"]),
        json={"score": "4"},
    )
    assert graded.status_code == 200, graded.text
    result = next(
        i
        for i in (await _feed(client, scene["student_token"]))["items"]
        if i["kind"] == "QUIZ_RESULT"
    )
    assert result["body"] == "نتیجهٔ «آزمون هفتهٔ پنجم»: ۶ از ۷"
    assert result["action_url"] == f"/quiz/{started['attempt_id']}/result"


async def test_stalled_project_alerts_the_lead_once(client, db_session) -> None:  # type: ignore[no-untyped-def]
    from silp.models.project import Project
    from silp.services.project_health_service import ProjectHealthService

    lead_token, _, project_id, _ = await _team_of_two(client, db_session)
    await db_session.execute(
        update(Project)
        .where(Project.id == uuid.UUID(project_id))
        .values(last_activity_at=datetime.now(UTC) - timedelta(days=20))
    )
    await ProjectHealthService(db_session).recompute()
    await ProjectHealthService(db_session).recompute()  # هنوز STALLED — اعلان دوباره نه
    stalled = [
        i for i in (await _feed(client, lead_token))["items"] if i["kind"] == "PROJECT_STALLED"
    ]
    assert len(stalled) == 1
    assert "۲۰ روز" in stalled[0]["body"]


async def test_new_badge_is_announced(client, db_session) -> None:  # type: ignore[no-untyped-def]
    """نشان را کار پس‌زمینه اعطا می‌کند؛ کاربر شاید آنلاین نباشد، پس اعلان لازم است."""
    from silp.services.badge_service import BadgeService

    lead_token, student_token, _, _ = await _team_of_two(client, db_session)
    student_id = uuid.UUID((await me(client, student_token))["id"])
    awarded = await BadgeService(db_session).evaluate_user(student_id)
    assert awarded, "دانشجوی پذیرفته‌شده دست‌کم «شروع سریع» را دارد"
    badges = [
        i for i in (await _feed(client, student_token))["items"] if i["kind"] == "BADGE_AWARDED"
    ]
    assert len(badges) == len(awarded)
    assert all(b["action_url"] == "/me/badges" for b in badges)
