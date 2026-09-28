"""اعلان به مشتریِ دارای حساب هنگام رسیدگی مالک به درخواست — ADR-0033.

PostgreSQL واقعی لازم است (الگوهای `message_templates` را مهاجرت ۰۰۲۷ می‌کارد).
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy import select, update
from tests.integration.helpers import auth, grant_role, login, me

from silp.models.identity import User
from silp.models.intake import IntakeRequest
from silp.models.messaging import Notification, OutboxMessage

pytestmark = pytest.mark.integration

OWNER = "09121780001"
CLIENT = "09121780002"
SECRET = "یادداشت خصوصی مالک دربارهٔ بودجه"
PUBLIC = "برای هماهنگی جلسه، فردا با شما تماس می‌گیریم."
KINDS = ("INTAKE_STATUS_CHANGED", "INTAKE_MESSAGE")


async def _owner(client: Any, session: Any) -> str:
    token = await login(client, OWNER)
    user_id = uuid.UUID(str((await me(client, token))["id"]))
    await grant_role(session, user_id, "ADMIN")
    return token


async def _submit(client: Any, mobile: str = CLIENT) -> str:
    response = await client.post(
        "/api/v1/public/intake",
        json={
            "need_type": "Commercial",
            "services": ["Website / Web App"],
            "summary": "برای کسب‌وکارم به یک وب‌سایت فروش نیاز دارم.",
            "name": "رضا محمدی",
            "mobile": mobile,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["tracking_code"]


async def _request(session: Any, code: str) -> IntakeRequest:
    row = await session.scalar(select(IntakeRequest).where(IntakeRequest.tracking_code == code))
    assert row is not None
    return row


async def _patch(client: Any, owner: str, request: IntakeRequest, **body: Any) -> None:
    response = await client.patch(
        f"/api/v1/admin/intake/{request.id}", json=body, headers=auth(owner)
    )
    assert response.status_code == 200, response.text


async def _notices(session: Any, user_id: uuid.UUID) -> list[Notification]:
    rows = await session.scalars(
        select(Notification)
        .where(Notification.user_id == user_id, Notification.kind.in_(KINDS))
        .order_by(Notification.created_at, Notification.id)
    )
    return list(rows)


async def _client_id(client: Any) -> uuid.UUID:
    token = await login(client, CLIENT)  # ورود با OTP ⇒ موبایل تأییدشده
    return uuid.UUID(str((await me(client, token))["id"]))


async def test_status_change_notifies_the_registered_client(client, db_session) -> None:  # type: ignore[no-untyped-def]
    owner = await _owner(client, db_session)
    code = await _submit(client)  # پیش از ثبت‌نام؛ `user_id` تهی است
    user_id = await _client_id(client)
    request = await _request(db_session, code)
    assert request.user_id is None

    await _patch(client, owner, request, status="ACCEPTED", public_note=PUBLIC, owner_note=SECRET)

    (notice,) = await _notices(db_session, user_id)
    assert notice.kind == "INTAKE_STATUS_CHANGED"
    assert code in notice.title and "پذیرفته‌شده" in notice.title
    assert code in notice.body and PUBLIC in notice.body
    assert notice.action_url == "/me/requests"
    # اعلان به داشبوردِ مشتری می‌رود و هیچ نشانی از یادداشت خصوصی یا راه تماس ندارد.
    text = f"{notice.title} {notice.body}"
    assert SECRET not in text and CLIENT not in text
    # پیامک هزینه دارد و برای این اعلان الگو ندارد (ADR-0013 بند ۵).
    sent = await db_session.scalars(
        select(OutboxMessage).where(
            OutboxMessage.user_id == user_id, OutboxMessage.template.in_(KINDS)
        )
    )
    assert "SMS" not in {m.channel for m in sent}


async def test_a_note_without_a_status_change_is_a_message(client, db_session) -> None:  # type: ignore[no-untyped-def]
    owner = await _owner(client, db_session)
    code = await _submit(client)
    user_id = await _client_id(client)
    request = await _request(db_session, code)

    await _patch(client, owner, request, public_note=PUBLIC)

    (notice,) = await _notices(db_session, user_id)
    assert notice.kind == "INTAKE_MESSAGE" and PUBLIC in notice.body and code in notice.body


async def test_each_handling_step_is_its_own_notice_and_internal_steps_are_silent(  # type: ignore[no-untyped-def]
    client, db_session
) -> None:
    owner = await _owner(client, db_session)
    code = await _submit(client)
    user_id = await _client_id(client)
    request = await _request(db_session, code)

    await _patch(client, owner, request, status="IN_REVIEW")
    await _patch(client, owner, request, owner_note=SECRET)  # فقط یادداشت خصوصی
    await _patch(client, owner, request, status="ARCHIVED")  # کار داخلی
    await _patch(client, owner, request, status="NEW")  # بازگشت داخلی
    await _patch(client, owner, request, status="DECLINED", public_note=PUBLIC)

    notices = await _notices(db_session, user_id)
    assert [n.kind for n in notices] == ["INTAKE_STATUS_CHANGED"] * 2
    assert "در حال بررسی" in notices[0].title and "پذیرفته‌نشده" in notices[1].title
    assert all(SECRET not in n.body for n in notices)


async def test_an_internal_status_change_with_a_note_still_delivers_the_note(  # type: ignore[no-untyped-def]
    client, db_session
) -> None:
    owner = await _owner(client, db_session)
    code = await _submit(client)
    user_id = await _client_id(client)
    request = await _request(db_session, code)

    await _patch(client, owner, request, status="ARCHIVED", public_note=PUBLIC)

    (notice,) = await _notices(db_session, user_id)
    assert notice.kind == "INTAKE_MESSAGE" and PUBLIC in notice.body


async def test_a_client_without_an_account_gets_nothing(client, db_session) -> None:  # type: ignore[no-untyped-def]
    owner = await _owner(client, db_session)
    code = await _submit(client)
    request = await _request(db_session, code)

    await _patch(client, owner, request, status="ACCEPTED", public_note=PUBLIC)

    assert not list(
        await db_session.scalars(select(Notification).where(Notification.kind.in_(KINDS)))
    )
    assert not list(
        await db_session.scalars(select(OutboxMessage).where(OutboxMessage.template.in_(KINDS)))
    )


async def test_an_unverified_contact_is_not_notified(client, db_session) -> None:  # type: ignore[no-untyped-def]
    """همان قاعدهٔ `/me/requests`: شمارهٔ تأییدنشده درخواست را به کسی نمی‌بندد."""
    owner = await _owner(client, db_session)
    code = await _submit(client)
    user_id = await _client_id(client)
    await db_session.execute(update(User).where(User.id == user_id).values(mobile_verified_at=None))
    request = await _request(db_session, code)

    await _patch(client, owner, request, status="ACCEPTED", public_note=PUBLIC)

    assert await _notices(db_session, user_id) == []


async def test_a_stored_link_beats_contact_matching(client, db_session) -> None:  # type: ignore[no-untyped-def]
    owner = await _owner(client, db_session)
    user_id = await _client_id(client)
    code = await _submit(client)  # حالا کاربر هست ⇒ ثبت با اتصال ذخیره‌شده
    request = await _request(db_session, code)
    assert request.user_id == user_id

    await _patch(client, owner, request, status="IN_REVIEW")

    assert len(await _notices(db_session, user_id)) == 1


async def test_owner_is_not_notified_about_their_own_request(client, db_session) -> None:  # type: ignore[no-untyped-def]
    owner = await _owner(client, db_session)
    code = await _submit(client, mobile=OWNER)
    owner_id = uuid.UUID(str((await me(client, owner))["id"]))
    request = await _request(db_session, code)

    await _patch(client, owner, request, status="ACCEPTED", public_note=PUBLIC)

    assert await _notices(db_session, owner_id) == []
