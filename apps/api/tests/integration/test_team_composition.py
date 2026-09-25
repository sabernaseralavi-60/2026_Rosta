"""پیشنهاد خودکار ترکیب تیم — FR-TEAM-04، ADR-0027.

مسیر فقط می‌خواند، پس آزمون دوام (`test_write_durability`) لازم نیست. نیمرخ‌ها
از API واقعی ساخته می‌شوند؛ سطح مهارت هر نفر جدا تنظیم می‌شود تا پوشش
متفاوت داشته باشند.
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import func, select
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

from silp.models.messaging import Notification

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

LEAD, MEMBER, ALPHA, BETA, GAMMA, HIDDEN, OUTSIDER = (f"091212600{n:02d}" for n in range(1, 8))


async def _person(
    client: Any, mobile: str, name: str, levels: tuple[int, int], *, public: bool = True
) -> tuple[str, str]:
    """`levels` = سطح دو مهارت اول."""
    token = await login(client, mobile)
    await complete_profile(client, token, first_name=name, skill_level=1)
    skills = await taxonomy_ids(client, "skills", limit=2)
    response = await client.patch(
        "/api/v1/me/survey/skills",
        headers=auth(token),
        json={
            "skills": [{"skill_id": s, "level": lv} for s, lv in zip(skills, levels, strict=True)]
        },
    )
    assert response.status_code == 200, response.text
    if public:
        response = await client.patch(
            "/api/v1/me/profile", headers=auth(token), json={"is_public": True}
        )
        assert response.status_code == 200, response.text
    return token, str((await me(client, token))["id"])


async def _project(client: Any, lead_token: str) -> str:
    skills = await taxonomy_ids(client, "skills", limit=2)
    created = await client.post(
        "/api/v1/projects",
        headers=auth(lead_token),
        json=project_payload(
            required_skills=[{"skill_id": s, "min_level": 3} for s in skills], team_size_max=4
        ),
    )
    assert created.status_code == 201, created.text
    project_id = str(created.json()["id"])
    response = await client.post(
        f"/api/v1/projects/{project_id}/milestones",
        headers=auth(lead_token),
        json=milestone_payload(),
    )
    assert response.status_code == 201, response.text
    published = await client.post(
        f"/api/v1/projects/{project_id}/publish", headers=auth(lead_token)
    )
    assert published.status_code == 200, published.text
    return project_id


async def _compose(client: Any, token: str, project_id: str, **params: Any) -> Any:
    return await client.get(
        "/api/v1/teams/compose",
        headers=auth(token),
        params={"project_id": project_id, **params},
    )


async def test_composition_covers_both_gaps_and_skips_private_profiles(client, db_session) -> None:  # type: ignore[no-untyped-def]
    lead, _ = await _person(client, LEAD, "صابر", (1, 1), public=False)
    _, alpha = await _person(client, ALPHA, "الف", (4, 1))
    _, beta = await _person(client, BETA, "ب", (1, 4))
    _, gamma = await _person(client, GAMMA, "گ", (4, 4))
    _, hidden = await _person(client, HIDDEN, "پنهان", (5, 5), public=False)
    project_id = await _project(client, lead)

    response = await _compose(client, lead, project_id, seats=2)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["project"]["id"] == project_id
    assert len(body["gaps"]) == 2 and body["seats"] == 2

    compositions = body["compositions"]
    assert compositions, "دست‌کم یک ترکیب باید پیشنهاد شود"
    everyone = {m["user"]["id"] for c in compositions for m in c["members"]}
    assert hidden not in everyone  # فقط نیمرخ عمومی (FR-TEAM-01)

    best = compositions[0]
    assert best["coverage_percent"] == 100.0 and best["uncovered"] == []
    assert [m["user"]["id"] for m in best["members"]] == [gamma]  # یک نفر کافی است
    assert all(m["covers"] and m["reason"] for c in compositions for m in c["members"])

    sets = [frozenset(m["user"]["id"] for m in c["members"]) for c in compositions]
    assert len(set(sets)) == len(sets)
    # آلفا و بتا هر کدام نیمی از کمبود را می‌پوشانند؛ فقط با هم کامل‌اند.
    for members in sets:
        if members & {alpha, beta} and gamma not in members:
            assert members == {alpha, beta}

    # فقط‌خواندنی: فراخوانی هیچ اعلانی نمی‌سازد.
    async def notifications() -> int:
        return int(await db_session.scalar(select(func.count()).select_from(Notification)) or 0)

    before = await notifications()
    assert (await _compose(client, lead, project_id, seats=2)).status_code == 200
    assert await notifications() == before


async def test_only_the_lead_may_ask_and_outsiders_see_nothing(client, db_session) -> None:  # type: ignore[no-untyped-def]
    lead, _ = await _person(client, LEAD, "صابر", (1, 1), public=False)
    member, member_id = await _person(client, MEMBER, "عضو", (1, 1))
    outsider, _ = await _person(client, OUTSIDER, "بیرونی", (1, 1))
    project_id = await _project(client, lead)

    applied = await client.post(
        f"/api/v1/projects/{project_id}/applications",
        headers=auth(member),
        json={"motivation": "انگیزه‌نامهٔ کاملاً معتبر برای این پروژه."},
    )
    assert applied.status_code == 201, applied.text
    decided = await client.post(
        f"/api/v1/applications/{applied.json()['id']}/decide",
        headers=auth(lead),
        json={"decision": "ACCEPTED"},
    )
    assert decided.status_code == 200, decided.text
    await invalidate(member_id)

    assert (await _compose(client, member, project_id)).status_code == 403
    assert (await _compose(client, outsider, project_id)).status_code == 404
    assert (await _compose(client, lead, "00000000-0000-0000-0000-000000000000")).status_code == 404
    assert (await _compose(client, lead, project_id, seats=6)).status_code == 422
    assert (await _compose(client, lead, project_id, seats=0)).status_code == 422
    assert (
        await client.get("/api/v1/teams/compose", params={"project_id": project_id})
    ).status_code == 401


async def test_no_gaps_or_no_candidates_returns_an_empty_list(client, db_session) -> None:  # type: ignore[no-untyped-def]
    strong, _ = await _person(client, LEAD, "صابر", (5, 5), public=False)
    project_id = await _project(client, strong)
    body = (await _compose(client, strong, project_id)).json()
    assert body["gaps"] == [] and body["compositions"] == []

    weak, _ = await _person(client, MEMBER, "ضعیف", (1, 1), public=False)
    project_id = await _project(client, weak)
    body = (await _compose(client, weak, project_id)).json()
    assert len(body["gaps"]) == 2 and body["compositions"] == []
