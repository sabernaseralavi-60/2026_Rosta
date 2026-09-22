"""مجوز همهٔ endpointهای پروژه — M2-13، §6.4.

قاعدهٔ §6.4: «PR بدون تست مجوز برای endpoint جدید، پذیرفته نمی‌شود.»

سه چیز جداگانه آزموده می‌شود و هر سه لازم‌اند:

۱. **بیرونی** (نه عضو، نه مدیر) به فضای کاری راه ندارد.
۲. **عضو ساده** کارهای مدیر پروژه را نمی‌تواند.
۳. **مدیر پروژهٔ الف** در پروژهٔ ب هیچ اختیاری ندارد — این همان چیزی
   است که یک بررسی نقشِ بدون قلمرو از دست می‌دهد.
"""

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

LEAD_A = "09121330001"
LEAD_B = "09121330002"
MEMBER = "09121330003"
OUTSIDER = "09121330004"


async def _actor(client: Any, mobile: str, **profile: Any) -> tuple[str, str]:
    token = await login(client, mobile)
    await complete_profile(client, token, **profile)
    return token, str((await me(client, token))["id"])


async def _project_with_team(client: Any, lead_token: str, member_token: str | None = None):  # type: ignore[no-untyped-def]
    """پروژهٔ در جریان با یک مرحله؛ در صورت نیاز با یک عضو عادی."""
    skills = await taxonomy_ids(client, "skills", limit=1)
    created = await client.post(
        "/api/v1/projects",
        headers=auth(lead_token),
        json=project_payload(
            required_skills=[{"skill_id": skills[0], "min_level": 3}], team_size_max=3
        ),
    )
    assert created.status_code == 201, created.text
    project_id = created.json()["id"]

    milestone = await client.post(
        f"/api/v1/projects/{project_id}/milestones",
        headers=auth(lead_token),
        json=milestone_payload(),
    )
    assert milestone.status_code == 201, milestone.text
    await client.post(f"/api/v1/projects/{project_id}/publish", headers=auth(lead_token))

    if member_token is not None:
        applied = await client.post(
            f"/api/v1/projects/{project_id}/applications",
            headers=auth(member_token),
            json={"motivation": "انگیزه‌نامهٔ کاملاً معتبر برای این پروژه."},
        )
        assert applied.status_code == 201, applied.text
        decided = await client.post(
            f"/api/v1/applications/{applied.json()['id']}/decide",
            headers=auth(lead_token),
            json={"decision": "ACCEPTED"},
        )
        assert decided.status_code == 200, decided.text
        member_id = str((await me(client, member_token))["id"])
        await invalidate(member_id)

    await client.post(f"/api/v1/projects/{project_id}/start", headers=auth(lead_token))
    return project_id, milestone.json()["id"]


# ── فضای کاری بستهٔ پروژه ──────────────────────────────────────────────
@pytest.mark.parametrize(
    "path",
    ["team", "milestones", "tasks", "discussion", "activity"],
)
async def test_outsider_cannot_read_the_workspace(client, db_session, path: str) -> None:  # type: ignore[no-untyped-def]
    lead_token, _ = await _actor(client, LEAD_A)
    outsider_token, _ = await _actor(client, OUTSIDER)
    project_id, _ = await _project_with_team(client, lead_token)

    response = await client.get(
        f"/api/v1/projects/{project_id}/{path}", headers=auth(outsider_token)
    )
    assert response.status_code == 403, response.text
    assert response.json()["error"]["code"] == "NOT_TEAM_MEMBER"


async def test_outsider_can_still_read_the_public_project_page(client, db_session) -> None:  # type: ignore[no-untyped-def]
    """§6.2 — پروژهٔ منتشرشده عمومی است؛ فقط فضای کاری بسته است."""
    lead_token, _ = await _actor(client, LEAD_A)
    outsider_token, _ = await _actor(client, OUTSIDER)
    project_id, _ = await _project_with_team(client, lead_token)

    response = await client.get(f"/api/v1/projects/{project_id}", headers=auth(outsider_token))
    assert response.status_code == 200, response.text
    assert response.json()["match"] is not None


