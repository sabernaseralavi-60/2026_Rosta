"""گفت‌وگوی استاد–دانشجو — ADR-0036.

دسترسی (کادر / دانشجوی همان ارائه / بیرونی)، خوانده‌نشده، کانال درس، گفت‌وگوی خصوصی،
و اینکه غیرعضو ۴۰۴ می‌گیرد (وجود گفت‌وگو لو نمی‌رود).
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

import pytest
from tests.integration.helpers import auth, grant_role, invalidate, login, me

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

INSTRUCTOR_MOBILE = "09122310001"
STUDENT_MOBILE = "09122310002"
SECOND_STUDENT_MOBILE = "09122310003"
PENDING_MOBILE = "09122310004"
OUTSIDER_MOBILE = "09122310005"


async def _scene(client: Any, session: Any) -> dict[str, Any]:
    from silp.models.education import Course, CourseOffering, Enrollment, Term

    instructor_token = await login(client, INSTRUCTOR_MOBILE)
    instructor = await me(client, instructor_token)
    await grant_role(session, instructor["id"], "INSTRUCTOR")

    users: dict[str, dict[str, str]] = {}
    for key, mobile in (
        ("a", STUDENT_MOBILE),
        ("b", SECOND_STUDENT_MOBILE),
        ("pending", PENDING_MOBILE),
        ("outsider", OUTSIDER_MOBILE),
    ):
        token = await login(client, mobile)
        users[key] = {"token": token, "id": (await me(client, token))["id"]}

    marker = uuid.uuid4().hex[:8]
    term = Term(
        code=f"T-{marker}",
        title_fa="نیم‌سال آزمایشی",
        starts_on=date(2026, 9, 23),
        ends_on=date(2027, 2, 4),
    )
    course = Course(code=f"C-{marker}", slug=f"course-{marker}", title_fa="مهندسی ترابری")
    session.add_all([term, course])
    await session.flush()
    offering = CourseOffering(
        course_id=course.id,
        term_id=term.id,
        instructor_id=uuid.UUID(instructor["id"]),
        status="OPEN",
    )
    session.add(offering)
    await session.flush()
    for key, status in (("a", "ACTIVE"), ("b", "ACTIVE"), ("pending", "PENDING")):
        session.add(
            Enrollment(
                offering_id=offering.id, student_id=uuid.UUID(users[key]["id"]), status=status
            )
        )
    await session.flush()
    await invalidate(instructor["id"])
    return {
        "offering": str(offering.id),
        "staff": auth(await login(client, INSTRUCTOR_MOBILE)),
        "users": users,
    }


def _h(scene: dict[str, Any], key: str) -> dict[str, str]:
    return auth(scene["users"][key]["token"])


async def test_direct_message_round_trip_and_unread(client: Any, db_session: Any) -> None:
    scene = await _scene(client, db_session)
    offering, staff = scene["offering"], scene["staff"]
    student_id = scene["users"]["a"]["id"]

    sent = await client.post(
        f"/api/v1/messaging/offerings/{offering}/send",
        headers=staff,
        json={"audience": "SELECTED", "student_ids": [student_id], "body": "سلام، فردا کلاس هست."},
    )
    assert sent.status_code == 200, sent.text
    assert sent.json() == {"sent": 1, "skipped_no_account": 0}

    inbox = (await client.get("/api/v1/messaging/inbox", headers=_h(scene, "a"))).json()
    assert len(inbox) == 1
    conv = inbox[0]
    assert conv["kind"] == "DIRECT"
    assert conv["unread"] == 1
    assert conv["can_write"] is True
    assert conv["last_preview"] == "سلام، فردا کلاس هست."

    messages = (
        await client.get(
            f"/api/v1/messaging/conversations/{conv['id']}/messages", headers=_h(scene, "a")
        )
    ).json()
    assert [m["body"] for m in messages] == ["سلام، فردا کلاس هست."]
    assert messages[0]["from_staff"] is True
    assert messages[0]["mine"] is False

    read = await client.post(
        f"/api/v1/messaging/conversations/{conv['id']}/read", headers=_h(scene, "a")
    )
    assert read.status_code == 204
    unread = (await client.get("/api/v1/messaging/unread", headers=_h(scene, "a"))).json()
    assert unread == {"unread": 0}

    reply = await client.post(
        f"/api/v1/messaging/conversations/{conv['id']}/messages",
        headers=_h(scene, "a"),
        json={"body": "ممنون، می‌آیم.", "reply_to_id": messages[0]["id"]},
    )
    assert reply.status_code == 201, reply.text

    threads = (
        await client.get(f"/api/v1/messaging/offerings/{offering}/threads", headers=staff)
    ).json()
    mine = next(t for t in threads if t["student_id"] == student_id)
    assert mine["unread"] == 1
    assert mine["last_preview"] == "ممنون، می‌آیم."
    other = next(t for t in threads if t["student_id"] == scene["users"]["b"]["id"])
    assert other["conversation_id"] is None


async def test_channel_post_reaches_all_but_students_cannot_write(
    client: Any, db_session: Any
) -> None:
    scene = await _scene(client, db_session)
    offering, staff = scene["offering"], scene["staff"]

    sent = await client.post(
        f"/api/v1/messaging/offerings/{offering}/send",
        headers=staff,
        json={"audience": "ALL", "body": "تمرین هفتهٔ سوم بارگذاری شد."},
    )
    assert sent.status_code == 200, sent.text
    assert sent.json()["sent"] == 2  # دو دانشجوی ACTIVE؛ PENDING شمرده نمی‌شود

    for key in ("a", "b"):
        inbox = (await client.get("/api/v1/messaging/inbox", headers=_h(scene, key))).json()
        assert [c["kind"] for c in inbox] == ["OFFERING"]
        assert inbox[0]["unread"] == 1
        assert inbox[0]["can_write"] is False

    channel_id = (await client.get("/api/v1/messaging/inbox", headers=_h(scene, "a"))).json()[0][
        "id"
    ]
    write = await client.post(
        f"/api/v1/messaging/conversations/{channel_id}/messages",
        headers=_h(scene, "a"),
        json={"body": "من هم یک سؤال دارم"},
    )
    assert write.status_code == 403

    for key in ("pending", "outsider"):
        blocked = await client.get(
            f"/api/v1/messaging/conversations/{channel_id}/messages", headers=_h(scene, key)
        )
        assert blocked.status_code == 404


async def test_direct_thread_is_private_to_its_student(client: Any, db_session: Any) -> None:
    scene = await _scene(client, db_session)
    offering, staff = scene["offering"], scene["staff"]

    opened = await client.post(
        f"/api/v1/messaging/offerings/{offering}/threads/{scene['users']['a']['id']}",
        headers=staff,
    )
    assert opened.status_code == 200, opened.text
    conv_id = opened.json()["id"]
    again = await client.post(
        f"/api/v1/messaging/offerings/{offering}/threads/{scene['users']['a']['id']}",
        headers=staff,
    )
    assert again.json()["id"] == conv_id  # بی‌اثر در تکرار

    for key in ("b", "pending", "outsider"):
        spy = await client.get(
            f"/api/v1/messaging/conversations/{conv_id}/messages", headers=_h(scene, key)
        )
        assert spy.status_code == 404
        post = await client.post(
            f"/api/v1/messaging/conversations/{conv_id}/messages",
            headers=_h(scene, key),
            json={"body": "نفوذ"},
        )
        assert post.status_code == 404


async def test_student_cannot_use_staff_endpoints_or_open_foreign_thread(
    client: Any, db_session: Any
) -> None:
    scene = await _scene(client, db_session)
    offering = scene["offering"]
    student = _h(scene, "a")

    for method, path, body in (
        ("get", f"/api/v1/messaging/offerings/{offering}/threads", None),
        (
            "post",
            f"/api/v1/messaging/offerings/{offering}/send",
            {"audience": "ALL", "body": "من استاد نیستم"},
        ),
        ("post", f"/api/v1/messaging/offerings/{offering}/channel", None),
    ):
        response = await getattr(client, method)(path, headers=student, **({"json": body} if body else {}))
        assert response.status_code == 403, (path, response.text)

    # دانشجوی در انتظار هنوز دانشجوی درس نیست؛ گفت‌وگو برایش ساخته نمی‌شود.
    pending = await client.post(
        f"/api/v1/messaging/offerings/{offering}/threads/{scene['users']['pending']['id']}",
        headers=scene["staff"],
    )
    assert pending.status_code == 404


async def test_body_validation_and_soft_delete(client: Any, db_session: Any) -> None:
    scene = await _scene(client, db_session)
    offering, staff = scene["offering"], scene["staff"]
    student_id = scene["users"]["a"]["id"]

    blank = await client.post(
        f"/api/v1/messaging/offerings/{offering}/send",
        headers=staff,
        json={"audience": "SELECTED", "student_ids": [student_id], "body": "   "},
    )
    assert blank.status_code == 409
    assert blank.json()["error"]["code"] == "MESSAGE_EMPTY"

    nobody = await client.post(
        f"/api/v1/messaging/offerings/{offering}/send",
        headers=staff,
        json={"audience": "SELECTED", "student_ids": [], "body": "سلام"},
    )
    assert nobody.status_code == 409

    await client.post(
        f"/api/v1/messaging/offerings/{offering}/send",
        headers=staff,
        json={"audience": "SELECTED", "student_ids": [student_id], "body": "پیام اشتباه"},
    )
    conv = (await client.get("/api/v1/messaging/inbox", headers=_h(scene, "a"))).json()[0]
    messages = (
        await client.get(
            f"/api/v1/messaging/conversations/{conv['id']}/messages", headers=_h(scene, "a")
        )
    ).json()

    # دانشجو پیام استاد را نمی‌تواند حذف کند؛ استاد می‌تواند.
    denied = await client.delete(
        f"/api/v1/messaging/messages/{messages[0]['id']}", headers=_h(scene, "a")
    )
    assert denied.status_code == 403
    ok = await client.delete(f"/api/v1/messaging/messages/{messages[0]['id']}", headers=staff)
    assert ok.status_code == 204
    after = (
        await client.get(
            f"/api/v1/messaging/conversations/{conv['id']}/messages", headers=_h(scene, "a")
        )
    ).json()
    assert after[0]["deleted"] is True
    assert after[0]["body"] == ""
