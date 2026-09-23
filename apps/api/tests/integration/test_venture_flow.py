"""کارآفرینی — M7-03 و M7-04، FR-VEN-01/02، §7.7.

مسیر اصلی: ثبت کسب‌وکار ← معیار خروج ← ثبت شاخص ← تأیید دیگری ← امتیاز
← ارتقای مرحله. به‌علاوهٔ دعوت به تیم و شاخص پروژهٔ عملیاتی.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import func, select
from tests.integration.helpers import auth, complete_profile, grant_role, login, me
from tests.integration.test_project_lifecycle import _published_project

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

FOUNDER = "09121220001"
MEMBER = "09121220002"
MENTOR = "09121220003"
OUTSIDER = "09121220004"

VENTURE = {
    "name": "خرمای صابر",
    "pitch": "فروش مستقیم خرمای مضافتی بم به خانواده‌های تهرانی، بدون واسطه.",
}
PROFILE_FIELDS = {
    "description": "تیم دانشجویی فروش خرما از باغ به مصرف‌کننده.",
    "problem": "واسطه‌ها سهم باغدار را کم می‌کنند و خرما گران به دست مشتری می‌رسد.",
    "target_market": "خانواده‌های تهرانی که خرمای مرغوب می‌خواهند.",
    "revenue_model": "حاشیهٔ سود ۱۵٪ روی هر جعبه.",
}


def _today() -> str:
    return (datetime.now(UTC) + timedelta(hours=3, minutes=30)).date().isoformat()


async def _person(client: Any, mobile: str, first_name: str) -> tuple[str, str]:
    token = await login(client, mobile)
    await complete_profile(client, token, first_name=first_name)
    return token, str((await me(client, token))["id"])


async def _points(db_session: Any, user_id: str, rule: str) -> Decimal:
    from silp.models.gamification import PointEntry

    total = await db_session.scalar(
        select(func.coalesce(func.sum(PointEntry.amount), 0)).where(
            PointEntry.user_id == user_id, PointEntry.rule_code == rule
        )
    )
    return Decimal(total)


async def _venture(client: Any, token: str, **overrides: Any) -> dict[str, Any]:
    response = await client.post(
        "/api/v1/ventures", headers=auth(token), json={**VENTURE, **overrides}
    )
    assert response.status_code == 201, response.text
    return dict(response.json())


async def _metric(client: Any, token: str, venture_id: str, **body: Any) -> dict[str, Any]:
    payload = {"metric": "MEETINGS", "value": 1, "occurred_on": _today(), **body}
    response = await client.post(
        f"/api/v1/ventures/{venture_id}/metrics", headers=auth(token), json=payload
    )
    assert response.status_code == 201, response.text
    return dict(response.json())


# ── ثبت ────────────────────────────────────────────────────────────────
async def test_register_requires_a_complete_profile(client, db_session) -> None:  # type: ignore[no-untyped-def]
    token = await login(client, OUTSIDER)
    response = await client.post("/api/v1/ventures", headers=auth(token), json=VENTURE)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "PROFILE_INCOMPLETE"


async def test_register_list_and_delete_only_in_idea_stage(client, db_session) -> None:  # type: ignore[no-untyped-def]
    token, user_id = await _person(client, FOUNDER, "صبا")
    venture = await _venture(client, token, looking_for_cofounder=True, needed_roles=["بازاریاب"])
    assert venture["stage"] == "IDEA"
    assert venture["can_manage"] is True
    assert venture["member_count"] == 1
    assert await _points(db_session, user_id, "VENTURE_CREATED") == Decimal(20)

    listing = (await client.get("/api/v1/ventures", params={"q": "خرما"})).json()
    assert listing["total"] == 1
    assert listing["items"][0]["needed_roles"] == ["بازاریاب"]
    cofounder = (
        await client.get("/api/v1/ventures", params={"looking_for_cofounder": True})
    ).json()
    assert cofounder["total"] == 1

    # بیرونی صفحه را می‌بیند، ولی نه آمادگی و فروش را.
    public = (await client.get(f"/api/v1/ventures/{venture['id']}")).json()
    assert public["readiness"] is None and public["totals"] is None

    response = await client.delete(f"/api/v1/ventures/{venture['id']}", headers=auth(token))
    assert response.status_code == 204
    assert await _points(db_session, user_id, "VENTURE_CREATED") == Decimal(0)


# ── مرحله و معیار خروج — §7.7 ──────────────────────────────────────────
async def test_stage_criteria_metrics_and_points(client, db_session) -> None:  # type: ignore[no-untyped-def]
    founder, founder_id = await _person(client, FOUNDER, "صبا")
    mentor, mentor_id = await _person(client, MENTOR, "منتور")
    venture = await _venture(client, founder)
    stage_url = f"/api/v1/ventures/{venture['id']}/stage"

    # IDEA ← VALIDATION: چهار فیلد لازم است و کمبودها برمی‌گردند.
    response = await client.post(stage_url, headers=auth(founder), json={"action": "ADVANCE"})
    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "STAGE_CRITERIA_NOT_MET"
    assert len(error["details"]["missing"]) == 4

    response = await client.patch(
        f"/api/v1/ventures/{venture['id']}",
        headers=auth(founder),
        json={**VENTURE, **PROFILE_FIELDS},
    )
    assert response.status_code == 200, response.text
    assert response.json()["readiness"]["ready"] is True

    response = await client.post(stage_url, headers=auth(founder), json={"action": "ADVANCE"})
    assert response.status_code == 200, response.text
    assert response.json()["stage"] == "VALIDATION"
    assert await _points(db_session, founder_id, "VENTURE_STAGE_UP") == Decimal(50)

    # VALIDATION ← MVP: ده جلسهٔ تأییدشده. خوداظهاری کافی نیست.
    rows = [
        await _metric(client, founder, venture["id"], value=5),
        await _metric(client, founder, venture["id"], metric="LEADS", value=5),
    ]
    response = await client.post(stage_url, headers=auth(founder), json={"action": "ADVANCE"})
    assert response.status_code == 409

    # بنیان‌گذار شاخص خودش را تأیید نمی‌کند؛ منتور می‌کند.
    review = f"/api/v1/metrics/{rows[0]['id']}/review"
    response = await client.post(review, headers=auth(founder), json={"decision": "VERIFIED"})
    assert response.status_code == 403

    response = await client.post(review, headers=auth(mentor), json={"decision": "VERIFIED"})
    assert response.status_code == 403  # هنوز منتور نیست
    await grant_role(db_session, mentor_id, "MENTOR")

    queue = (await client.get("/api/v1/metrics/review-queue", headers=auth(mentor))).json()
    assert {q["id"] for q in queue} == {r["id"] for r in rows}
    assert queue[0]["owner_title"] == VENTURE["name"]

    for row in rows:
        response = await client.post(
            f"/api/v1/metrics/{row['id']}/review",
            headers=auth(mentor),
            json={"decision": "VERIFIED"},
        )
        assert response.status_code == 200, response.text
    # «۵ جلسه» سقف روزانهٔ ۵ دارد: ۵ × ۵ = ۲۵؛ سرنخ بی‌سقف: ۵ × ۳ = ۱۵.
    assert await _points(db_session, founder_id, "METRIC_MEETINGS") == Decimal(25)
    assert await _points(db_session, founder_id, "METRIC_LEADS") == Decimal(15)

    again = await client.post(
        f"/api/v1/metrics/{rows[0]['id']}/review",
        headers=auth(mentor),
        json={"decision": "REJECTED"},
    )
    assert again.status_code == 409

    response = await client.post(stage_url, headers=auth(founder), json={"action": "ADVANCE"})
    assert response.status_code == 200, response.text
    detail = response.json()
    assert detail["stage"] == "MVP"
    assert [h["to_stage"] for h in detail["history"]] == ["VALIDATION", "MVP"]
    assert detail["totals"]["verified"] == {"MEETINGS": 5, "LEADS": 5}
    # MVP=۲ ⇒ ۱۰۰؛ جمع با VALIDATION: ۱۵۰.
    assert await _points(db_session, founder_id, "VENTURE_STAGE_UP") == Decimal(150)

    # توقف دلیل می‌خواهد، ازسرگیری به همان مرحله برمی‌گردد و امتیاز تازه نمی‌دهد.
    response = await client.post(stage_url, headers=auth(founder), json={"action": "PAUSE"})
    assert response.status_code == 422
    response = await client.post(
        stage_url, headers=auth(founder), json={"action": "PAUSE", "reason": "امتحانات"}
    )
    assert response.json()["stage"] == "PAUSED"
    response = await client.post(stage_url, headers=auth(founder), json={"action": "RESUME"})
    assert response.json()["stage"] == "MVP"
    assert await _points(db_session, founder_id, "VENTURE_STAGE_UP") == Decimal(150)

    # کسب‌وکاری که از ایده گذشته، حذف نمی‌شود.
    response = await client.delete(f"/api/v1/ventures/{venture['id']}", headers=auth(founder))
    assert response.status_code == 409


async def test_rejection_needs_a_reason_and_notifies(client, db_session) -> None:  # type: ignore[no-untyped-def]
    from silp.models.messaging import Notification

    founder, founder_id = await _person(client, FOUNDER, "صبا")
    mentor, mentor_id = await _person(client, MENTOR, "منتور")
    await grant_role(db_session, mentor_id, "MENTOR")
    venture = await _venture(client, founder)
    row = await _metric(client, founder, venture["id"], metric="SALES_AMOUNT", value=12_000_000)
    url = f"/api/v1/metrics/{row['id']}/review"

    response = await client.post(url, headers=auth(mentor), json={"decision": "REJECTED"})
    assert response.status_code == 422
    response = await client.post(
        url, headers=auth(mentor), json={"decision": "REJECTED", "note": "رسید فروش پیوست نیست."}
    )
    assert response.json()["status"] == "REJECTED"
    assert await _points(db_session, founder_id, "METRIC_SALES_AMOUNT") == Decimal(0)

    notification = await db_session.scalar(
        select(Notification).where(Notification.kind == "METRIC_REVIEWED")
    )
    assert notification is not None
    assert "رد شد" in notification.title
    assert "رسید فروش" in notification.body


async def test_verified_sales_unlock_first_sale_badge(client, db_session) -> None:  # type: ignore[no-untyped-def]
    from silp.services.badge_service import BadgeService

    founder, founder_id = await _person(client, FOUNDER, "صبا")
    mentor, mentor_id = await _person(client, MENTOR, "منتور")
    await grant_role(db_session, mentor_id, "MENTOR")
    venture = await _venture(client, founder)
    row = await _metric(client, founder, venture["id"], metric="SALES_AMOUNT", value=12_000_000)
    await client.post(
        f"/api/v1/metrics/{row['id']}/review", headers=auth(mentor), json={"decision": "VERIFIED"}
    )
    # ۱۲ میلیون ریال ÷ ۵ میلیون = ۲٫۴ امتیاز.
    assert await _points(db_session, founder_id, "METRIC_SALES_AMOUNT") == Decimal("2.40")

    import uuid

    awarded = await BadgeService(db_session).evaluate_user(uuid.UUID(founder_id))
    assert "FIRST_SALE" in awarded
    assert "RAINMAKER" not in awarded


async def test_metrics_are_private_and_validated(client, db_session) -> None:  # type: ignore[no-untyped-def]
    founder, _ = await _person(client, FOUNDER, "صبا")
    outsider, _ = await _person(client, OUTSIDER, "بیرونی")
    venture = await _venture(client, founder)
    url = f"/api/v1/ventures/{venture['id']}/metrics"

    response = await client.get(url, headers=auth(outsider))
    assert response.status_code == 404
    response = await client.post(
        url, headers=auth(outsider), json={"metric": "CALLS", "value": 3, "occurred_on": _today()}
    )
    assert response.status_code == 403

    future = (datetime.now(UTC) + timedelta(days=3)).date().isoformat()
    response = await client.post(
        url, headers=auth(founder), json={"metric": "CALLS", "value": 3, "occurred_on": future}
    )
    assert response.status_code == 422

    row = await _metric(client, founder, venture["id"], metric="CALLS", value=3)
    listing = (await client.get(url, headers=auth(founder))).json()
    assert listing["totals"]["pending"] == {"CALLS": 3}
    assert listing["items"][0]["is_mine"] is True
    assert listing["metric_titles"]["CALLS"] == "تماس فروش"

    response = await client.delete(f"/api/v1/metrics/{row['id']}", headers=auth(outsider))
    assert response.status_code == 403
    response = await client.delete(f"/api/v1/metrics/{row['id']}", headers=auth(founder))
    assert response.status_code == 204


# ── تیم کسب‌وکار ───────────────────────────────────────────────────────
async def test_invite_accept_leave(client, db_session) -> None:  # type: ignore[no-untyped-def]
    founder, _ = await _person(client, FOUNDER, "صبا")
    member, member_id = await _person(client, MEMBER, "آرین")
    venture = await _venture(client, founder)
    username = (await me(client, member))["username"]
    assert username, "نام کاربری باید با ثبت نام ساخته شده باشد"

    url = f"/api/v1/ventures/{venture['id']}/invitations"
    response = await client.post(url, headers=auth(member), json={"username": username})
    assert response.status_code == 403
    response = await client.post(url, headers=auth(founder), json={"username": "no-such-user"})
    assert response.status_code == 404

    response = await client.post(
        url, headers=auth(founder), json={"username": username, "message": "بازاریاب لازم داریم."}
    )
    assert response.status_code == 201, response.text
    invitation = response.json()
    # دعوت دوباره همان دعوت است.
    again = await client.post(url, headers=auth(founder), json={"username": username})
    assert again.json()["id"] == invitation["id"]
    assert len((await client.get(url, headers=auth(founder))).json()) == 1

    mine = (await client.get("/api/v1/me/invitations", headers=auth(member))).json()
    assert [i["id"] for i in mine] == [invitation["id"]]
    assert mine[0]["target_type"] == "VENTURE"
    assert mine[0]["inviter_name"]

    response = await client.post(
        f"/api/v1/invitations/{invitation['id']}/accept", headers=auth(member)
    )
    assert response.status_code == 200, response.text
    assert response.json()["href"] == f"/ventures/{venture['id']}"

    detail = (await client.get(f"/api/v1/ventures/{venture['id']}", headers=auth(member))).json()
    assert detail["is_member"] is True and detail["member_count"] == 2
    # عضو شاخص ثبت می‌کند، ولی مرحله را عوض نمی‌کند.
    await _metric(client, member, venture["id"], metric="CALLS", value=4)
    response = await client.post(
        f"/api/v1/ventures/{venture['id']}/stage", headers=auth(member), json={"action": "CLOSE"}
    )
    assert response.status_code == 403

    response = await client.post(f"/api/v1/ventures/{venture['id']}/leave", headers=auth(member))
    assert response.status_code == 204
    response = await client.post(f"/api/v1/ventures/{venture['id']}/leave", headers=auth(founder))
    assert response.status_code == 409
    detail = (await client.get(f"/api/v1/ventures/{venture['id']}", headers=auth(founder))).json()
    assert detail["member_count"] == 1
    assert member_id not in {m["user_id"] for m in detail["members"]}


async def test_declined_invitation_is_closed(client, db_session) -> None:  # type: ignore[no-untyped-def]
    founder, _ = await _person(client, FOUNDER, "صبا")
    member, _ = await _person(client, MEMBER, "آرین")
    outsider, _ = await _person(client, OUTSIDER, "بیرونی")
    venture = await _venture(client, founder)
    username = (await me(client, member))["username"]
    invitation = (
        await client.post(
            f"/api/v1/ventures/{venture['id']}/invitations",
            headers=auth(founder),
            json={"username": username},
        )
    ).json()

    # دعوت دیگران برای بیرونی «وجود ندارد».
    response = await client.post(
        f"/api/v1/invitations/{invitation['id']}/accept", headers=auth(outsider)
    )
    assert response.status_code == 404
    response = await client.post(
        f"/api/v1/invitations/{invitation['id']}/decline", headers=auth(member)
    )
    assert response.status_code == 204
    response = await client.post(
        f"/api/v1/invitations/{invitation['id']}/accept", headers=auth(member)
    )
    assert response.status_code == 409


# ── پروژهٔ عملیاتی — FR-VEN-02 ─────────────────────────────────────────
async def test_project_metrics_verified_by_lead(client, db_session) -> None:  # type: ignore[no-untyped-def]
    lead, lead_id = await _person(client, MENTOR, "مدیر")
    member, member_id = await _person(client, MEMBER, "آرین")
    await grant_role(db_session, lead_id, "MENTOR")  # نوع A مجوز ساخت مدیریت‌شده می‌خواهد
    project_id = await _published_project(
        client, db_session, lead, kind="A_VENTURE", team_size_max=4
    )
    username = (await me(client, member))["username"]
    invitation = await client.post(
        f"/api/v1/projects/{project_id}/invitations",
        headers=auth(lead),
        json={"username": username},
    )
    assert invitation.status_code == 201, invitation.text
    response = await client.post(
        f"/api/v1/invitations/{invitation.json()['id']}/accept", headers=auth(member)
    )
    assert response.status_code == 200, response.text

    url = f"/api/v1/projects/{project_id}/metrics"
    row = await client.post(
        url,
        headers=auth(member),
        json={"metric": "SALES_COUNT", "value": 2, "occurred_on": _today()},
    )
    assert row.status_code == 201, row.text

    response = await client.post(
        f"/api/v1/metrics/{row.json()['id']}/review",
        headers=auth(lead),
        json={"decision": "VERIFIED"},
    )
    assert response.status_code == 200, response.text
    assert await _points(db_session, member_id, "METRIC_SALES_COUNT") == Decimal(30)

    board = (await client.get(url, headers=auth(lead))).json()
    assert board["by_member"][0]["user_id"] == member_id
    assert board["by_member"][0]["verified"] == {"SALES_COUNT": 2}


async def test_non_venture_projects_do_not_take_metrics(client, db_session) -> None:  # type: ignore[no-untyped-def]
    lead, _ = await _person(client, FOUNDER, "صبا")
    project_id = await _published_project(client, db_session, lead)
    response = await client.post(
        f"/api/v1/projects/{project_id}/metrics",
        headers=auth(lead),
        json={"metric": "CALLS", "value": 1, "occurred_on": _today()},
    )
    assert response.status_code == 409


async def test_project_can_belong_to_a_venture(client, db_session) -> None:  # type: ignore[no-untyped-def]
    from tests.integration.helpers import project_payload

    founder, _ = await _person(client, FOUNDER, "صبا")
    outsider, _ = await _person(client, OUTSIDER, "بیرونی")
    venture = await _venture(client, founder)

    response = await client.post(
        "/api/v1/projects",
        headers=auth(outsider),
        json=project_payload(venture_id=venture["id"]),
    )
    assert response.status_code == 403
    response = await client.post(
        "/api/v1/projects",
        headers=auth(founder),
        json=project_payload(venture_id=venture["id"]),
    )
    assert response.status_code == 201, response.text
    detail = (await client.get(f"/api/v1/ventures/{venture['id']}")).json()
    assert [p["id"] for p in detail["projects"]] == [response.json()["id"]]
