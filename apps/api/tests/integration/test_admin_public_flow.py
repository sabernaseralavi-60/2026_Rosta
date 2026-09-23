"""M7 بخش د — صفحهٔ عمومی، گواهی، نیمرخ عمومی، پنل مدیریت و جستجوی ⌘K.

PostgreSQL واقعی لازم است: ایندکس یکتای «یک گواهی معتبر برای هر موضوع»،
تریگر فقط‌افزودنی `audit_logs` و `fa_normalize` جستجو هیچ‌کدام در حافظه
شبیه‌سازی نمی‌شوند.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from tests.integration.helpers import (
    auth,
    complete_profile,
    grant_role,
    invalidate,
    login,
    me,
    milestone_payload,
    project_payload,
    taxonomy_ids,
)

pytestmark = pytest.mark.integration

LEAD = "09121770001"
MEMBER = "09121770002"
ADMIN = "09121770003"
SUPPORT = "09121770004"
OUTSIDER = "09121770005"
MENTOR = "09121770006"
TEACHER = "09121770007"


async def _person(client: Any, mobile: str, first_name: str) -> tuple[str, str]:
    token = await login(client, mobile)
    await complete_profile(client, token, first_name=first_name)
    return token, str((await me(client, token))["id"])


async def _staff(client: Any, db_session: Any, mobile: str, role: str) -> tuple[str, str]:
    token, user_id = await _person(client, mobile, "کارمند")
    await grant_role(db_session, user_id, role)
    return token, user_id


async def _audit(db_session: Any, action: str, **where: Any) -> list[Any]:
    from silp.models.admin import AuditLog

    stmt = select(AuditLog).where(AuditLog.action == action)
    for key, value in where.items():
        stmt = stmt.where(getattr(AuditLog, key) == value)
    return list(await db_session.scalars(stmt.order_by(AuditLog.id)))


async def _kinds(db_session: Any, user_id: str) -> list[str]:
    from silp.models.messaging import Notification

    return list(
        await db_session.scalars(select(Notification.kind).where(Notification.user_id == user_id))
    )


async def _completed_project(
    client: Any, db_session: Any, *, title: str = "فروش خرمای مضافتی کرمان"
) -> dict[str, str]:
    """پروژهٔ دونفره که یک مرحلهٔ تأییدشده دارد و مدیرش آن را بسته است."""
    lead_token, lead_id = await _person(client, LEAD, "صابر")
    member_token, member_id = await _person(client, MEMBER, "زهرا")
    skills = await taxonomy_ids(client, "skills", limit=1)
    response = await client.post(
        "/api/v1/projects",
        headers=auth(lead_token),
        json=project_payload(
            title_fa=title,
            required_skills=[{"skill_id": skills[0], "min_level": 3, "weight": 2}],
        ),
    )
    assert response.status_code == 201, response.text
    project_id = response.json()["id"]
    response = await client.post(
        f"/api/v1/projects/{project_id}/milestones",
        headers=auth(lead_token),
        json=milestone_payload(),
    )
    assert response.status_code == 201, response.text
    assert (
        await client.post(f"/api/v1/projects/{project_id}/publish", headers=auth(lead_token))
    ).status_code == 200

    response = await client.post(
        f"/api/v1/projects/{project_id}/applications",
        headers=auth(member_token),
        json={"motivation": "به فروش علاقه دارم و وقت آزاد دارم."},
    )
    assert response.status_code == 201, response.text
    response = await client.post(
        f"/api/v1/applications/{response.json()['id']}/decide",
        headers=auth(lead_token),
        json={"decision": "ACCEPTED"},
    )
    assert response.status_code == 200, response.text
    await invalidate(member_id)
    assert (
        await client.post(f"/api/v1/projects/{project_id}/start", headers=auth(lead_token))
    ).status_code == 200

    milestone = (
        await client.get(f"/api/v1/projects/{project_id}/milestones", headers=auth(member_token))
    ).json()[0]
    response = await client.post(
        f"/api/v1/milestones/{milestone['id']}/deliverables",
        headers=auth(member_token),
        json={"body": "گزارش ده مصاحبه", "links": ["https://example.org/report"]},
    )
    assert response.status_code == 201, response.text
    response = await client.post(
        f"/api/v1/deliverables/{response.json()['id']}/review",
        headers=auth(lead_token),
        json={"decision": "APPROVED", "score": 45, "feedback": "خوب بود."},
    )
    assert response.status_code == 200, response.text
    response = await client.post(
        f"/api/v1/projects/{project_id}/complete",
        headers=auth(lead_token),
        json={"final_report": "با فروش دوازده میلیونی بسته شد."},
    )
    assert response.status_code == 200, response.text
    return {
        "project_id": project_id,
        "lead_token": lead_token,
        "lead_id": lead_id,
        "member_token": member_token,
        "member_id": member_id,
    }


async def _certificates(client: Any, token: str) -> list[dict[str, Any]]:
    response = await client.get("/api/v1/me/certificates", headers=auth(token))
    assert response.status_code == 200, response.text
    return list(response.json())


# ── گواهی — M7-11 ──────────────────────────────────────────────────────
async def test_completing_a_project_certifies_every_active_member(client, db_session) -> None:  # type: ignore[no-untyped-def]
    scene = await _completed_project(client, db_session)

    member_certs = await _certificates(client, scene["member_token"])
    assert len(member_certs) == 1
    cert = member_certs[0]
    assert cert["kind"] == "PROJECT"
    assert cert["title_fa"] == "تکمیل پروژهٔ «فروش خرمای مضافتی کرمان»"
    assert cert["details"]["role"] == "MEMBER"
    assert cert["details"]["team_size"] == 2
    # صادرکننده کسی است که پروژه را بست.
    assert cert["issuer_name"] == "صابر رستمی"
    assert cert["verify_path"] == f"/verify/{cert['public_code']}"
    assert "CERTIFICATE_ISSUED" in await _kinds(db_session, scene["member_id"])

    # مدیری که پروژهٔ خودش را بست، گواهی‌اش را خودش صادر نکرده است.
    lead_cert = (await _certificates(client, scene["lead_token"]))[0]
    assert lead_cert["details"]["role"] == "LEAD"
    assert lead_cert["issuer_name"] == "سامانهٔ نوآوری و یادگیری صابر"

    # راستی‌آزمایی عمومی — بی‌ورود، با کد کوچک و بی‌خط‌تیره هم.
    loose = cert["public_code"].replace("-", "").lower()
    response = await client.get(f"/api/v1/public/certificates/{loose}")
    assert response.status_code == 200, response.text
    public = response.json()
    assert public["valid"] is True
    assert public["holder_name"] == "زهرا رستمی"
    assert public["issuer"] == "صابر رستمی"
    assert public["holder_username"] is None  # نیمرخ عمومی نیست
    assert "mobile" not in response.text and "09121770002" not in response.text
    assert response.headers["cache-control"] == "public, max-age=60"

    response = await client.get("/api/v1/public/certificates/ZZZZ-ZZZZ")
    assert response.status_code == 404


async def test_issuing_is_idempotent(client, db_session) -> None:  # type: ignore[no-untyped-def]
    from silp.models.delivery import Certificate
    from silp.services import certificate_listeners, events

    scene = await _completed_project(client, db_session)
    await certificate_listeners.on_project_completed(
        db_session, events.ProjectCompleted(project_id=uuid.UUID(scene["project_id"]))
    )
    count = await db_session.scalar(
        select(func.count())
        .select_from(Certificate)
        .where(Certificate.subject_id == uuid.UUID(scene["project_id"]))
    )
    assert count == 2


async def test_admin_revokes_with_reason_and_the_page_says_revoked(client, db_session) -> None:  # type: ignore[no-untyped-def]
    scene = await _completed_project(client, db_session)
    admin, admin_id = await _staff(client, db_session, ADMIN, "ADMIN")
    cert = (await _certificates(client, scene["member_token"]))[0]
    revoke = f"/api/v1/admin/certificates/{cert['id']}/revoke"

    response = await client.post(
        revoke, headers=auth(scene["lead_token"]), json={"reason": "تقلب در گزارش"}
    )
    assert response.status_code == 403
    response = await client.post(revoke, headers=auth(admin), json={"reason": "کم"})
    assert response.status_code == 422

    response = await client.post(
        revoke, headers=auth(admin), json={"reason": "گزارش نهایی از پروژهٔ دیگری کپی شده بود."}
    )
    assert response.status_code == 200, response.text
    assert response.json()["revoked_at"] is not None
    response = await client.post(revoke, headers=auth(admin), json={"reason": "دوباره باطل کن"})
    assert response.status_code == 409

    public = (await client.get(f"/api/v1/public/certificates/{cert['public_code']}")).json()
    assert public["valid"] is False
    assert public["revoke_reason"] == "گزارش نهایی از پروژهٔ دیگری کپی شده بود."
    rows = await _audit(db_session, "CERTIFICATE_REVOKED", actor_id=uuid.UUID(admin_id))
    assert len(rows) == 1 and rows[0].after["revoked"] is True
    assert "CERTIFICATE_REVOKED" in await _kinds(db_session, scene["member_id"])

    # موضوع باطل‌شده می‌تواند دوباره گواهی بگیرد (اصلاح اشتباه).
    from silp.services import certificate_listeners, events

    await certificate_listeners.on_project_completed(
        db_session, events.ProjectCompleted(project_id=uuid.UUID(scene["project_id"]))
    )
    certs = await _certificates(client, scene["member_token"])
    assert sorted(c["revoked_at"] is None for c in certs) == [False, True]


async def test_approved_research_level_is_certified(client, db_session) -> None:  # type: ignore[no-untyped-def]
    from tests.integration.test_research_flow import LEVEL_ONE

    student, _ = await _person(client, OUTSIDER, "سارا")
    mentor, mentor_id = await _staff(client, db_session, MENTOR, "MENTOR")
    response = await client.post(
        "/api/v1/research/tracks/1/submit", headers=auth(student), json=LEVEL_ONE
    )
    assert response.status_code == 201, response.text
    response = await client.post(
        f"/api/v1/research/submissions/{response.json()['id']}/review",
        headers=auth(mentor),
        json={"decision": "APPROVED"},
    )
    assert response.status_code == 200, response.text

    [cert] = await _certificates(client, student)
    assert cert["kind"] == "RESEARCH_LEVEL"
    assert cert["title_fa"] == "سطح ۱ مسیر پژوهش — مرور ادبیات"
    assert cert["issuer_name"] == "کارمند رستمی"
    assert cert["details"]["level"] == 1


async def test_course_certificate_follows_the_final_grade(client, db_session) -> None:  # type: ignore[no-untyped-def]
    from silp.models.education import Course, CourseOffering, Enrollment, Term

    teacher, teacher_id = await _staff(client, db_session, TEACHER, "INSTRUCTOR")
    student, student_id = await _person(client, OUTSIDER, "سارا")
    marker = uuid.uuid4().hex[:8]
    term = Term(
        code=f"T-{marker}",
        title_fa="پاییز ۱۴۰۵",
        starts_on=date(2026, 9, 23),
        ends_on=date(2027, 2, 4),
    )
    course = Course(code=f"C-{marker}", slug=f"c-{marker}", title_fa="مهندسی ترابری")
    db_session.add_all([term, course])
    await db_session.flush()
    offering = CourseOffering(
        course_id=course.id,
        term_id=term.id,
        instructor_id=uuid.UUID(teacher_id),
        status="IN_PROGRESS",
    )
    db_session.add(offering)
    await db_session.flush()
    enrollment = Enrollment(
        offering_id=offering.id, student_id=uuid.UUID(student_id), status="ACTIVE"
    )
    db_session.add(enrollment)
    await db_session.flush()
    await invalidate(teacher_id)

    grade = f"/api/v1/teach/enrollments/{enrollment.id}/grade"
    response = await client.patch(grade, headers=auth(teacher), json={"grade": 15})
    assert response.status_code == 200, response.text
    [cert] = await _certificates(client, student)
    assert cert["kind"] == "COURSE" and cert["title_fa"] == "گذراندن درس «مهندسی ترابری»"
    assert "grade" not in str(cert["details"])  # نمره روی گواهی نمی‌آید (FR-PROF-03)

    # نمرهٔ اصلاح‌شده به زیر ده، گواهی را باطل می‌کند.
    response = await client.patch(grade, headers=auth(teacher), json={"grade": 8})
    assert response.status_code == 200, response.text
    [cert] = await _certificates(client, student)
    assert cert["revoked_at"] is not None
    rows = await _audit(db_session, "FINAL_GRADE_SET", entity_id=enrollment.id)
    assert [r.after["final_grade"] for r in rows] == [15.0, 8.0]
    assert float(rows[1].before["final_grade"]) == 15


# ── نیمرخ عمومی — FR-PROF-03 ───────────────────────────────────────────
async def test_public_profile_respects_is_public_and_sections(client, db_session) -> None:  # type: ignore[no-untyped-def]
    scene = await _completed_project(client, db_session)
    member = await me(client, scene["member_token"])
    username = member["username"]
    path = f"/api/v1/profiles/{username}"

    # خصوصی ⇒ ۴۰۴ برای همه جز خودش.
    assert (await client.get(path)).status_code == 404
    response = await client.get(path, headers=auth(scene["lead_token"]))
    assert response.status_code == 404
    response = await client.get(path, headers=auth(scene["member_token"]))
    assert response.status_code == 200
    assert response.json()["is_owner"] is True and response.json()["is_public"] is False
    assert response.headers["cache-control"] == "private, no-store"

    response = await client.patch(
        "/api/v1/me/profile", headers=auth(scene["member_token"]), json={"is_public": True}
    )
    assert response.status_code == 200, response.text
    assert all(response.json()["privacy"].values())

    response = await client.get(path)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["name"] == "زهرا رستمی"
    assert [p["title_fa"] for p in body["projects"]] == ["فروش خرمای مضافتی کرمان"]
    assert body["projects"][0]["role_fa"] == "عضو تیم"
    assert len(body["certificates"]) == 1
    assert body["skills"] and all(s["level"] >= 4 for s in body["skills"])
    assert body["points"]["total"] > 0
    for secret in ("mobile", "email", "national", "grade", "rank", "09121770002"):
        assert secret not in response.text

    # گواهی حالا نام کاربری دارنده را هم دارد.
    code = body["certificates"][0]["public_code"]
    assert (await client.get(f"/api/v1/public/certificates/{code}")).json()[
        "holder_username"
    ] == username

    response = await client.patch(
        "/api/v1/me/profile",
        headers=auth(scene["member_token"]),
        json={"privacy": {"projects": False, "points": False}},
    )
    assert response.status_code == 200, response.text
    assert response.json()["privacy"]["projects"] is False
    assert response.json()["privacy"]["skills"] is True
    body = (await client.get(path)).json()
    assert body["projects"] == [] and body["points"] is None
    assert body["sections"]["projects"] is False
    assert body["certificates"]  # بخش دیگر دست نخورده

    response = await client.patch(
        "/api/v1/me/profile",
        headers=auth(scene["member_token"]),
        json={"privacy": {"mobile": True}},
    )
    assert response.status_code == 422


# ── صفحهٔ اصلی — M7-10 ─────────────────────────────────────────────────
async def test_public_stats_and_stories_are_real(client, db_session) -> None:  # type: ignore[no-untyped-def]
    response = await client.get("/api/v1/public/stats")
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "public, max-age=300"
    before = response.json()

    scene = await _completed_project(client, db_session, title="داستان واقعی خرما")
    after = (await client.get("/api/v1/public/stats")).json()
    assert after["completed_projects"] == before["completed_projects"] + 1
    assert after["certificates"] == before["certificates"] + 2
    assert after["completed_milestones"] == before["completed_milestones"] + 1

    stories = (await client.get("/api/v1/public/stories")).json()
    story = next(s for s in stories if s["project_id"] == scene["project_id"])
    assert story["team_size"] == 2 and story["approved_milestones"] == 1
    assert story["members"] == []  # هیچ‌کدام نیمرخ عمومی ندارند

    await client.patch(
        "/api/v1/me/profile", headers=auth(scene["lead_token"]), json={"is_public": True}
    )
    stories = (await client.get("/api/v1/public/stories")).json()
    story = next(s for s in stories if s["project_id"] == scene["project_id"])
    assert [m["name"] for m in story["members"]] == ["صابر رستمی"]
    assert story["members"][0]["is_lead"] is True


# ── پنل مدیریت — M7-12 ─────────────────────────────────────────────────
async def test_user_directory_needs_permission_and_masks_contact_for_support(  # type: ignore[no-untyped-def]
    client, db_session
) -> None:
    student, _ = await _person(client, OUTSIDER, "سارا")
    support, _ = await _staff(client, db_session, SUPPORT, "SUPPORT")
    admin, _ = await _staff(client, db_session, ADMIN, "ADMIN")

    assert (await client.get("/api/v1/admin/users", headers=auth(student))).status_code == 403

    response = await client.get(
        "/api/v1/admin/users", headers=auth(support), params={"q": "1770005"}
    )
    assert response.status_code == 200, response.text
    [row] = response.json()["items"]
    assert row["mobile"] == "0912***0005"
    assert row["roles"] == ["STUDENT"]

    response = await client.get("/api/v1/admin/users", headers=auth(admin), params={"q": "سارا"})
    assert "09121770005" in [r["mobile"] for r in response.json()["items"]]

    # نقش‌دادن کار پشتیبانی نیست.
    response = await client.post(
        f"/api/v1/admin/users/{row['id']}/roles", headers=auth(support), json={"role": "MENTOR"}
    )
    assert response.status_code == 403


async def test_role_grant_and_revoke_are_audited(client, db_session) -> None:  # type: ignore[no-untyped-def]
    student, student_id = await _person(client, OUTSIDER, "سارا")
    admin, admin_id = await _staff(client, db_session, ADMIN, "ADMIN")
    roles = f"/api/v1/admin/users/{student_id}/roles"

    response = await client.post(roles, headers=auth(admin), json={"role": "PROJECT_LEAD"})
    assert response.status_code == 422  # نقش مشتق
    response = await client.post(
        roles, headers=auth(admin), json={"role": "MENTOR", "scope_type": "OFFERING"}
    )
    assert response.status_code == 422  # منتور فقط سراسری

    response = await client.post(roles, headers=auth(admin), json={"role": "MENTOR"})
    assert response.status_code == 201, response.text
    detail = response.json()
    assert {g["code"] for g in detail["grants"]} == {"STUDENT", "MENTOR"}
    mentor_grant = next(g for g in detail["grants"] if g["code"] == "MENTOR")
    assert mentor_grant["granted_by_name"] == "کارمند رستمی"
    assert detail["recent_audit"][0]["action"] == "ROLE_GRANTED"
    assert "ROLE_GRANTED" in await _kinds(db_session, student_id)
    assert any(r["code"] == "MENTOR" for r in (await me(client, student))["roles"])
    response = await client.post(roles, headers=auth(admin), json={"role": "MENTOR"})
    assert response.status_code == 409

    response = await client.delete(f"{roles}/MENTOR", headers=auth(admin))
    assert response.status_code == 200, response.text
    assert {g["code"] for g in response.json()["grants"]} == {"STUDENT"}
    [granted] = await _audit(db_session, "ROLE_GRANTED", entity_id=uuid.UUID(student_id))
    [revoked] = await _audit(db_session, "ROLE_REVOKED", entity_id=uuid.UUID(student_id))
    assert granted.actor_id == uuid.UUID(admin_id) and granted.after["role"] == "MENTOR"
    assert revoked.before["role"] == "MENTOR"

    # مدیر نقش مدیر خودش را برنمی‌دارد.
    response = await client.delete(
        f"/api/v1/admin/users/{admin_id}/roles/ADMIN", headers=auth(admin)
    )
    assert response.status_code == 409


async def test_suspension_locks_the_account_immediately(client, db_session) -> None:  # type: ignore[no-untyped-def]
    from silp.models.identity import RefreshToken

    student, student_id = await _person(client, OUTSIDER, "سارا")
    admin, admin_id = await _staff(client, db_session, ADMIN, "ADMIN")
    path = f"/api/v1/admin/users/{student_id}"

    response = await client.patch(path, headers=auth(admin), json={"status": "SUSPENDED"})
    assert response.status_code == 422  # دلیل اجباری است
    response = await client.patch(
        path, headers=auth(admin), json={"status": "SUSPENDED", "reason": "گزارش تقلب در آزمون"}
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "SUSPENDED"

    response = await client.get("/api/v1/me", headers=auth(student))
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ACCOUNT_SUSPENDED"
    open_sessions = await db_session.scalar(
        select(func.count())
        .select_from(RefreshToken)
        .where(RefreshToken.user_id == uuid.UUID(student_id), RefreshToken.revoked_at.is_(None))
    )
    assert open_sessions == 0
    [row] = await _audit(db_session, "USER_STATUS_CHANGED", entity_id=uuid.UUID(student_id))
    assert row.before == {"status": "ACTIVE"} and row.after["reason"] == "گزارش تقلب در آزمون"

    response = await client.patch(
        f"/api/v1/admin/users/{admin_id}",
        headers=auth(admin),
        json={"status": "SUSPENDED", "reason": "آزمایش تعلیق خود"},
    )
    assert response.status_code == 409


async def test_impersonation_is_read_only_logged_and_announced(client, db_session) -> None:  # type: ignore[no-untyped-def]
    student, student_id = await _person(client, OUTSIDER, "سارا")
    support, support_id = await _staff(client, db_session, SUPPORT, "SUPPORT")
    admin, admin_id = await _staff(client, db_session, ADMIN, "ADMIN")

    response = await client.post(
        f"/api/v1/admin/users/{support_id}/impersonate", headers=auth(student)
    )
    assert response.status_code == 403
    response = await client.post(
        f"/api/v1/admin/users/{admin_id}/impersonate", headers=auth(support)
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "IMPERSONATION_FORBIDDEN"

    detail = (await client.get(f"/api/v1/admin/users/{student_id}", headers=auth(support))).json()
    assert detail["can_impersonate"] is True
    response = await client.post(
        f"/api/v1/admin/users/{student_id}/impersonate", headers=auth(support)
    )
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    assert response.json()["user_name"] == "سارا رستمی"

    response = await client.get("/api/v1/me", headers=auth(token))
    assert response.status_code == 200
    assert response.json()["id"] == student_id
    response = await client.post(
        "/api/v1/ideas",
        headers=auth(token),
        json={
            "title": "ایدهٔ جعلی",
            "body": "این نباید ثبت شود چون فقط خواندنی است.",
            "category": "OTHER",
        },
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "IMPERSONATION_READ_ONLY"

    started = await _audit(db_session, "IMPERSONATION_STARTED", actor_id=uuid.UUID(support_id))
    assert [r.entity_id for r in started] == [uuid.UUID(student_id)]
    requests = await _audit(
        db_session, "IMPERSONATED_REQUEST", impersonated_by=uuid.UUID(support_id)
    )
    assert requests and all(r.actor_id == uuid.UUID(student_id) for r in requests)
    assert requests[0].after["path"] == "/api/v1/me"
    assert "ACCOUNT_VIEWED_BY_SUPPORT" in await _kinds(db_session, student_id)

    response = await client.post(
        "/api/v1/admin/impersonation/end", headers=auth(support), json={"user_id": student_id}
    )
    assert response.status_code == 204
    assert await _audit(db_session, "IMPERSONATION_ENDED", actor_id=uuid.UUID(support_id))

    # پشتیبانی که نقشش را از دست داد، توکن جعل هویتش هم می‌میرد.
    await client.delete(f"/api/v1/admin/users/{support_id}/roles/SUPPORT", headers=auth(admin))
    assert (await client.get("/api/v1/me", headers=auth(token))).status_code == 401


async def test_audit_log_is_append_only_searchable_and_exportable(client, db_session) -> None:  # type: ignore[no-untyped-def]
    student, student_id = await _person(client, OUTSIDER, "سارا")
    admin, _ = await _staff(client, db_session, ADMIN, "ADMIN")
    await client.post(
        f"/api/v1/admin/users/{student_id}/roles", headers=auth(admin), json={"role": "MENTOR"}
    )
    response = await client.patch(
        "/api/v1/admin/point-rules/IDEA_SUBMITTED", headers=auth(admin), json={"base_points": 7}
    )
    assert response.status_code == 200, response.text
    [rule] = await _audit(db_session, "POINT_RULE_UPDATED")
    assert rule.before["code"] == "IDEA_SUBMITTED" and rule.after["base_points"] == "7"

    with pytest.raises(DBAPIError, match="append-only"):
        async with db_session.begin_nested():
            await db_session.execute(text("UPDATE audit_logs SET action = 'ERASED'"))
    with pytest.raises(DBAPIError, match="append-only"):
        async with db_session.begin_nested():
            await db_session.execute(text("DELETE FROM audit_logs"))

    assert (await client.get("/api/v1/admin/audit", headers=auth(student))).status_code == 403
    response = await client.get(
        "/api/v1/admin/audit", headers=auth(admin), params={"user_id": student_id, "limit": 1}
    )
    assert response.status_code == 200, response.text
    page = response.json()
    assert page["items"][0]["action_fa"] == "اعطای نقش"
    assert page["items"][0]["actor_name"] == "کارمند رستمی"

    response = await client.get(
        "/api/v1/admin/audit/export", headers=auth(admin), params={"action": "ROLE_GRANTED"}
    )
    assert response.status_code == 200
    assert response.content.startswith("﻿".encode())
    assert "اعطای نقش" in response.content.decode("utf-8")


async def test_metrics_for_support(client, db_session) -> None:  # type: ignore[no-untyped-def]
    student, _ = await _person(client, OUTSIDER, "سارا")
    support, _ = await _staff(client, db_session, SUPPORT, "SUPPORT")
    assert (await client.get("/api/v1/admin/metrics", headers=auth(student))).status_code == 403
    response = await client.get("/api/v1/admin/metrics", headers=auth(support))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["users_total"] >= 2 and body["roles"]["SUPPORT"] >= 1


# ── جستجوی سراسری ⌘K — M7-13 ───────────────────────────────────────────
async def test_global_search_respects_visibility_and_normalizes_persian(client, db_session) -> None:  # type: ignore[no-untyped-def]
    lead, lead_id = await _person(client, LEAD, "صابر")
    other, _ = await _person(client, OUTSIDER, "کیانا")
    response = await client.post(
        "/api/v1/projects",
        headers=auth(lead),
        json=project_payload(title_fa="پیش‌نویس محرمانهٔ کیمیاگری"),
    )
    assert response.status_code == 201
    draft_id = response.json()["id"]

    assert (await client.get("/api/v1/search", params={"q": "کیمیا"})).status_code == 401
    assert (await client.get("/api/v1/search", headers=auth(other), params={"q": "ک"})).json()[
        "groups"
    ] == []

    # «ي» و «ك» عربی همان «ی» و «ک» فارسی‌اند.
    arabic = "كيمياگري"
    mine = (await client.get("/api/v1/search", headers=auth(lead), params={"q": arabic})).json()
    projects = next(g for g in mine["groups"] if g["kind"] == "PROJECT")
    assert projects["items"][0]["id"] == draft_id
    assert projects["items"][0]["href"] == f"/projects/{draft_id}"
    theirs = (await client.get("/api/v1/search", headers=auth(other), params={"q": arabic})).json()
    assert all(g["kind"] != "PROJECT" for g in theirs["groups"])

    # فرد فقط با نیمرخ عمومی.
    found = (
        await client.get("/api/v1/search", headers=auth(other), params={"q": "صابر رستمی"})
    ).json()
    assert all(g["kind"] != "PERSON" for g in found["groups"])
    await client.patch("/api/v1/me/profile", headers=auth(lead), json={"is_public": True})
    found = (
        await client.get("/api/v1/search", headers=auth(other), params={"q": "صابر رستمی"})
    ).json()
    people = next(g for g in found["groups"] if g["kind"] == "PERSON")
    username = (await me(client, lead))["username"]
    assert people["items"][0]["href"] == f"/u/{username}"
    assert people["items"][0]["id"] == lead_id
