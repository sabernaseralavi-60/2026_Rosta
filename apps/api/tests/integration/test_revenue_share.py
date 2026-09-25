"""سهم دانشجو از فروش تأییدشده و گزارش درآمد — FR-VEN-03، ADR-0025.

PostgreSQL واقعی لازم است: سهم هنگام تأیید روی ردیف ثبت می‌شود و قیدهای
مهاجرت ۰۰۲۱ هم باید در خود دیتابیس آزموده شوند.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select, update
from tests.integration.helpers import auth, complete_profile, grant_role, login, me
from tests.integration.test_project_lifecycle import _published_project

from silp.domain.calendar import to_jalali
from silp.domain.text import to_persian_digits
from silp.models.project import Project

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

LEAD = "09121330001"
SELLER = "09121330002"
OUTSIDER = "09121330003"
MENTOR = "09121330004"


def _local_day(days_ago: int = 0) -> Any:
    local = datetime.now(UTC) + timedelta(hours=3, minutes=30) - timedelta(days=days_ago)
    return local.date()


def _day(days_ago: int = 0) -> str:
    return str(_local_day(days_ago).isoformat())


async def _person(client: Any, mobile: str, name: str) -> tuple[str, str]:
    token = await login(client, mobile)
    await complete_profile(client, token, first_name=name)
    return token, str((await me(client, token))["id"])


async def _set_rewards(db_session: Any, project_id: str, rewards: dict[str, Any]) -> None:
    await db_session.execute(
        update(Project).where(Project.id == project_id).values(rewards=rewards)
    )
    await db_session.flush()


async def _team(client: Any, db_session: Any, *, percent: Any = 15) -> dict[str, Any]:
    """پروژهٔ نوع A با یک مدیر، یک فروشنده و درصد سهم داده‌شده."""
    lead, lead_id = await _person(client, LEAD, "مدیر")
    seller, seller_id = await _person(client, SELLER, "آرین")
    await grant_role(db_session, lead_id, "MENTOR")
    project_id = await _published_project(
        client, db_session, lead, kind="A_VENTURE", team_size_max=4
    )
    rewards: dict[str, Any] = {"points": 200}
    if percent is not None:
        rewards["revenue_share_percent"] = percent
    await _set_rewards(db_session, project_id, rewards)

    username = (await me(client, seller))["username"]
    invite = await client.post(
        f"/api/v1/projects/{project_id}/invitations",
        headers=auth(lead),
        json={"username": username},
    )
    assert invite.status_code == 201, invite.text
    accept = await client.post(
        f"/api/v1/invitations/{invite.json()['id']}/accept", headers=auth(seller)
    )
    assert accept.status_code == 200, accept.text
    return {"lead": lead, "seller": seller, "seller_id": seller_id, "project_id": project_id}


async def _sale(
    client: Any,
    team: dict[str, Any],
    value: int,
    *,
    days_ago: int = 0,
    metric: str = "SALES_AMOUNT",
) -> dict[str, Any]:
    response = await client.post(
        f"/api/v1/projects/{team['project_id']}/metrics",
        headers=auth(team["seller"]),
        json={
            "metric": metric,
            "value": value,
            "occurred_on": _day(days_ago),
            "note": "جعبهٔ مضافتی",
        },
    )
    assert response.status_code == 201, response.text
    return dict(response.json())


async def _review(client: Any, team: dict[str, Any], metric_id: str, **body: Any) -> Any:
    return await client.post(
        f"/api/v1/metrics/{metric_id}/review",
        headers=auth(team["lead"]),
        json={"decision": "VERIFIED", **body},
    )


async def _report(client: Any, token: str) -> dict[str, Any]:
    response = await client.get("/api/v1/me/revenue", headers=auth(token))
    assert response.status_code == 200, response.text
    return dict(response.json())


async def test_verified_sale_freezes_the_share_and_later_edits_do_not_move_it(  # type: ignore[no-untyped-def]
    client, db_session
) -> None:
    team = await _team(client, db_session)
    row = await _sale(client, team, 12_000_000)
    assert row["share_percent"] is None and row["share_rial"] is None  # هنوز ادعاست

    reviewed = await _review(client, team, row["id"])
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["share_percent"] == 15.0
    assert reviewed.json()["share_rial"] == 1_800_000

    # مدیر بعداً درصد را عوض می‌کند؛ ماه بسته‌شده نباید جابه‌جا شود.
    changed = {"points": 200, "revenue_share_percent": 50}
    await _set_rewards(db_session, team["project_id"], changed)

    report = await _report(client, team["seller"])
    assert report["total_sales_rial"] == 12_000_000
    assert report["total_share_rial"] == 1_800_000
    line = report["months"][0]["lines"][0]
    assert line["share_percent"] == 15.0 and line["share_rial"] == 1_800_000
    assert line["project_id"] == team["project_id"]
    assert line["note"] == "جعبهٔ مضافتی"

    url = f"/api/v1/projects/{team['project_id']}/metrics"
    board = (await client.get(url, headers=auth(team["lead"]))).json()
    assert board["share_percent"] == 50.0  # درصد فعلی پروژه، نه عکس ردیف‌ها
    assert board["share_total_rial"] == 1_800_000
    assert board["by_member"][0]["share_rial"] == 1_800_000
    assert board["items"][0]["share_rial"] == 1_800_000


async def test_report_groups_by_jalali_month_of_the_sale_not_the_review(  # type: ignore[no-untyped-def]
    client, db_session
) -> None:
    team = await _team(client, db_session, percent=10)
    recent = await _sale(client, team, 10_000_000)
    older = await _sale(client, team, 4_000_000, days_ago=40)  # همیشه ماه شمسی دیگر
    for row in (recent, older):
        assert (await _review(client, team, row["id"])).status_code == 200

    report = await _report(client, team["seller"])
    assert [m["sales_rial"] for m in report["months"]] == [10_000_000, 4_000_000]
    assert [m["share_rial"] for m in report["months"]] == [1_000_000, 400_000]

    assert [m["month"] for m in report["months"]] == [
        to_jalali(_local_day())[1],
        to_jalali(_local_day(40))[1],
    ]
    first = report["months"][0]
    assert first["title"].endswith(to_persian_digits(first["year"]))
    assert report["total_share_rial"] == 1_400_000


async def test_pending_is_listed_apart_and_rejected_is_left_out(client, db_session) -> None:  # type: ignore[no-untyped-def]
    team = await _team(client, db_session)
    verified = await _sale(client, team, 6_000_000)
    rejected = await _sale(client, team, 3_000_000)
    await _sale(client, team, 2_000_000)  # در انتظار می‌ماند

    assert (await _review(client, team, verified["id"])).status_code == 200
    denied = await _review(
        client, team, rejected["id"], decision="REJECTED", note="رسید فروش پیوست نیست."
    )
    assert denied.status_code == 200 and denied.json()["share_rial"] is None

    report = await _report(client, team["seller"])
    assert report["total_sales_rial"] == 6_000_000
    assert report["total_share_rial"] == 900_000
    assert report["pending_sales_rial"] == 2_000_000
    assert report["pending_count"] == 1
    assert sum(len(m["lines"]) for m in report["months"]) == 1


async def test_no_agreed_percent_means_a_zero_share_but_the_sale_still_shows(  # type: ignore[no-untyped-def]
    client, db_session
) -> None:
    team = await _team(client, db_session, percent=None)
    row = await _sale(client, team, 5_000_000)
    reviewed = await _review(client, team, row["id"])
    assert reviewed.json()["share_percent"] == 0.0
    assert reviewed.json()["share_rial"] == 0

    report = await _report(client, team["seller"])
    assert report["total_sales_rial"] == 5_000_000 and report["total_share_rial"] == 0


async def test_only_sales_amount_carries_a_share(client, db_session) -> None:  # type: ignore[no-untyped-def]
    team = await _team(client, db_session)
    count = await _sale(client, team, 3, metric="SALES_COUNT")
    reviewed = await _review(client, team, count["id"])
    assert reviewed.status_code == 200
    assert reviewed.json()["share_rial"] is None

    report = await _report(client, team["seller"])
    assert report["months"] == [] and report["total_share_rial"] == 0


async def test_venture_sales_have_no_share(client, db_session) -> None:  # type: ignore[no-untyped-def]
    founder, _ = await _person(client, SELLER, "صبا")
    mentor, mentor_id = await _person(client, MENTOR, "منتور")
    await grant_role(db_session, mentor_id, "MENTOR")
    venture = await client.post(
        "/api/v1/ventures",
        headers=auth(founder),
        json={"name": "خرمای صابر", "pitch": "فروش مستقیم خرمای مضافتی بم به خانواده‌ها."},
    )
    assert venture.status_code == 201, venture.text
    venture_id = venture.json()["id"]
    metric = await client.post(
        f"/api/v1/ventures/{venture_id}/metrics",
        headers=auth(founder),
        json={"metric": "SALES_AMOUNT", "value": 9_000_000, "occurred_on": _day()},
    )
    assert metric.status_code == 201, metric.text
    reviewed = await client.post(
        f"/api/v1/metrics/{metric.json()['id']}/review",
        headers=auth(mentor),
        json={"decision": "VERIFIED"},
    )
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["share_rial"] is None

    board = (
        await client.get(f"/api/v1/ventures/{venture_id}/metrics", headers=auth(founder))
    ).json()
    assert board["share_percent"] is None and board["share_total_rial"] == 0
    assert (await _report(client, founder))["months"] == []


async def test_report_is_personal_and_needs_login(client, db_session) -> None:  # type: ignore[no-untyped-def]
    team = await _team(client, db_session)
    row = await _sale(client, team, 8_000_000)
    assert (await _review(client, team, row["id"])).status_code == 200
    outsider, _ = await _person(client, OUTSIDER, "بیرونی")

    assert (await _report(client, outsider))["total_sales_rial"] == 0
    assert (await client.get("/api/v1/me/revenue")).status_code == 401
    url = f"/api/v1/projects/{team['project_id']}/metrics"
    assert (await client.get(url, headers=auth(outsider))).status_code == 404  # §6.4 قاعدهٔ ۴


async def test_reviewing_notifies_the_seller_with_the_share(client, db_session) -> None:  # type: ignore[no-untyped-def]
    from silp.models.messaging import Notification

    team = await _team(client, db_session)
    row = await _sale(client, team, 12_000_000)
    assert (await _review(client, team, row["id"])).status_code == 200

    notification = await db_session.scalar(
        select(Notification).where(Notification.kind == "METRIC_REVIEWED")
    )
    assert notification is not None
    assert "سهمت" in notification.body
    assert "۱٬۸۰۰٬۰۰۰" in notification.body


async def test_share_constraints_hold_in_the_database(client, db_session) -> None:  # type: ignore[no-untyped-def]
    """قیدهای ۰۰۲۱ را خود دیتابیس می‌پاید، نه فقط سرویس."""
    from sqlalchemy.exc import IntegrityError

    from silp.models.venture import VentureMetric

    team = await _team(client, db_session)
    row = await _sale(client, team, 1_000_000)  # هنوز PENDING

    async def attempt(**values: Any) -> None:
        with pytest.raises(IntegrityError):
            async with db_session.begin_nested():
                await db_session.execute(
                    update(VentureMetric).where(VentureMetric.id == row["id"]).values(**values)
                )

    await attempt(share_percent=10, share_rial=100_000)  # سهم روی ردیف در انتظار
    await attempt(share_percent=10)  # جفت نیست

    assert (await _review(client, team, row["id"])).status_code == 200
    await attempt(share_percent=101, share_rial=0)
    await attempt(share_percent=10, share_rial=1_000_001)  # بیشتر از فروش
    await attempt(share_percent=10, share_rial=-1)
