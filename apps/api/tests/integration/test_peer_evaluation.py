"""ارزیابی همتا — FR-PRJ-08، ADR-0024 برش ب.

PostgreSQL واقعی لازم است: امتیاز از کلید یکتای دفتر کل و «یک‌بار برای هر
(ارزیابی‌کننده، پروژه)» از کلید اصلی سه‌ستونهٔ `peer_evaluations` می‌آید.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import func, select, update
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
from tests.integration.test_gamification_flow import _active, _ledger

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

MOBILES = [f"091219200{n:02d}" for n in range(1, 8)]
OUTSIDER = "09121920099"


class Team:
    """پروژهٔ بسته‌شده با مدیر و چند عضو؛ `people[0]` مدیر است."""

    def __init__(self, project_id: str, people: list[tuple[str, str]]) -> None:
        self.project_id = project_id
        self.people = people

    @property
    def lead(self) -> tuple[str, str]:
        return self.people[0]

    @property
    def members(self) -> list[tuple[str, str]]:
        return self.people[1:]


async def _person(client: Any, mobile: str, first_name: str) -> tuple[str, str]:
    token = await login(client, mobile)
    await complete_profile(client, token, first_name=first_name)
    return token, str((await me(client, token))["id"])


async def _team(client: Any, size: int, *, close: bool = True) -> Team:
    """مدیر + (size-1) عضو، همه پذیرفته‌شده؛ پروژه در جریان یا (close) بسته."""
    names = ["صابر", "مینا", "زهرا", "علی", "نیما", "سارا", "رضا"]
    people = [await _person(client, MOBILES[i], names[i]) for i in range(size)]
    lead_token = people[0][0]

    skills = await taxonomy_ids(client, "skills", limit=1)
    created = await client.post(
        "/api/v1/projects",
        headers=auth(lead_token),
        json=project_payload(
            required_skills=[{"skill_id": skills[0], "min_level": 3}], team_size_max=max(size, 2)
        ),
    )
    assert created.status_code == 201, created.text
    project_id = created.json()["id"]
    # مرحلهٔ اختیاری: بستن پروژه به تأیید تحویل‌دادنی وابسته نیست.
    response = await client.post(
        f"/api/v1/projects/{project_id}/milestones",
        headers=auth(lead_token),
        json=milestone_payload(is_required=False, points=0),
    )
    assert response.status_code == 201, response.text
    await client.post(f"/api/v1/projects/{project_id}/publish", headers=auth(lead_token))

    for token, user_id in people[1:]:
        applied = await client.post(
            f"/api/v1/projects/{project_id}/applications",
            headers=auth(token),
            json={"motivation": "انگیزه‌نامهٔ کاملاً معتبر برای این پروژه."},
        )
        assert applied.status_code == 201, applied.text
        decided = await client.post(
            f"/api/v1/applications/{applied.json()['id']}/decide",
            headers=auth(lead_token),
            json={"decision": "ACCEPTED"},
        )
        assert decided.status_code == 200, decided.text
        await invalidate(user_id)
    started = await client.post(f"/api/v1/projects/{project_id}/start", headers=auth(lead_token))
    assert started.status_code == 200, started.text

    if close:
        closed = await client.post(
            f"/api/v1/projects/{project_id}/complete",
            headers=auth(lead_token),
            json={"final_report": "بسته شد تا ارزیابی همتا انجام شود."},
        )
        assert closed.status_code == 200, closed.text
    return Team(project_id, people)


def _url(team: Team, suffix: str = "") -> str:
    return f"/api/v1/projects/{team.project_id}/peer-evaluations{suffix}"


def _ratings(
    team: Team, who: int, *, contribution: int = 4, reliability: int | None = 5
) -> dict[str, Any]:
    """ارزیابی کاملِ `people[who]` از همهٔ هم‌تیمی‌های دیگر."""
    return {
        "evaluations": [
            {"evaluatee_id": user_id, "contribution": contribution, "reliability": reliability}
            for index, (_, user_id) in enumerate(team.people)
            if index != who
        ]
    }


async def _put(client: Any, team: Team, who: int, body: dict[str, Any] | None = None) -> Any:
    return await client.put(
        _url(team), headers=auth(team.people[who][0]), json=body or _ratings(team, who)
    )


async def _state(client: Any, team: Team, who: int) -> dict[str, Any]:
    response = await client.get(_url(team), headers=auth(team.people[who][0]))
    assert response.status_code == 200, response.text
    return dict(response.json())


async def _summary(client: Any, team: Team, who: int = 0) -> Any:
    return await client.get(_url(team, "/summary"), headers=auth(team.people[who][0]))


def _earned(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return _active(items, "PEER_EVAL_COMPLETED")


# ── پیش از پایان و تیم تک‌نفره ──────────────────────────────────────────
async def test_evaluation_waits_for_the_project_to_close(client, db_session) -> None:  # type: ignore[no-untyped-def]
    team = await _team(client, 3, close=False)

    state = await _state(client, team, 1)
    assert state["can_submit"] is False
    assert "بسته شدن" in state["reason"]
    assert len(state["peers"]) == 2

    response = await _put(client, team, 1)
    assert response.status_code == 409, response.text
    assert _earned(await _ledger(client, team.people[1][0])) == []


async def test_a_one_person_team_has_no_peers_and_no_points(client, db_session) -> None:  # type: ignore[no-untyped-def]
    team = await _team(client, 1)

    state = await _state(client, team, 0)
    assert state["can_submit"] is False
    assert state["peers"] == []
    assert "تک‌نفره" in state["reason"]

    stranger = str(uuid.uuid4())
    response = await client.put(
        _url(team),
        headers=auth(team.lead[0]),
        json={"evaluations": [{"evaluatee_id": stranger, "contribution": 3}]},
    )
    assert response.status_code == 409, response.text
    assert _earned(await _ledger(client, team.lead[0])) == []


# ── مسیر خوش ────────────────────────────────────────────────────────────
async def test_state_lists_the_other_active_members_and_the_reward(client, db_session) -> None:  # type: ignore[no-untyped-def]
    team = await _team(client, 3)

    state = await _state(client, team, 1)
    assert state["can_submit"] is True
    assert state["points"] == 5
    assert state["mine"] == []
    assert [p["user_id"] for p in state["peers"]] == [team.people[0][1], team.people[2][1]]
    assert state["peers"][0]["is_lead"] is True
    assert state["peers"][0]["full_name"] == "صابر رستمی"


async def test_rating_everyone_earns_five_community_points_once(client, db_session) -> None:  # type: ignore[no-untyped-def]
    team = await _team(client, 4)
    token = team.people[1][0]

    response = await _put(client, team, 1)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["can_submit"] is False
    assert len(body["mine"]) == 3
    assert {row["contribution"] for row in body["mine"]} == {4}

    # ۳ همتا، ولی ۵ امتیاز (نه ۱۵): امتیاز برای «انجام» است، یک‌بار برای پروژه.
    [entry] = _earned(await _ledger(client, token))
    assert Decimal(entry["amount"]) == 5
    assert entry["category"] == "COMMUNITY"

    again = await _put(client, team, 1, _ratings(team, 1, contribution=1))
    assert again.status_code == 409, again.text
    assert len(_earned(await _ledger(client, token))) == 1

    from silp.models.delivery import PeerEvaluation

    stored = await db_session.scalars(
        select(PeerEvaluation.contribution).where(
            PeerEvaluation.project_id == uuid.UUID(team.project_id)
        )
    )
    assert list(stored) == [4, 4, 4], "دومی نباید چیزی را عوض کند"


async def test_reliability_is_optional(client, db_session) -> None:  # type: ignore[no-untyped-def]
    team = await _team(client, 2)
    response = await _put(client, team, 1, _ratings(team, 1, reliability=None))
    assert response.status_code == 200, response.text
    assert response.json()["mine"][0]["reliability"] is None
    assert len(_earned(await _ledger(client, team.people[1][0]))) == 1


async def test_the_lead_evaluates_too(client, db_session) -> None:  # type: ignore[no-untyped-def]
    team = await _team(client, 3)
    assert (await _put(client, team, 0)).status_code == 200
    assert len(_earned(await _ledger(client, team.lead[0]))) == 1


# ── ناقص، اضافی، بی‌معنی ────────────────────────────────────────────────
async def test_an_incomplete_evaluation_is_refused_and_earns_nothing(client, db_session) -> None:  # type: ignore[no-untyped-def]
    team = await _team(client, 4)
    token = team.people[1][0]
    body = _ratings(team, 1)
    body["evaluations"].pop()

    response = await _put(client, team, 1, body)
    assert response.status_code == 422, response.text
    assert "ناقص" in response.json()["error"]["message"]
    assert (await _state(client, team, 1))["can_submit"] is True, "چیزی نیمه‌کاره ذخیره نشد"
    assert _earned(await _ledger(client, token)) == []


async def test_only_other_active_members_can_be_rated(client, db_session) -> None:  # type: ignore[no-untyped-def]
    team = await _team(client, 3)
    outsider_token, outsider_id = await _person(client, OUTSIDER, "بیرونی")
    del outsider_token

    for extra in (outsider_id, team.people[1][1]):  # بیرونی، و خودِ ارزیابی‌کننده
        body = _ratings(team, 1)
        body["evaluations"].append({"evaluatee_id": extra, "contribution": 3})
        response = await _put(client, team, 1, body)
        assert response.status_code == 422, response.text

    duplicate = _ratings(team, 1)
    duplicate["evaluations"].append(dict(duplicate["evaluations"][0]))
    assert (await _put(client, team, 1, duplicate)).status_code == 422
    assert _earned(await _ledger(client, team.people[1][0])) == []


@pytest.mark.parametrize("field", ["contribution", "reliability"])
@pytest.mark.parametrize("value", [0, 6])
async def test_ratings_outside_one_to_five_are_refused(client, db_session, field, value) -> None:  # type: ignore[no-untyped-def]
    team = await _team(client, 2)
    body = _ratings(team, 1)
    body["evaluations"][0][field] = value
    response = await _put(client, team, 1, body)
    assert response.status_code == 422, response.text


async def test_the_note_column_is_not_collected(client, db_session) -> None:  # type: ignore[no-untyped-def]
    """ADR-0024 بند ۱۰: `note` را نه رابط می‌گیرد نه API."""
    team = await _team(client, 2)
    body = _ratings(team, 1)
    body["evaluations"][0]["note"] = "خیلی کم‌کار بود"
    response = await _put(client, team, 1, body)
    assert response.status_code == 422, response.text

    body = _ratings(team, 1)
    body["note"] = "متن آزاد"
    assert (await _put(client, team, 1, body)).status_code == 422


# ── دسترسی ──────────────────────────────────────────────────────────────
async def test_only_team_members_may_read_write_or_summarise(client, db_session) -> None:  # type: ignore[no-untyped-def]
    team = await _team(client, 2)
    token = await login(client, OUTSIDER)
    await complete_profile(client, token, first_name="بیرونی")

    assert (await client.get(_url(team), headers=auth(token))).status_code == 403
    assert (
        await client.put(_url(team), headers=auth(token), json=_ratings(team, 1))
    ).status_code == 403
    assert (await client.get(_url(team, "/summary"), headers=auth(token))).status_code == 403
    assert _earned(await _ledger(client, token)) == []


async def test_a_member_who_left_neither_rates_nor_is_required(client, db_session) -> None:  # type: ignore[no-untyped-def]
    from silp.models.project import TeamMember

    team = await _team(client, 4)
    leaver = team.people[3][1]
    await db_session.execute(
        update(TeamMember)
        .where(TeamMember.user_id == uuid.UUID(leaver))
        .values(status="LEFT", left_at=func.now())
    )
    await db_session.flush()

    assert (await _put(client, team, 3)).status_code == 403

    # همتایان دیگر لازم نیست او را ارزیابی کنند، و اگر بکنند ۴۲۲ می‌گیرند.
    state = await _state(client, team, 1)
    assert [p["user_id"] for p in state["peers"]] == [team.people[0][1], team.people[2][1]]
    assert (await _put(client, team, 1, _ratings(team, 1))).status_code == 422
    body = {
        "evaluations": [e for e in _ratings(team, 1)["evaluations"] if e["evaluatee_id"] != leaver]
    }
    assert (await _put(client, team, 1, body)).status_code == 200


async def test_unknown_project_is_not_found(client, db_session) -> None:  # type: ignore[no-untyped-def]
    token = await login(client, OUTSIDER)
    await complete_profile(client, token, first_name="بیرونی")
    response = await client.get(
        "/api/v1/projects/00000000-0000-0000-0000-000000000000/peer-evaluations",
        headers=auth(token),
    )
    assert response.status_code == 404, response.text


# ── امتیاز ──────────────────────────────────────────────────────────────
async def test_a_disabled_rule_keeps_the_evaluation_but_awards_nothing(client, db_session) -> None:  # type: ignore[no-untyped-def]
    from silp.models.gamification import PointRule

    team = await _team(client, 2)
    await db_session.execute(
        update(PointRule).where(PointRule.code == "PEER_EVAL_COMPLETED").values(is_active=False)
    )
    await db_session.flush()

    assert (await _state(client, team, 1))["points"] is None
    response = await _put(client, team, 1)
    assert response.status_code == 200, response.text
    assert len(response.json()["mine"]) == 1
    assert _earned(await _ledger(client, team.people[1][0])) == []


async def test_giving_five_stars_to_everyone_earns_the_same_as_honest_ratings(  # type: ignore[no-untyped-def]
    client, db_session
) -> None:
    """امتیاز برای انجام است، نه برای مقدار — تورم نمره سودی ندارد."""
    team = await _team(client, 3)
    await _put(client, team, 1, _ratings(team, 1, contribution=5, reliability=5))
    await _put(client, team, 2, _ratings(team, 2, contribution=1, reliability=1))

    first = _earned(await _ledger(client, team.people[1][0]))
    second = _earned(await _ledger(client, team.people[2][0]))
    assert [Decimal(e["amount"]) for e in first + second] == [5, 5]


# ── خلاصه — فقط مدیر، فقط میانگین، فقط با ارزیابی کافی ───────────────────
async def test_only_the_lead_may_see_the_summary(client, db_session) -> None:  # type: ignore[no-untyped-def]
    team = await _team(client, 3)
    assert (await _summary(client, team, 0)).status_code == 200
    for who in (1, 2):
        response = await _summary(client, team, who)
        assert response.status_code == 403, response.text


async def test_summary_shows_averages_once_two_others_have_rated(client, db_session) -> None:  # type: ignore[no-untyped-def]
    team = await _team(client, 4)
    # مدیر همه را ۱ می‌دهد؛ نظر او در میانگین دیگران نمی‌آید.
    await _put(client, team, 0, _ratings(team, 0, contribution=1, reliability=1))
    await _put(client, team, 1, _ratings(team, 1, contribution=5, reliability=4))
    await _put(client, team, 2, _ratings(team, 2, contribution=3, reliability=None))
    await _put(client, team, 3, _ratings(team, 3, contribution=4, reliability=2))

    response = await _summary(client, team)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["min_evaluations"] == 2

    by_id = {row["user_id"]: row for row in body["members"]}
    assert team.lead[1] not in by_id, "مدیر نتیجهٔ خودش را نمی‌بیند"
    assert len(by_id) == 3

    # دریافتی‌های نفر ۱: از ۲ ← ۳ و از ۳ ← ۴ (نظر مدیر: ۱، نمی‌آید).
    first = by_id[team.people[1][1]]
    assert first["evaluations"] == 2
    assert first["contribution_avg"] == 3.5
    assert first["reliability_avg"] is None, "قابل‌اعتماد بودن فقط یک مقدار دارد"

    # دریافتی‌های نفر ۲: از ۱ ← ۵ و از ۳ ← ۴؛ اعتماد: ۴ و ۲.
    second = by_id[team.people[2][1]]
    assert second["contribution_avg"] == 4.5
    assert second["reliability_avg"] == 3.0


async def test_summary_hides_an_average_that_would_be_one_persons_opinion(  # type: ignore[no-untyped-def]
    client, db_session
) -> None:
    team = await _team(client, 2)
    await _put(client, team, 0)
    await _put(client, team, 1)

    body = (await _summary(client, team)).json()
    [row] = body["members"]
    # تنها ارزیابی‌کنندهٔ او خودِ مدیر است و نظر مدیر در میانگین نمی‌آید.
    assert row["evaluations"] == 0
    assert row["contribution_avg"] is None
    assert row["reliability_avg"] is None


async def test_the_leads_own_rating_cannot_be_subtracted_out(client, db_session) -> None:  # type: ignore[no-untyped-def]
    """تیم سه‌نفره: اگر نظر مدیر در میانگین می‌آمد، با کم‌کردنش نظر نفر سوم عیناً لو می‌رفت."""
    team = await _team(client, 3)
    await _put(client, team, 0, _ratings(team, 0, contribution=2))
    await _put(client, team, 2, _ratings(team, 2, contribution=5))

    body = (await _summary(client, team)).json()
    for row in body["members"]:
        assert row["evaluations"] <= 1
        assert row["contribution_avg"] is None


async def test_summary_before_anyone_rated_is_empty_not_an_error(client, db_session) -> None:  # type: ignore[no-untyped-def]
    team = await _team(client, 3)
    body = (await _summary(client, team)).json()
    assert [row["evaluations"] for row in body["members"]] == [0, 0]
    assert all(row["contribution_avg"] is None for row in body["members"])


async def test_summary_never_names_who_gave_which_rating(client, db_session) -> None:  # type: ignore[no-untyped-def]
    team = await _team(client, 4)
    for who in range(4):
        await _put(client, team, who, _ratings(team, who, contribution=2 + who))

    body = (await _summary(client, team)).json()
    assert set(body) == {"min_evaluations", "members"}
    for row in body["members"]:
        assert set(row) == {
            "user_id",
            "full_name",
            "evaluations",
            "contribution_avg",
            "reliability_avg",
        }
