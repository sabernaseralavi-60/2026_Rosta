"""بازتاب پایان پروژه — FR-PRJ-08، ADR-0024 برش الف.

PostgreSQL واقعی لازم است: امتیاز از کلید یکتای دفتر کل و اعلان از صف
`notifications` می‌آید؛ هیچ‌کدام در حافظه شبیه‌سازی نمی‌شوند.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import func, select, update
from tests.integration.helpers import auth, complete_profile, login
from tests.integration.test_admin_public_flow import _completed_project, _kinds
from tests.integration.test_gamification_flow import _active, _ledger
from tests.integration.test_workspace import _running_project

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

OUTSIDER = "09121880003"
LEARNED = "یاد گرفتم مصاحبهٔ مشتری را با سؤال باز شروع کنم و یادداشت‌ها را همان روز مرور کنم."


def _body(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "learned": LEARNED,
        "challenges": "هماهنگی زمان مصاحبه‌ها",
        "would_do_differently": "زودتر سراغ مشتری‌ها می‌رفتم",
        "satisfaction": 4,
    }
    payload.update(overrides)
    return payload


async def _state(client: Any, token: str, project_id: str) -> dict[str, Any]:
    response = await client.get(f"/api/v1/projects/{project_id}/reflection", headers=auth(token))
    assert response.status_code == 200, response.text
    return dict(response.json())


async def _post(client: Any, token: str, project_id: str, body: dict[str, Any]) -> Any:
    return await client.post(
        f"/api/v1/projects/{project_id}/reflection", headers=auth(token), json=body
    )


# ── پیش از پایان ────────────────────────────────────────────────────────
async def test_reflection_waits_for_the_project_to_close(client, db_session) -> None:  # type: ignore[no-untyped-def]
    lead_token, member_token, _, project_id, _ = await _running_project(client)

    state = await _state(client, member_token, project_id)
    assert state["can_submit"] is False
    assert "بسته شدن" in state["reason"]

    response = await _post(client, member_token, project_id, _body())
    assert response.status_code == 409, response.text
    assert _active(await _ledger(client, member_token), "REFLECTION_SUBMITTED") == []


# ── پس از پایان ─────────────────────────────────────────────────────────
async def test_state_before_writing_shows_the_reward_and_the_minimum(client, db_session) -> None:  # type: ignore[no-untyped-def]
    scene = await _completed_project(client, db_session)

    state = await _state(client, scene["member_token"], scene["project_id"])
    assert state["can_submit"] is True
    assert state["reflection"] is None
    assert state["points"] == 15
    assert state["min_learned_chars"] == 30


async def test_writing_it_earns_fifteen_learning_points_once(client, db_session) -> None:  # type: ignore[no-untyped-def]
    scene = await _completed_project(client, db_session)
    token, project_id = scene["member_token"], scene["project_id"]

    response = await _post(client, token, project_id, _body())
    assert response.status_code == 201, response.text
    assert response.json()["learned"] == LEARNED

    [entry] = _active(await _ledger(client, token), "REFLECTION_SUBMITTED")
    assert Decimal(entry["amount"]) == 15
    assert entry["category"] == "LEARNING"

    # دوباره ۴۰۹ و امتیاز همان یکی؛ وضعیت حالا بازتاب خودش را نشان می‌دهد.
    again = await _post(client, token, project_id, _body(learned=LEARNED + " و بیشتر"))
    assert again.status_code == 409, again.text
    assert len(_active(await _ledger(client, token), "REFLECTION_SUBMITTED")) == 1

    state = await _state(client, token, project_id)
    assert state["can_submit"] is False
    assert state["reflection"]["learned"] == LEARNED


async def test_a_one_word_reflection_is_refused_and_earns_nothing(client, db_session) -> None:  # type: ignore[no-untyped-def]
    scene = await _completed_project(client, db_session)
    token, project_id = scene["member_token"], scene["project_id"]

    for learned in ("خوب بود", "   " + "الف" * 5 + "   "):
        response = await _post(client, token, project_id, _body(learned=learned))
        assert response.status_code == 422, response.text
    assert _active(await _ledger(client, token), "REFLECTION_SUBMITTED") == []

    # فقط بخش الزامی سنجیده می‌شود؛ بقیه اختیاری‌اند.
    ok = await _post(client, token, project_id, {"learned": LEARNED})
    assert ok.status_code == 201, ok.text
    assert ok.json()["satisfaction"] is None


async def test_satisfaction_outside_one_to_five_is_refused(client, db_session) -> None:  # type: ignore[no-untyped-def]
    scene = await _completed_project(client, db_session)
    for value in (0, 6):
        response = await _post(
            client, scene["member_token"], scene["project_id"], _body(satisfaction=value)
        )
        assert response.status_code == 422, response.text


async def test_every_member_writes_their_own_including_the_lead(client, db_session) -> None:  # type: ignore[no-untyped-def]
    scene = await _completed_project(client, db_session)
    project_id = scene["project_id"]

    assert (await _post(client, scene["member_token"], project_id, _body())).status_code == 201
    lead_state = await _state(client, scene["lead_token"], project_id)
    assert lead_state["can_submit"] is True, "بازتاب عضو دیگر جلوی مدیر را نمی‌گیرد"
    assert lead_state["reflection"] is None, "بازتاب خصوصی است"

    other = LEARNED.replace("مصاحبهٔ مشتری", "گزارش فروش")
    assert (
        await _post(client, scene["lead_token"], project_id, _body(learned=other))
    ).status_code == 201
    assert len(_active(await _ledger(client, scene["lead_token"]), "REFLECTION_SUBMITTED")) == 1

    from silp.models.delivery import ProjectReflection

    count = await db_session.scalar(select(func.count()).select_from(ProjectReflection))
    assert count == 2


async def test_only_team_members_may_read_or_write(client, db_session) -> None:  # type: ignore[no-untyped-def]
    scene = await _completed_project(client, db_session)
    token = await login(client, OUTSIDER)
    await complete_profile(client, token, first_name="بیرونی")

    response = await client.get(
        f"/api/v1/projects/{scene['project_id']}/reflection", headers=auth(token)
    )
    assert response.status_code == 403, response.text
    response = await _post(client, token, scene["project_id"], _body())
    assert response.status_code == 403, response.text
    assert _active(await _ledger(client, token), "REFLECTION_SUBMITTED") == []


async def test_a_member_who_left_cannot_write(client, db_session) -> None:  # type: ignore[no-untyped-def]
    """عضو «فعال» — کسی که پیش از بسته شدن تیم را ترک کرد، بازتاب ندارد."""
    from silp.models.project import TeamMember

    scene = await _completed_project(client, db_session)
    await db_session.execute(
        update(TeamMember)
        .where(TeamMember.user_id == scene["member_id"])
        .values(status="LEFT", left_at=func.now())
    )
    await db_session.flush()

    response = await _post(client, scene["member_token"], scene["project_id"], _body())
    assert response.status_code == 403, response.text


async def test_unknown_field_is_refused(client, db_session) -> None:  # type: ignore[no-untyped-def]
    scene = await _completed_project(client, db_session)
    response = await _post(client, scene["member_token"], scene["project_id"], _body(score=5))
    assert response.status_code == 422, response.text


# ── امتیاز و اعلان ──────────────────────────────────────────────────────
async def test_a_disabled_rule_keeps_the_reflection_but_awards_nothing(client, db_session) -> None:  # type: ignore[no-untyped-def]
    from silp.models.gamification import PointRule

    scene = await _completed_project(client, db_session)
    await db_session.execute(
        update(PointRule).where(PointRule.code == "REFLECTION_SUBMITTED").values(is_active=False)
    )
    await db_session.flush()

    state = await _state(client, scene["member_token"], scene["project_id"])
    assert state["points"] is None

    response = await _post(client, scene["member_token"], scene["project_id"], _body())
    assert response.status_code == 201, response.text
    assert _active(await _ledger(client, scene["member_token"]), "REFLECTION_SUBMITTED") == []


async def test_closing_the_project_asks_every_active_member_once(client, db_session) -> None:  # type: ignore[no-untyped-def]
    from silp.models.messaging import Notification

    scene = await _completed_project(client, db_session)
    for user_id in (scene["lead_id"], scene["member_id"]):
        assert (await _kinds(db_session, user_id)).count("REFLECTION_REQUESTED") == 1

    row = await db_session.scalar(
        select(Notification).where(
            Notification.user_id == scene["member_id"], Notification.kind == "REFLECTION_REQUESTED"
        )
    )
    assert row is not None
    assert row.action_url == f"/projects/{scene['project_id']}/workspace"
    assert "15" not in row.body, "ارقام باید فارسی نمایش داده شوند"
    assert "۱۵ امتیاز" in row.body


async def test_unknown_project_is_not_found(client, db_session) -> None:  # type: ignore[no-untyped-def]
    token = await login(client, OUTSIDER)
    await complete_profile(client, token, first_name="بیرونی")
    response = await client.get(
        "/api/v1/projects/00000000-0000-0000-0000-000000000000/reflection", headers=auth(token)
    )
    assert response.status_code == 404, response.text
