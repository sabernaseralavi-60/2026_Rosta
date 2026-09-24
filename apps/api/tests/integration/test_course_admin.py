"""تعریف درس، نیم‌سال و ارائه در پنل — §3.6 `/admin/courses`، ADR-0020.

آخرین مانع معرفی در کلاس: تا اینجا ارائهٔ تازه فقط با `seed_launch` روی سرور
ساخته می‌شد. این تست‌ها کل چرخه را از دید مدیر آموزشی می‌روند و مرزها را
می‌پایند: استاد ارائه نمی‌سازد، درس پوشه‌ای در پنل ویرایش نمی‌شود، و ارائهٔ
استفاده‌شده حذف نمی‌شود.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import func, select
from tests.integration.helpers import auth, grant_role, login, me

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

COORDINATOR_MOBILE = "09122200001"
INSTRUCTOR_MOBILE = "09122200002"
SECOND_INSTRUCTOR_MOBILE = "09122200003"
STUDENT_MOBILE = "09122200004"
SUPPORT_MOBILE = "09122200005"
TA_MOBILE = "09122200006"

TODAY = datetime.now(UTC).date()


async def _coordinator(client: Any, session: Any) -> str:
    token = await login(client, COORDINATOR_MOBILE)
    await grant_role(session, (await me(client, token))["id"], "COORDINATOR")
    return token


async def _user(client: Any, mobile: str) -> tuple[str, str]:
    token = await login(client, mobile)
    return token, (await me(client, token))["id"]


def _marker() -> str:
    return uuid.uuid4().hex[:6].upper()


async def _term(client: Any, token: str, **overrides: Any) -> dict[str, Any]:
    body = {
        "code": f"T{_marker()}",
        "title_fa": "نیم‌سال آزمایشی",
        "starts_on": (TODAY - timedelta(days=10)).isoformat(),
        "ends_on": (TODAY + timedelta(days=120)).isoformat(),
        **overrides,
    }
    response = await client.post("/api/v1/admin/terms", headers=auth(token), json=body)
    assert response.status_code == 201, response.text
    return dict(response.json())


async def _course(client: Any, token: str, **overrides: Any) -> dict[str, Any]:
    body = {"code": f"CE-{_marker()}", "title_fa": "برنامه‌ریزی حمل‌ونقل", **overrides}
    response = await client.post("/api/v1/admin/courses", headers=auth(token), json=body)
    assert response.status_code == 201, response.text
    return dict(response.json())


async def _offering(client: Any, token: str, **body: Any) -> Any:
    return await client.post("/api/v1/admin/offerings", headers=auth(token), json=body)


# ── دسترسی ─────────────────────────────────────────────────────────────
async def test_instructor_and_support_cannot_define_courses(client: Any, db_session: Any) -> None:
    """ADR-0019 بند ۱: ارائه استاد را می‌سازد، نه برعکس — `offering.create` دیگر
    برای استاد نیست. پشتیبانی هم پنل را می‌بیند ولی آموزش را تعریف نمی‌کند."""
    instructor_token, instructor_id = await _user(client, INSTRUCTOR_MOBILE)
    await grant_role(db_session, instructor_id, "INSTRUCTOR")
    support_token, support_id = await _user(client, SUPPORT_MOBILE)
    await grant_role(db_session, support_id, "SUPPORT")

    for token in (instructor_token, support_token):
        for path in ("/api/v1/admin/terms", "/api/v1/admin/courses", "/api/v1/admin/offerings"):
            response = await client.get(path, headers=auth(token))
            assert response.status_code == 403, (path, response.text)
        response = await _offering(
            client,
            token,
            course_id=str(uuid.uuid4()),
            term_id=str(uuid.uuid4()),
            instructor_id=instructor_id,
        )
        assert response.status_code == 403


# ── نیم‌سال ────────────────────────────────────────────────────────────
async def test_only_one_term_is_current(client: Any, db_session: Any) -> None:
    token = await _coordinator(client, db_session)
    first = await _term(client, token, is_current=True)
    second = await _term(client, token)

    response = await client.patch(
        f"/api/v1/admin/terms/{second['id']}", headers=auth(token), json={"is_current": True}
    )
    assert response.status_code == 200, response.text
    assert response.json()["is_current"] is True

    terms = (await client.get("/api/v1/admin/terms", headers=auth(token))).json()
    current = [t["id"] for t in terms if t["is_current"]]
    assert current == [second["id"]]
    assert first["id"] not in current


async def test_term_validation_and_duplicate_code(client: Any, db_session: Any) -> None:
    token = await _coordinator(client, db_session)
    term = await _term(client, token)

    response = await client.post(
        "/api/v1/admin/terms",
        headers=auth(token),
        json={
            "code": term["code"],
            "title_fa": "تکراری",
            "starts_on": "2027-01-01",
            "ends_on": "2027-06-01",
        },
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "TERM_CODE_TAKEN"

    response = await client.patch(
        f"/api/v1/admin/terms/{term['id']}",
        headers=auth(token),
        json={"ends_on": term["starts_on"]},
    )
    assert response.status_code == 422

    response = await client.patch(
        f"/api/v1/admin/terms/{term['id']}", headers=auth(token), json={"title_fa": None}
    )
    assert response.status_code == 422


async def test_term_in_use_is_not_deleted(client: Any, db_session: Any) -> None:
    token = await _coordinator(client, db_session)
    _, instructor_id = await _user(client, INSTRUCTOR_MOBILE)
    used = await _term(client, token)
    unused = await _term(client, token)
    course = await _course(client, token)
    response = await _offering(
        client, token, course_id=course["id"], term_id=used["id"], instructor_id=instructor_id
    )
    assert response.status_code == 201, response.text

    response = await client.delete(f"/api/v1/admin/terms/{used['id']}", headers=auth(token))
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "TERM_IN_USE"

    response = await client.delete(f"/api/v1/admin/terms/{unused['id']}", headers=auth(token))
    assert response.status_code == 204
    ids = [t["id"] for t in (await client.get("/api/v1/admin/terms", headers=auth(token))).json()]
    assert unused["id"] not in ids
    assert used["id"] in ids


# ── درس ────────────────────────────────────────────────────────────────
async def test_course_slug_comes_from_code_and_keys_are_unique(
    client: Any, db_session: Any
) -> None:
    token = await _coordinator(client, db_session)
    marker = _marker()
    course = await _course(client, token, code=f"traffic-{marker}", topics=["جریان", " "])
    assert course["code"] == f"TRAFFIC-{marker}"
    assert course["slug"] == f"traffic-{marker.lower()}"
    assert course["topics"] == ["جریان"]
    assert course["source_dir"] is None

    response = await client.post(
        "/api/v1/admin/courses",
        headers=auth(token),
        json={"code": f"TRAFFIC-{marker}", "title_fa": "تکراری"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "COURSE_CODE_TAKEN"

    response = await client.post(
        "/api/v1/admin/courses",
        headers=auth(token),
        json={"code": f"X-{marker}", "slug": course["slug"], "title_fa": "تکراری"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "COURSE_SLUG_TAKEN"

    response = await client.patch(
        f"/api/v1/admin/courses/{course['id']}",
        headers=auth(token),
        json={"title_fa": "مهندسی ترافیک", "credits": 3, "is_active": False},
    )
    assert response.status_code == 200, response.text
    assert response.json()["title_fa"] == "مهندسی ترافیک"
    assert response.json()["is_active"] is False

    # درس غیرفعال در ویترین نیست ولی در پنل هست.
    response = await client.get(f"/api/v1/courses/{course['slug']}")
    assert response.status_code == 404
    listed = (await client.get("/api/v1/admin/courses", headers=auth(token))).json()
    assert course["id"] in [c["id"] for c in listed]


async def test_folder_course_is_read_only_in_the_panel(client: Any, db_session: Any) -> None:
    """`sync_courses` هر بار درس پوشه‌ای را از course.yml بازنویسی می‌کند؛
    ویرایش در پنل بی‌صدا برمی‌گشت."""
    from silp.models.education import Course

    token = await _coordinator(client, db_session)
    marker = _marker()
    course = Course(
        code=f"F-{marker}",
        slug=f"folder-{marker.lower()}",
        title_fa="درس پوشه‌ای",
        source_dir=f"Folder {marker}",
    )
    db_session.add(course)
    await db_session.flush()

    response = await client.patch(
        f"/api/v1/admin/courses/{course.id}", headers=auth(token), json={"title_fa": "تغییر"}
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "COURSE_MANAGED_BY_FOLDER"


# ── ارائه ──────────────────────────────────────────────────────────────
async def test_created_offering_is_immediately_the_instructors(
    client: Any, db_session: Any
) -> None:
    """نقش استاد مشتق از ردیف ارائه است و کشش باطل می‌شود؛ استاد بی‌درنگ
    ارائه را در `/teach` می‌بیند و تنظیمش می‌کند."""
    from silp.models.admin import AuditLog

    token = await _coordinator(client, db_session)
    instructor_token, instructor_id = await _user(client, INSTRUCTOR_MOBILE)
    # پیش از سپردن، کش نقش استاد پر می‌شود — همان چیزی که باید باطل شود.
    assert (
        await client.get("/api/v1/teach/offerings", headers=auth(instructor_token))
    ).json() == []

    term = await _term(client, token)
    course = await _course(client, token)
    response = await _offering(
        client,
        token,
        course_id=course["id"],
        term_id=term["id"],
        instructor_id=instructor_id,
        capacity=40,
        enrollment_code="MTP-1405",
    )
    assert response.status_code == 201, response.text
    offering = response.json()
    assert offering["status"] == "DRAFT"
    assert offering["weeks_created"] == 0
    assert offering["has_enrollment_code"] is True
    assert offering["course_code"] == course["code"]

    response = await client.get(
        f"/api/v1/teach/offerings/{offering['id']}", headers=auth(instructor_token)
    )
    assert response.status_code == 200, response.text
    detail = response.json()
    assert detail["enrollment_code"] == "MTP-1405"
    assert detail["grading_policy"] == {
        "quiz": 30,
        "project": 50,
        "attendance": 10,
        "participation": 10,
    }
    assert detail["allowed_statuses"] == ["OPEN"]

    response = await client.patch(
        f"/api/v1/teach/offerings/{offering['id']}",
        headers=auth(instructor_token),
        json={"status": "OPEN"},
    )
    assert response.status_code == 200, response.text

    logged = await db_session.scalar(
        select(func.count()).where(
            AuditLog.action == "OFFERING_CREATED",
            AuditLog.entity_id == uuid.UUID(offering["id"]),
        )
    )
    assert logged == 1


async def test_offering_rules(client: Any, db_session: Any) -> None:
    token = await _coordinator(client, db_session)
    _, instructor_id = await _user(client, INSTRUCTOR_MOBILE)
    term = await _term(client, token)
    ended = await _term(
        client,
        token,
        starts_on=(TODAY - timedelta(days=200)).isoformat(),
        ends_on=(TODAY - timedelta(days=1)).isoformat(),
    )
    course = await _course(client, token)
    base = {"course_id": course["id"], "instructor_id": instructor_id}

    response = await _offering(client, token, **base, term_id=ended["id"])
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "TERM_ENDED"

    response = await _offering(client, token, **base, term_id=term["id"], enrollment_code="AB")
    assert response.status_code == 422

    response = await _offering(
        client, token, **base, term_id=term["id"], grading_policy={"quiz": 50, "project": 40}
    )
    assert response.status_code == 422

    response = await _offering(client, token, **base, term_id=term["id"], weeks_from="SYLLABUS")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "SYLLABUS_UNAVAILABLE"
    # خطای منبع هفته‌ها ارائهٔ نیمه‌کاره نمی‌گذارد.
    listed = await client.get(
        f"/api/v1/admin/offerings?course_id={course['id']}", headers=auth(token)
    )
    assert listed.json() == []

    response = await _offering(client, token, **base, term_id=term["id"], status="OPEN")
    assert response.status_code == 201, response.text
    assert response.json()["status"] == "OPEN"

    response = await _offering(client, token, **base, term_id=term["id"])
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "OFFERING_EXISTS"

    response = await client.patch(
        f"/api/v1/admin/courses/{course['id']}", headers=auth(token), json={"is_active": False}
    )
    assert response.status_code == 200
    _, other_id = await _user(client, SECOND_INSTRUCTOR_MOBILE)
    response = await _offering(
        client, token, course_id=course["id"], instructor_id=other_id, term_id=term["id"]
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "COURSE_INACTIVE"


async def test_weeks_from_the_course_folder_syllabus(
    client: Any, db_session: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from silp.models.education import Course
    from silp.scripts import sync_courses

    marker = _marker()
    folder = tmp_path / f"Course {marker}"
    folder.mkdir()
    (folder / "course.yml").write_text(
        f"code: S-{marker}\n"
        f"slug: syllabus-{marker.lower()}\n"
        "title_fa: درس با برنامه\n"
        "syllabus:\n"
        "  - week: 1\n    title_fa: مقدمه\n"
        "  - week: 2\n    title_fa: تحلیل تقاضا\n    objectives: [مدل چهارمرحله‌ای]\n"
        "  - week: 3\n    title_fa: تخصیص ترافیک\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(sync_courses, "resolve_root", lambda explicit: tmp_path)

    course = Course(
        code=f"S-{marker}",
        slug=f"syllabus-{marker.lower()}",
        title_fa="درس با برنامه",
        source_dir=folder.name,
    )
    db_session.add(course)
    await db_session.flush()

    token = await _coordinator(client, db_session)
    _, instructor_id = await _user(client, INSTRUCTOR_MOBILE)
    term = await _term(client, token)

    listed = (await client.get("/api/v1/admin/courses", headers=auth(token))).json()
    assert next(c for c in listed if c["id"] == str(course.id))["syllabus_weeks"] == 3

    response = await _offering(
        client,
        token,
        course_id=str(course.id),
        term_id=term["id"],
        instructor_id=instructor_id,
        weeks_from="SYLLABUS",
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["weeks_created"] == 3
    assert body["week_count"] == 3
    assert body["published_weeks"] == 0


async def test_weeks_copied_from_a_previous_offering(client: Any, db_session: Any) -> None:
    from silp.models.education import CourseWeek

    token = await _coordinator(client, db_session)
    _, instructor_id = await _user(client, INSTRUCTOR_MOBILE)
    old_term = await _term(client, token)
    new_term = await _term(client, token)
    course = await _course(client, token)

    previous = (
        await _offering(
            client,
            token,
            course_id=course["id"],
            term_id=old_term["id"],
            instructor_id=instructor_id,
        )
    ).json()
    for n in (1, 2):
        db_session.add(
            CourseWeek(
                offering_id=uuid.UUID(previous["id"]),
                week_number=n,
                title_fa=f"هفتهٔ {n}",
                status="PUBLISHED",
            )
        )
    await db_session.flush()

    response = await _offering(
        client,
        token,
        course_id=course["id"],
        term_id=new_term["id"],
        instructor_id=instructor_id,
        weeks_from="OFFERING",
        copy_from_offering_id=previous["id"],
    )
    assert response.status_code == 201, response.text
    assert response.json()["weeks_created"] == 2
    # محتوای نیم‌سال گذشته روز اول ترم تازه یک‌جا منتشر نمی‌شود.
    assert response.json()["published_weeks"] == 0

    other = await _course(client, token)
    response = await _offering(
        client,
        token,
        course_id=other["id"],
        term_id=new_term["id"],
        instructor_id=instructor_id,
        weeks_from="OFFERING",
        copy_from_offering_id=previous["id"],
    )
    assert response.status_code == 422
    assert (
        await client.get(f"/api/v1/admin/offerings?course_id={other['id']}", headers=auth(token))
    ).json() == []


async def test_reassigning_moves_access_between_instructors(client: Any, db_session: Any) -> None:
    from silp.models.education import Enrollment

    token = await _coordinator(client, db_session)
    first_token, first_id = await _user(client, INSTRUCTOR_MOBILE)
    second_token, second_id = await _user(client, SECOND_INSTRUCTOR_MOBILE)
    term = await _term(client, token)
    other_term = await _term(client, token)
    course = await _course(client, token)
    offering = (
        await _offering(
            client, token, course_id=course["id"], term_id=term["id"], instructor_id=first_id
        )
    ).json()
    path = f"/api/v1/teach/offerings/{offering['id']}"
    assert (await client.get(path, headers=auth(first_token))).status_code == 200
    assert (await client.get(path, headers=auth(second_token))).status_code == 403

    response = await client.patch(
        f"/api/v1/admin/offerings/{offering['id']}",
        headers=auth(token),
        json={"instructor_id": second_id},
    )
    assert response.status_code == 200, response.text
    assert response.json()["instructor_id"] == second_id
    assert (await client.get(path, headers=auth(first_token))).status_code == 403
    assert (await client.get(path, headers=auth(second_token))).status_code == 200

    _, student_id = await _user(client, STUDENT_MOBILE)
    db_session.add(
        Enrollment(
            offering_id=uuid.UUID(offering["id"]), student_id=uuid.UUID(student_id), status="ACTIVE"
        )
    )
    await db_session.flush()
    response = await client.patch(
        f"/api/v1/admin/offerings/{offering['id']}",
        headers=auth(token),
        json={"term_id": other_term["id"]},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "OFFERING_HAS_ENROLLMENTS"


async def test_assignment_notifies_both_instructors(client: Any, db_session: Any) -> None:
    """ADR-0021 — استاد تازه اعلانی با پیوند ارائه می‌گیرد، استاد قبلی خبر
    بسته شدن دسترسی‌اش را؛ جابه‌جایی نیم‌سال و سپردن به خود اعلان ندارد."""
    from silp.models.messaging import Notification

    token = await _coordinator(client, db_session)
    _, coordinator_id = await _user(client, COORDINATOR_MOBILE)
    _, first_id = await _user(client, INSTRUCTOR_MOBILE)
    _, second_id = await _user(client, SECOND_INSTRUCTOR_MOBILE)
    term = await _term(client, token, title_fa="نیم‌سال اول ۱۴۰۵")
    other_term = await _term(client, token)
    course = await _course(client, token, title_fa="مهندسی ترافیک")

    # همهٔ ردیف‌های فیکسچر یک `created_at` دارند (زمان تراکنش)؛ پس با نوع جدا می‌شوند.
    async def notices(user_id: str, kind: str = "OFFERING_ASSIGNED") -> list[Any]:
        return list(
            await db_session.scalars(
                select(Notification).where(
                    Notification.user_id == uuid.UUID(user_id), Notification.kind == kind
                )
            )
        )

    offering = (
        await _offering(
            client, token, course_id=course["id"], term_id=term["id"], instructor_id=first_id
        )
    ).json()
    [assigned] = await notices(first_id)
    assert assigned.action_url == f"/teach/offerings/{offering['id']}"
    assert assigned.priority == "IMPORTANT"
    assert "«مهندسی ترافیک»" in assigned.title
    assert "نیم‌سال اول ۱۴۰۵" in assigned.body
    assert "خارج و دوباره وارد شو" in assigned.body

    response = await client.patch(
        f"/api/v1/admin/offerings/{offering['id']}",
        headers=auth(token),
        json={"term_id": other_term["id"]},
    )
    assert response.status_code == 200, response.text
    assert len(await notices(first_id)) == 1

    response = await client.patch(
        f"/api/v1/admin/offerings/{offering['id']}",
        headers=auth(token),
        json={"instructor_id": second_id},
    )
    assert response.status_code == 200, response.text
    [reassigned] = await notices(first_id, "OFFERING_REASSIGNED")
    assert reassigned.data == {"offering_id": offering["id"]}
    assert "دسترسی تو به آن بسته شد" in reassigned.body
    assert len(await notices(second_id)) == 1
    assert await notices(second_id, "OFFERING_REASSIGNED") == []

    # بازگرداندن به استاد اول: اعلان تازه، نه حذف تکراری.
    response = await client.patch(
        f"/api/v1/admin/offerings/{offering['id']}",
        headers=auth(token),
        json={"instructor_id": first_id},
    )
    assert response.status_code == 200, response.text
    assert len(await notices(first_id)) == 2
    assert len(await notices(second_id, "OFFERING_REASSIGNED")) == 1

    # مدیری که ارائه را به خودش می‌سپارد اعلان نمی‌گیرد.
    response = await _offering(
        client, token, course_id=course["id"], term_id=term["id"], instructor_id=coordinator_id
    )
    assert response.status_code == 201, response.text
    assert await notices(coordinator_id) == []


async def test_only_unused_offerings_are_deleted(client: Any, db_session: Any) -> None:
    from silp.core.permissions import Role, ScopeType
    from silp.models.education import CourseWeek, Enrollment
    from silp.models.identity import UserRole
    from silp.services import authz

    token = await _coordinator(client, db_session)
    _, instructor_id = await _user(client, INSTRUCTOR_MOBILE)
    ta_token, ta_id = await _user(client, TA_MOBILE)
    term = await _term(client, token)
    course = await _course(client, token)
    offering = (
        await _offering(
            client, token, course_id=course["id"], term_id=term["id"], instructor_id=instructor_id
        )
    ).json()
    offering_id = uuid.UUID(offering["id"])
    db_session.add(CourseWeek(offering_id=offering_id, week_number=1, title_fa="مقدمه"))
    await authz.grant_role(
        db_session,
        user_id=uuid.UUID(ta_id),
        role=Role.TA,
        scope_type=ScopeType.OFFERING,
        scope_id=offering_id,
    )
    await db_session.flush()
    await authz.invalidate_roles(uuid.UUID(ta_id))

    _, student_id = await _user(client, STUDENT_MOBILE)
    enrollment = Enrollment(
        offering_id=offering_id, student_id=uuid.UUID(student_id), status="DROPPED"
    )
    db_session.add(enrollment)
    await db_session.flush()

    response = await client.delete(f"/api/v1/admin/offerings/{offering_id}", headers=auth(token))
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "OFFERING_IN_USE"
    assert response.json()["error"]["details"] == {"enrollments": 1}

    await db_session.delete(enrollment)
    await db_session.flush()
    response = await client.delete(f"/api/v1/admin/offerings/{offering_id}", headers=auth(token))
    assert response.status_code == 204, response.text

    weeks = await db_session.scalar(
        select(func.count()).where(CourseWeek.offering_id == offering_id)
    )
    grants = await db_session.scalar(select(func.count()).where(UserRole.scope_id == offering_id))
    assert (weeks, grants) == (0, 0)
    response = await client.get("/api/v1/teach/offerings", headers=auth(ta_token))
    assert offering["id"] not in [o["id"] for o in response.json()]


async def test_instructor_candidates_are_masked_for_a_coordinator(
    client: Any, db_session: Any
) -> None:
    token = await _coordinator(client, db_session)
    _, instructor_id = await _user(client, INSTRUCTOR_MOBILE)

    response = await client.get(
        "/api/v1/admin/instructor-candidates?q=22200002", headers=auth(token)
    )
    assert response.status_code == 200, response.text
    found = [c for c in response.json() if c["id"] == instructor_id]
    assert len(found) == 1
    assert found[0]["mobile"] == "0912***0002"
    assert found[0]["active_offerings"] == 0

    response = await client.get("/api/v1/admin/instructor-candidates?q=a", headers=auth(token))
    assert response.status_code == 422