# ── کارهای مخصوص مدیر پروژه ────────────────────────────────────────────
async def test_member_cannot_do_lead_only_actions(client, db_session) -> None:  # type: ignore[no-untyped-def]
    lead_token, _ = await _actor(client, LEAD_A)
    member_token, member_id = await _actor(client, MEMBER)
    project_id, milestone_id = await _project_with_team(client, lead_token, member_token)

    blocked = [
        await client.patch(
            f"/api/v1/projects/{project_id}",
            headers=auth(member_token),
            json=project_payload(),
        ),
        await client.post(
            f"/api/v1/projects/{project_id}/milestones",
            headers=auth(member_token),
            json=milestone_payload(title_fa="مرحلهٔ خودسرانه"),
        ),
        await client.patch(
            f"/api/v1/milestones/{milestone_id}",
            headers=auth(member_token),
            json=milestone_payload(title_fa="تغییر خودسرانه"),
        ),
        await client.get(f"/api/v1/projects/{project_id}/applications", headers=auth(member_token)),
        await client.post(
            f"/api/v1/projects/{project_id}/cancel",
            headers=auth(member_token),
            json={"reason": "دلم خواست"},
        ),
        await client.post(
            f"/api/v1/projects/{project_id}/complete",
            headers=auth(member_token),
            json={"final_report": "گزارش نهایی ساختگی"},
        ),
        await client.delete(
            f"/api/v1/projects/{project_id}/team/{member_id}",
            headers=auth(member_token),
            params={"reason": "حذف خودسرانه"},
        ),
    ]
    assert [r.status_code for r in blocked] == [403] * len(blocked)


async def test_member_cannot_review_a_deliverable(client, db_session) -> None:  # type: ignore[no-untyped-def]
    """§6.2 — «بررسی تحویل‌دادنی» فقط مدیر، منتور، استاد و ادمین."""
    lead_token, _ = await _actor(client, LEAD_A)
    member_token, _ = await _actor(client, MEMBER)
    project_id, milestone_id = await _project_with_team(client, lead_token, member_token)

    submitted = await client.post(
        f"/api/v1/milestones/{milestone_id}/deliverables",
        headers=auth(member_token),
        json={"body": "گزارش عضو"},
    )
    assert submitted.status_code == 201, submitted.text

    response = await client.post(
        f"/api/v1/deliverables/{submitted.json()['id']}/review",
        headers=auth(member_token),
        json={"decision": "APPROVED", "score": 10},
    )
    assert response.status_code == 403, response.text


async def test_outsider_cannot_submit_a_deliverable(client, db_session) -> None:  # type: ignore[no-untyped-def]
    lead_token, _ = await _actor(client, LEAD_A)
    outsider_token, _ = await _actor(client, OUTSIDER)
    _, milestone_id = await _project_with_team(client, lead_token)

    response = await client.post(
        f"/api/v1/milestones/{milestone_id}/deliverables",
        headers=auth(outsider_token),
        json={"body": "من که عضو نیستم"},
    )
    assert response.status_code == 403, response.text


