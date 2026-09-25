"""تحلیل مشارکت تیمی — FR-PRJ-08، ADR-0026.

مسیر فقط می‌خواند، پس آزمون دوام (`test_write_durability`) لازم نیست. شمارها
را از API واقعی می‌سازیم (وظیفه، گفتگو)؛ تحویل تأییدشده و فعالیت تأییدشده را
مستقیم در دیتابیس می‌گذاریم چون مسیر تأییدشان جای دیگری آزموده می‌شود.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import select
from tests.integration.helpers import auth, complete_profile, invalidate, login, me
from tests.integration.test_peer_evaluation import OUTSIDER, Team, _person, _team

from silp.core.permissions import Role, ScopeType
from silp.models.delivery import Deliverable, Milestone
from silp.models.venture import VentureMetric
from silp.services import authz

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


def _url(team: Team) -> str:
    return f"/api/v1/projects/{team.project_id}/contribution"


async def _get(client: Any, team: Team, token: str) -> Any:
    return await client.get(_url(team), headers=auth(token))


async def _task(client: Any, team: Team, who: int, *, assignee: int | None, status: str) -> None:
    body: dict[str, Any] = {"title": "وظیفهٔ آزمایشی", "status": status}
    if assignee is not None:
        body["assignee_id"] = team.people[assignee][1]
    response = await client.post(
        f"/api/v1/projects/{team.project_id}/tasks", headers=auth(team.people[who][0]), json=body
    )
    assert response.status_code == 201, response.text


async def _say(client: Any, team: Team, who: int, times: int = 1) -> None:
    for _ in range(times):
        response = await client.post(
            f"/api/v1/projects/{team.project_id}/discussion",
            headers=auth(team.people[who][0]),
            json={"body": "یک پیام کوتاه برای تیم."},
        )
        assert response.status_code == 201, response.text


async def _approve_deliverable(
    db_session: Any, team: Team, who: int, *, status: str, version: int = 1
) -> None:
    """تحویلی به نام `people[who]`؛ بازبین `people[0]` (مدیر) است، مگر خودش تحویل داده باشد."""
    milestone = await db_session.scalar(
        select(Milestone).where(Milestone.project_id == uuid.UUID(team.project_id))
    )
    reviewer = team.people[1 if who == 0 else 0][1]
    db_session.add(
        Deliverable(
            milestone_id=milestone.id,
            submitter_id=uuid.UUID(team.people[who][1]),
            version=version,
            body="تحویل آزمایشی",
            status=status,
            feedback="بازخورد" if status in ("CHANGES_REQUESTED", "REJECTED") else None,
            reviewed_by=uuid.UUID(reviewer),
            reviewed_at=datetime.now(UTC),
        )
    )
    await db_session.flush()


async def _verified_activity(db_session: Any, team: Team, who: int, *, status: str) -> None:
    reviewed = status != "PENDING"
    db_session.add(
        VentureMetric(
            project_id=uuid.UUID(team.project_id),
            user_id=uuid.UUID(team.people[who][1]),
            metric="CALLS",
            value=5,
            occurred_on=datetime.now(UTC).date(),
            status=status,
            reviewed_by=uuid.UUID(team.people[(who + 1) % len(team.people)][1])
            if reviewed
            else None,
            reviewed_at=datetime.now(UTC) if reviewed else None,
        )
    )
    await db_session.flush()


def _row(body: dict[str, Any], team: Team, who: int) -> dict[str, Any]:
    (row,) = [m for m in body["members"] if m["user_id"] == team.people[who][1]]
    return dict(row)


def _signal(row: dict[str, Any], dimension: str) -> dict[str, Any]:
    (signal,) = [s for s in row["signals"] if s["dimension"] == dimension]
    return dict(signal)


# ── دید ────────────────────────────────────────────────────────────────
async def test_the_lead_sees_every_member_ordered_by_share(client, db_session) -> None:  # type: ignore[no-untyped-def]
    team = await _team(client, 3, close=False)
    await _task(client, team, 0, assignee=2, status="DONE")
    await _task(client, team, 0, assignee=2, status="DONE")
    await _task(client, team, 0, assignee=1, status="DONE")

    response = await _get(client, team, team.lead[0])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["scope"] == "TEAM"
    assert [m["user_id"] for m in body["members"]][:2] == [team.people[2][1], team.people[1][1]]
    assert _row(body, team, 2)["share_percent"] == pytest.approx(66.7)
    assert _row(body, team, 1)["share_percent"] == pytest.approx(33.3)
    assert _row(body, team, 0)["share_percent"] == 0.0
    assert next(d for d in body["dimensions"] if d["dimension"] == "TASKS")["team_total"] == 3


async def test_a_regular_member_only_gets_their_own_row(client, db_session) -> None:  # type: ignore[no-untyped-def]
    team = await _team(client, 3, close=False)
    await _task(client, team, 0, assignee=1, status="DONE")
    await _task(client, team, 0, assignee=2, status="DONE")
    await _say(client, team, 1, 2)

    response = await _get(client, team, team.people[1][0])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["scope"] == "SELF"
    # نه اینکه پنهان باشد: ردیف دیگران اصلاً در پاسخ نیست.
    assert [m["user_id"] for m in body["members"]] == [team.people[1][1]]
    assert team.people[2][1] not in response.text
    assert team.people[0][1] not in response.text
    assert all(d["team_total"] is None for d in body["dimensions"])
    # سهم او هنوز نسبت به کل تیم سنجیده می‌شود.
    assert body["members"][0]["share_percent"] > 50


async def test_a_supervising_instructor_sees_the_whole_team(client, db_session) -> None:  # type: ignore[no-untyped-def]
    team = await _team(client, 2, close=False)
    await _task(client, team, 0, assignee=1, status="DONE")

    token = await login(client, "09121920090")
    await complete_profile(client, token, first_name="استاد")
    teacher = await me(client, token)
    await authz.grant_role(
        db_session,
        user_id=uuid.UUID(teacher["id"]),
        role=Role.INSTRUCTOR,
        scope_type=ScopeType.PROJECT,
        scope_id=uuid.UUID(team.project_id),
    )
    await db_session.flush()
    await invalidate(teacher["id"])

    response = await _get(client, team, token)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["scope"] == "TEAM"
    assert len(body["members"]) == 2


async def test_an_outsider_and_a_non_supervising_mentor_are_refused(client, db_session) -> None:  # type: ignore[no-untyped-def]
    team = await _team(client, 2, close=False)

    stranger, _ = await _person(client, OUTSIDER, "غریبه")
    assert (await _get(client, team, stranger)).status_code == 403

    token = await login(client, "09121920091")
    await complete_profile(client, token, first_name="منتور")
    mentor = await me(client, token)
    await authz.grant_role(db_session, user_id=uuid.UUID(mentor["id"]), role=Role.MENTOR)
    await db_session.flush()
    await invalidate(mentor["id"])
    assert (await _get(client, team, token)).status_code == 403


async def test_a_project_without_a_team_yet_is_a_conflict(client, db_session) -> None:  # type: ignore[no-untyped-def]
    from tests.integration.helpers import project_payload, taxonomy_ids

    lead, _ = await _person(client, "09121920092", "صابر")
    skills = await taxonomy_ids(client, "skills", limit=1)
    created = await client.post(
        "/api/v1/projects",
        headers=auth(lead),
        json=project_payload(required_skills=[{"skill_id": skills[0], "min_level": 3}]),
    )
    assert created.status_code == 201, created.text

    response = await client.get(
        f"/api/v1/projects/{created.json()['id']}/contribution", headers=auth(lead)
    )
    assert response.status_code == 409, response.text
    assert "تیم" in response.json()["error"]["message"]


# ── شمارش ──────────────────────────────────────────────────────────────
async def test_only_approved_done_verified_and_undeleted_things_count(client, db_session) -> None:  # type: ignore[no-untyped-def]
    team = await _team(client, 2, close=False)
    member = 1

    await _approve_deliverable(db_session, team, member, status="APPROVED")
    await _approve_deliverable(db_session, team, member, status="CHANGES_REQUESTED", version=2)
    await _approve_deliverable(db_session, team, member, status="REJECTED", version=3)
    await _verified_activity(db_session, team, member, status="VERIFIED")
    await _verified_activity(db_session, team, member, status="PENDING")
    await _verified_activity(db_session, team, member, status="REJECTED")
    await _task(client, team, 0, assignee=member, status="DONE")
    await _task(client, team, 0, assignee=member, status="DOING")
    await _task(client, team, 0, assignee=member, status="TODO")
    await _task(client, team, 0, assignee=None, status="DONE")
    await _say(client, team, member, 3)

    row = _row((await _get(client, team, team.lead[0])).json(), team, member)
    assert _signal(row, "DELIVERABLES")["count"] == 1
    assert _signal(row, "VERIFIED_ACTIVITY")["count"] == 1
    assert _signal(row, "TASKS")["count"] == 1, "وظیفهٔ بی‌مسئول برای هیچ‌کس نیست"
    assert _signal(row, "DISCUSSION")["count"] == 3
    assert row["is_silent"] is False


async def test_a_deleted_message_stops_counting(client, db_session) -> None:  # type: ignore[no-untyped-def]
    team = await _team(client, 2, close=False)
    posted = await client.post(
        f"/api/v1/projects/{team.project_id}/discussion",
        headers=auth(team.people[1][0]),
        json={"body": "پیامی که پاک می‌شود."},
    )
    assert posted.status_code == 201, posted.text
    await _say(client, team, 1)

    deleted = await client.delete(
        f"/api/v1/projects/{team.project_id}/discussion/{posted.json()['id']}",
        headers=auth(team.people[1][0]),
    )
    assert deleted.status_code == 204, deleted.text

    row = _row((await _get(client, team, team.lead[0])).json(), team, 1)
    assert _signal(row, "DISCUSSION")["count"] == 1


async def test_a_deliverable_belongs_to_its_submitter_not_its_reviewer(client, db_session) -> None:  # type: ignore[no-untyped-def]
    team = await _team(client, 2, close=False)
    await _approve_deliverable(db_session, team, 1, status="APPROVED")

    body = (await _get(client, team, team.lead[0])).json()
    assert _signal(_row(body, team, 1), "DELIVERABLES")["share_percent"] == 100.0
    assert _signal(_row(body, team, 0), "DELIVERABLES")["count"] == 0


async def test_chatter_cannot_buy_more_than_its_dimension_is_worth(client, db_session) -> None:  # type: ignore[no-untyped-def]
    team = await _team(client, 2, close=False)
    await _approve_deliverable(db_session, team, 0, status="APPROVED")
    await _verified_activity(db_session, team, 0, status="VERIFIED")
    await _task(client, team, 0, assignee=0, status="DONE")
    await _say(client, team, 1, 30)

    body = (await _get(client, team, team.lead[0])).json()
    assert _row(body, team, 1)["share_percent"] == pytest.approx(15.0)
    assert _row(body, team, 0)["share_percent"] == pytest.approx(85.0)


async def test_nothing_recorded_means_no_share_and_everyone_active_is_silent(
    client, db_session
) -> None:  # type: ignore[no-untyped-def]
    team = await _team(client, 2, close=False)

    body = (await _get(client, team, team.lead[0])).json()
    assert [m["share_percent"] for m in body["members"]] == [None, None]
    assert all(m["is_silent"] for m in body["members"])
    assert all(d["weight"] == 0 for d in body["dimensions"])


async def test_a_member_who_left_keeps_their_share_and_is_not_silent(client, db_session) -> None:  # type: ignore[no-untyped-def]
    team = await _team(client, 3, close=False)
    await _task(client, team, 0, assignee=2, status="DONE")
    await _task(client, team, 0, assignee=0, status="DONE")
    left = await client.post(
        f"/api/v1/projects/{team.project_id}/leave",
        headers=auth(team.people[2][0]),
        json={"reason": "درگیری درسی"},
    )
    assert left.status_code == 204, left.text

    body = (await _get(client, team, team.lead[0])).json()
    row = _row(body, team, 2)
    assert row["status"] == "LEFT"
    assert row["left_at"] is not None
    assert row["share_percent"] == 50.0, "کارش رفته است، سهمش نه"
    assert _row(body, team, 1)["is_silent"] is True

    # و خودش، که دیگر عضو نیست، دید ندارد.
    assert (await _get(client, team, team.people[2][0])).status_code == 403


async def test_someone_who_left_and_came_back_is_counted_once(client, db_session) -> None:  # type: ignore[no-untyped-def]
    from silp.models.project import Team as TeamRow
    from silp.models.project import TeamMember

    team = await _team(client, 2, close=False)
    await _task(client, team, 0, assignee=1, status="DONE")
    # ردیف دوم برای همان کاربر (رفت و برگشت): جمع تیم نباید دوبرابر شود.
    team_row = await db_session.scalar(
        select(TeamRow).where(TeamRow.project_id == uuid.UUID(team.project_id))
    )
    db_session.add(
        TeamMember(
            team_id=team_row.id,
            user_id=uuid.UUID(team.people[1][1]),
            status="LEFT",
            joined_at=datetime(2020, 1, 1, tzinfo=UTC),
            left_at=datetime(2020, 2, 1, tzinfo=UTC),
        )
    )
    await db_session.flush()

    body = (await _get(client, team, team.lead[0])).json()
    assert len(body["members"]) == 2
    assert next(d for d in body["dimensions"] if d["dimension"] == "TASKS")["team_total"] == 1
    assert _row(body, team, 1)["share_percent"] == 100.0
