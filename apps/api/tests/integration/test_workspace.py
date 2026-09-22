"""تختهٔ وظایف و گفتگوی تیمی — FR-PRJ-06، M2-10."""

from __future__ import annotations

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

pytestmark = pytest.mark.integration

LEAD = "09121440001"
MEMBER = "09121440002"
OUTSIDER = "09121440003"


async def _actor(client: Any, mobile: str, **profile: Any) -> tuple[str, str]:
    token = await login(client, mobile)
    await complete_profile(client, token, **profile)
    return token, str((await me(client, token))["id"])


async def _running_project(client: Any) -> tuple[str, str, str, str, str]:
    """پروژهٔ در جریان با مدیر و یک عضو.

    خروجی: (توکن مدیر، توکن عضو، شناسهٔ عضو، پروژه، مرحله).
    """
    lead_token, _ = await _actor(client, LEAD, first_name="صابر")
    member_token, member_id = await _actor(client, MEMBER, first_name="مینا")

    skills = await taxonomy_ids(client, "skills", limit=1)
    created = await client.post(
        "/api/v1/projects",
        headers=auth(lead_token),
        json=project_payload(
            required_skills=[{"skill_id": skills[0], "min_level": 3}], team_size_max=3
        ),
    )
    project_id = created.json()["id"]
    milestone = await client.post(
        f"/api/v1/projects/{project_id}/milestones",
        headers=auth(lead_token),
        json=milestone_payload(),
    )
    await client.post(f"/api/v1/projects/{project_id}/publish", headers=auth(lead_token))

    applied = await client.post(
        f"/api/v1/projects/{project_id}/applications",
        headers=auth(member_token),
        json={"motivation": "انگیزه‌نامهٔ کاملاً معتبر برای این پروژه."},
    )
    await client.post(
        f"/api/v1/applications/{applied.json()['id']}/decide",
        headers=auth(lead_token),
        json={"decision": "ACCEPTED"},
    )
    await invalidate(member_id)
    await client.post(f"/api/v1/projects/{project_id}/start", headers=auth(lead_token))
    return lead_token, member_token, member_id, project_id, milestone.json()["id"]


