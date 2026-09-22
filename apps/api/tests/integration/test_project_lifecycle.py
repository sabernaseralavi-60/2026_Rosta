"""چرخهٔ کامل پروژه — M2، تعریف انجام‌شدهٔ §13.

«دانشجو درخواست می‌دهد، مدیر می‌پذیرد، دانشجو تحویل‌دادنی می‌فرستد، مدیر
تأیید می‌کند، و همه چیز در پایگاه داده درست ثبت می‌شود.»

PostgreSQL واقعی لازم است: قیدهای §4.6، ایندکس یکتای عضویت فعال، و
شماره‌گذاری نسخه با قید یکتا هیچ‌کدام در حافظه شبیه‌سازی نمی‌شوند.
"""

from __future__ import annotations

from typing import Any

import pytest
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

LEAD_MOBILE = "09121220001"
STUDENT_MOBILE = "09121220002"
OUTSIDER_MOBILE = "09121220003"
THIRD_MOBILE = "09121220004"


async def _actor(client: Any, db_session: Any, mobile: str, **profile: Any) -> tuple[str, str]:
    """ورود + نیمرخ کامل. خروجی: (توکن، شناسهٔ کاربر)."""
    token = await login(client, mobile)
    await complete_profile(client, token, **profile)
    user_id = str((await me(client, token))["id"])
    return token, user_id


async def _publishable_payload(client: Any, **overrides: Any) -> dict[str, Any]:
    """بدنه‌ای که شرط §7.4 برای انتشار را دارد: دست‌کم یک مهارت لازم."""
    if "required_skills" not in overrides:
        skills = await taxonomy_ids(client, "skills", limit=1)
        overrides["required_skills"] = [{"skill_id": skills[0], "min_level": 3, "weight": 2}]
    return project_payload(**overrides)


async def _published_project(client: Any, db_session: Any, token: str, **overrides: Any) -> str:
    """پروژه‌ای که مرحله و مهارت لازم دارد و منتشر شده است."""
    response = await client.post(
        "/api/v1/projects",
        headers=auth(token),
        json=await _publishable_payload(client, **overrides),
    )
    assert response.status_code == 201, response.text
    project_id = str(response.json()["id"])

    response = await client.post(
        f"/api/v1/projects/{project_id}/milestones",
        headers=auth(token),
        json=milestone_payload(),
    )
    assert response.status_code == 201, response.text

    response = await client.post(f"/api/v1/projects/{project_id}/publish", headers=auth(token))
    assert response.status_code == 200, response.text
    return project_id


