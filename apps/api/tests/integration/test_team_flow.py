"""تیم — M7-07 و M7-08، FR-TEAM-01/02/03، §8.14، ADR-0015.

جستجوی هم‌تیمی (فقط نیمرخ عمومی، مکملیت با تیم پروژه)، و آگهی: ثبت،
اعلان هدفمند، درخواست، پذیرش با ردِ خودکار بقیه، انقضا و تمدید، و
`TEAM_FORMED` فقط پس از اولین کار تأییدشدهٔ تیم.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import func, select, update
from tests.integration.helpers import auth, complete_profile, grant_role, login, me, taxonomy_ids
from tests.integration.test_project_lifecycle import _published_project

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

LEAD = "09121240001"
EXPERT = "09121240002"
SECOND = "09121240003"
NEWBIE = "09121240004"
MENTOR = "09121240005"


def _today() -> str:
    return (datetime.now(UTC) + timedelta(hours=3, minutes=30)).date().isoformat()


async def _person(
    client: Any, mobile: str, first_name: str, *, skill_level: int = 4, public: bool = False
) -> tuple[str, str]:
    token = await login(client, mobile)
    await complete_profile(client, token, first_name=first_name, skill_level=skill_level)
    if public:
        response = await client.patch(
            "/api/v1/me/profile", headers=auth(token), json={"is_public": True}
        )
        assert response.status_code == 200, response.text
    return token, str((await me(client, token))["id"])


async def _points(db_session: Any, user_id: str, rule: str) -> Decimal:
    from silp.models.gamification import PointEntry

    total = await db_session.scalar(
        select(func.coalesce(func.sum(PointEntry.amount), 0)).where(
            PointEntry.user_id == user_id, PointEntry.rule_code == rule
        )
    )
    return Decimal(total)


async def _kinds(db_session: Any, user_id: str) -> list[str]:
    from silp.models.messaging import Notification

    return list(
        await db_session.scalars(select(Notification.kind).where(Notification.user_id == user_id))
    )


# ── جستجو — FR-TEAM-01 ─────────────────────────────────────────────────
async def test_only_public_profiles_are_searchable(client, db_session) -> None:  # type: ignore[no-untyped-def]
    lead, _ = await _person(client, LEAD, "صابر", skill_level=1)
    _, expert_id = await _person(client, EXPERT, "علی")
    skill = (await taxonomy_ids(client, "skills", limit=1))[0]

    found = (await client.get("/api/v1/teams/search", headers=auth(lead))).json()
    assert found["total"] == 0
    assert found["context"]["my_profile_is_public"] is False

    await _person(client, EXPERT, "علی", public=True)
    found = (
        await client.get(
            "/api/v1/teams/search",
            headers=auth(lead),
            params={"skill_id": skill, "min_level": 4},
        )
    ).json()
    assert [item["user"]["id"] for item in found["items"]] == [expert_id]
    item = found["items"][0]
    assert item["complement_score"] is None  # بدون پروژه، عددی نیست
    assert item["stronger_reason"] is not None and "قوی‌تر" in item["stronger_reason"]

    none = (
        await client.get(
            "/api/v1/teams/search",
            headers=auth(lead),
            params={"skill_id": skill, "min_level": 5},
        )
    ).json()
    assert none["total"] == 0


async def test_complement_ranks_against_the_project_team(client, db_session) -> None:  # type: ignore[no-untyped-def]
    lead, _ = await _person(client, LEAD, "صابر", skill_level=1)
    _, expert_id = await _person(client, EXPERT, "علی", skill_level=4, public=True)
    _, newbie_id = await _person(client, NEWBIE, "نیما", skill_level=2, public=True)
    project_id = await _published_project(client, db_session, lead)

    found = (
        await client.get(
            "/api/v1/teams/search",
            headers=auth(lead),
            params={"complement_project_id": project_id},
        )
    ).json()
    assert found["context"]["project"]["id"] == project_id
    assert found["context"]["can_invite"] is True
    assert len(found["context"]["gaps"]) == 1
    ranked = [item["user"]["id"] for item in found["items"]]
    assert ranked.index(expert_id) < ranked.index(newbie_id)
    top = found["items"][ranked.index(expert_id)]
    assert top["complement_score"] == 100.0
    assert "هیچ‌کس در تیم ندارد" in top["complement_reason"]

    # تیم پروژهٔ دیگران برای بیرونی «وجود ندارد».
    outsider, _ = await _person(client, SECOND, "سمیرا")
    response = await client.get(
        "/api/v1/teams/search",
        headers=auth(outsider),
        params={"complement_project_id": project_id},
    )
    assert response.status_code == 404


# ── آگهی — FR-TEAM-02/03 ───────────────────────────────────────────────
async def _opening(client: Any, token: str, **body: Any) -> dict[str, Any]:
    skill = (await taxonomy_ids(client, "skills", limit=1))[0]
    payload = {
        "title": "تحلیلگر GIS",
        "description": "برای نقشه‌کشی تقاطع‌های پرتصادف به یک هم‌تیمی GIS نیاز داریم.",
        "needed_skill_ids": [skill],
        "commitment_hpw": 6,
        **body,
    }
    response = await client.post("/api/v1/teams/openings", headers=auth(token), json=payload)
    assert response.status_code == 201, response.text
    return dict(response.json())


async def test_opening_lifecycle_and_team_formed(client, db_session) -> None:  # type: ignore[no-untyped-def]
    from silp.models.delivery import Milestone

    lead, lead_id = await _person(client, LEAD, "صابر", skill_level=1)
    expert, expert_id = await _person(client, EXPERT, "علی")
    second, second_id = await _person(client, SECOND, "سمیرا")
    mentor, mentor_id = await _person(client, MENTOR, "منتور", skill_level=1)
    await grant_role(db_session, mentor_id, "MENTOR")
    project_id = await _published_project(client, db_session, lead, team_size_max=4)

    # فقط مدیر پروژه آگهی می‌دهد.
    response = await client.post(
        "/api/v1/teams/openings",
        headers=auth(expert),
        json={
            "project_id": project_id,
            "title": "تحلیلگر GIS",
            "description": "به یک هم‌تیمی GIS نیاز داریم برای نقشه.",
        },
    )
    assert response.status_code == 403
    managed = (await client.get("/api/v1/teams/managed", headers=auth(lead))).json()
    assert [t["id"] for t in managed] == [project_id]

    opening = await _opening(client, lead, project_id=project_id)
    assert opening["effective_status"] == "OPEN" and opening["can_manage"] is True
    # اعلان هدفمند به دانشجویان هم‌خوان (سطح ۴)، نه به مدیر پروژه.
    assert "OPENING_MATCH" in await _kinds(db_session, expert_id)
    assert "OPENING_MATCH" not in await _kinds(db_session, lead_id)

    listing = (await client.get("/api/v1/teams/openings")).json()
    assert [o["id"] for o in listing["items"]] == [opening["id"]]
    assert listing["items"][0]["pending_count"] is None  # مهمان شمارش نمی‌بیند

    apply = f"/api/v1/teams/openings/{opening['id']}/apply"
    response = await client.post(apply, headers=auth(expert), json={"message": "GIS بلدم."})
    assert response.status_code == 201, response.text
    accepted = response.json()
    response = await client.post(apply, headers=auth(expert), json={"message": "دوباره"})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "DUPLICATE_APPLICATION"
    response = await client.post(apply, headers=auth(second), json={"message": "من هم."})
    assert response.status_code == 201
    declined = response.json()
    assert "OPENING_APPLIED" in await _kinds(db_session, lead_id)

    newcomer = await login(client, NEWBIE)
    response = await client.post(apply, headers=auth(newcomer), json={"message": "سلام"})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "PROFILE_INCOMPLETE"

    detail = (
        await client.get(f"/api/v1/teams/openings/{opening['id']}", headers=auth(lead))
    ).json()
    assert detail["pending_count"] == 2 and len(detail["applications"]) == 2

    # پذیرش یکی ⇒ عضویت، آگهی پر، بقیه خودکار رد با یادداشت.
    response = await client.post(
        f"/api/v1/teams/applications/{accepted['id']}/decide",
        headers=auth(lead),
        json={"decision": "ACCEPTED"},
    )
    assert response.status_code == 200, response.text
    mine = (await client.get("/api/v1/teams/applications/mine", headers=auth(second))).json()
    assert mine[0]["id"] == declined["id"] and mine[0]["status"] == "DECLINED"
    assert mine[0]["decision_note"] == "این جای خالی پر شد."
    assert "OPENING_DECIDED" in await _kinds(db_session, expert_id)
    assert "OPENING_DECIDED" in await _kinds(db_session, second_id)
    response = await client.post(apply, headers=auth(mentor), json={"message": "هنوز جا هست؟"})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "OPENING_CLOSED"
    assert (await client.get("/api/v1/teams/openings")).json()["total"] == 0

    # TEAM_FORMED: نه با پذیرش، بلکه با اولین تحویل تأییدشده — و نه وقتی
    # تأییدکننده خود آگهی‌دهنده است.
    assert await _points(db_session, lead_id, "TEAM_FORMED") == Decimal(0)
    milestone_id = await db_session.scalar(
        select(Milestone.id).where(Milestone.project_id == project_id)
    )
    submit = f"/api/v1/milestones/{milestone_id}/deliverables"
    response = await client.post(
        submit, headers=auth(expert), json={"body": "نقشهٔ تقاطع‌ها", "links": []}
    )
    assert response.status_code == 201, response.text
    response = await client.post(
        f"/api/v1/deliverables/{response.json()['id']}/review",
        headers=auth(lead),
        json={"decision": "CHANGES_REQUESTED", "feedback": "لایهٔ حجم تردد را بیفزا."},
    )
    assert response.status_code == 200, response.text
    response = await client.post(
        submit, headers=auth(expert), json={"body": "نقشه با لایهٔ تردد", "links": []}
    )
    assert response.status_code == 201, response.text
    response = await client.post(
        f"/api/v1/deliverables/{response.json()['id']}/review",
        headers=auth(mentor),
        json={"decision": "APPROVED", "score": 40},
    )
    assert response.status_code == 200, response.text
    assert await _points(db_session, lead_id, "TEAM_FORMED") == Decimal(15)


async def test_expired_opening_rejects_applications_until_renewed(client, db_session) -> None:  # type: ignore[no-untyped-def]
    from silp.models.delivery import TeamOpening
    from silp.services.opening_service import OpeningService

    lead, lead_id = await _person(client, LEAD, "صابر", skill_level=1)
    expert, _ = await _person(client, EXPERT, "علی")
    project_id = await _published_project(client, db_session, lead, team_size_max=4)
    opening = await _opening(client, lead, project_id=project_id)
    await db_session.execute(
        update(TeamOpening)
        .where(TeamOpening.id == opening["id"])
        .values(expires_at=datetime.now(UTC) - timedelta(hours=1))
    )
    await db_session.flush()

    assert (await client.get("/api/v1/teams/openings")).json()["total"] == 0
    response = await client.post(
        f"/api/v1/teams/openings/{opening['id']}/apply",
        headers=auth(expert),
        json={"message": "GIS بلدم."},
    )
    assert response.json()["error"]["code"] == "OPENING_CLOSED"
    response = await client.get(f"/api/v1/teams/openings/{opening['id']}", headers=auth(expert))
    assert response.status_code == 404  # منقضی برای بیرونی دیده نمی‌شود

    assert await OpeningService(db_session).notify_expired() == 1
    assert await OpeningService(db_session).notify_expired() == 0  # بی‌اثر در تکرار
    assert "OPENING_EXPIRED" in await _kinds(db_session, lead_id)

    mine = (
        await client.get("/api/v1/teams/openings", headers=auth(lead), params={"mine": True})
    ).json()
    assert mine["items"][0]["effective_status"] == "EXPIRED"
    response = await client.post(
        f"/api/v1/teams/openings/{opening['id']}/renew", headers=auth(lead)
    )
    assert response.status_code == 200
    assert response.json()["effective_status"] == "OPEN"
    response = await client.post(
        f"/api/v1/teams/openings/{opening['id']}/apply",
        headers=auth(expert),
        json={"message": "GIS بلدم."},
    )
    assert response.status_code == 201


async def test_venture_opening_team_formed_from_verified_metric(client, db_session) -> None:  # type: ignore[no-untyped-def]
    founder, founder_id = await _person(client, LEAD, "صابر")
    member, _ = await _person(client, EXPERT, "علی")
    mentor, mentor_id = await _person(client, MENTOR, "منتور")
    await grant_role(db_session, mentor_id, "MENTOR")
    venture = (
        await client.post(
            "/api/v1/ventures",
            headers=auth(founder),
            json={
                "name": "خرمای صابر",
                "pitch": "فروش مستقیم خرمای مضافتی بم به خانواده‌های تهرانی.",
            },
        )
    ).json()
    opening = await _opening(client, founder, venture_id=venture["id"], needed_skill_ids=[])
    assert opening["target"]["kind"] == "VENTURE"
    application = (
        await client.post(
            f"/api/v1/teams/openings/{opening['id']}/apply",
            headers=auth(member),
            json={"message": "فروش بلدم."},
        )
    ).json()
    response = await client.post(
        f"/api/v1/teams/applications/{application['id']}/decide",
        headers=auth(founder),
        json={"decision": "ACCEPTED"},
    )
    assert response.status_code == 200, response.text

    metric = (
        await client.post(
            f"/api/v1/ventures/{venture['id']}/metrics",
            headers=auth(member),
            json={"metric": "MEETINGS", "value": 2, "occurred_on": _today()},
        )
    ).json()
    response = await client.post(
        f"/api/v1/metrics/{metric['id']}/review",
        headers=auth(mentor),
        json={"decision": "VERIFIED"},
    )
    assert response.status_code == 200, response.text
    assert await _points(db_session, founder_id, "TEAM_FORMED") == Decimal(15)
