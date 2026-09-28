"""صندوق درخواست‌های ورودی، داشبورد مالک و پیگیری مشتری — ADR-0032.

PostgreSQL واقعی لازم است: دنبالهٔ کد پیگیری، `fa_normalize` جست‌وجو، ستون آرایه‌ای
و قیدهای CHECK جدول `intake_events` در حافظه شبیه‌سازی نمی‌شوند.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import delete, select, text, update
from tests.integration.helpers import auth, grant_role, login, me

from silp.models.admin import AuditLog
from silp.models.identity import User
from silp.models.intake import IntakeEvent, IntakeRequest

pytestmark = pytest.mark.integration

OWNER = "09121770001"
CLIENT = "09121770002"
OUTSIDER = "09121770003"
SECRET = "یادداشت خصوصی مالک دربارهٔ بودجه"
PUBLIC = "درخواست شما بررسی شد؛ به‌زودی تماس می‌گیریم."


def _intake(**overrides: Any) -> dict[str, Any]:
    return {
        "need_type": "Commercial",
        "services": ["Website / Web App"],
        "summary": "برای کسب‌وکارم به یک وب‌سایت فروش نیاز دارم.",
        "name": "رضا محمدی",
        "mobile": CLIENT,
        **overrides,
    }


def _collab(**overrides: Any) -> dict[str, Any]:
    return {
        "name": "سارا کریمی",
        "email": "sara@example.com",
        "intro": "می‌خواهم در تحلیل داده همکاری کنم.",
        "ways": ["Research"],
        **overrides,
    }


async def _owner(client: Any, session: Any) -> tuple[str, uuid.UUID]:
    token = await login(client, OWNER)
    user_id = uuid.UUID(str((await me(client, token))["id"]))
    await grant_role(session, user_id, "ADMIN")
    return token, user_id


async def _submit(client: Any, path: str, body: dict[str, Any]) -> str:
    response = await client.post(f"/api/v1/public/{path}", json=body)
    assert response.status_code == 201, response.text
    return response.json()["tracking_code"]


async def _backdate(
    session: Any, request_id: uuid.UUID, *, days: int, created: bool = False
) -> None:
    """`set_updated_at()` هر UPDATE را به now() برمی‌گرداند؛ برای عقب بردنِ ساعت باید
    تریگر را (درون همین تراکنشِ آزمون) خاموش کرد."""
    when = datetime.now(UTC) - timedelta(days=days)
    values = {"updated_at": when, **({"created_at": when} if created else {})}
    await session.execute(text("ALTER TABLE intake_requests DISABLE TRIGGER USER"))
    await session.execute(
        update(IntakeRequest).where(IntakeRequest.id == request_id).values(**values)
    )
    await session.execute(text("ALTER TABLE intake_requests ENABLE TRIGGER USER"))


async def _row(session: Any, code: str) -> IntakeRequest:
    row = await session.scalar(select(IntakeRequest).where(IntakeRequest.tracking_code == code))
    assert row is not None
    return row


# ── دسترسی ─────────────────────────────────────────────────────────────
async def test_inbox_is_owner_only(client, db_session) -> None:  # type: ignore[no-untyped-def]
    code = await _submit(client, "intake", _intake())
    row = await _row(db_session, code)
    student = await login(client, OUTSIDER)

    for method, path in (
        ("get", "/api/v1/admin/intake"),
        ("get", f"/api/v1/admin/intake/{row.id}"),
        ("get", "/api/v1/admin/owner/overview"),
        ("patch", f"/api/v1/admin/intake/{row.id}"),
    ):
        kwargs: dict[str, Any] = {"json": {"status": "ACCEPTED"}} if method == "patch" else {}
        anonymous = await getattr(client, method)(path, **kwargs)
        assert anonymous.status_code == 401, path
        forbidden = await getattr(client, method)(path, headers=auth(student), **kwargs)
        assert forbidden.status_code == 403, path
        assert forbidden.json()["error"]["details"]["permission"] == "intake.manage"


# ── فهرست ──────────────────────────────────────────────────────────────
async def test_list_filters_search_and_counts(client, db_session) -> None:  # type: ignore[no-untyped-def]
    owner, _ = await _owner(client, db_session)
    intake_code = await _submit(client, "intake", _intake(organization="شرکت آزمایشی نمونه"))
    collab_code = await _submit(client, "collaboration", _collab())
    intake = await _row(db_session, intake_code)
    intake.status = "IN_REVIEW"
    await db_session.flush()

    page = (await client.get("/api/v1/admin/intake", headers=auth(owner))).json()
    codes = [i["tracking_code"] for i in page["items"]]
    assert intake_code in codes and collab_code in codes
    assert page["counts"]["IN_REVIEW"] >= 1 and page["counts"]["NEW"] >= 1

    only = (await client.get("/api/v1/admin/intake?kind=COLLABORATION", headers=auth(owner))).json()
    assert {i["kind"] for i in only["items"]} == {"COLLABORATION"}

    review = (await client.get("/api/v1/admin/intake?status=IN_REVIEW", headers=auth(owner))).json()
    assert intake_code in [i["tracking_code"] for i in review["items"]]
    # شمار وضعیت‌ها با فیلتر وضعیت کم نمی‌شود، تا زبانه‌ها همیشه عدد درست بدهند.
    assert review["counts"]["NEW"] >= 1

    found = (await client.get("/api/v1/admin/intake?q=آزمایشی نمونه", headers=auth(owner))).json()
    assert [i["tracking_code"] for i in found["items"]] == [intake_code]
    by_code = (
        await client.get(f"/api/v1/admin/intake?q={collab_code}", headers=auth(owner))
    ).json()
    assert [i["tracking_code"] for i in by_code["items"]] == [collab_code]
    wildcard = (await client.get("/api/v1/admin/intake?q=%25%25", headers=auth(owner))).json()
    assert wildcard["items"] == []  # «%%» عبارت است، نه «همه»


async def test_detail_shows_payload_contact_and_private_note(client, db_session) -> None:  # type: ignore[no-untyped-def]
    owner, _ = await _owner(client, db_session)
    code = await _submit(client, "intake", _intake(budget="۱۰ میلیون", sector="کشاورزی"))
    row = await _row(db_session, code)
    row.owner_note = SECRET
    await db_session.flush()

    detail = (await client.get(f"/api/v1/admin/intake/{row.id}", headers=auth(owner))).json()
    assert detail["owner_note"] == SECRET
    assert detail["contact_mobile"] == CLIENT
    assert detail["payload"]["budget"] == "۱۰ میلیون"
    assert detail["events"] == []
    missing = await client.get(f"/api/v1/admin/intake/{uuid.uuid4()}", headers=auth(owner))
    assert missing.status_code == 404


# ── رسیدگی ─────────────────────────────────────────────────────────────
async def test_status_change_writes_event_and_audit_row(client, db_session) -> None:  # type: ignore[no-untyped-def]
    owner, owner_id = await _owner(client, db_session)
    code = await _submit(client, "intake", _intake())
    row = await _row(db_session, code)

    response = await client.patch(
        f"/api/v1/admin/intake/{row.id}",
        json={"status": "IN_REVIEW", "public_note": PUBLIC, "owner_note": SECRET},
        headers=auth(owner),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "IN_REVIEW" and body["owner_note"] == SECRET
    assert [(e["from_status"], e["to_status"], e["public_note"]) for e in body["events"]] == [
        ("NEW", "IN_REVIEW", PUBLIC)
    ]

    audit = await db_session.scalar(
        select(AuditLog).where(
            AuditLog.actor_id == owner_id,
            AuditLog.action == "INTAKE_UPDATED",
            AuditLog.entity_id == row.id,
        )
    )
    assert audit is not None
    assert audit.before == {"status": "NEW", "owner_note": False}
    assert audit.after["status"] == "IN_REVIEW" and audit.after["tracking_code"] == code
    # لاگ حسابرسی متن یادداشت خصوصی را نگه نمی‌دارد، فقط این‌که هست.
    assert SECRET not in str(audit.after) and SECRET not in str(audit.before)


async def test_a_no_change_patch_makes_no_event_and_an_empty_body_is_422(  # type: ignore[no-untyped-def]
    client, db_session
) -> None:
    owner, _ = await _owner(client, db_session)
    code = await _submit(client, "intake", _intake())
    row = await _row(db_session, code)
    url = f"/api/v1/admin/intake/{row.id}"

    same = await client.patch(url, json={"status": "NEW"}, headers=auth(owner))
    assert same.status_code == 200 and same.json()["events"] == []
    assert (await client.patch(url, json={}, headers=auth(owner))).status_code == 422
    assert (
        await client.patch(url, json={"status": "DONE"}, headers=auth(owner))
    ).status_code == 422

    note_only = await client.patch(url, json={"public_note": PUBLIC}, headers=auth(owner))
    events = note_only.json()["events"]
    assert [(e["from_status"], e["to_status"]) for e in events] == [("NEW", "NEW")]

    cleared = await client.patch(url, json={"owner_note": SECRET}, headers=auth(owner))
    assert cleared.json()["owner_note"] == SECRET
    cleared = await client.patch(url, json={"owner_note": ""}, headers=auth(owner))
    assert cleared.json()["owner_note"] is None


# ── داشبورد مالک ───────────────────────────────────────────────────────
async def test_overview_counts_and_follow_up(client, db_session) -> None:  # type: ignore[no-untyped-def]
    owner, _ = await _owner(client, db_session)
    before = (await client.get("/api/v1/admin/owner/overview", headers=auth(owner))).json()

    fresh = await _submit(client, "intake", _intake(name="تازه‌وارد آزمایشی"))
    old = await _submit(client, "collaboration", _collab(name="قدیمی آزمایشی"))
    old_row = await _row(db_session, old)
    await _backdate(db_session, old_row.id, days=9, created=True)
    accepted = await _submit(client, "intake", _intake(name="پذیرفته‌شده", mobile="09121770009"))
    await client.patch(
        f"/api/v1/admin/intake/{(await _row(db_session, accepted)).id}",
        json={"status": "ACCEPTED"},
        headers=auth(owner),
    )

    after = (await client.get("/api/v1/admin/owner/overview", headers=auth(owner))).json()
    assert after["intake"]["INTAKE"]["NEW"] == before["intake"]["INTAKE"]["NEW"] + 1
    assert after["intake"]["COLLABORATION"]["NEW"] == before["intake"]["COLLABORATION"]["NEW"] + 1
    assert after["intake"]["INTAKE"]["ACCEPTED"] == before["intake"]["INTAKE"]["ACCEPTED"] + 1
    assert after["clients_accepted"] == before["clients_accepted"] + 1
    assert after["stale"] == before["stale"] + 1
    assert after["oldest_new_days"] >= 9
    follow = {i["tracking_code"]: i for i in after["follow_up"]}
    assert old in follow and follow[old]["stale"] is True
    assert fresh not in follow  # تازه است، نیاز به پیگیری ندارد
    assert set(after["content"]) <= {"DRAFT", "PUBLISHED", "ARCHIVED"}


async def test_touching_a_request_restarts_its_follow_up_clock(client, db_session) -> None:  # type: ignore[no-untyped-def]
    owner, _ = await _owner(client, db_session)
    code = await _submit(client, "intake", _intake())
    row = await _row(db_session, code)
    await _backdate(db_session, row.id, days=5)
    await db_session.refresh(row)
    listed = (await client.get(f"/api/v1/admin/intake?q={code}", headers=auth(owner))).json()
    assert listed["items"][0]["stale"] is True

    await client.patch(
        f"/api/v1/admin/intake/{row.id}", json={"public_note": PUBLIC}, headers=auth(owner)
    )
    listed = (await client.get(f"/api/v1/admin/intake?q={code}", headers=auth(owner))).json()
    assert listed["items"][0]["stale"] is False


# ── مشتری واردشده ──────────────────────────────────────────────────────
async def test_my_requests_by_user_id_and_verified_contact_only(client, db_session) -> None:  # type: ignore[no-untyped-def]
    await _owner(client, db_session)
    mine = await _submit(client, "intake", _intake())  # موبایل مشتری، هنوز کاربر نیست
    theirs = await _submit(client, "intake", _intake(name="دیگری", mobile="09121770077"))

    token = await login(client, CLIENT)  # حالا با OTP واردشده ⇒ موبایل تأییدشده
    listing = (await client.get("/api/v1/me/requests", headers=auth(token))).json()
    assert [r["tracking_code"] for r in listing] == [mine]
    assert theirs not in [r["tracking_code"] for r in listing]

    # اگر تأییدشده نباشد، فقط `user_id` می‌ماند.
    user_id = uuid.UUID(str((await me(client, token))["id"]))
    await db_session.execute(update(User).where(User.id == user_id).values(mobile_verified_at=None))
    assert (await client.get("/api/v1/me/requests", headers=auth(token))).json() == []
    row = await _row(db_session, mine)
    row.user_id = user_id
    await db_session.flush()
    assert len((await client.get("/api/v1/me/requests", headers=auth(token))).json()) == 1

    assert (await client.get("/api/v1/me/requests")).status_code == 401


async def test_client_sees_public_notes_and_never_the_private_one(client, db_session) -> None:  # type: ignore[no-untyped-def]
    owner, _ = await _owner(client, db_session)
    code = await _submit(client, "intake", _intake())
    row = await _row(db_session, code)
    await client.patch(
        f"/api/v1/admin/intake/{row.id}",
        json={"status": "ACCEPTED", "public_note": PUBLIC, "owner_note": SECRET},
        headers=auth(owner),
    )

    token = await login(client, CLIENT)
    response = await client.get("/api/v1/me/requests", headers=auth(token))
    assert response.status_code == 200
    body = response.json()
    assert body[0]["status"] == "ACCEPTED"
    assert body[0]["events"][0]["public_note"] == PUBLIC
    assert SECRET not in response.text and "owner_note" not in response.text
    assert "contact_mobile" not in response.text  # راه تماس هم برنمی‌گردد


# ── مشتری بی‌ورود ──────────────────────────────────────────────────────
async def test_track_needs_code_and_the_registered_contact(client, db_session) -> None:  # type: ignore[no-untyped-def]
    owner, _ = await _owner(client, db_session)
    code = await _submit(client, "intake", _intake())
    row = await _row(db_session, code)
    await client.patch(
        f"/api/v1/admin/intake/{row.id}",
        json={"status": "IN_REVIEW", "public_note": PUBLIC, "owner_note": SECRET},
        headers=auth(owner),
    )

    for contact in (CLIENT, "+98 912 177 0002", "۰۹۱۲۱۷۷۰۰۰۲"):
        ok = await client.post(
            "/api/v1/public/track", json={"tracking_code": code.lower(), "contact": contact}
        )
        assert ok.status_code == 200, (contact, ok.text)
        body = ok.json()
        assert body["status"] == "IN_REVIEW" and body["events"][0]["public_note"] == PUBLIC
        # کد و راه تماس شاید لو رفته باشد: هیچ متنی از درخواست برنمی‌گردد.
        for leaked in (SECRET, "وب‌سایت فروش", "رضا", CLIENT, "summary", "owner_note"):
            assert leaked not in ok.text, leaked


async def test_track_failures_are_indistinguishable(client, db_session) -> None:  # type: ignore[no-untyped-def]
    code = await _submit(client, "intake", _intake())
    wrong_contact = await client.post(
        "/api/v1/public/track", json={"tracking_code": code, "contact": "09121770099"}
    )
    unknown_code = await client.post(
        "/api/v1/public/track", json={"tracking_code": "Q-9999999", "contact": CLIENT}
    )
    assert wrong_contact.status_code == unknown_code.status_code == 404
    assert wrong_contact.json()["error"]["message"] == unknown_code.json()["error"]["message"]

    for bad in (
        {"tracking_code": "X-1", "contact": CLIENT},
        {"tracking_code": code, "contact": "abc"},
    ):
        assert (await client.post("/api/v1/public/track", json=bad)).status_code == 422


async def test_track_email_contact_and_rate_limit_per_code(client, db_session) -> None:  # type: ignore[no-untyped-def]
    code = await _submit(client, "collaboration", _collab())
    ok = await client.post(
        "/api/v1/public/track", json={"tracking_code": code, "contact": "SARA@example.com"}
    )
    assert ok.status_code == 200 and ok.json()["kind"] == "COLLABORATION"

    guess = {"tracking_code": code, "contact": "09121770055"}
    statuses = [
        (await client.post("/api/v1/public/track", json=guess)).status_code for _ in range(6)
    ]
    # یک موفق قبلی + چهار ۴۰۴ = پنج؛ ششمین بار (حدس‌زنی) سهمیهٔ کد را می‌شکند.
    assert statuses[:4] == [404] * 4 and 429 in statuses[4:]


# ── پایداری: از اتصال دیگر ─────────────────────────────────────────────
async def test_update_survives_the_request(committing_client, committing_session) -> None:  # type: ignore[no-untyped-def]
    from silp.db.session import get_session_factory

    mobile = f"0912{uuid.uuid4().int % 10_000_000:07d}"
    owner_token = await login(committing_client, mobile)
    owner_id = uuid.UUID(str((await me(committing_client, owner_token))["id"]))
    code: str | None = None
    try:
        await grant_role(committing_session, owner_id, "ADMIN")
        await committing_session.commit()
        code = await _submit(
            committing_client, "intake", _intake(mobile=f"0913{uuid.uuid4().int % 10_000_000:07d}")
        )
        row = await _row(committing_session, code)
        response = await committing_client.patch(
            f"/api/v1/admin/intake/{row.id}",
            json={"status": "ACCEPTED", "public_note": PUBLIC, "owner_note": SECRET},
            headers=auth(owner_token),
        )
        assert response.status_code == 200, response.text

        async with get_session_factory()() as other:
            stored = await _row(other, code)
            assert stored.status == "ACCEPTED" and stored.owner_note == SECRET
            events = list(
                await other.scalars(select(IntakeEvent).where(IntakeEvent.request_id == stored.id))
            )
            assert [e.public_note for e in events] == [PUBLIC]
            audit = await other.scalar(
                select(AuditLog).where(
                    AuditLog.action == "INTAKE_UPDATED", AuditLog.entity_id == stored.id
                )
            )
            assert audit is not None
    finally:
        if code:
            await committing_session.execute(
                delete(IntakeRequest).where(IntakeRequest.tracking_code == code)
            )
        await committing_session.execute(delete(User).where(User.id == owner_id))
        await committing_session.commit()