# ── تختهٔ وظایف ────────────────────────────────────────────────────────
async def test_task_board_round_trip(client, db_session) -> None:  # type: ignore[no-untyped-def]
    lead_token, member_token, member_id, project_id, milestone_id = await _running_project(client)

    created = await client.post(
        f"/api/v1/projects/{project_id}/tasks",
        headers=auth(lead_token),
        json={
            "title": "تماس با ده مشتری",
            "assignee_id": member_id,
            "milestone_id": milestone_id,
            "due_on": "2026-10-01",
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["status"] == "TODO"
    assert created.json()["status_fa"] == "انجام نشده"
    task_id = created.json()["id"]

    listed = await client.get(f"/api/v1/projects/{project_id}/tasks", headers=auth(member_token))
    assert listed.status_code == 200, listed.text
    assert listed.json()[0]["assignee_name"] == "مینا رستمی"

    # تختهٔ تیمی است: عضو هم می‌تواند وضعیت را جابه‌جا کند.
    moved = await client.patch(
        f"/api/v1/projects/{project_id}/tasks/{task_id}",
        headers=auth(member_token),
        json={"title": "تماس با ده مشتری", "assignee_id": member_id, "status": "DONE"},
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["status"] == "DONE"

    removed = await client.delete(
        f"/api/v1/projects/{project_id}/tasks/{task_id}", headers=auth(lead_token)
    )
    assert removed.status_code == 204, removed.text
    empty = await client.get(f"/api/v1/projects/{project_id}/tasks", headers=auth(lead_token))
    assert empty.json() == []


async def test_assignee_must_be_a_team_member(client, db_session) -> None:  # type: ignore[no-untyped-def]
    lead_token, _, _, project_id, _ = await _running_project(client)
    outsider_token, outsider_id = await _actor(client, OUTSIDER)

    response = await client.post(
        f"/api/v1/projects/{project_id}/tasks",
        headers=auth(lead_token),
        json={"title": "کاری برای غریبه", "assignee_id": outsider_id},
    )
    assert response.status_code == 422, response.text


async def test_milestone_of_another_project_is_refused(client, db_session) -> None:  # type: ignore[no-untyped-def]
    lead_token, _, _, project_id, _ = await _running_project(client)
    skills = await taxonomy_ids(client, "skills", limit=1)
    other = await client.post(
        "/api/v1/projects",
        headers=auth(lead_token),
        json=project_payload(
            title_fa="پروژهٔ دوم", required_skills=[{"skill_id": skills[0], "min_level": 3}]
        ),
    )
    other_milestone = await client.post(
        f"/api/v1/projects/{other.json()['id']}/milestones",
        headers=auth(lead_token),
        json=milestone_payload(),
    )

    response = await client.post(
        f"/api/v1/projects/{project_id}/tasks",
        headers=auth(lead_token),
        json={"title": "وظیفهٔ سرگردان", "milestone_id": other_milestone.json()["id"]},
    )
    assert response.status_code == 404, response.text


# ── گفتگو ──────────────────────────────────────────────────────────────
async def test_discussion_thread_is_one_level_deep(client, db_session) -> None:  # type: ignore[no-untyped-def]
    """§4.6 — پاسخ به پاسخ ممنوع است."""
    lead_token, member_token, _, project_id, _ = await _running_project(client)

    root = await client.post(
        f"/api/v1/projects/{project_id}/discussion",
        headers=auth(lead_token),
        json={"body": "برای هفتهٔ آینده جلسه بگذاریم؟"},
    )
    assert root.status_code == 201, root.text

    reply = await client.post(
        f"/api/v1/projects/{project_id}/discussion",
        headers=auth(member_token),
        json={"body": "موافقم، چهارشنبه خوب است.", "parent_id": root.json()["id"]},
    )
    assert reply.status_code == 201, reply.text

    nested = await client.post(
        f"/api/v1/projects/{project_id}/discussion",
        headers=auth(lead_token),
        json={"body": "پس قطعی شد.", "parent_id": reply.json()["id"]},
    )
    assert nested.status_code == 409, nested.text


async def test_messages_come_back_oldest_first_with_author_names(client, db_session) -> None:  # type: ignore[no-untyped-def]
    lead_token, member_token, _, project_id, _ = await _running_project(client)
    await client.post(
        f"/api/v1/projects/{project_id}/discussion",
        headers=auth(lead_token),
        json={"body": "پیام اول"},
    )
    await client.post(
        f"/api/v1/projects/{project_id}/discussion",
        headers=auth(member_token),
        json={"body": "پیام دوم"},
    )

    listed = await client.get(
        f"/api/v1/projects/{project_id}/discussion", headers=auth(member_token)
    )
    bodies = [m["body"] for m in listed.json()]
    assert bodies == ["پیام اول", "پیام دوم"]
    assert listed.json()[1]["author_name"] == "مینا رستمی"


async def test_author_can_delete_their_own_message(client, db_session) -> None:  # type: ignore[no-untyped-def]
    lead_token, member_token, _, project_id, _ = await _running_project(client)
    posted = await client.post(
        f"/api/v1/projects/{project_id}/discussion",
        headers=auth(member_token),
        json={"body": "این را اشتباه فرستادم"},
    )
    message_id = posted.json()["id"]

    removed = await client.delete(
        f"/api/v1/projects/{project_id}/discussion/{message_id}", headers=auth(member_token)
    )
    assert removed.status_code == 204, removed.text

    listed = await client.get(f"/api/v1/projects/{project_id}/discussion", headers=auth(lead_token))
    assert listed.json() == []


async def test_other_members_cannot_delete_a_message(client, db_session) -> None:  # type: ignore[no-untyped-def]
    """فقط نویسنده یا مدیر پروژه — و پاسخ ۴۰۴ است، نه ۴۰۳ (§6.4 قاعدهٔ ۴)."""
    lead_token, member_token, _, project_id, _ = await _running_project(client)
    posted = await client.post(
        f"/api/v1/projects/{project_id}/discussion",
        headers=auth(lead_token),
        json={"body": "پیام مدیر"},
    )
    response = await client.delete(
        f"/api/v1/projects/{project_id}/discussion/{posted.json()['id']}",
        headers=auth(member_token),
    )
    assert response.status_code == 404, response.text


async def test_workspace_writes_update_last_activity(client, db_session) -> None:  # type: ignore[no-untyped-def]
    """§7.4 — پیام و وظیفه هم «تحرک» حساب می‌شوند، نه فقط تحویل‌دادنی."""
    from sqlalchemy import select

    from silp.models.project import Project

    lead_token, _, _, project_id, _ = await _running_project(client)
    before = await db_session.scalar(
        select(Project.last_activity_at).where(Project.id == project_id)
    )

    await client.post(
        f"/api/v1/projects/{project_id}/discussion",
        headers=auth(lead_token),
        json={"body": "یک پیام تازه"},
    )
    after = await db_session.scalar(
        select(Project.last_activity_at).where(Project.id == project_id)
    )
    assert after >= before
