"""ناحیهٔ استاد و فعال‌سازی اشتراک — §13.6، ADR-0019.

آنچه صفحه‌های `/teach` و `/admin/subscriptions` لازم داشتند و API نداشت:
فهرست ارائه برای دستیار، نمای کادر آموزشی و تنظیمات ارائه، خواندن حضور،
دفتر نمره، و چرخهٔ کامل تأیید یا رد اشتراک با صاحبش.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select
from tests.integration.helpers import auth, grant_role, invalidate, login, me

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

INSTRUCTOR_MOBILE = "09122190001"
STUDENT_MOBILE = "09122190002"
SECOND_STUDENT_MOBILE = "09122190003"
TA_MOBILE = "09122190004"
OUTSIDER_MOBILE = "09122190005"
SUPPORT_MOBILE = "09122190006"
PENDING_MOBILE = "09122190007"

SINGLE = {"options": [{"id": "a", "text": "۱"}, {"id": "b", "text": "۲"}], "correct": ["b"]}


async def _scene(client: Any, session: Any, **offering_kw: Any) -> dict[str, Any]:
    """استاد، دو دانشجوی فعال، یک دانشجوی در انتظار، و ارائه‌ای با کد."""
    from silp.models.education import Course, CourseOffering, Enrollment, Term

    instructor_token = await login(client, INSTRUCTOR_MOBILE)
    instructor = await me(client, instructor_token)
    await grant_role(session, instructor["id"], "INSTRUCTOR")

    students = []
    for mobile in (STUDENT_MOBILE, SECOND_STUDENT_MOBILE, PENDING_MOBILE):
        token = await login(client, mobile)
        students.append({"token": token, "id": (await me(client, token))["id"]})

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
        status=offering_kw.get("status", "OPEN"),
        enrollment_code=offering_kw.get("enrollment_code", "TRANS-1405"),
    )
    session.add(offering)
    await session.flush()
    for student, status in zip(students, ("ACTIVE", "ACTIVE", "PENDING"), strict=True):
        session.add(
            Enrollment(offering_id=offering.id, student_id=uuid.UUID(student["id"]), status=status)
        )
    await session.flush()
    await invalidate(instructor["id"])
    instructor_token = await login(client, INSTRUCTOR_MOBILE)
    return {
        "instructor_token": instructor_token,
        "instructor_id": instructor["id"],
        "students": students,
        "offering": offering,
        "course": course,
    }


async def _scoped_ta(client: Any, session: Any, offering_id: uuid.UUID) -> str:
    from silp.core.permissions import Role, ScopeType
    from silp.services import authz

    token = await login(client, TA_MOBILE)
    ta = await me(client, token)
    await authz.grant_role(
        session,
        user_id=uuid.UUID(ta["id"]),
        role=Role.TA,
        scope_type=ScopeType.OFFERING,
        scope_id=offering_id,
    )
    await session.flush()
    await invalidate(ta["id"])
    return await login(client, TA_MOBILE)


# ── فهرست و نمای ارائه ─────────────────────────────────────────────────
async def test_ta_sees_the_offering_they_were_scoped_to(client: Any, db_session: Any) -> None:
    """پیش از ADR-0019 فهرست فقط `instructor_id` را می‌دید و دستیار هیچ نداشت."""
    scene = await _scene(client, db_session)
    ta_token = await _scoped_ta(client, db_session, scene["offering"].id)

    response = await client.get("/api/v1/teach/offerings", headers=auth(ta_token))
    assert response.status_code == 200, response.text
    mine = [o for o in response.json() if o["id"] == str(scene["offering"].id)]
    assert len(mine) == 1
    assert mine[0]["staff_role"] == "TA"
    assert mine[0]["pending_enrollments"] == 1


async def test_ta_detail_hides_management_and_the_enrollment_code(
    client: Any, db_session: Any
) -> None:
    scene = await _scene(client, db_session)
    ta_token = await _scoped_ta(client, db_session, scene["offering"].id)

    response = await client.get(
        f"/api/v1/teach/offerings/{scene['offering'].id}", headers=auth(ta_token)
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["enrollment_code"] is None
    assert body["permissions"]["manage"] is False
    assert body["permissions"]["submit_final_grades"] is False
    assert body["permissions"]["record_attendance"] is True
    assert body["permissions"]["grade_quizzes"] is True

    response = await client.patch(
        f"/api/v1/teach/offerings/{scene['offering'].id}",
        headers=auth(ta_token),
        json={"requires_approval": True},
    )
    assert response.status_code == 403


async def test_instructor_detail_has_drafts_code_and_transitions(
    client: Any, db_session: Any
) -> None:
    scene = await _scene(client, db_session)
    token = scene["instructor_token"]
    oid = scene["offering"].id
    response = await client.put(
        f"/api/v1/teach/offerings/{oid}/weeks",
        headers=auth(token),
        json={"week_number": 1, "title_fa": "مقدمه"},
    )
    assert response.status_code == 200, response.text

    response = await client.get(f"/api/v1/teach/offerings/{oid}", headers=auth(token))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["staff_role"] == "INSTRUCTOR"
    assert body["enrollment_code"] == "TRANS-1405"
    assert [w["status"] for w in body["weeks"]] == ["DRAFT"]
    assert set(body["allowed_statuses"]) == {"DRAFT", "IN_PROGRESS", "CLOSED"}
    assert body["permissions"]["manage"] is True


async def test_student_and_other_instructor_are_locked_out(client: Any, db_session: Any) -> None:
    scene = await _scene(client, db_session)
    oid = scene["offering"].id
    outsider = await login(client, OUTSIDER_MOBILE)
    outsider_id = (await me(client, outsider))["id"]
    await grant_role(db_session, outsider_id, "INSTRUCTOR")
    outsider = await login(client, OUTSIDER_MOBILE)

    for token in (scene["students"][0]["token"], outsider):
        for path in ("", "/gradebook", "/attendance"):
            response = await client.get(f"/api/v1/teach/offerings/{oid}{path}", headers=auth(token))
            assert response.status_code == 403, (path, response.text)


# ── تنظیمات ارائه ──────────────────────────────────────────────────────
async def test_offering_status_follows_the_transition_table(client: Any, db_session: Any) -> None:
    scene = await _scene(client, db_session)
    url = f"/api/v1/teach/offerings/{scene['offering'].id}"
    headers = auth(scene["instructor_token"])

    # ثبت‌نام دارد، پس به پیش‌نویس برنمی‌گردد.
    response = await client.patch(url, headers=headers, json={"status": "DRAFT"})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "OFFERING_HAS_ENROLLMENTS"

    # از «باز» یک‌راست بایگانی نمی‌شود.
    response = await client.patch(url, headers=headers, json={"status": "ARCHIVED"})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "OFFERING_TRANSITION_INVALID"

    response = await client.patch(url, headers=headers, json={"status": "CLOSED"})
    assert response.status_code == 200, response.text
    assert response.json()["allowed_statuses"] == ["IN_PROGRESS", "ARCHIVED"]

    # دو دانشجوی فعال بی‌نمره — بایگانی ممنوع.
    response = await client.patch(url, headers=headers, json={"status": "ARCHIVED"})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "OFFERING_HAS_ACTIVE_STUDENTS"


async def test_capacity_code_and_approval_settings(client: Any, db_session: Any) -> None:
    scene = await _scene(client, db_session)
    url = f"/api/v1/teach/offerings/{scene['offering'].id}"
    headers = auth(scene["instructor_token"])

    response = await client.patch(url, headers=headers, json={"capacity": 2})
    assert response.status_code == 422  # سه ثبت‌نام، از جمله در انتظار

    response = await client.patch(
        url,
        headers=headers,
        json={"capacity": 40, "requires_approval": True, "clear_enrollment_code": True},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["capacity"], body["requires_approval"], body["has_enrollment_code"]) == (
        40,
        True,
        False,
    )

    response = await client.patch(url, headers=headers, json={"enrollment_code": "  KERMAN  "})
    assert response.status_code == 200, response.text
    assert response.json()["enrollment_code"] == "KERMAN"


# ── حضور و غیاب ────────────────────────────────────────────────────────
async def test_attendance_can_be_read_back_and_corrected(client: Any, db_session: Any) -> None:
    scene = await _scene(client, db_session)
    oid = scene["offering"].id
    headers = auth(scene["instructor_token"])
    first, second, _pending = scene["students"]
    day = date(2026, 10, 4)

    body = {
        "held_on": day.isoformat(),
        "week_number": 2,
        "topic": "تخمین تقاضا",
        "entries": [
            {"student_id": first["id"], "status": "PRESENT"},
            {"student_id": second["id"], "status": "ABSENT"},
        ],
    }
    response = await client.post(
        f"/api/v1/teach/offerings/{oid}/attendance", headers=headers, json=body
    )
    assert response.status_code == 200, response.text

    response = await client.get(f"/api/v1/teach/offerings/{oid}/attendance", headers=headers)
    assert response.status_code == 200, response.text
    (session,) = response.json()
    assert (session["present"], session["absent"], session["week_number"]) == (1, 1, 2)

    # همان روز دوباره ⇒ اصلاح، نه جلسهٔ دوم.
    body["entries"][1]["status"] = "EXCUSED"
    body["entries"][1]["note"] = "گواهی پزشکی"
    await client.post(f"/api/v1/teach/offerings/{oid}/attendance", headers=headers, json=body)
    response = await client.get(
        f"/api/v1/teach/offerings/{oid}/attendance/{day.isoformat()}", headers=headers
    )
    assert response.status_code == 200, response.text
    sheet = response.json()
    assert (sheet["present"], sheet["absent"], sheet["excused"]) == (1, 0, 1)
    marks = {m["student_id"]: m for m in sheet["marks"]}
    assert marks[second["id"]]["note"] == "گواهی پزشکی"

    response = await client.get(
        f"/api/v1/teach/offerings/{oid}/attendance/2026-10-05", headers=headers
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ATTENDANCE_NOT_RECORDED"


# ── دفتر نمره ──────────────────────────────────────────────────────────
async def test_gradebook_brings_quizzes_attendance_and_final_grade_together(
    client: Any, db_session: Any
) -> None:
    scene = await _scene(client, db_session)
    oid = scene["offering"].id
    headers = auth(scene["instructor_token"])
    first, second, pending = scene["students"]
    now = datetime.now(UTC)

    response = await client.post(
        f"/api/v1/teach/offerings/{oid}/quizzes",
        headers=headers,
        json={
            "title_fa": "آزمون هفتهٔ ۲",
            "duration_min": 20,
            "opens_at": (now - timedelta(minutes=5)).isoformat(),
            "closes_at": (now + timedelta(hours=2)).isoformat(),
            "result_visibility": "IMMEDIATE",
            "shuffle_questions": False,
            "shuffle_options": False,
        },
    )
    quiz_id = response.json()["id"]
    response = await client.post(
        f"/api/v1/teach/quizzes/{quiz_id}/questions",
        headers=headers,
        json={"kind": "SINGLE_CHOICE", "body": "۱+۱؟", "payload": SINGLE, "points": "4"},
    )
    question_id = response.json()["id"]
    await client.post(f"/api/v1/teach/quizzes/{quiz_id}/publish", headers=headers)

    started = (
        await client.post(f"/api/v1/quizzes/{quiz_id}/attempts", headers=auth(first["token"]))
    ).json()
    await client.put(
        f"/api/v1/attempts/{started['attempt_id']}/answers/{question_id}",
        headers=auth(first["token"]),
        json={"response": {"selected": ["b"]}},
    )
    response = await client.post(
        f"/api/v1/attempts/{started['attempt_id']}/submit",
        headers=auth(first["token"]),
        json={"confirm_unanswered": 0},
    )
    assert response.status_code == 200, response.text

    await client.post(
        f"/api/v1/teach/offerings/{oid}/attendance",
        headers=headers,
        json={
            "held_on": "2026-10-04",
            "entries": [
                {"student_id": first["id"], "status": "PRESENT"},
                {"student_id": second["id"], "status": "LATE"},
            ],
        },
    )

    response = await client.get(f"/api/v1/teach/offerings/{oid}/gradebook", headers=headers)
    assert response.status_code == 200, response.text
    book = response.json()
    assert book["sessions_held"] == 1
    assert [q["id"] for q in book["quizzes"]] == [quiz_id]
    rows = {r["student_id"]: r for r in book["rows"]}
    assert pending["id"] not in rows  # در انتظار نمره ندارد
    assert float(rows[first["id"]]["quizzes"][0]["score"]) == 4.0
    assert rows[first["id"]]["attendance"]["present"] == 1
    assert rows[second["id"]]["quizzes"][0]["score"] is None
    assert rows[second["id"]]["attendance"]["late"] == 1
    assert rows[first["id"]]["learning_score"] is not None
    assert rows[first["id"]]["suggested_grade"] is not None

    enrollment_id = rows[first["id"]]["enrollment_id"]
    response = await client.patch(
        f"/api/v1/teach/enrollments/{enrollment_id}/grade", headers=headers, json={"grade": 18.5}
    )
    assert response.status_code == 200, response.text
    response = await client.get(f"/api/v1/teach/offerings/{oid}/gradebook", headers=headers)
    row = next(r for r in response.json()["rows"] if r["student_id"] == first["id"])
    assert (row["final_grade"], row["status"]) == (18.5, "COMPLETED")


async def test_final_grade_is_refused_for_a_pending_enrollment(
    client: Any, db_session: Any
) -> None:
    """نمره درس را COMPLETED می‌کند؛ بی این قاعده، تأیید ثبت‌نام دور زده می‌شد."""
    from silp.models.education import Enrollment

    scene = await _scene(client, db_session)
    pending_id = uuid.UUID(scene["students"][2]["id"])
    enrollment_id = await db_session.scalar(
        select(Enrollment.id).where(
            Enrollment.offering_id == scene["offering"].id, Enrollment.student_id == pending_id
        )
    )
    response = await client.patch(
        f"/api/v1/teach/enrollments/{enrollment_id}/grade",
        headers=auth(scene["instructor_token"]),
        json={"grade": 15},
    )
    assert response.status_code == 422


# ── اشتراک از دید پشتیبانی ─────────────────────────────────────────────
async def _support(client: Any, session: Any) -> str:
    token = await login(client, SUPPORT_MOBILE)
    await grant_role(session, (await me(client, token))["id"], "SUPPORT")
    return await login(client, SUPPORT_MOBILE)


async def _request(client: Any, token: str, note: str = "فیش ۴۴۱۲") -> dict[str, Any]:
    response = await client.post(
        "/api/v1/subscriptions",
        headers=auth(token),
        json={"plan_code": "MONTHLY_ALL", "note": note},
    )
    assert response.status_code == 201, response.text
    return dict(response.json())


async def test_pending_list_names_the_owner_with_a_masked_mobile(
    client: Any, db_session: Any
) -> None:
    support = await _support(client, db_session)
    user_token = await login(client, PENDING_MOBILE)
    requested = await _request(client, user_token)

    response = await client.get("/api/v1/subscriptions/admin?status=PENDING", headers=auth(support))
    assert response.status_code == 200, response.text
    row = next(r for r in response.json() if r["id"] == requested["id"])
    assert row["user_mobile"] == "0912***0007"  # پشتیبانی شمارهٔ کامل را نمی‌بیند
    assert row["note"] == "فیش ۴۴۱۲"
    assert row["status"] == "PENDING"

    response = await client.get("/api/v1/subscriptions/admin", headers=auth(user_token))
    assert response.status_code == 403


async def test_activation_counts_the_period_from_approval_not_request(
    client: Any, db_session: Any
) -> None:
    """درخواستی که ده روز در صف ماند، ده روز از دوره‌اش را نمی‌سوزاند."""
    from silp.models.access import Subscription
    from silp.models.admin import AuditLog
    from silp.models.messaging import Notification

    support = await _support(client, db_session)
    user_token = await login(client, PENDING_MOBILE)
    requested = await _request(client, user_token)

    row = await db_session.get(Subscription, uuid.UUID(requested["id"]))
    row.starts_at = row.starts_at - timedelta(days=10)
    row.ends_at = row.ends_at - timedelta(days=10)
    await db_session.flush()

    url = f"/api/v1/subscriptions/{requested['id']}/activate"
    response = await client.post(url, headers=auth(support), json={})
    assert response.status_code == 422  # بی کد پیگیری فعال نمی‌شود

    before = datetime.now(UTC)
    response = await client.post(url, headers=auth(support), json={"payment_ref": "RRN-771"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "ACTIVE"
    assert datetime.fromisoformat(body["starts_at"]) >= before - timedelta(seconds=5)
    assert body["days_remaining"] == 30  # سقف: همین حالا فعال شد

    audit_row = await db_session.scalar(
        select(AuditLog).where(
            AuditLog.entity_id == uuid.UUID(requested["id"]),
            AuditLog.action == "SUBSCRIPTION_ACTIVATED",
        )
    )
    assert audit_row is not None and audit_row.after["payment_ref"] == "RRN-771"
    notice = await db_session.scalar(
        select(Notification).where(
            Notification.user_id == row.user_id, Notification.kind == "SUBSCRIPTION_ACTIVATED"
        )
    )
    assert notice is not None


async def test_rejection_needs_a_reason_and_tells_the_user(client: Any, db_session: Any) -> None:
    from silp.models.messaging import Notification

    support = await _support(client, db_session)
    user_token = await login(client, PENDING_MOBILE)
    user_id = uuid.UUID((await me(client, user_token))["id"])
    requested = await _request(client, user_token)
    url = f"/api/v1/subscriptions/{requested['id']}/reject"

    response = await client.post(url, headers=auth(support), json={"reason": "نه"})
    assert response.status_code == 422

    response = await client.post(
        url, headers=auth(support), json={"reason": "مبلغ فیش با طرح نمی‌خواند"}
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "CANCELLED"

    response = await client.post(url, headers=auth(support), json={"reason": "دوباره رد"})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "SUBSCRIPTION_NOT_PENDING"

    notice = await db_session.scalar(
        select(Notification).where(
            Notification.user_id == user_id, Notification.kind == "SUBSCRIPTION_REJECTED"
        )
    )
    assert notice is not None and "مبلغ فیش" in notice.body


async def test_direct_grant_needs_a_payment_ref_or_a_reason(client: Any, db_session: Any) -> None:
    support = await _support(client, db_session)
    user_token = await login(client, PENDING_MOBILE)
    user_id = (await me(client, user_token))["id"]

    response = await client.post(
        "/api/v1/subscriptions/grant",
        headers=auth(support),
        json={"user_id": user_id, "plan_code": "MONTHLY_ALL"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "PAYMENT_REF_REQUIRED"

    response = await client.post(
        "/api/v1/subscriptions/grant",
        headers=auth(support),
        json={"user_id": user_id, "plan_code": "MONTHLY_ALL", "note": "هدیهٔ برندهٔ مسابقه"},
    )
    assert response.status_code == 201, response.text
    assert response.json()["status"] == "ACTIVE"


async def test_ta_reads_the_roster_without_final_grades(client: Any, db_session: Any) -> None:
    """دستیار حضور ثبت می‌کند، پس فهرست کلاس را لازم دارد — ولی نه نمره را."""
    from silp.models.education import Enrollment

    scene = await _scene(client, db_session)
    oid = scene["offering"].id
    first_id = uuid.UUID(scene["students"][0]["id"])
    enrollment = await db_session.scalar(
        select(Enrollment).where(Enrollment.offering_id == oid, Enrollment.student_id == first_id)
    )
    response = await client.patch(
        f"/api/v1/teach/enrollments/{enrollment.id}/grade",
        headers=auth(scene["instructor_token"]),
        json={"grade": 17},
    )
    assert response.status_code == 200, response.text
    ta_token = await _scoped_ta(client, db_session, oid)

    response = await client.get(f"/api/v1/teach/offerings/{oid}/students", headers=auth(ta_token))
    assert response.status_code == 200, response.text
    assert len(response.json()) == 3
    assert all(row["final_grade"] is None for row in response.json())

    response = await client.get(
        f"/api/v1/teach/offerings/{oid}/students", headers=auth(scene["instructor_token"])
    )
    graded = next(r for r in response.json() if r["student_id"] == str(first_id))
    assert graded["final_grade"] == 17


async def test_copy_content_needs_scope_on_the_source_too(client: Any, db_session: Any) -> None:
    """هم‌درس بودن کافی نیست: پیش‌نویس ارائهٔ استاد دیگر از این راه خوانده نمی‌شد."""
    from silp.models.education import CourseOffering, Term

    scene = await _scene(client, db_session)
    other = await login(client, OUTSIDER_MOBILE)
    other_id = (await me(client, other))["id"]
    await grant_role(db_session, other_id, "INSTRUCTOR")
    term = Term(
        code=f"T-{uuid.uuid4().hex[:8]}",
        title_fa="نیم‌سال بعد",
        starts_on=date(2027, 2, 5),
        ends_on=date(2027, 6, 30),
    )
    db_session.add(term)
    await db_session.flush()
    theirs = CourseOffering(
        course_id=scene["course"].id,
        term_id=term.id,
        instructor_id=uuid.UUID(other_id),
        status="DRAFT",
    )
    db_session.add(theirs)
    await db_session.flush()
    await invalidate(other_id)
    other = await login(client, OUTSIDER_MOBILE)

    response = await client.post(
        f"/api/v1/teach/offerings/{theirs.id}/copy-content",
        headers=auth(other),
        json={"source_offering_id": str(scene["offering"].id)},
    )
    assert response.status_code == 403, response.text


async def test_ta_grades_an_essay_but_only_the_instructor_changes_a_score(
    client: Any, db_session: Any
) -> None:
    """§6.2 «بازنویسی نمره: TA ❌» — تا ADR-0019 هیچ‌جا اجرا نمی‌شد."""
    scene = await _scene(client, db_session)
    oid = scene["offering"].id
    headers = auth(scene["instructor_token"])
    student = scene["students"][0]
    now = datetime.now(UTC)
    quiz_id = (
        await client.post(
            f"/api/v1/teach/offerings/{oid}/quizzes",
            headers=headers,
            json={
                "title_fa": "آزمون تشریحی",
                "duration_min": 20,
                "opens_at": (now - timedelta(minutes=5)).isoformat(),
                "closes_at": (now + timedelta(hours=2)).isoformat(),
                "shuffle_questions": False,
                "shuffle_options": False,
            },
        )
    ).json()["id"]
    essay = (
        await client.post(
            f"/api/v1/teach/quizzes/{quiz_id}/questions",
            headers=headers,
            json={"kind": "ESSAY", "body": "توضیح بده.", "payload": {}, "points": "4"},
        )
    ).json()["id"]
    closed = (
        await client.post(
            f"/api/v1/teach/quizzes/{quiz_id}/questions",
            headers=headers,
            json={"kind": "SINGLE_CHOICE", "body": "۱+۱؟", "payload": SINGLE, "points": "1"},
        )
    ).json()["id"]
    await client.post(f"/api/v1/teach/quizzes/{quiz_id}/publish", headers=headers)
    attempt = (
        await client.post(f"/api/v1/quizzes/{quiz_id}/attempts", headers=auth(student["token"]))
    ).json()["attempt_id"]
    for qid, response in ((essay, {"text": "پاسخ"}), (closed, {"selected": ["b"]})):
        await client.put(
            f"/api/v1/attempts/{attempt}/answers/{qid}",
            headers=auth(student["token"]),
            json={"response": response},
        )
    await client.post(
        f"/api/v1/attempts/{attempt}/submit",
        headers=auth(student["token"]),
        json={"confirm_unanswered": 0},
    )
    ta = await _scoped_ta(client, db_session, oid)
    url = f"/api/v1/teach/quizzes/{quiz_id}/attempts/{attempt}/answers"

    response = await client.put(f"{url}/{essay}", headers=auth(ta), json={"score": "3"})
    assert response.status_code == 200, response.text  # تصحیح نخست
    response = await client.put(f"{url}/{essay}", headers=auth(ta), json={"score": "4"})
    assert response.status_code == 403  # بازنویسی تشریحی
    response = await client.put(f"{url}/{closed}", headers=auth(ta), json={"score": "0"})
    assert response.status_code == 403  # بازنویسی سؤال بسته
    response = await client.put(f"{url}/{essay}", headers=headers, json={"score": "4"})
    assert response.status_code == 200, response.text
