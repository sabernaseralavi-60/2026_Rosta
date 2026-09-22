"""چرخهٔ کامل آموزش — از ساخت ارائه تا دروازهٔ اشتراک.

مرجع: FR-EDU-01 تا FR-EDU-06، ADR-0008، ADR-0009.

این تست‌ها روی PostgreSQL واقعی اجرا می‌شوند و در نبودش رد می‌شوند
(نه شکست). چیزی که هیچ تست واحدی نمی‌تواند نشان دهد و اینجا نشان داده
می‌شود: قیدهای پایگاه‌داده، فیلتر سطح کوئری، و اینکه ۴۰۲ واقعاً از
مسیر HTTP بیرون می‌آید.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Any

import pytest
from tests.integration.helpers import auth, grant_role, invalidate, login, me

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

INSTRUCTOR_MOBILE = "09121110001"
STUDENT_MOBILE = "09121110002"
OUTSIDER_MOBILE = "09121110003"
SUPPORT_MOBILE = "09121110004"


# ── ساخت صحنه ──────────────────────────────────────────────────────────
async def _term(session: Any) -> Any:
    from silp.models.education import Term

    term = Term(
        code=f"T-{uuid.uuid4().hex[:8]}",
        title_fa="نیم‌سال آزمایشی",
        starts_on=date(2026, 9, 23),
        ends_on=date(2027, 2, 4),
    )
    session.add(term)
    await session.flush()
    return term


async def _course(session: Any, *, tier: str = "SUBSCRIBER") -> Any:
    from silp.models.education import Course

    marker = uuid.uuid4().hex[:8]
    course = Course(
        code=f"C-{marker}",
        slug=f"course-{marker}",
        title_fa="تحلیل و مدل‌سازی ایمنی راه",
        description="درس آزمایشی.",
        degree_level="MASTER",
        is_public=True,
        default_access_tier=tier,
    )
    session.add(course)
    await session.flush()
    return course


async def _material(session: Any, course: Any, *, tier: str, title: str = "کتاب درس") -> Any:
    """مادهٔ کتابخانه با نشانی بیرونی — فایل واقعی برای این تست‌ها لازم نیست."""
    from silp.models.education import CourseMaterial

    material = CourseMaterial(
        course_id=course.id,
        kind="BOOK",
        title_fa=title,
        external_url="https://example.invalid/book.pdf",
        access_tier=tier,
    )
    session.add(material)
    await session.flush()
    return material


async def _offering(
    session: Any, course: Any, term: Any, instructor_id: uuid.UUID, **kw: Any
) -> Any:
    """ارائه + ابطال کش نقش استاد.

    نقش `INSTRUCTOR` این ارائه از `course_offerings.instructor_id` مشتق
    می‌شود (§6.1) و کش نقش ۶۰ ثانیه عمر دارد. بدون ابطال، تستی که
    پیش از ساخت ارائه وارد شده، با اعطاهای کهنه کار می‌کند.
    """
    from silp.models.education import CourseOffering

    offering = CourseOffering(
        course_id=course.id,
        term_id=term.id,
        instructor_id=instructor_id,
        status=kw.get("status", "OPEN"),
        capacity=kw.get("capacity"),
        enrollment_code=kw.get("enrollment_code"),
        requires_approval=kw.get("requires_approval", False),
    )
    session.add(offering)
    await session.flush()
    await invalidate(instructor_id)
    return offering


async def _scene(client: Any, db_session: Any, **offering_kw: Any) -> dict[str, Any]:
    """استاد + درس + ارائه + دانشجو، آمادهٔ استفاده."""
    instructor_token = await login(client, INSTRUCTOR_MOBILE)
    instructor = await me(client, instructor_token)
    await grant_role(db_session, instructor["id"], "INSTRUCTOR")
    instructor_token = await login(client, INSTRUCTOR_MOBILE)

    student_token = await login(client, STUDENT_MOBILE)
    student = await me(client, student_token)

    term = await _term(db_session)
    course = await _course(db_session)
    offering = await _offering(db_session, course, term, uuid.UUID(instructor["id"]), **offering_kw)
    return {
        "instructor_token": instructor_token,
        "instructor_id": instructor["id"],
        "student_token": student_token,
        "student_id": student["id"],
        "term": term,
        "course": course,
        "offering": offering,
    }


# ── ویترین ─────────────────────────────────────────────────────────────
async def test_course_catalog_is_open_to_guests(client: Any, db_session: Any) -> None:
    course = await _course(db_session)
    response = await client.get("/api/v1/courses")
    assert response.status_code == 200, response.text
    slugs = [item["slug"] for item in response.json()["items"]]
    assert course.slug in slugs


async def test_guest_sees_locked_material_but_not_its_link(client: Any, db_session: Any) -> None:
    """ماده پنهان نمی‌شود؛ فقط لینکش بسته است — ADR-0009."""
    course = await _course(db_session)
    await _material(db_session, course, tier="SUBSCRIBER")

    response = await client.get(f"/api/v1/courses/{course.slug}")
    assert response.status_code == 200, response.text
    material = response.json()["materials"][0]

    assert material["title_fa"] == "کتاب درس"
    assert material["access"]["allowed"] is False
    assert material["access"]["blocker"] == "SUBSCRIPTION"
    assert material["external_url"] is None
    assert "اشتراک" in material["access"]["note_fa"]


async def test_public_material_is_open_to_guests(client: Any, db_session: Any) -> None:
    course = await _course(db_session)
    await _material(db_session, course, tier="PUBLIC", title="پادکست رایگان")

    response = await client.get(f"/api/v1/courses/{course.slug}")
    material = response.json()["materials"][0]
    assert material["access"]["allowed"] is True
    assert material["access"]["reason"] == "PUBLIC"
    assert material["external_url"] is not None


# ── ثبت‌نام — §7.2 ─────────────────────────────────────────────────────
async def test_student_enrolls_and_sees_the_class(client: Any, db_session: Any) -> None:
    scene = await _scene(client, db_session)
    offering_id = scene["offering"].id

    response = await client.post(
        f"/api/v1/offerings/{offering_id}/enroll",
        headers=auth(scene["student_token"]),
        json={},
    )
    assert response.status_code == 201, response.text
    assert response.json()["status"] == "ACTIVE"

    response = await client.get(
        f"/api/v1/offerings/{offering_id}", headers=auth(scene["student_token"])
    )
    assert response.status_code == 200, response.text
    assert response.json()["my_status"] == "ACTIVE"


async def test_enrollment_code_is_enforced(client: Any, db_session: Any) -> None:
    scene = await _scene(client, db_session, enrollment_code="RSA1405")
    offering_id = scene["offering"].id

    response = await client.post(
        f"/api/v1/offerings/{offering_id}/enroll",
        headers=auth(scene["student_token"]),
        json={"enrollment_code": "WRONG"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ENROLLMENT_CODE_INVALID"

    response = await client.post(
        f"/api/v1/offerings/{offering_id}/enroll",
        headers=auth(scene["student_token"]),
        json={"enrollment_code": "rsa1405"},  # حروف کوچک هم قبول است
    )
    assert response.status_code == 201, response.text


async def test_double_enrollment_is_rejected(client: Any, db_session: Any) -> None:
    scene = await _scene(client, db_session)
    offering_id = scene["offering"].id
    headers = auth(scene["student_token"])

    assert (
        await client.post(f"/api/v1/offerings/{offering_id}/enroll", headers=headers, json={})
    ).status_code == 201
    response = await client.post(
        f"/api/v1/offerings/{offering_id}/enroll", headers=headers, json={}
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ALREADY_ENROLLED"


async def test_capacity_is_enforced(client: Any, db_session: Any) -> None:
    scene = await _scene(client, db_session, capacity=1)
    offering_id = scene["offering"].id

    assert (
        await client.post(
            f"/api/v1/offerings/{offering_id}/enroll",
            headers=auth(scene["student_token"]),
            json={},
        )
    ).status_code == 201

    outsider_token = await login(client, OUTSIDER_MOBILE)
    response = await client.post(
        f"/api/v1/offerings/{offering_id}/enroll", headers=auth(outsider_token), json={}
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "OFFERING_FULL"


async def test_approval_flow_holds_the_student_pending(client: Any, db_session: Any) -> None:
    scene = await _scene(client, db_session, requires_approval=True)
    offering_id = scene["offering"].id

    response = await client.post(
        f"/api/v1/offerings/{offering_id}/enroll",
        headers=auth(scene["student_token"]),
        json={},
    )
    assert response.json()["status"] == "PENDING"
    enrollment_id = response.json()["id"]

    response = await client.post(
        f"/api/v1/teach/enrollments/{enrollment_id}/decide",
        headers=auth(scene["instructor_token"]),
        json={"approve": True},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "ACTIVE"


async def test_outsider_cannot_open_the_class(client: Any, db_session: Any) -> None:
    scene = await _scene(client, db_session)
    outsider_token = await login(client, OUTSIDER_MOBILE)
    response = await client.get(
        f"/api/v1/offerings/{scene['offering'].id}", headers=auth(outsider_token)
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "NOT_ENROLLED"


# ── هفته و انتشار — FR-EDU-02 ──────────────────────────────────────────
async def test_draft_week_is_invisible_to_students(client: Any, db_session: Any) -> None:
    """فیلتر در سطح کوئری — §6.4 قاعدهٔ ۳."""
    scene = await _scene(client, db_session)
    offering_id = scene["offering"].id
    await client.post(
        f"/api/v1/offerings/{offering_id}/enroll",
        headers=auth(scene["student_token"]),
        json={},
    )

    response = await client.put(
        f"/api/v1/teach/offerings/{offering_id}/weeks",
        headers=auth(scene["instructor_token"]),
        json={"week_number": 1, "title_fa": "مفاهیم ایمنی راه", "objectives": ["الف"]},
    )
    assert response.status_code == 200, response.text
    week_id = response.json()["id"]
    assert response.json()["status"] == "DRAFT"

    response = await client.get(
        f"/api/v1/offerings/{offering_id}/weeks", headers=auth(scene["student_token"])
    )
    assert response.json() == []

    response = await client.get(
        f"/api/v1/offerings/{offering_id}/weeks/1", headers=auth(scene["student_token"])
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "WEEK_NOT_PUBLISHED"

    # استاد همان هفته را می‌بیند.
    response = await client.get(
        f"/api/v1/offerings/{offering_id}/weeks", headers=auth(scene["instructor_token"])
    )
    assert [w["id"] for w in response.json()] == [week_id]


async def test_published_week_reaches_the_student(client: Any, db_session: Any) -> None:
    scene = await _scene(client, db_session)
    offering_id = scene["offering"].id
    await client.post(
        f"/api/v1/offerings/{offering_id}/enroll",
        headers=auth(scene["student_token"]),
        json={},
    )
    response = await client.put(
        f"/api/v1/teach/offerings/{offering_id}/weeks",
        headers=auth(scene["instructor_token"]),
        json={"week_number": 1, "title_fa": "مفاهیم ایمنی راه"},
    )
    week_id = response.json()["id"]

    response = await client.post(
        f"/api/v1/teach/weeks/{week_id}/publish",
        headers=auth(scene["instructor_token"]),
        json={},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "PUBLISHED"

    response = await client.get(
        f"/api/v1/offerings/{offering_id}/weeks/1", headers=auth(scene["student_token"])
    )
    assert response.status_code == 200, response.text
    assert response.json()["title_fa"] == "مفاهیم ایمنی راه"


async def test_scheduled_publish_keeps_the_week_draft(client: Any, db_session: Any) -> None:
    from datetime import UTC, datetime

    scene = await _scene(client, db_session)
    offering_id = scene["offering"].id
    response = await client.put(
        f"/api/v1/teach/offerings/{offering_id}/weeks",
        headers=auth(scene["instructor_token"]),
        json={"week_number": 2, "title_fa": "هفتهٔ دوم"},
    )
    week_id = response.json()["id"]

    future = (datetime.now(UTC) + timedelta(days=7)).isoformat()
    response = await client.post(
        f"/api/v1/teach/weeks/{week_id}/publish",
        headers=auth(scene["instructor_token"]),
        json={"publish_at": future},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "DRAFT"
    assert response.json()["publish_at"] is not None


async def test_instructor_of_another_offering_cannot_write(client: Any, db_session: Any) -> None:
    """قلمرو مجوز — §6.4. استاد ارائهٔ الف روی ارائهٔ ب بی‌اختیار است."""
    scene = await _scene(client, db_session)
    other_token = await login(client, OUTSIDER_MOBILE)
    other = await me(client, other_token)
    await grant_role(db_session, other["id"], "INSTRUCTOR")
    other_token = await login(client, OUTSIDER_MOBILE)

    response = await client.put(
        f"/api/v1/teach/offerings/{scene['offering'].id}/weeks",
        headers=auth(other_token),
        json={"week_number": 1, "title_fa": "نفوذ"},
    )
    assert response.status_code == 403


# ── دروازهٔ اشتراک — ADR-0009 ──────────────────────────────────────────
async def test_enrolled_student_downloads_course_material_free(
    client: Any, db_session: Any
) -> None:
    """قاعدهٔ اصلی محصول، از راه HTTP."""
    scene = await _scene(client, db_session)
    material = await _material(db_session, scene["course"], tier="SUBSCRIBER")
    await client.post(
        f"/api/v1/offerings/{scene['offering'].id}/enroll",
        headers=auth(scene["student_token"]),
        json={},
    )

    response = await client.get(
        f"/api/v1/courses/{scene['course'].slug}", headers=auth(scene["student_token"])
    )
    entry = next(m for m in response.json()["materials"] if m["id"] == str(material.id))
    assert entry["access"]["allowed"] is True
    assert entry["access"]["reason"] == "ENROLLED"


async def test_non_student_download_is_402(client: Any, db_session: Any) -> None:
    scene = await _scene(client, db_session)
    material = await _material(db_session, scene["course"], tier="SUBSCRIBER")

    response = await client.get(
        f"/api/v1/materials/{material.id}/download", headers=auth(scene["student_token"])
    )
    assert response.status_code == 402, response.text
    body = response.json()["error"]
    assert body["code"] == "SUBSCRIPTION_REQUIRED"
    assert body["details"]["course_slug"] == scene["course"].slug


async def test_subscription_opens_the_library(client: Any, db_session: Any) -> None:
    from silp.models.access import SubscriptionPlan
    from silp.services.subscription_service import SubscriptionService

    scene = await _scene(client, db_session)
    material = await _material(db_session, scene["course"], tier="SUBSCRIBER")

    plan = SubscriptionPlan(
        code=f"P-{uuid.uuid4().hex[:8]}",
        title_fa="ماهانه",
        scope="ALL_COURSES",
        duration_days=30,
        price_irr=1_990_000,
    )
    db_session.add(plan)
    await db_session.flush()

    support_token = await login(client, SUPPORT_MOBILE)
    support = await me(client, support_token)
    await SubscriptionService(db_session).grant(
        user_id=uuid.UUID(scene["student_id"]),
        plan_id=plan.id,
        granted_by=uuid.UUID(support["id"]),
        payment_ref="فیش ۱۲۳",
    )

    response = await client.get(
        f"/api/v1/courses/{scene['course'].slug}", headers=auth(scene["student_token"])
    )
    entry = next(m for m in response.json()["materials"] if m["id"] == str(material.id))
    assert entry["access"]["allowed"] is True
    assert entry["access"]["reason"] == "SUBSCRIPTION"


async def test_subscription_does_not_open_enrolled_only_material(
    client: Any, db_session: Any
) -> None:
    """بانک سؤال فروختنی نیست — ۴۰۳، نه ۴۰۲."""
    from silp.models.access import SubscriptionPlan
    from silp.services.subscription_service import SubscriptionService

    scene = await _scene(client, db_session)
    material = await _material(db_session, scene["course"], tier="ENROLLED", title="بانک سؤال")

    plan = SubscriptionPlan(
        code=f"P-{uuid.uuid4().hex[:8]}",
        title_fa="ماهانه",
        scope="ALL_COURSES",
        duration_days=30,
        price_irr=1_990_000,
    )
    db_session.add(plan)
    await db_session.flush()
    support_token = await login(client, SUPPORT_MOBILE)
    support = await me(client, support_token)
    await SubscriptionService(db_session).grant(
        user_id=uuid.UUID(scene["student_id"]),
        plan_id=plan.id,
        granted_by=uuid.UUID(support["id"]),
    )

    response = await client.get(
        f"/api/v1/materials/{material.id}/download", headers=auth(scene["student_token"])
    )
    assert response.status_code == 403, response.text
    assert response.json()["error"]["code"] == "ENROLLMENT_REQUIRED"


async def test_single_course_subscription_does_not_leak_to_other_courses(
    client: Any, db_session: Any
) -> None:
    from silp.models.access import SubscriptionPlan
    from silp.services.subscription_service import SubscriptionService

    scene = await _scene(client, db_session)
    other_course = await _course(db_session)
    other_material = await _material(db_session, other_course, tier="SUBSCRIBER")

    plan = SubscriptionPlan(
        code=f"P-{uuid.uuid4().hex[:8]}",
        title_fa="ماهانهٔ یک درس",
        scope="SINGLE_COURSE",
        duration_days=30,
        price_irr=890_000,
    )
    db_session.add(plan)
    await db_session.flush()
    support_token = await login(client, SUPPORT_MOBILE)
    support = await me(client, support_token)
    await SubscriptionService(db_session).grant(
        user_id=uuid.UUID(scene["student_id"]),
        plan_id=plan.id,
        granted_by=uuid.UUID(support["id"]),
        course_id=scene["course"].id,
    )

    response = await client.get(
        f"/api/v1/materials/{other_material.id}/download",
        headers=auth(scene["student_token"]),
    )
    assert response.status_code == 402


async def test_plans_are_public(client: Any, db_session: Any) -> None:
    from silp.models.access import SubscriptionPlan

    db_session.add(
        SubscriptionPlan(
            code=f"P-{uuid.uuid4().hex[:8]}",
            title_fa="ماهانه",
            scope="ALL_COURSES",
            duration_days=30,
            price_irr=1_990_000,
        )
    )
    await db_session.flush()

    response = await client.get("/api/v1/subscriptions/plans")
    assert response.status_code == 200, response.text
    assert any(p["price_fa"].endswith("تومان") for p in response.json())


# ── کتابخانه ← هفته (ADR-0008) ─────────────────────────────────────────
async def test_library_material_shows_up_inside_the_week(client: Any, db_session: Any) -> None:
    scene = await _scene(client, db_session)
    material = await _material(db_session, scene["course"], tier="SUBSCRIBER")
    offering_id = scene["offering"].id
    await client.post(
        f"/api/v1/offerings/{offering_id}/enroll",
        headers=auth(scene["student_token"]),
        json={},
    )

    response = await client.put(
        f"/api/v1/teach/offerings/{offering_id}/weeks",
        headers=auth(scene["instructor_token"]),
        json={"week_number": 3, "title_fa": "هفتهٔ سوم"},
    )
    week_id = response.json()["id"]
    response = await client.post(
        f"/api/v1/teach/offerings/{offering_id}/weeks/{week_id}/materials",
        headers=auth(scene["instructor_token"]),
        json={"material_id": str(material.id), "section": "فصل ۲ تا ۴"},
    )
    assert response.status_code == 204, response.text
    await client.post(
        f"/api/v1/teach/weeks/{week_id}/publish",
        headers=auth(scene["instructor_token"]),
        json={},
    )

    response = await client.get(
        f"/api/v1/offerings/{offering_id}/weeks/3", headers=auth(scene["student_token"])
    )
    assert response.status_code == 200, response.text
    materials = response.json()["materials"]
    assert len(materials) == 1
    assert materials[0]["section"] == "فصل ۲ تا ۴"
    assert materials[0]["access"]["allowed"] is True


async def test_material_of_another_course_cannot_be_linked(client: Any, db_session: Any) -> None:
    scene = await _scene(client, db_session)
    other_course = await _course(db_session)
    foreign = await _material(db_session, other_course, tier="PUBLIC")
    offering_id = scene["offering"].id

    response = await client.put(
        f"/api/v1/teach/offerings/{offering_id}/weeks",
        headers=auth(scene["instructor_token"]),
        json={"week_number": 4, "title_fa": "هفتهٔ چهارم"},
    )
    week_id = response.json()["id"]
    response = await client.post(
        f"/api/v1/teach/offerings/{offering_id}/weeks/{week_id}/materials",
        headers=auth(scene["instructor_token"]),
        json={"material_id": str(foreign.id)},
    )
    assert response.status_code == 422


# ── کپی از ارائهٔ قبلی — FR-EDU-01 ─────────────────────────────────────
async def test_copy_content_brings_weeks_as_drafts(client: Any, db_session: Any) -> None:
    scene = await _scene(client, db_session)
    source_id = scene["offering"].id
    for number in (1, 2):
        response = await client.put(
            f"/api/v1/teach/offerings/{source_id}/weeks",
            headers=auth(scene["instructor_token"]),
            json={"week_number": number, "title_fa": f"هفتهٔ {number}"},
        )
        await client.post(
            f"/api/v1/teach/weeks/{response.json()['id']}/publish",
            headers=auth(scene["instructor_token"]),
            json={},
        )

    next_term = await _term(db_session)
    target = await _offering(
        db_session,
        scene["course"],
        next_term,
        uuid.UUID(scene["instructor_id"]),
    )

    response = await client.post(
        f"/api/v1/teach/offerings/{target.id}/copy-content",
        headers=auth(scene["instructor_token"]),
        json={"source_offering_id": str(source_id)},
    )
    assert response.status_code == 200, response.text
    assert response.json()["weeks_copied"] == 2

    response = await client.get(
        f"/api/v1/teach/offerings/{target.id}/weeks"
        if False
        else f"/api/v1/offerings/{target.id}/weeks",
        headers=auth(scene["instructor_token"]),
    )
    # محتوای نیم‌سال گذشته روز اول ترم تازه منتشر نمی‌شود.
    assert all(week["status"] == "DRAFT" for week in response.json())


# ── پیشرفت مطالعه — FR-EDU-04 ──────────────────────────────────────────
async def test_video_completes_itself_at_ninety_percent(client: Any, db_session: Any) -> None:
    scene = await _scene(client, db_session)
    offering_id = scene["offering"].id
    await client.post(
        f"/api/v1/offerings/{offering_id}/enroll",
        headers=auth(scene["student_token"]),
        json={},
    )
    response = await client.put(
        f"/api/v1/teach/offerings/{offering_id}/weeks",
        headers=auth(scene["instructor_token"]),
        json={"week_number": 5, "title_fa": "هفتهٔ پنجم"},
    )
    week_id = response.json()["id"]
    response = await client.post(
        f"/api/v1/teach/offerings/{offering_id}/weeks/{week_id}/resources",
        headers=auth(scene["instructor_token"]),
        json={
            "kind": "VIDEO",
            "title_fa": "ویدئوی جلسه",
            "external_url": "https://example.invalid/v.mp4",
            "duration_sec": 600,
        },
    )
    assert response.status_code == 201, response.text
    resource_id = response.json()["id"]
    await client.post(
        f"/api/v1/teach/weeks/{week_id}/publish",
        headers=auth(scene["instructor_token"]),
        json={},
    )

    headers = auth(scene["student_token"])
    response = await client.post(
        f"/api/v1/resources/{resource_id}/progress",
        headers=headers,
        json={"percent": 40, "position_sec": 240},
    )
    assert response.json()["status"] == "IN_PROGRESS"

    response = await client.post(
        f"/api/v1/resources/{resource_id}/progress",
        headers=headers,
        json={"percent": 92, "position_sec": 552},
    )
    assert response.json()["status"] == "COMPLETED"

    # پیشرفت پس نمی‌رود.
    response = await client.post(
        f"/api/v1/resources/{resource_id}/progress", headers=headers, json={"percent": 5}
    )
    assert response.json()["status"] == "COMPLETED"


async def test_outsider_cannot_touch_a_week_resource(client: Any, db_session: Any) -> None:
    scene = await _scene(client, db_session)
    offering_id = scene["offering"].id
    response = await client.put(
        f"/api/v1/teach/offerings/{offering_id}/weeks",
        headers=auth(scene["instructor_token"]),
        json={"week_number": 6, "title_fa": "هفتهٔ ششم"},
    )
    week_id = response.json()["id"]
    response = await client.post(
        f"/api/v1/teach/offerings/{offering_id}/weeks/{week_id}/resources",
        headers=auth(scene["instructor_token"]),
        json={
            "kind": "PDF",
            "title_fa": "جزوه",
            "external_url": "https://example.invalid/n.pdf",
        },
    )
    resource_id = response.json()["id"]

    outsider_token = await login(client, OUTSIDER_MOBILE)
    response = await client.post(
        f"/api/v1/resources/{resource_id}/progress", headers=auth(outsider_token), json={}
    )
    assert response.status_code == 404


# ── اعلان و حضور ───────────────────────────────────────────────────────
async def test_announcement_reaches_enrolled_students(client: Any, db_session: Any) -> None:
    scene = await _scene(client, db_session)
    offering_id = scene["offering"].id
    await client.post(
        f"/api/v1/offerings/{offering_id}/enroll",
        headers=auth(scene["student_token"]),
        json={},
    )
    response = await client.post(
        f"/api/v1/teach/offerings/{offering_id}/announcements",
        headers=auth(scene["instructor_token"]),
        json={"title": "جلسهٔ جبرانی", "body": "پنج‌شنبه ساعت ۱۰.", "priority": "IMPORTANT"},
    )
    assert response.status_code == 201, response.text

    response = await client.get(
        f"/api/v1/offerings/{offering_id}/announcements",
        headers=auth(scene["student_token"]),
    )
    assert [a["title"] for a in response.json()] == ["جلسهٔ جبرانی"]


async def test_attendance_rejects_students_outside_the_class(client: Any, db_session: Any) -> None:
    scene = await _scene(client, db_session)
    outsider_token = await login(client, OUTSIDER_MOBILE)
    outsider = await me(client, outsider_token)

    response = await client.post(
        f"/api/v1/teach/offerings/{scene['offering'].id}/attendance",
        headers=auth(scene["instructor_token"]),
        json={
            "held_on": "2026-10-05",
            "entries": [{"student_id": outsider["id"], "status": "PRESENT"}],
        },
    )
    assert response.status_code == 422


async def test_attendance_is_recorded_and_correctable(client: Any, db_session: Any) -> None:
    scene = await _scene(client, db_session)
    offering_id = scene["offering"].id
    await client.post(
        f"/api/v1/offerings/{offering_id}/enroll",
        headers=auth(scene["student_token"]),
        json={},
    )
    body = {
        "held_on": "2026-10-05",
        "week_number": 2,
        "entries": [{"student_id": scene["student_id"], "status": "ABSENT"}],
    }
    response = await client.post(
        f"/api/v1/teach/offerings/{offering_id}/attendance",
        headers=auth(scene["instructor_token"]),
        json=body,
    )
    assert response.status_code == 200, response.text
    assert response.json()["recorded"] == 1

    # ثبت دوبارهٔ همان روز اصلاح است، نه جلسهٔ دوم.
    body["entries"][0]["status"] = "PRESENT"
    response = await client.post(
        f"/api/v1/teach/offerings/{offering_id}/attendance",
        headers=auth(scene["instructor_token"]),
        json=body,
    )
    assert response.status_code == 200, response.text


# ── نمره ───────────────────────────────────────────────────────────────
async def test_grading_policy_must_sum_to_hundred(client: Any, db_session: Any) -> None:
    scene = await _scene(client, db_session)
    response = await client.put(
        f"/api/v1/teach/offerings/{scene['offering'].id}/grading-policy",
        headers=auth(scene["instructor_token"]),
        json={"quiz": 30, "project": 30, "attendance": 10, "participation": 10},
    )
    assert response.status_code == 422
    assert "۱۰۰" in response.json()["error"]["message"]


async def test_final_grade_completes_the_enrollment(client: Any, db_session: Any) -> None:
    """درس تمام‌شده دسترسی رایگان به کتابخانه را نگه می‌دارد — ADR-0009."""
    scene = await _scene(client, db_session)
    material = await _material(db_session, scene["course"], tier="SUBSCRIBER")
    response = await client.post(
        f"/api/v1/offerings/{scene['offering'].id}/enroll",
        headers=auth(scene["student_token"]),
        json={},
    )
    enrollment_id = response.json()["id"]

    response = await client.patch(
        f"/api/v1/teach/enrollments/{enrollment_id}/grade",
        headers=auth(scene["instructor_token"]),
        json={"grade": 18.5},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "COMPLETED"

    response = await client.get(
        f"/api/v1/courses/{scene['course'].slug}", headers=auth(scene["student_token"])
    )
    entry = next(m for m in response.json()["materials"] if m["id"] == str(material.id))
    assert entry["access"]["allowed"] is True
    assert entry["access"]["reason"] == "ENROLLED"