# ── چرخهٔ کامل ─────────────────────────────────────────────────────────
async def test_full_loop_from_application_to_approved_deliverable(  # type: ignore[no-untyped-def]
    client, db_session
) -> None:
    """تعریف انجام‌شدهٔ M2 — یک مسیر، از ابتدا تا انتها."""
    lead_token, lead_id = await _actor(client, db_session, LEAD_MOBILE, first_name="صابر")
    student_token, student_id = await _actor(client, db_session, STUDENT_MOBILE, first_name="زهرا")
    project_id = await _published_project(client, db_session, lead_token)

    # ۱. دانشجو درخواست می‌دهد و امتیاز تطابق عکس‌برداری می‌شود.
    response = await client.post(
        f"/api/v1/projects/{project_id}/applications",
        headers=auth(student_token),
        json={"motivation": "به فروش علاقه دارم و وقت آزاد دارم."},
    )
    assert response.status_code == 201, response.text
    application = response.json()
    assert application["status"] == "PENDING"
    assert application["match_score"] is not None
    assert set(application["match_breakdown"]) == {
        "skill",
        "asset",
        "interest",
        "time",
        "style",
        "goal",
    }
    application_id = application["id"]

    # ۲. مدیر پروژه درخواست را با امتیاز تطابق می‌بیند.
    response = await client.get(
        f"/api/v1/projects/{project_id}/applications", headers=auth(lead_token)
    )
    assert response.status_code == 200, response.text
    assert [a["id"] for a in response.json()] == [application_id]
    assert response.json()[0]["applicant_name"] == "زهرا رستمی"

    # ۳. مدیر می‌پذیرد ⇒ عضویت تیم.
    response = await client.post(
        f"/api/v1/applications/{application_id}/decide",
        headers=auth(lead_token),
        json={"decision": "ACCEPTED", "note": "خوش آمدی."},
    )
    assert response.status_code == 200, response.text
    assert response.json()["application"]["status"] == "ACCEPTED"
    await invalidate(student_id)

    response = await client.get(f"/api/v1/projects/{project_id}/team", headers=auth(lead_token))
    assert response.status_code == 200, response.text
    team = response.json()
    assert team["active_members"] == 2
    assert {m["user_id"] for m in team["members"]} == {lead_id, student_id}
    assert team["open_seats"] == 1

    # ۴. پروژه شروع می‌شود و مراحل فعال می‌شوند.
    response = await client.post(f"/api/v1/projects/{project_id}/start", headers=auth(lead_token))
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "IN_PROGRESS"

    response = await client.get(
        f"/api/v1/projects/{project_id}/milestones", headers=auth(student_token)
    )
    assert response.status_code == 200, response.text
    milestone = response.json()[0]
    assert milestone["status"] == "IN_PROGRESS"
    assert milestone["my_deliverable"] is None

    # ۵. عضو تحویل‌دادنی می‌فرستد.
    response = await client.post(
        f"/api/v1/milestones/{milestone['id']}/deliverables",
        headers=auth(student_token),
        json={"body": "گزارش ده مصاحبه", "links": ["https://example.org/report"]},
    )
    assert response.status_code == 201, response.text
    deliverable = response.json()
    assert deliverable["version"] == 1
    assert deliverable["status"] == "SUBMITTED"
    assert deliverable["is_late"] is False

    # ۶. مدیر تأیید می‌کند ⇒ مرحله تأیید و پروژه آمادهٔ بستن.
    response = await client.post(
        f"/api/v1/deliverables/{deliverable['id']}/review",
        headers=auth(lead_token),
        json={"decision": "APPROVED", "score": 45, "feedback": "کار خوبی بود."},
    )
    assert response.status_code == 200, response.text
    outcome = response.json()
    assert outcome["milestone"]["status"] == "APPROVED"
    assert outcome["milestone"]["approved_at"] is not None
    assert outcome["project_ready_to_close"] is True

    # ۷. بستن پروژه.
    response = await client.post(
        f"/api/v1/projects/{project_id}/complete",
        headers=auth(lead_token),
        json={"final_report": "پروژه با فروش ۱۲ میلیون تومانی بسته شد."},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "COMPLETED"

    # ۸. جریان فعالیت همهٔ این‌ها را ثبت کرده است.
    response = await client.get(f"/api/v1/projects/{project_id}/activity", headers=auth(lead_token))
    kinds = {a["kind"] for a in response.json()}
    assert {
        "PROJECT_PUBLISHED",
        "APPLICATION_SUBMITTED",
        "MEMBER_JOINED",
        "DELIVERABLE_SUBMITTED",
        "DELIVERABLE_REVIEWED",
        "PROJECT_COMPLETED",
    } <= kinds


# ── ساخت و انتشار ──────────────────────────────────────────────────────
async def test_student_cannot_create_managed_project_kinds(client, db_session) -> None:  # type: ignore[no-untyped-def]
    """§6.2 — نوع A/B/C مجوز مدیریتی می‌خواهد؛ D برای همه باز است."""
    token, _ = await _actor(client, db_session, LEAD_MOBILE)

    blocked = await client.post(
        "/api/v1/projects", headers=auth(token), json=project_payload(kind="A_VENTURE")
    )
    assert blocked.status_code == 403, blocked.text
    assert blocked.json()["error"]["code"] == "PERMISSION_DENIED"

    allowed = await client.post(
        "/api/v1/projects", headers=auth(token), json=project_payload(kind="D_PERSONAL")
    )
    assert allowed.status_code == 201, allowed.text


async def test_instructor_can_create_venture_project(client, db_session) -> None:  # type: ignore[no-untyped-def]
    token, user_id = await _actor(client, db_session, LEAD_MOBILE)
    await grant_role(db_session, user_id, "INSTRUCTOR")

    response = await client.post(
        "/api/v1/projects", headers=auth(token), json=project_payload(kind="A_VENTURE")
    )
    assert response.status_code == 201, response.text
    assert response.json()["kind"] == "A_VENTURE"


async def test_draft_project_is_hidden_from_the_project_bank(client, db_session) -> None:  # type: ignore[no-untyped-def]
    """پروژهٔ منتشرنشده در فهرست عمومی نیست ولی در «پروژه‌های من» هست."""
    token, _ = await _actor(client, db_session, LEAD_MOBILE)
    created = await client.post("/api/v1/projects", headers=auth(token), json=project_payload())
    project_id = created.json()["id"]

    public = await client.get("/api/v1/projects")
    assert project_id not in {p["id"] for p in public.json()["items"]}

    mine = await client.get("/api/v1/projects/mine", headers=auth(token))
    assert project_id in {p["id"] for p in mine.json()}


async def test_publishing_requires_a_milestone_and_a_skill(client, db_session) -> None:  # type: ignore[no-untyped-def]
    """§7.4 — بدون مرحله، پروژه تحویل‌دادنی ندارد."""
    token, _ = await _actor(client, db_session, LEAD_MOBILE)
    created = await client.post("/api/v1/projects", headers=auth(token), json=project_payload())
    project_id = created.json()["id"]

    blocked = await client.post(f"/api/v1/projects/{project_id}/publish", headers=auth(token))
    assert blocked.status_code == 409, blocked.text
    assert "مرحله" in blocked.json()["error"]["message"]


async def test_publish_creates_the_team_with_the_lead_inside(client, db_session) -> None:  # type: ignore[no-untyped-def]
    """§7.12 — تیم هنگام انتشار ساخته می‌شود، نه هنگام پذیرش اولین عضو."""
    token, lead_id = await _actor(client, db_session, LEAD_MOBILE)
    project_id = await _published_project(client, db_session, token)

    response = await client.get(f"/api/v1/projects/{project_id}/team", headers=auth(token))
    assert response.status_code == 200, response.text
    members = response.json()["members"]
    assert len(members) == 1
    assert members[0]["user_id"] == lead_id
    assert members[0]["is_lead"] is True


# ── درخواست پیوستن — §7.5 ──────────────────────────────────────────────
async def test_application_needs_a_complete_profile(client, db_session) -> None:  # type: ignore[no-untyped-def]
    """§7.5 — نیمرخ ناقص یعنی امتیاز تطابق بی‌معنا."""
    lead_token, _ = await _actor(client, db_session, LEAD_MOBILE)
    project_id = await _published_project(client, db_session, lead_token)

    half_token = await login(client, STUDENT_MOBILE)
    await client.patch(
        "/api/v1/me/profile",
        headers=auth(half_token),
        json={"first_name": "حسن", "last_name": "نوری", "degree_level": "BACHELOR"},
    )

    response = await client.post(
        f"/api/v1/projects/{project_id}/applications",
        headers=auth(half_token),
        json={"motivation": "دوست دارم در این پروژه باشم."},
    )
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "PROFILE_INCOMPLETE"


async def test_duplicate_application_is_rejected(client, db_session) -> None:  # type: ignore[no-untyped-def]
    lead_token, _ = await _actor(client, db_session, LEAD_MOBILE)
    student_token, _ = await _actor(client, db_session, STUDENT_MOBILE)
    project_id = await _published_project(client, db_session, lead_token)

    body = {"motivation": "انگیزه‌نامهٔ کاملاً معتبر برای این پروژه."}
    first = await client.post(
        f"/api/v1/projects/{project_id}/applications", headers=auth(student_token), json=body
    )
    assert first.status_code == 201, first.text

    second = await client.post(
        f"/api/v1/projects/{project_id}/applications", headers=auth(student_token), json=body
    )
    assert second.status_code == 409, second.text
    assert second.json()["error"]["code"] == "DUPLICATE_APPLICATION"


async def test_lead_cannot_apply_to_own_project(client, db_session) -> None:  # type: ignore[no-untyped-def]
    lead_token, _ = await _actor(client, db_session, LEAD_MOBILE)
    project_id = await _published_project(client, db_session, lead_token)

    response = await client.post(
        f"/api/v1/projects/{project_id}/applications",
        headers=auth(lead_token),
        json={"motivation": "می‌خواهم به پروژهٔ خودم بپیوندم."},
    )
    assert response.status_code == 409, response.text


async def test_application_to_a_draft_project_is_refused(client, db_session) -> None:  # type: ignore[no-untyped-def]
    lead_token, _ = await _actor(client, db_session, LEAD_MOBILE)
    student_token, _ = await _actor(client, db_session, STUDENT_MOBILE)
    created = await client.post(
        "/api/v1/projects", headers=auth(lead_token), json=project_payload()
    )
    project_id = created.json()["id"]

    response = await client.post(
        f"/api/v1/projects/{project_id}/applications",
        headers=auth(student_token),
        json={"motivation": "انگیزه‌نامهٔ کاملاً معتبر برای این پروژه."},
    )
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "PROJECT_NOT_OPEN"


async def test_rejection_always_carries_three_alternatives(client, db_session) -> None:  # type: ignore[no-untyped-def]
    """§7.5 — «رد شدم» و «مسیر بهتری پیدا کردم» دو تجربهٔ متفاوت‌اند."""
    lead_token, lead_id = await _actor(client, db_session, LEAD_MOBILE)
    await grant_role(db_session, lead_id, "INSTRUCTOR")
    student_token, _ = await _actor(client, db_session, STUDENT_MOBILE)

    target = await _published_project(client, db_session, lead_token)
    # چند پروژهٔ دیگر تا موتور توصیه‌گر چیزی برای پیشنهاد داشته باشد.
    for index in range(4):
        await _published_project(
            client,
            db_session,
            lead_token,
            title_fa=f"پروژهٔ جایگزین شمارهٔ {index}",
            kind="C_PROBLEM",
        )

    applied = await client.post(
        f"/api/v1/projects/{target}/applications",
        headers=auth(student_token),
        json={"motivation": "انگیزه‌نامهٔ کاملاً معتبر برای این پروژه."},
    )
    application_id = applied.json()["id"]

    response = await client.post(
        f"/api/v1/applications/{application_id}/decide",
        headers=auth(lead_token),
        json={"decision": "REJECTED", "note": "این دوره ظرفیت نداریم."},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["application"]["status"] == "REJECTED"
    assert 1 <= len(body["alternatives"]) <= 3
    assert all(a["project"]["id"] != target for a in body["alternatives"])
    assert all(a["reasons"] for a in body["alternatives"])


async def test_capacity_is_enforced_on_accept(client, db_session) -> None:  # type: ignore[no-untyped-def]
    """§7.12 — مدیر در ظرفیت حساب می‌شود؛ `team_size_max=2` یعنی یک نفر دیگر."""
    lead_token, _ = await _actor(client, db_session, LEAD_MOBILE)
    first_token, first_id = await _actor(client, db_session, STUDENT_MOBILE)
    second_token, _ = await _actor(client, db_session, THIRD_MOBILE)
    project_id = await _published_project(
        client, db_session, lead_token, team_size_min=1, team_size_max=2
    )

    body = {"motivation": "انگیزه‌نامهٔ کاملاً معتبر برای این پروژه."}
    first = await client.post(
        f"/api/v1/projects/{project_id}/applications", headers=auth(first_token), json=body
    )
    second = await client.post(
        f"/api/v1/projects/{project_id}/applications", headers=auth(second_token), json=body
    )

    accepted = await client.post(
        f"/api/v1/applications/{first.json()['id']}/decide",
        headers=auth(lead_token),
        json={"decision": "ACCEPTED"},
    )
    assert accepted.status_code == 200, accepted.text
    await invalidate(first_id)

    overflow = await client.post(
        f"/api/v1/applications/{second.json()['id']}/decide",
        headers=auth(lead_token),
        json={"decision": "ACCEPTED"},
    )
    assert overflow.status_code == 409, overflow.text
    assert overflow.json()["error"]["code"] == "PROJECT_CAPACITY_FULL"


async def test_applicant_can_withdraw(client, db_session) -> None:  # type: ignore[no-untyped-def]
    lead_token, _ = await _actor(client, db_session, LEAD_MOBILE)
    student_token, _ = await _actor(client, db_session, STUDENT_MOBILE)
    project_id = await _published_project(client, db_session, lead_token)

    applied = await client.post(
        f"/api/v1/projects/{project_id}/applications",
        headers=auth(student_token),
        json={"motivation": "انگیزه‌نامهٔ کاملاً معتبر برای این پروژه."},
    )
    application_id = applied.json()["id"]

    response = await client.delete(
        f"/api/v1/applications/{application_id}", headers=auth(student_token)
    )
    assert response.status_code == 204, response.text

    mine = await client.get("/api/v1/applications/mine", headers=auth(student_token))
    assert mine.json()[0]["status"] == "WITHDRAWN"


async def test_other_students_cannot_withdraw_someone_elses_application(  # type: ignore[no-untyped-def]
    client, db_session
) -> None:
    """§6.4 قاعدهٔ ۴ — ۴۰۴، نه ۴۰۳: وجود درخواست هم افشا نمی‌شود."""
    lead_token, _ = await _actor(client, db_session, LEAD_MOBILE)
    student_token, _ = await _actor(client, db_session, STUDENT_MOBILE)
    outsider_token, _ = await _actor(client, db_session, OUTSIDER_MOBILE)
    project_id = await _published_project(client, db_session, lead_token)

    applied = await client.post(
        f"/api/v1/projects/{project_id}/applications",
        headers=auth(student_token),
        json={"motivation": "انگیزه‌نامهٔ کاملاً معتبر برای این پروژه."},
    )
    response = await client.delete(
        f"/api/v1/applications/{applied.json()['id']}", headers=auth(outsider_token)
    )
    assert response.status_code == 404, response.text


# ── تحویل‌دادنی — §7.6 ─────────────────────────────────────────────────
async def _team_of_two(client: Any, db_session: Any) -> tuple[str, str, str, str]:
    """پروژهٔ در جریان با مدیر و یک عضو. خروجی: (توکن مدیر، توکن عضو، پروژه، مرحله)."""
    lead_token, _ = await _actor(client, db_session, LEAD_MOBILE)
    student_token, student_id = await _actor(client, db_session, STUDENT_MOBILE)
    project_id = await _published_project(client, db_session, lead_token)

    applied = await client.post(
        f"/api/v1/projects/{project_id}/applications",
        headers=auth(student_token),
        json={"motivation": "انگیزه‌نامهٔ کاملاً معتبر برای این پروژه."},
    )
    await client.post(
        f"/api/v1/applications/{applied.json()['id']}/decide",
        headers=auth(lead_token),
        json={"decision": "ACCEPTED"},
    )
    await invalidate(student_id)
    await client.post(f"/api/v1/projects/{project_id}/start", headers=auth(lead_token))

    milestones = await client.get(
        f"/api/v1/projects/{project_id}/milestones", headers=auth(lead_token)
    )
    return lead_token, student_token, project_id, milestones.json()[0]["id"]


async def test_changes_requested_needs_written_feedback(client, db_session) -> None:  # type: ignore[no-untyped-def]
    """§7.6 — بدون بازخورد، دانشجو نمی‌داند چه چیزی را درست کند."""
    lead_token, student_token, _, milestone_id = await _team_of_two(client, db_session)
    submitted = await client.post(
        f"/api/v1/milestones/{milestone_id}/deliverables",
        headers=auth(student_token),
        json={"body": "نسخهٔ اول"},
    )
    deliverable_id = submitted.json()["id"]

    response = await client.post(
        f"/api/v1/deliverables/{deliverable_id}/review",
        headers=auth(lead_token),
        json={"decision": "CHANGES_REQUESTED"},
    )
    assert response.status_code == 422, response.text
    assert "بازخورد" in response.json()["error"]["message"]


async def test_changes_requested_opens_a_new_version_and_keeps_history(  # type: ignore[no-untyped-def]
    client, db_session
) -> None:
    """§7.6 — نسخه‌ها هرگز پاک نمی‌شوند."""
    lead_token, student_token, _, milestone_id = await _team_of_two(client, db_session)
    first = await client.post(
        f"/api/v1/milestones/{milestone_id}/deliverables",
        headers=auth(student_token),
        json={"body": "نسخهٔ اول"},
    )
    await client.post(
        f"/api/v1/deliverables/{first.json()['id']}/review",
        headers=auth(lead_token),
        json={"decision": "CHANGES_REQUESTED", "feedback": "بخش تحلیل ناقص است."},
    )

    second = await client.post(
        f"/api/v1/milestones/{milestone_id}/deliverables",
        headers=auth(student_token),
        json={"body": "نسخهٔ دوم با تحلیل کامل"},
    )
    assert second.status_code == 201, second.text
    assert second.json()["version"] == 2

    history = await client.get(
        f"/api/v1/milestones/{milestone_id}/deliverables", headers=auth(student_token)
    )
    versions = [(d["version"], d["status"]) for d in history.json()]
    assert versions == [(1, "CHANGES_REQUESTED"), (2, "SUBMITTED")]
    assert history.json()[0]["feedback"] == "بخش تحلیل ناقص است."


async def test_second_version_is_blocked_while_the_first_is_pending(client, db_session) -> None:  # type: ignore[no-untyped-def]
    lead_token, student_token, _, milestone_id = await _team_of_two(client, db_session)
    await client.post(
        f"/api/v1/milestones/{milestone_id}/deliverables",
        headers=auth(student_token),
        json={"body": "نسخهٔ اول"},
    )
    again = await client.post(
        f"/api/v1/milestones/{milestone_id}/deliverables",
        headers=auth(student_token),
        json={"body": "دوباره"},
    )
    assert again.status_code == 409, again.text


async def test_empty_deliverable_is_refused(client, db_session) -> None:  # type: ignore[no-untyped-def]
    _, student_token, _, milestone_id = await _team_of_two(client, db_session)
    response = await client.post(
        f"/api/v1/milestones/{milestone_id}/deliverables",
        headers=auth(student_token),
        json={"body": "   "},
    )
    assert response.status_code == 422, response.text


async def test_links_must_be_http(client, db_session) -> None:  # type: ignore[no-untyped-def]
    _, student_token, _, milestone_id = await _team_of_two(client, db_session)
    response = await client.post(
        f"/api/v1/milestones/{milestone_id}/deliverables",
        headers=auth(student_token),
        json={"body": "گزارش", "links": ["javascript:alert(1)"]},
    )
    assert response.status_code == 422, response.text


async def test_reviewer_cannot_review_their_own_deliverable(client, db_session) -> None:  # type: ignore[no-untyped-def]
    """مدیر پروژه هم عضو تیم است و می‌تواند تحویل بدهد — ولی نه خودش تأیید کند."""
    lead_token, _, _, milestone_id = await _team_of_two(client, db_session)
    submitted = await client.post(
        f"/api/v1/milestones/{milestone_id}/deliverables",
        headers=auth(lead_token),
        json={"body": "تحویل خود مدیر"},
    )
    assert submitted.status_code == 201, submitted.text

    response = await client.post(
        f"/api/v1/deliverables/{submitted.json()['id']}/review",
        headers=auth(lead_token),
        json={"decision": "APPROVED", "score": 40},
    )
    assert response.status_code == 409, response.text


async def test_late_submission_is_allowed_but_flagged(client, db_session) -> None:  # type: ignore[no-untyped-def]
    """§7.6 — مهلت گذشته کار را متوقف نمی‌کند، فقط علامت می‌زند."""
    lead_token, student_token, project_id, _ = await _team_of_two(client, db_session)
    overdue = await client.post(
        f"/api/v1/projects/{project_id}/milestones",
        headers=auth(lead_token),
        json=milestone_payload(
            title_fa="مرحلهٔ دیرشده", sort_order=2, due_on="2020-01-01", is_required=False
        ),
    )
    assert overdue.status_code == 201, overdue.text

    response = await client.post(
        f"/api/v1/milestones/{overdue.json()['id']}/deliverables",
        headers=auth(student_token),
        json={"body": "دیر رسید ولی رسید"},
    )
    assert response.status_code == 201, response.text
    assert response.json()["is_late"] is True


async def test_approved_milestone_stops_accepting_deliverables(client, db_session) -> None:  # type: ignore[no-untyped-def]
    lead_token, student_token, _, milestone_id = await _team_of_two(client, db_session)
    submitted = await client.post(
        f"/api/v1/milestones/{milestone_id}/deliverables",
        headers=auth(student_token),
        json={"body": "گزارش"},
    )
    await client.post(
        f"/api/v1/deliverables/{submitted.json()['id']}/review",
        headers=auth(lead_token),
        json={"decision": "APPROVED", "score": 50, "feedback": "عالی"},
    )

    response = await client.post(
        f"/api/v1/milestones/{milestone_id}/deliverables",
        headers=auth(student_token),
        json={"body": "باز هم"},
    )
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "MILESTONE_NOT_OPEN"


async def test_project_cannot_close_with_a_pending_required_milestone(  # type: ignore[no-untyped-def]
    client, db_session
) -> None:
    """FR-PRJ-08 — بستن پروژه نیازمند تأیید همهٔ مراحل الزامی است."""
    lead_token, _, project_id, _ = await _team_of_two(client, db_session)
    response = await client.post(
        f"/api/v1/projects/{project_id}/complete",
        headers=auth(lead_token),
        json={"final_report": "گزارش نهایی که هنوز زود است."},
    )
    assert response.status_code == 409, response.text
    assert "الزامی" in response.json()["error"]["message"]


# ── تیم ────────────────────────────────────────────────────────────────
async def test_lead_cannot_leave_or_be_removed(client, db_session) -> None:  # type: ignore[no-untyped-def]
    lead_token, lead_id = await _actor(client, db_session, LEAD_MOBILE)
    project_id = await _published_project(client, db_session, lead_token)

    leaving = await client.post(
        f"/api/v1/projects/{project_id}/leave",
        headers=auth(lead_token),
        json={"reason": "دیگر وقت ندارم."},
    )
    assert leaving.status_code == 409, leaving.text

    removing = await client.delete(
        f"/api/v1/projects/{project_id}/team/{lead_id}",
        headers=auth(lead_token),
        params={"reason": "حذف خودم"},
    )
    assert removing.status_code == 409, removing.text


async def test_member_can_leave_and_frees_a_seat(client, db_session) -> None:  # type: ignore[no-untyped-def]
    lead_token, student_token, project_id, _ = await _team_of_two(client, db_session)

    response = await client.post(
        f"/api/v1/projects/{project_id}/leave",
        headers=auth(student_token),
        json={"reason": "با درس‌هایم جور در نیامد."},
    )
    assert response.status_code == 204, response.text

    team = await client.get(f"/api/v1/projects/{project_id}/team", headers=auth(lead_token))
    assert team.json()["active_members"] == 1
    left = next(m for m in team.json()["members"] if m["status"] == "LEFT")
    assert left["left_at"] is not None
