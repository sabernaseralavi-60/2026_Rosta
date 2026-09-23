"""بانک ایده — M7-01 و M7-02، FR-IDEA-01/02/03، §7.8.

PostgreSQL واقعی لازم است: شمارندهٔ رأی و نظر تریگرند، جستجو روی ستون
تولیدشدهٔ `fa_normalize`، و رتبهٔ «داغ» یک عبارت SQL.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import select
from tests.integration.helpers import auth, complete_profile, grant_role, login, me

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

AUTHOR = "09121110001"
VOTER = "09121110002"
TEACHER = "09121110003"
MODERATOR = "09121110004"

IDEA = {
    "title": "اپلیکیشن اشتراک خودرو برای دانشجویان",
    "body": "دانشجویان خوابگاهی هر روز با تاکسی جداگانه به دانشگاه می‌روند؛ یک سامانهٔ هم‌سفری.",
    "problem": "هزینه و ترافیک رفت‌وآمد دانشجویان",
    "category": "TRANSPORT",
    "tags": ["حمل‌ونقل", "#هم‌سفری"],
}


async def _person(client: Any, mobile: str, first_name: str) -> tuple[str, str]:
    token = await login(client, mobile)
    await complete_profile(client, token, first_name=first_name)
    return token, str((await me(client, token))["id"])


async def _idea(client: Any, token: str, **overrides: Any) -> dict[str, Any]:
    response = await client.post("/api/v1/ideas", headers=auth(token), json={**IDEA, **overrides})
    assert response.status_code == 201, response.text
    return dict(response.json())


async def _points(db_session: Any, user_id: str, rule: str) -> Decimal:
    from sqlalchemy import func

    from silp.models.gamification import PointEntry

    total = await db_session.scalar(
        select(func.coalesce(func.sum(PointEntry.amount), 0)).where(
            PointEntry.user_id == user_id, PointEntry.rule_code == rule
        )
    )
    return Decimal(total)


# ── ثبت و فهرست ────────────────────────────────────────────────────────
async def test_submit_list_search_and_points(client, db_session) -> None:  # type: ignore[no-untyped-def]
    token, user_id = await _person(client, AUTHOR, "نسترن")
    idea = await _idea(client, token)
    assert idea["tags"] == ["حمل‌ونقل", "هم‌سفری"]
    assert idea["category_fa"] == "حمل‌ونقل و ترافیک"
    assert idea["author"]["name"]
    assert idea["is_mine"] is True
    assert await _points(db_session, user_id, "IDEA_SUBMITTED") == Decimal(5)

    # عمومی: بدون ورود هم دیده می‌شود.
    response = await client.get("/api/v1/ideas")
    assert response.status_code == 200
    assert [i["id"] for i in response.json()["items"]] == [idea["id"]]

    # جستجوی فارسی با «ي» عربی — `fa_normalize`.
    response = await client.get("/api/v1/ideas", params={"q": "دانشجويان"})
    assert response.json()["total"] == 1
    response = await client.get("/api/v1/ideas", params={"category": "AGRICULTURE"})
    assert response.json()["total"] == 0
    response = await client.get("/api/v1/ideas", params={"tag": "هم‌سفری"})
    assert response.json()["total"] == 1


async def test_anonymous_author_is_hidden_from_everyone_else(client, db_session) -> None:  # type: ignore[no-untyped-def]
    token, _ = await _person(client, AUTHOR, "نسترن")
    idea = await _idea(client, token, is_anonymous=True)
    assert idea["author"] is not None  # خود نویسنده خودش را می‌بیند

    response = await client.get(f"/api/v1/ideas/{idea['id']}")
    assert response.json()["author"] is None
    other, _ = await _person(client, VOTER, "کاوه")
    response = await client.get("/api/v1/ideas", headers=auth(other))
    assert response.json()["items"][0]["author"] is None


# ── رأی ────────────────────────────────────────────────────────────────
async def test_vote_rules_and_counter_trigger(client, db_session) -> None:  # type: ignore[no-untyped-def]
    author, _ = await _person(client, AUTHOR, "نسترن")
    voter, _ = await _person(client, VOTER, "کاوه")
    idea = await _idea(client, author)
    url = f"/api/v1/ideas/{idea['id']}/vote"

    response = await client.post(url, headers=auth(author))
    assert response.status_code == 409  # به ایدهٔ خودت نه

    response = await client.post(url, headers=auth(voter))
    assert response.status_code == 200, response.text
    assert response.json() == {"idea_id": idea["id"], "vote_count": 1, "voted_by_me": True}

    response = await client.post(url, headers=auth(voter))
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "DUPLICATE_VOTE"

    response = await client.get(f"/api/v1/ideas/{idea['id']}", headers=auth(voter))
    assert response.json()["voted_by_me"] is True

    response = await client.delete(url, headers=auth(voter))
    assert response.json()["vote_count"] == 0
    response = await client.delete(url, headers=auth(voter))
    assert response.status_code == 404


async def test_ten_votes_award_the_milestone_once(client, db_session) -> None:  # type: ignore[no-untyped-def]
    from silp.models.idea import IdeaVote
    from silp.models.identity import User

    author, author_id = await _person(client, AUTHOR, "نسترن")
    idea = await _idea(client, author)
    # نُه رأی مستقیم در دیتابیس، رأی دهم از مسیر — آستانه با رویداد رأی بررسی می‌شود.
    for n in range(9):
        user = User(mobile=f"0935000{n:04d}")
        db_session.add(user)
        await db_session.flush()
        db_session.add(IdeaVote(idea_id=idea["id"], user_id=user.id))
    await db_session.flush()
    voter, _ = await _person(client, VOTER, "کاوه")
    response = await client.post(f"/api/v1/ideas/{idea['id']}/vote", headers=auth(voter))
    assert response.json()["vote_count"] == 10
    assert await _points(db_session, author_id, "IDEA_VOTES_10") == Decimal(25)

    # رأی پس گرفته و دوباره داده شد — آستانه یک‌بار است.
    await client.delete(f"/api/v1/ideas/{idea['id']}/vote", headers=auth(voter))
    await client.post(f"/api/v1/ideas/{idea['id']}/vote", headers=auth(voter))
    assert await _points(db_session, author_id, "IDEA_VOTES_10") == Decimal(25)


# ── نظر ────────────────────────────────────────────────────────────────
async def test_comments_thread_one_level_and_notify(client, db_session) -> None:  # type: ignore[no-untyped-def]
    from silp.models.messaging import Notification

    author, author_id = await _person(client, AUTHOR, "نسترن")
    voter, voter_id = await _person(client, VOTER, "کاوه")
    idea = await _idea(client, author)
    url = f"/api/v1/ideas/{idea['id']}/comments"

    root = (await client.post(url, headers=auth(voter), json={"body": "ایدهٔ خوبی است."})).json()
    reply = await client.post(
        url, headers=auth(author), json={"body": "ممنون!", "parent_id": root["id"]}
    )
    assert reply.status_code == 201, reply.text
    # پاسخ به پاسخ، زیر همان ریشه می‌نشیند.
    nested = await client.post(
        url, headers=auth(voter), json={"body": "خواهش.", "parent_id": reply.json()["id"]}
    )
    assert nested.json()["parent_id"] == root["id"]

    detail = (await client.get(f"/api/v1/ideas/{idea['id']}")).json()
    assert detail["comment_count"] == 3

    kinds = {
        (n.user_id.hex, n.kind)
        for n in await db_session.scalars(
            select(Notification).where(Notification.kind == "IDEA_COMMENTED")
        )
    }
    # نویسنده از نظر کاوه خبردار شد؛ کاوه از پاسخ نویسنده به نظرش.
    assert (author_id.replace("-", ""), "IDEA_COMMENTED") in kinds
    assert (voter_id.replace("-", ""), "IDEA_COMMENTED") in kinds

    # حذف ریشه: پاسخ‌ها می‌مانند، ریشه با متن پنهان.
    response = await client.delete(f"/api/v1/ideas/comments/{root['id']}", headers=auth(voter))
    assert response.status_code == 204
    detail = (await client.get(f"/api/v1/ideas/{idea['id']}")).json()
    assert detail["comment_count"] == 2
    placeholder = next(c for c in detail["comments"] if c["id"] == root["id"])
    assert placeholder["is_deleted"] is True and placeholder["body"] is None

    response = await client.delete(
        f"/api/v1/ideas/comments/{nested.json()['id']}", headers=auth(author)
    )
    assert response.status_code == 403


# ── حذف و بایگانی ──────────────────────────────────────────────────────
async def test_deleting_an_idea_reverses_its_points(client, db_session) -> None:  # type: ignore[no-untyped-def]
    token, user_id = await _person(client, AUTHOR, "نسترن")
    idea = await _idea(client, token)
    response = await client.delete(f"/api/v1/ideas/{idea['id']}", headers=auth(token))
    assert response.status_code == 204
    assert await _points(db_session, user_id, "IDEA_SUBMITTED") == Decimal(0)
    assert (await client.get(f"/api/v1/ideas/{idea['id']}")).status_code == 404


async def test_moderator_archives_and_hides(client, db_session) -> None:  # type: ignore[no-untyped-def]
    author, author_id = await _person(client, AUTHOR, "نسترن")
    moderator, moderator_id = await _person(client, MODERATOR, "ناظر")
    idea = await _idea(client, author)

    response = await client.post(
        f"/api/v1/ideas/{idea['id']}/archive", headers=auth(author), json={"reason": "تکراری"}
    )
    assert response.status_code == 403

    await grant_role(db_session, moderator_id, "SUPPORT")
    response = await client.post(
        f"/api/v1/ideas/{idea['id']}/archive", headers=auth(moderator), json={"reason": "تکراری"}
    )
    assert response.status_code == 200, response.text
    assert await _points(db_session, author_id, "IDEA_SUBMITTED") == Decimal(0)
    assert (await client.get("/api/v1/ideas")).json()["total"] == 0
    assert (await client.get(f"/api/v1/ideas/{idea['id']}")).status_code == 404
    # نویسنده ایدهٔ بایگانی‌شده‌اش را با دلیل می‌بیند.
    own = await client.get(f"/api/v1/ideas/{idea['id']}", headers=auth(author))
    assert own.json()["archived_reason"] == "تکراری"


# ── ارتقا — §7.8 ───────────────────────────────────────────────────────
async def test_promote_to_project_invites_the_author(client, db_session) -> None:  # type: ignore[no-untyped-def]
    author, author_id = await _person(client, AUTHOR, "نسترن")
    teacher, teacher_id = await _person(client, TEACHER, "صابر")
    idea = await _idea(client, author, is_anonymous=True)
    url = f"/api/v1/ideas/{idea['id']}/promote"

    response = await client.post(url, headers=auth(author), json={"target": "PROJECT"})
    assert response.status_code == 403

    await grant_role(db_session, teacher_id, "INSTRUCTOR")
    response = await client.post(
        url, headers=auth(teacher), json={"target": "PROJECT", "project_kind": "C_PROBLEM"}
    )
    assert response.status_code == 200, response.text
    project_id = response.json()["target_id"]
    assert response.json()["href"] == f"/projects/{project_id}"

    project = (await client.get(f"/api/v1/projects/{project_id}")).json()
    assert project["status"] == "DRAFT"
    assert project["lead_id"] == teacher_id
    assert project["title_fa"] == IDEA["title"]

    detail = (await client.get(f"/api/v1/ideas/{idea['id']}")).json()
    assert detail["status"] == "PROMOTED"
    assert detail["promoted_to_id"] == project_id
    assert await _points(db_session, author_id, "IDEA_PROMOTED") == Decimal(100)

    # دوباره ارتقا نمی‌یابد.
    again = await client.post(url, headers=auth(teacher), json={"target": "VENTURE"})
    assert again.status_code == 409

    invitations = (await client.get("/api/v1/me/invitations", headers=auth(author))).json()
    assert len(invitations) == 1
    assert invitations[0]["source"] == "IDEA_PROMOTION"
    assert invitations[0]["target_id"] == project_id

    response = await client.post(
        f"/api/v1/invitations/{invitations[0]['id']}/accept", headers=auth(author)
    )
    assert response.status_code == 200, response.text
    team = await client.get(f"/api/v1/projects/{project_id}/team", headers=auth(author))
    assert team.status_code == 200, team.text
    assert author_id in {m["user_id"] for m in team.json()["members"]}

    # دعوت پذیرفته‌شده دوباره پذیرفته نمی‌شود.
    response = await client.post(
        f"/api/v1/invitations/{invitations[0]['id']}/accept", headers=auth(author)
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVITATION_CLOSED"


async def test_promote_to_venture_makes_author_founder(client, db_session) -> None:  # type: ignore[no-untyped-def]
    author, author_id = await _person(client, AUTHOR, "نسترن")
    teacher, teacher_id = await _person(client, TEACHER, "صابر")
    await grant_role(db_session, teacher_id, "INSTRUCTOR")

    anonymous = await _idea(client, author, is_anonymous=True)
    response = await client.post(
        f"/api/v1/ideas/{anonymous['id']}/promote",
        headers=auth(teacher),
        json={"target": "VENTURE"},
    )
    assert response.status_code == 409  # ناشناسی بی‌اجازه شکسته نمی‌شود

    idea = await _idea(client, author, title="خرمای صابر برای بازار تهران")
    response = await client.post(
        f"/api/v1/ideas/{idea['id']}/promote", headers=auth(teacher), json={"target": "VENTURE"}
    )
    assert response.status_code == 200, response.text
    venture_id = response.json()["target_id"]

    venture = (await client.get(f"/api/v1/ventures/{venture_id}", headers=auth(author))).json()
    assert venture["founder"]["user_id"] == author_id
    assert venture["origin_idea_id"] == idea["id"]
    assert venture["stage"] == "IDEA"
    assert venture["is_member"] is True
    assert await _points(db_session, author_id, "VENTURE_CREATED") == Decimal(20)
    assert await _points(db_session, author_id, "IDEA_PROMOTED") == Decimal(100)
