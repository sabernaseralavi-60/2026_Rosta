"""پروژه‌های تحت نظارت و صف واحد بررسی — §3.5، ADR-0022.

سه چیز باید با هم راست باشد و هر سه اینجا آزموده می‌شود:

۱. **پل مجوز** — استادِ ارائه تحویل پروژهٔ همان ارائه را بررسی می‌کند، بدون
   نقش سراسری؛ استادِ ارائهٔ دیگر و هر بیرونی نه.
۲. **پیوند** — پروژه فقط با `OFFERING_MANAGE` به ارائه می‌چسبد.
۳. **صف و فهرست** — همان مجموعه‌ای را می‌بینند که داشبورد می‌شمارد.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

import pytest
from tests.integration.helpers import (
    auth,
    complete_profile,
    invalidate,
    login,
    me,
    milestone_payload,
    project_payload,
    taxonomy_ids,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

INSTRUCTOR_MOBILE = "09122250001"
OTHER_INSTRUCTOR_MOBILE = "09122250002"
STUDENT_MOBILE = "09122250003"
SECOND_STUDENT_MOBILE = "09122250004"
OUTSIDER_MOBILE = "09122250005"


async def _offering(client: Any, session: Any, mobile: str) -> dict[str, Any]:
    """استادِ رسمی یک ارائه — **بدون** نقش سراسری `INSTRUCTOR`.

    نبودِ اعطای سراسری عمدی است: تنها همین حالت پل مجوز را می‌آزماید.
    """
    from silp.models.education import Course, CourseOffering, Term

    token = await login(client, mobile)
    await complete_profile(client, token, first_name="استاد")
    instructor = await me(client, token)

    marker = uuid.uuid4().hex[:8]
    term = Term(
        code=f"T-{marker}",
        title_fa="نیم‌سال آزمایشی",
        starts_on=date(2026, 9, 23),
        ends_on=date(2027, 2, 4),
    )
    course = Course(code=f"C-{marker}", slug=f"course-{marker}", title_fa="برنامه‌ریزی حمل‌ونقل")
    session.add_all([term, course])
    await session.flush()
    offering = CourseOffering(
        course_id=course.id,
        term_id=term.id,
        instructor_id=uuid.UUID(instructor["id"]),
        status="OPEN",
        enrollment_code=f"E-{marker}",
    )
    session.add(offering)
    await session.flush()
    await invalidate(instructor["id"])
    return {
        "token": await login(client, mobile),
        "id": instructor["id"],
        "offering": offering,
    }


async def _student_project(
    client: Any, session: Any, offering_id: uuid.UUID | None, *, mobile: str = STUDENT_MOBILE
) -> dict[str, Any]:
    """پروژهٔ دانشجویی در جریان، با یک تحویل منتظر بررسی.

    پیوند به ارائه مستقیم در دیتابیس زده می‌شود: دانشجو (`D_PERSONAL`) خودش
    نمی‌تواند پروژه را به ارائه بچسباند — همین قاعده در تست پیوند سنجیده می‌شود.
    """
    from silp.models.project import Project

    token = await login(client, mobile)
    await complete_profile(client, token, first_name="مینا")
    skills = await taxonomy_ids(client, "skills", limit=1)
    created = await client.post(
        "/api/v1/projects",
        headers=auth(token),
        json=project_payload(
            required_skills=[{"skill_id": skills[0], "min_level": 3}], team_size_max=3
        ),
    )
    assert created.status_code == 201, created.text
    project_id = created.json()["id"]
    milestone = await client.post(
        f"/api/v1/projects/{project_id}/milestones",
        headers=auth(token),
        json=milestone_payload(),
    )
    assert milestone.status_code == 201, milestone.text
    assert (
        await client.post(f"/api/v1/projects/{project_id}/publish", headers=auth(token))
    ).status_code == 200
    assert (
        await client.post(f"/api/v1/projects/{project_id}/start", headers=auth(token))
    ).status_code == 200
    submitted = await client.post(
        f"/api/v1/milestones/{milestone.json()['id']}/deliverables",
        headers=auth(token),
        json={"body": "گزارش ده مصاحبه"},
    )
    assert submitted.status_code == 201, submitted.text

    if offering_id is not None:
        row = await session.get(Project, uuid.UUID(project_id))
        row.offering_id = offering_id
        await session.flush()
    return {
        "token": token,
        "project_id": project_id,
        "milestone_id": milestone.json()["id"],
        "deliverable_id": submitted.json()["id"],
    }


# ── ۱. پل مجوز ─────────────────────────────────────────────────────────
async def test_instructor_reviews_a_project_of_their_own_offering(
    client: Any, db_session: Any
) -> None:
    """پیش از ADR-0022 این ۴۰۳ بود: نقش استاد قلمرو ارائه دارد و مجوز بررسی، پروژه."""
    teacher = await _offering(client, db_session, INSTRUCTOR_MOBILE)
    scene = await _student_project(client, db_session, teacher["offering"].id)
    await invalidate(teacher["id"])

    response = await client.post(
        f"/api/v1/deliverables/{scene['deliverable_id']}/review",
        headers=auth(teacher["token"]),
        json={"decision": "APPROVED", "score": 40, "feedback": "خوب بود."},
    )
    assert response.status_code == 200, response.text
    assert response.json()["deliverable"]["status"] == "APPROVED"


async def test_the_bridge_stops_at_the_offering_boundary(client: Any, db_session: Any) -> None:
    """استادِ ارائهٔ دیگر و نقش‌بی‌قلمرو، همان پروژه را نمی‌بینند."""
    teacher = await _offering(client, db_session, INSTRUCTOR_MOBILE)
    other = await _offering(client, db_session, OTHER_INSTRUCTOR_MOBILE)
    scene = await _student_project(client, db_session, teacher["offering"].id)
    outsider_token = await login(client, OUTSIDER_MOBILE)
    await invalidate(teacher["id"])
    await invalidate(other["id"])

    for token in (other["token"], outsider_token):
        response = await client.post(
            f"/api/v1/deliverables/{scene['deliverable_id']}/review",
            headers=auth(token),
            json={"decision": "APPROVED", "score": 40},
        )
        assert response.status_code == 403, response.text
        queue = await client.get(
            f"/api/v1/projects/{scene['project_id']}/review-queue", headers=auth(token)
        )
        assert queue.status_code == 403, queue.text


async def test_a_project_without_an_offering_stays_closed_to_instructors(
    client: Any, db_session: Any
) -> None:
    """پروژهٔ بی‌ارائه به هیچ استادی تعلق ندارد — پل فقط از `offering_id` می‌گذرد."""
    teacher = await _offering(client, db_session, INSTRUCTOR_MOBILE)
    scene = await _student_project(client, db_session, None)
    await invalidate(teacher["id"])

    response = await client.post(
        f"/api/v1/deliverables/{scene['deliverable_id']}/review",
        headers=auth(teacher["token"]),
        json={"decision": "APPROVED", "score": 40},
    )
    assert response.status_code == 403, response.text


# ── ۲. پیوند پروژه به ارائه ────────────────────────────────────────────
async def _managed_payload(
    client: Any, offering_id: uuid.UUID | str, **extra: Any
) -> dict[str, Any]:
    skills = await taxonomy_ids(client, "skills", limit=1)
    return project_payload(
        kind="C_PROBLEM",
        offering_id=str(offering_id),
        required_skills=[{"skill_id": skills[0], "min_level": 3}],
        **extra,
    )


async def test_the_instructor_of_an_offering_links_a_project_to_it(
    client: Any, db_session: Any
) -> None:
    teacher = await _offering(client, db_session, INSTRUCTOR_MOBILE)

    created = await client.post(
        "/api/v1/projects",
        headers=auth(teacher["token"]),
        json=await _managed_payload(client, teacher["offering"].id),
    )
    assert created.status_code == 201, created.text

    listed = await client.get("/api/v1/teach/projects", headers=auth(teacher["token"]))
    assert listed.status_code == 200, listed.text
    [row] = [p for p in listed.json() if p["id"] == created.json()["id"]]
    assert row["offering_id"] == str(teacher["offering"].id)
    assert row["course_title_fa"] == "برنامه‌ریزی حمل‌ونقل"


async def test_linking_needs_the_right_to_manage_that_offering(
    client: Any, db_session: Any
) -> None:
    """استادِ ارائهٔ الف پروژه‌اش را به ارائهٔ ب نمی‌چسباند؛ دانشجو هم نه."""
    mine = await _offering(client, db_session, INSTRUCTOR_MOBILE)
    theirs = await _offering(client, db_session, OTHER_INSTRUCTOR_MOBILE)
    student_token = await login(client, STUDENT_MOBILE)
    await complete_profile(client, student_token, first_name="مینا")

    stolen = await client.post(
        "/api/v1/projects",
        headers=auth(mine["token"]),
        json=await _managed_payload(client, theirs["offering"].id),
    )
    assert stolen.status_code == 403, stolen.text

    by_student = await client.post(
        "/api/v1/projects",
        headers=auth(student_token),
        json=project_payload(offering_id=str(mine["offering"].id)),
    )
    assert by_student.status_code == 403, by_student.text


async def test_linking_rejects_a_missing_or_archived_offering(client: Any, db_session: Any) -> None:
    teacher = await _offering(client, db_session, INSTRUCTOR_MOBILE)

    unknown = await client.post(
        "/api/v1/projects",
        headers=auth(teacher["token"]),
        json=await _managed_payload(client, uuid.uuid4()),
    )
    assert unknown.status_code == 422, unknown.text

    teacher["offering"].status = "ARCHIVED"
    await db_session.flush()
    archived = await client.post(
        "/api/v1/projects",
        headers=auth(teacher["token"]),
        json=await _managed_payload(client, teacher["offering"].id),
    )
    assert archived.status_code == 422, archived.text


async def test_the_offering_of_a_project_does_not_change_after_creation(
    client: Any, db_session: Any
) -> None:
    mine = await _offering(client, db_session, INSTRUCTOR_MOBILE)
    theirs = await _offering(client, db_session, OTHER_INSTRUCTOR_MOBILE)
    payload = await _managed_payload(client, mine["offering"].id)
    created = await client.post("/api/v1/projects", headers=auth(mine["token"]), json=payload)
    assert created.status_code == 201, created.text
    url = f"/api/v1/projects/{created.json()['id']}"

    moved = await client.patch(
        url,
        headers=auth(mine["token"]),
        json={**payload, "offering_id": str(theirs["offering"].id)},
    )
    assert moved.status_code == 422, moved.text
    # فرم ویرایشی که `offering_id` نمی‌فرستد، پیوند را برنمی‌دارد و خطا هم نمی‌گیرد.
    payload.pop("offering_id")
    edited = await client.patch(url, headers=auth(mine["token"]), json=payload)
    assert edited.status_code == 200, edited.text
    listed = await client.get("/api/v1/teach/projects", headers=auth(mine["token"]))
    [row] = [p for p in listed.json() if p["id"] == created.json()["id"]]
    assert row["offering_id"] == str(mine["offering"].id)


# ── ۳. فهرست پروژه‌ها ──────────────────────────────────────────────────
async def test_projects_list_carries_what_a_supervisor_triages_by(
    client: Any, db_session: Any
) -> None:
    teacher = await _offering(client, db_session, INSTRUCTOR_MOBILE)
    scene = await _student_project(client, db_session, teacher["offering"].id)
    await invalidate(teacher["id"])

    response = await client.get("/api/v1/teach/projects", headers=auth(teacher["token"]))
    assert response.status_code == 200, response.text
    [row] = response.json()
    assert row["id"] == scene["project_id"]
    assert row["status"] == "IN_PROGRESS"
    assert row["health"] == "HEALTHY"
    assert row["health_fa"] == "سالم"
    assert row["kind_fa"] == "پروژهٔ شخصی"
    assert row["lead_name"] == "مینا رستمی"
    assert row["active_members"] == 1
    assert row["milestones_total"] == 1
    assert row["milestones_approved"] == 0
    assert row["open_deliverables"] == 1
    assert row["oldest_open_days"] == 0


async def test_stalled_projects_come_before_healthy_ones(client: Any, db_session: Any) -> None:
    from silp.models.project import Project

    teacher = await _offering(client, db_session, INSTRUCTOR_MOBILE)
    healthy = await _student_project(client, db_session, teacher["offering"].id)
    stalled = await _student_project(
        client, db_session, teacher["offering"].id, mobile=SECOND_STUDENT_MOBILE
    )
    row = await db_session.get(Project, uuid.UUID(stalled["project_id"]))
    row.health = "STALLED"
    await db_session.flush()
    await invalidate(teacher["id"])

    response = await client.get("/api/v1/teach/projects", headers=auth(teacher["token"]))
    assert [p["id"] for p in response.json()] == [stalled["project_id"], healthy["project_id"]]


async def test_projects_of_another_offering_are_not_listed(client: Any, db_session: Any) -> None:
    teacher = await _offering(client, db_session, INSTRUCTOR_MOBILE)
    other = await _offering(client, db_session, OTHER_INSTRUCTOR_MOBILE)
    await _student_project(client, db_session, teacher["offering"].id)
    await invalidate(teacher["id"])
    await invalidate(other["id"])

    response = await client.get("/api/v1/teach/projects", headers=auth(other["token"]))
    assert response.status_code == 200, response.text
    assert response.json() == []


# ── ۴. صف واحد بررسی ───────────────────────────────────────────────────
async def test_review_queue_is_oldest_first_and_matches_the_dashboard(
    client: Any, db_session: Any
) -> None:
    from datetime import UTC, datetime, timedelta

    from silp.models.delivery import Deliverable

    teacher = await _offering(client, db_session, INSTRUCTOR_MOBILE)
    newer = await _student_project(client, db_session, teacher["offering"].id)
    older = await _student_project(
        client, db_session, teacher["offering"].id, mobile=SECOND_STUDENT_MOBILE
    )
    row = await db_session.get(Deliverable, uuid.UUID(older["deliverable_id"]))
    row.submitted_at = datetime.now(UTC) - timedelta(days=5)
    await db_session.flush()
    await invalidate(teacher["id"])

    response = await client.get("/api/v1/teach/review-queue", headers=auth(teacher["token"]))
    assert response.status_code == 200, response.text
    queue = response.json()
    assert queue["total"] == 2
    assert queue["oldest_days"] == 5
    assert [i["deliverable_id"] for i in queue["items"]] == [
        older["deliverable_id"],
        newer["deliverable_id"],
    ]
    first = queue["items"][0]
    assert first["status_fa"] == "در انتظار بررسی"
    assert first["submitter_name"] == "مینا رستمی"
    assert first["excerpt"] == "گزارش ده مصاحبه"
    assert first["days_waiting"] == 5
    assert first["course_title_fa"] == "برنامه‌ریزی حمل‌ونقل"

    # همان عددی که داشبورد می‌شمارد — وگرنه استاد «۲ منتظر» می‌بیند و صف خالی است.
    dashboard = await client.get("/api/v1/teach/dashboard", headers=auth(teacher["token"]))
    assert dashboard.json()["needs_attention"]["deliverables_pending"]["count"] == queue["total"]


async def test_a_reviewed_deliverable_leaves_the_queue(client: Any, db_session: Any) -> None:
    teacher = await _offering(client, db_session, INSTRUCTOR_MOBILE)
    scene = await _student_project(client, db_session, teacher["offering"].id)
    await invalidate(teacher["id"])

    reviewed = await client.post(
        f"/api/v1/deliverables/{scene['deliverable_id']}/review",
        headers=auth(teacher["token"]),
        json={"decision": "CHANGES_REQUESTED", "feedback": "ده مصاحبهٔ دیگر هم بیاور."},
    )
    assert reviewed.status_code == 200, reviewed.text

    queue = await client.get("/api/v1/teach/review-queue", headers=auth(teacher["token"]))
    assert queue.json() == {"total": 0, "oldest_days": None, "items": []}


async def test_queue_and_list_are_empty_for_someone_who_supervises_nothing(
    client: Any, db_session: Any
) -> None:
    teacher = await _offering(client, db_session, INSTRUCTOR_MOBILE)
    await _student_project(client, db_session, teacher["offering"].id)
    outsider_token = await login(client, OUTSIDER_MOBILE)
    await invalidate(teacher["id"])

    queue = await client.get("/api/v1/teach/review-queue", headers=auth(outsider_token))
    projects = await client.get("/api/v1/teach/projects", headers=auth(outsider_token))
    assert queue.status_code == projects.status_code == 200
    assert queue.json()["items"] == []
    assert projects.json() == []


async def test_a_teaching_assistant_gets_no_review_queue(client: Any, db_session: Any) -> None:
    """دستیار مجوز بررسی ندارد؛ صفی که نتواند در آن کاری کند فقط ۴۰۳ می‌سازد."""
    from silp.core.permissions import Role, ScopeType
    from silp.services import authz

    teacher = await _offering(client, db_session, INSTRUCTOR_MOBILE)
    await _student_project(client, db_session, teacher["offering"].id)
    ta_token = await login(client, OTHER_INSTRUCTOR_MOBILE)
    ta = await me(client, ta_token)
    await authz.grant_role(
        db_session,
        user_id=uuid.UUID(ta["id"]),
        role=Role.TA,
        scope_type=ScopeType.OFFERING,
        scope_id=teacher["offering"].id,
    )
    await db_session.flush()
    await invalidate(ta["id"])
    await invalidate(teacher["id"])

    queue = await client.get("/api/v1/teach/review-queue", headers=auth(ta_token))
    assert queue.status_code == 200, queue.text
    assert queue.json()["items"] == []
