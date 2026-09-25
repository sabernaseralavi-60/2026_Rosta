"""اعلان Push وب — ADR-0029.

PostgreSQL واقعی لازم است: `endpoint` یک ایندکس یکتاست و انتقال اشتراک بین
دو حساب یک `ON CONFLICT DO UPDATE` است. آداپتور حافظه‌ای است
(`PUSH_PROVIDER=memory`)؛ رمزنگاری خودش در `tests/unit/test_push.py` آزموده شده.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import pytest
from sqlalchemy import func, select
from tests.integration.helpers import auth, login, me

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

FCM = "https://fcm.googleapis.com/fcm/send/"
MOZ = "https://updates.push.services.mozilla.com/wpush/v2/"
PATH = "/api/v1/notifications/push/subscriptions"


def _sub(endpoint: str) -> dict[str, Any]:
    return {"endpoint": endpoint, "keys": {"p256dh": "BPk" + "A" * 84, "auth": "auth-secret-16b"}}


async def _subscribe(client: Any, token: str, endpoint: str) -> Any:
    return await client.post(PATH, headers=auth(token), json=_sub(endpoint))


async def _user(client: Any, mobile: str) -> tuple[str, uuid.UUID]:
    token = await login(client, mobile)
    return token, uuid.UUID((await me(client, token))["id"])


async def _outbox(session: Any, user_id: uuid.UUID, channel: str = "PUSH") -> list[Any]:
    from silp.models.messaging import OutboxMessage

    return list(
        await session.scalars(
            select(OutboxMessage)
            .where(OutboxMessage.user_id == user_id, OutboxMessage.channel == channel)
            .order_by(OutboxMessage.created_at)
        )
    )


async def _subscriptions(session: Any, user_id: uuid.UUID) -> list[str]:
    from silp.models.messaging import PushSubscription

    return list(
        await session.scalars(
            select(PushSubscription.endpoint)
            .where(PushSubscription.user_id == user_id)
            .order_by(PushSubscription.created_at, PushSubscription.id)
        )
    )


def _dispatcher(session: Any) -> Any:
    from silp.services.outbox_service import OutboxService

    return OutboxService(session)


async def _notify(session: Any, user_id: uuid.UUID, **kwargs: Any) -> None:
    from silp.services.notification_service import NotificationService

    await NotificationService(session).notify(
        "APPLICATION_ACCEPTED", [user_id], {"project": "پروژهٔ خرما"}, **kwargs
    )
    await session.commit()


# ── تنظیمات ─────────────────────────────────────────────────────────────
async def test_preferences_offer_push_and_the_public_key(client, db_session) -> None:  # type: ignore[no-untyped-def]
    token, _ = await _user(client, "09121228801")
    prefs = (await client.get("/api/v1/notifications/preferences", headers=auth(token))).json()
    push = next(c for c in prefs["channels"] if c["channel"] == "PUSH")
    assert push["available"] and not push["linked"] and not push["requires_link"]
    assert push["devices"] == 0 and push["address_masked"] is None
    assert prefs["push_public_key"] == "BTestPublicKeyOnlyForTests"
    assert all("PUSH" not in g["channels"] for g in prefs["groups"])  # پیش‌فرض خاموش


async def test_public_key_is_withheld_when_push_is_off(client, db_session, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from silp.core.config import get_settings

    token, _ = await _user(client, "09121228802")
    monkeypatch.setattr(get_settings(), "push_provider", "disabled")
    prefs = (await client.get("/api/v1/notifications/preferences", headers=auth(token))).json()
    push = next(c for c in prefs["channels"] if c["channel"] == "PUSH")
    assert not push["available"]
    assert prefs["push_public_key"] is None
    refused = await _subscribe(client, token, FCM + "off")
    assert refused.status_code == 422 and "فعال نیست" in refused.json()["error"]["message"]


# ── ثبت و برداشتن ───────────────────────────────────────────────────────
async def test_subscribing_turns_push_on_for_every_group(client, db_session) -> None:  # type: ignore[no-untyped-def]
    token, user_id = await _user(client, "09121228803")
    response = await _subscribe(client, token, FCM + "phone")
    assert response.status_code == 200, response.text
    assert response.json() == {"devices": 1}

    prefs = (await client.get("/api/v1/notifications/preferences", headers=auth(token))).json()
    assert all("PUSH" in g["channels"] and "IN_APP" in g["channels"] for g in prefs["groups"])
    push = next(c for c in prefs["channels"] if c["channel"] == "PUSH")
    assert push["linked"] and push["devices"] == 1

    # دستگاه دوم ترجیحات را دوباره روشن نمی‌کند: کاربر ممکن است یک دسته را خاموش کرده باشد.
    await client.put(
        "/api/v1/notifications/preferences",
        headers=auth(token),
        json={"groups": {"SOCIAL": ["IN_APP"]}},
    )
    assert (await _subscribe(client, token, MOZ + "laptop")).json() == {"devices": 2}
    groups = {
        g["group"]: g["channels"]
        for g in (
            await client.get("/api/v1/notifications/preferences", headers=auth(token))
        ).json()["groups"]
    }
    assert "PUSH" not in groups["SOCIAL"] and "PUSH" in groups["COURSE"]
    assert len(await _subscriptions(db_session, user_id)) == 2


async def test_resubscribing_the_same_browser_is_idempotent(client, db_session) -> None:  # type: ignore[no-untyped-def]
    token, user_id = await _user(client, "09121228804")
    await _subscribe(client, token, FCM + "same")
    again = await _subscribe(client, token, FCM + "same")
    assert again.json() == {"devices": 1}
    assert await _subscriptions(db_session, user_id) == [FCM + "same"]


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://fcm.googleapis.com/fcm/send/x",
        "https://localhost/x",
        "https://127.0.0.1/x",
        "https://10.1.2.3/x",
        "https://evil.example.com/fcm.googleapis.com",
        "https://fcm.googleapis.com.evil.example/x",
    ],
)
async def test_endpoints_outside_the_allowlist_are_refused(client, db_session, endpoint) -> None:  # type: ignore[no-untyped-def]
    token, user_id = await _user(client, "09121228805")
    response = await _subscribe(client, token, endpoint)
    assert response.status_code == 422, response.text
    assert await _subscriptions(db_session, user_id) == []


async def test_missing_keys_are_refused(client, db_session) -> None:  # type: ignore[no-untyped-def]
    token, _ = await _user(client, "09121228806")
    response = await client.post(
        PATH, headers=auth(token), json={"endpoint": FCM + "k", "keys": {"p256dh": "x"}}
    )
    assert response.status_code == 422


async def test_subscribing_requires_a_token(client) -> None:  # type: ignore[no-untyped-def]
    assert (await client.post(PATH, json=_sub(FCM + "anon"))).status_code == 401
    assert (await client.delete(PATH, params={"endpoint": FCM + "anon"})).status_code == 401


async def test_unsubscribing_removes_only_this_browser(client, db_session) -> None:  # type: ignore[no-untyped-def]
    token, user_id = await _user(client, "09121228807")
    await _subscribe(client, token, FCM + "one")
    await _subscribe(client, token, MOZ + "two")
    response = await client.delete(PATH, headers=auth(token), params={"endpoint": FCM + "one"})
    assert response.status_code == 200 and response.json() == {"devices": 1}
    assert await _subscriptions(db_session, user_id) == [MOZ + "two"]


async def test_nobody_can_remove_another_users_subscription(client, db_session) -> None:  # type: ignore[no-untyped-def]
    owner, owner_id = await _user(client, "09121228808")
    other, _ = await _user(client, "09121228809")
    await _subscribe(client, owner, FCM + "mine")
    response = await client.delete(PATH, headers=auth(other), params={"endpoint": FCM + "mine"})
    assert response.status_code == 200 and response.json() == {
        "devices": 0
    }  # نه ۴۰۴: وجودش لو نرود
    assert await _subscriptions(db_session, owner_id) == [FCM + "mine"]


async def test_a_shared_browser_follows_the_latest_login(client, db_session) -> None:  # type: ignore[no-untyped-def]
    """رایانهٔ مشترک: اعلان کاربر قبلی نباید روی دستگاه کاربر بعدی بیاید، و برعکس."""
    first, first_id = await _user(client, "09121228810")
    second, second_id = await _user(client, "09121228811")
    await _subscribe(client, first, FCM + "lab-pc")
    assert (await _subscribe(client, second, FCM + "lab-pc")).json() == {"devices": 1}

    assert await _subscriptions(db_session, first_id) == []
    assert await _subscriptions(db_session, second_id) == [FCM + "lab-pc"]
    from silp.models.messaging import PushSubscription

    total = await db_session.scalar(
        select(func.count())
        .select_from(PushSubscription)
        .where(PushSubscription.endpoint == FCM + "lab-pc")
    )
    assert total == 1


async def test_only_the_ten_newest_devices_are_kept(client, db_session) -> None:  # type: ignore[no-untyped-def]
    token, user_id = await _user(client, "09121228812")
    for n in range(12):
        response = await _subscribe(client, token, f"{FCM}dev-{n:02d}")
        assert response.status_code == 200
    kept = await _subscriptions(db_session, user_id)
    assert len(kept) == 10
    assert f"{FCM}dev-00" not in kept and f"{FCM}dev-11" in kept


# ── ارسال ───────────────────────────────────────────────────────────────
async def test_each_device_gets_its_own_message(client, db_session, channels) -> None:  # type: ignore[no-untyped-def]
    token, user_id = await _user(client, "09121228813")
    await _subscribe(client, token, FCM + "phone")
    await _subscribe(client, token, MOZ + "laptop")

    await _notify(db_session, user_id, action_url="/projects/abc/workspace")
    queued = await _outbox(db_session, user_id)
    assert len(queued) == 2 and {m.status for m in queued} == {"QUEUED"}

    stats = await _dispatcher(db_session).dispatch()
    assert stats.sent >= 2
    sent = channels["PUSH"].sent
    assert len(sent) == 2
    endpoints = {json.loads(m.recipient)["endpoint"] for m in sent}
    assert endpoints == {FCM + "phone", MOZ + "laptop"}
    first = sent[0]
    assert first.subject and "http" not in first.body  # لینک در متن نیست
    assert first.link and first.link.endswith("/projects/abc/workspace")
    assert first.priority in {"NORMAL", "IMPORTANT", "URGENT"}


async def test_no_devices_means_no_push(client, db_session, channels) -> None:  # type: ignore[no-untyped-def]
    _, user_id = await _user(client, "09121228814")
    await _notify(db_session, user_id)
    assert await _outbox(db_session, user_id) == []


async def test_group_preference_can_switch_push_off(client, db_session, channels) -> None:  # type: ignore[no-untyped-def]
    token, user_id = await _user(client, "09121228815")
    await _subscribe(client, token, FCM + "phone")
    await client.put(
        "/api/v1/notifications/preferences",
        headers=auth(token),
        json={"groups": {"PROJECT": ["SMS"]}},
    )
    await _notify(db_session, user_id)
    assert await _outbox(db_session, user_id) == []


async def test_revoked_subscription_is_forgotten_without_alarming_admins(  # type: ignore[no-untyped-def]
    client, db_session, channels
) -> None:
    from silp.models.messaging import Notification
    from silp.services.outbox_service import REVOKED_ERROR

    token, user_id = await _user(client, "09121228816")
    await _subscribe(client, token, FCM + "gone")
    await _subscribe(client, token, MOZ + "alive")
    await _notify(db_session, user_id)

    channels["PUSH"].fail_next(1, revoked=True, error="webpush: 410")
    stats = await _dispatcher(db_session).dispatch()
    assert stats.revoked == 1 and stats.dead == 0 and stats.sent >= 1

    dead = [m for m in await _outbox(db_session, user_id) if m.status == "DEAD"]
    assert len(dead) == 1 and dead[0].last_error == REVOKED_ERROR
    # هر اشتراکی که پیام اولش رد شد پاک شد؛ دیگری می‌ماند.
    remaining = await _subscriptions(db_session, user_id)
    assert len(remaining) == 1

    alerts = await db_session.scalar(
        select(func.count()).select_from(Notification).where(Notification.kind == "OUTBOX_DEAD")
    )
    assert not alerts


async def test_push_outage_does_not_stop_other_channels(client, db_session, channels) -> None:  # type: ignore[no-untyped-def]
    """FCM از ایران در دسترس نیست: پیام Push می‌ماند، پیامک می‌رود (FR-MSG-02)."""
    token, user_id = await _user(client, "09121228817")
    await _subscribe(client, token, FCM + "phone")
    channels["PUSH"].fail_next(1)
    await _notify(db_session, user_id)

    stats = await _dispatcher(db_session).dispatch()
    assert stats.failed >= 1
    [push] = await _outbox(db_session, user_id, "PUSH")
    [sms] = await _outbox(db_session, user_id, "SMS")
    assert push.status == "FAILED" and push.attempts == 1
    assert sms.status == "SENT"


async def test_admin_outbox_shows_the_push_host_not_the_keys(client, db_session, channels) -> None:  # type: ignore[no-untyped-def]
    from tests.integration.helpers import grant_role

    admin = await login(client, "09121228818")
    await grant_role(db_session, (await me(client, admin))["id"], "ADMIN")
    admin = await login(client, "09121228818")
    token, user_id = await _user(client, "09121228819")
    await _subscribe(client, token, FCM + "secret-device-token")
    await _notify(db_session, user_id)

    listing = await client.get(
        "/api/v1/admin/outbox",
        headers=auth(admin),
        params={"channel": "PUSH", "user_id": str(user_id)},
    )
    assert listing.status_code == 200, listing.text
    [row] = listing.json()["items"]
    assert row["recipient_masked"] == "fcm.googleapis.com"
    assert "secret-device-token" not in listing.text and "auth-secret" not in listing.text