# ── قلمرو: مدیر پروژهٔ الف در پروژهٔ ب ──────────────────────────────────
async def test_lead_of_one_project_has_no_power_over_another(client, db_session) -> None:  # type: ignore[no-untyped-def]
    """§6.4 — اگر مجوز قلمرو نداشت، همین تست سبز می‌ماند و اشکال پنهان می‌شد."""
    lead_a_token, _ = await _actor(client, LEAD_A)
    lead_b_token, _ = await _actor(client, LEAD_B)
    _, _ = await _project_with_team(client, lead_a_token)
    project_b, milestone_b = await _project_with_team(client, lead_b_token)

    blocked = [
        await client.patch(
            f"/api/v1/projects/{project_b}", headers=auth(lead_a_token), json=project_payload()
        ),
        await client.post(
            f"/api/v1/projects/{project_b}/milestones",
            headers=auth(lead_a_token),
            json=milestone_payload(),
        ),
        await client.patch(
            f"/api/v1/milestones/{milestone_b}",
            headers=auth(lead_a_token),
            json=milestone_payload(),
        ),
        await client.get(f"/api/v1/projects/{project_b}/applications", headers=auth(lead_a_token)),
        await client.get(f"/api/v1/projects/{project_b}/review-queue", headers=auth(lead_a_token)),
        await client.post(f"/api/v1/projects/{project_b}/publish", headers=auth(lead_a_token)),
    ]
    assert [r.status_code for r in blocked] == [403] * len(blocked)


async def test_lead_cannot_decide_another_projects_application(client, db_session) -> None:  # type: ignore[no-untyped-def]
    lead_a_token, _ = await _actor(client, LEAD_A)
    lead_b_token, _ = await _actor(client, LEAD_B)
    applicant_token, _ = await _actor(client, MEMBER)
    project_b, _ = await _project_with_team(client, lead_b_token)

    # پروژهٔ ب پس از `start` دیگر `OPEN` نیست؛ توقف و از سرگیری آن را
    # به `OPEN` برمی‌گرداند تا بتوان درخواست داد.
    await client.post(
        f"/api/v1/projects/{project_b}/pause",
        headers=auth(lead_b_token),
        json={"reason": "بازگشت به پذیرش"},
    )
    await client.post(f"/api/v1/projects/{project_b}/resume", headers=auth(lead_b_token))

    applied = await client.post(
        f"/api/v1/projects/{project_b}/applications",
        headers=auth(applicant_token),
        json={"motivation": "انگیزه‌نامهٔ کاملاً معتبر برای این پروژه."},
    )
    assert applied.status_code == 201, applied.text

    response = await client.post(
        f"/api/v1/applications/{applied.json()['id']}/decide",
        headers=auth(lead_a_token),
        json={"decision": "ACCEPTED"},
    )
    assert response.status_code == 403, response.text


# ── بدون احراز هویت ────────────────────────────────────────────────────
@pytest.mark.parametrize(
    ("method", "suffix"),
    [
        ("get", "/team"),
        ("get", "/milestones"),
        ("get", "/tasks"),
        ("get", "/discussion"),
        ("get", "/activity"),
        ("get", "/applications"),
        ("post", "/publish"),
    ],
)
async def test_anonymous_requests_are_rejected(  # type: ignore[no-untyped-def]
    client, db_session, method: str, suffix: str
) -> None:
    lead_token, _ = await _actor(client, LEAD_A)
    project_id, _ = await _project_with_team(client, lead_token)

    response = await getattr(client, method)(f"/api/v1/projects/{project_id}{suffix}")
    assert response.status_code == 401, response.text


async def test_removed_member_loses_access_immediately(client, db_session) -> None:  # type: ignore[no-untyped-def]
    """§6.4 قاعدهٔ ۵ — حذف عضو باید کش نقش را فوراً باطل کند."""
    lead_token, _ = await _actor(client, LEAD_A)
    member_token, member_id = await _actor(client, MEMBER)
    project_id, _ = await _project_with_team(client, lead_token, member_token)

    allowed = await client.get(f"/api/v1/projects/{project_id}/tasks", headers=auth(member_token))
    assert allowed.status_code == 200, allowed.text

    removed = await client.delete(
        f"/api/v1/projects/{project_id}/team/{member_id}",
        headers=auth(lead_token),
        params={"reason": "غیبت طولانی"},
    )
    assert removed.status_code == 204, removed.text

    blocked = await client.get(f"/api/v1/projects/{project_id}/tasks", headers=auth(member_token))
    assert blocked.status_code == 403, blocked.text
