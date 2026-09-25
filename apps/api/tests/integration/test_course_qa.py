"""پرسش‌وپاسخ درس — FR-EDU-07، ADR-0024 برش ج.

PostgreSQL واقعی لازم است: شمارندهٔ `helpful_count` تریگر دیتابیس است، امتیاز از
کلید یکتای دفتر کل می‌آید و اعلان از صف `notifications`؛ هیچ‌کدام شبیه‌سازی نمی‌شوند.

سناریوی پایه: یک ارائه با استاد، یک دستیار (TA) و پنج دانشجوی فعال.
`s[0]` می‌پرسد، `s[1]` پاسخ می‌دهد، و `s[2]`، `s[3]`، `s[4]` رأی می‌دهند.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import select
from tests.integration.helpers import auth, grant_role
from tests.integration.test_admin_public_flow import _kinds
from tests.integration.test_education_flow import _scene
from tests.integration.test_gamification_flow import _active, _ledger, _net

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

D = Decimal
STUDENTS = 5

HELPFUL = "QA_ANSWER_HELPFUL"
OFFICIAL = "QA_ANSWER_OFFICIAL_MATCH"

TITLE = "چرا ضریب اصطکاک در باران کم می‌شود؟"
BODY = "در جزوهٔ هفتهٔ اول نوشته شده اصطکاک کم می‌شود، ولی دلیل فیزیکی‌اش را نفهمیدم."
ANSWER = "لایهٔ نازک آب بین لاستیک و آسفالت قرار می‌گیرد و تماس مستقیم را کم می‌کند."


# ── ساخت صحنه ──────────────────────────────────────────────────────────
async def _user(db_session: Any) -> dict[str, str]:
    """کاربر تازه با توکن مستقیم — نه OTP.

    ورود با OTP سقف ۱۰ در ساعت برای هر IP دارد و این سناریو بیش از ۱۰ کاربر
    می‌خواهد. توکن همان است که `/auth/otp/verify` می‌دهد؛ `get_current_user` فقط
    وجود و فعال‌بودن کاربر را در دیتابیس می‌سنجد.
    """
    from silp.core.config import get_settings
    from silp.core.security import create_access_token
    from silp.models.identity import User

    user = User(mobile=f"0912{uuid.uuid4().int % 10_000_000:07d}")
    db_session.add(user)
    await db_session.flush()
    token, _ = create_access_token(
        get_settings(), user_id=user.id, roles=[], session_id=uuid.uuid4()
    )
    return {"token": token, "id": str(user.id)}


async def _enroll(db_session: Any, offering_id: Any, user_id: str, status: str = "ACTIVE") -> None:
    from silp.models.education import Enrollment

    db_session.add(
        Enrollment(offering_id=offering_id, student_id=uuid.UUID(user_id), status=status)
    )
    await db_session.flush()


async def _class(client: Any, db_session: Any) -> dict[str, Any]:
    scene = await _scene(client, db_session)
    offering_id = scene["offering"].id
    students = [await _user(db_session) for _ in range(STUDENTS)]
    for student in students:
        await _enroll(db_session, offering_id, student["id"])

    week = await client.put(
        f"/api/v1/teach/offerings/{offering_id}/weeks",
        headers=auth(scene["instructor_token"]),
        json={"week_number": 1, "title_fa": "اصطکاک و ترمز"},
    )
    assert week.status_code == 200, week.text
    published = await client.post(
        f"/api/v1/teach/weeks/{week.json()['id']}/publish",
        headers=auth(scene["instructor_token"]),
        json={},
    )
    assert published.status_code == 200, published.text

    from silp.core.permissions import Role, ScopeType
    from silp.services import authz

    ta = await _user(db_session)
    await authz.grant_role(
        db_session,
        user_id=uuid.UUID(ta["id"]),
        role=Role.TA,
        scope_type=ScopeType.OFFERING,
        scope_id=offering_id,
    )
    await db_session.flush()
    await authz.invalidate_roles(uuid.UUID(ta["id"]))
    return {
        "offering_id": str(offering_id),
        "instructor": scene["instructor_token"],
        "instructor_id": scene["instructor_id"],
        "ta": ta["token"],
        "ta_id": ta["id"],
        #: ثبت‌نام‌نشده — همان دانشجوی صحنهٔ عمومی.
        "outsider": scene["student_token"],
        "s": students,
    }


def _threads_url(c: dict[str, Any]) -> str:
    return f"/api/v1/offerings/{c['offering_id']}/qa/threads"


async def _ask(client: Any, c: dict[str, Any], token: str, **overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"title": TITLE, "body": BODY}
    payload.update(overrides)
    response = await client.post(_threads_url(c), headers=auth(token), json=payload)
    assert response.status_code == 201, response.text
    return dict(response.json())


async def _reply(client: Any, token: str, thread_id: str, body: str = ANSWER) -> dict[str, Any]:
    response = await client.post(
        f"/api/v1/qa/threads/{thread_id}/replies", headers=auth(token), json={"body": body}
    )
    assert response.status_code == 201, response.text
    return dict(response.json())


async def _vote(client: Any, token: str, reply_id: str) -> Any:
    return await client.post(f"/api/v1/qa/replies/{reply_id}/vote", headers=auth(token))


async def _endorse(client: Any, token: str, reply_id: str) -> Any:
    return await client.post(f"/api/v1/qa/replies/{reply_id}/endorse", headers=auth(token))


async def _question_with_answer(
    client: Any, c: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    thread = await _ask(client, c, c["s"][0]["token"])
    return thread, await _reply(client, c["s"][1]["token"], thread["id"])


# ── دسترسی ─────────────────────────────────────────────────────────────
async def test_outsider_and_pending_student_get_404_not_403(client, db_session) -> None:  # type: ignore[no-untyped-def]
    c = await _class(client, db_session)
    thread, _ = await _question_with_answer(client, c)

    pending = await _user(db_session)
    await _enroll(db_session, uuid.UUID(c["offering_id"]), pending["id"], "PENDING")

    for token in (c["outsider"], pending["token"]):
        assert (await client.get(_threads_url(c), headers=auth(token))).status_code == 404
        assert (
            await client.post(
                _threads_url(c), headers=auth(token), json={"title": TITLE, "body": BODY}
            )
        ).status_code == 404
        assert (
            await client.get(f"/api/v1/qa/threads/{thread['id']}", headers=auth(token))
        ).status_code == 404
        assert (
            await client.post(
                f"/api/v1/qa/threads/{thread['id']}/replies",
                headers=auth(token),
                json={"body": ANSWER},
            )
        ).status_code == 404

    unauthenticated = await client.get(_threads_url(c))
    assert unauthenticated.status_code == 401


async def test_instructor_of_another_offering_is_an_outsider(client, db_session) -> None:  # type: ignore[no-untyped-def]
    c = await _class(client, db_session)
    other = await _user(db_session)
    await grant_role(db_session, other["id"], "INSTRUCTOR")

    response = await client.get(_threads_url(c), headers=auth(other["token"]))
    assert response.status_code == 404


async def test_staff_and_students_share_one_board(client, db_session) -> None:  # type: ignore[no-untyped-def]
    c = await _class(client, db_session)
    thread = await _ask(client, c, c["s"][0]["token"])
    assert thread["is_mine"] is True
    assert thread["reply_count"] == 0

    for token in (c["instructor"], c["ta"], c["s"][3]["token"]):
        response = await client.get(_threads_url(c), headers=auth(token))
        assert response.status_code == 200, response.text
        assert [t["id"] for t in response.json()["items"]] == [thread["id"]]


# ── پرسیدن ─────────────────────────────────────────────────────────────
async def test_anonymous_asker_is_hidden_from_classmates_only(client, db_session) -> None:  # type: ignore[no-untyped-def]
    c = await _class(client, db_session)
    thread = await _ask(client, c, c["s"][0]["token"], is_anonymous=True)
    asker_id = c["s"][0]["id"]

    async def author_of(token: str) -> Any:
        detail = await client.get(f"/api/v1/qa/threads/{thread['id']}", headers=auth(token))
        listing = await client.get(_threads_url(c), headers=auth(token))
        assert detail.status_code == 200 and listing.status_code == 200
        assert detail.json()["author"] == listing.json()["items"][0]["author"]
        return detail.json()["author"]

    assert await author_of(c["s"][2]["token"]) is None
    assert await author_of(c["ta"]) is None, "دستیار استاد نیست؛ ناشناس را نمی‌بیند"
    assert (await author_of(c["s"][0]["token"]))["id"] == asker_id
    assert (await author_of(c["instructor"]))["id"] == asker_id


async def test_thread_validation_speaks_persian(client, db_session) -> None:  # type: ignore[no-untyped-def]
    c = await _class(client, db_session)
    token = c["s"][0]["token"]

    response = await client.post(
        _threads_url(c), headers=auth(token), json={"title": "کوتاه", "body": BODY}
    )
    assert response.status_code == 201, "۵ نویسه حداقل مجاز است"
    response = await client.post(
        _threads_url(c), headers=auth(token), json={"title": "؟", "body": BODY}
    )
    assert response.status_code == 422
    assert "عنوان" in response.json()["error"]["message"]
    response = await client.post(
        _threads_url(c), headers=auth(token), json={"title": TITLE, "body": "کوتاه"}
    )
    assert response.status_code == 422
    assert "شرح" in response.json()["error"]["message"]
    response = await client.post(
        _threads_url(c),
        headers=auth(token),
        json={"title": TITLE, "body": BODY, "is_official": True},
    )
    assert response.status_code == 422, "فیلد ناشناخته پذیرفته نمی‌شود"


async def test_week_binding_and_draft_weeks(client, db_session) -> None:  # type: ignore[no-untyped-def]
    c = await _class(client, db_session)
    draft = await client.put(
        f"/api/v1/teach/offerings/{c['offering_id']}/weeks",
        headers=auth(c["instructor"]),
        json={"week_number": 2, "title_fa": "هفتهٔ منتشرنشده"},
    )
    assert draft.status_code == 200, draft.text
    student = c["s"][0]["token"]

    bound = await _ask(client, c, student, week_number=1)
    assert bound["week_number"] == 1

    for number in (2, 9):
        response = await client.post(
            _threads_url(c),
            headers=auth(student),
            json={"title": TITLE, "body": BODY, "week_number": number},
        )
        assert response.status_code == 404, f"هفتهٔ {number}"

    staff = await _ask(client, c, c["instructor"], week_number=2)
    assert staff["week_number"] == 2
    # پرسش هفتهٔ منتشرنشده برای دانشجو نیست، برای استاد هست.
    listing = await client.get(_threads_url(c), headers=auth(student))
    assert [t["id"] for t in listing.json()["items"]] == [bound["id"]]
    assert (
        await client.get(f"/api/v1/qa/threads/{staff['id']}", headers=auth(student))
    ).status_code == 404
    listing = await client.get(_threads_url(c), headers=auth(c["instructor"]))
    assert {t["id"] for t in listing.json()["items"]} == {bound["id"], staff["id"]}


async def test_list_puts_unanswered_first_and_filters(client, db_session) -> None:  # type: ignore[no-untyped-def]
    c = await _class(client, db_session)
    asker, other = c["s"][0]["token"], c["s"][1]["token"]
    answered = await _ask(client, c, asker, title="پرسش پاسخ‌داده‌شده")
    await _reply(client, other, answered["id"])
    unanswered = await _ask(client, c, other, title="پرسش بی‌پاسخ")
    weekly = await _ask(client, c, asker, title="پرسش هفتهٔ اول", week_number=1)

    async def ids(**params: Any) -> list[str]:
        response = await client.get(_threads_url(c), headers=auth(asker), params=params)
        assert response.status_code == 200, response.text
        return [t["id"] for t in response.json()["items"]]

    # بی‌پاسخ‌ها اول (تازه‌ترین بالاتر)، سپس پاسخ‌داده‌شده.
    assert await ids() == [weekly["id"], unanswered["id"], answered["id"]]
    assert await ids(filter="unanswered") == [weekly["id"], unanswered["id"]]
    assert await ids(filter="mine") == [weekly["id"], answered["id"]]
    assert await ids(week_number=1) == [weekly["id"]]

    resolved = await client.patch(
        f"/api/v1/qa/threads/{answered['id']}", headers=auth(asker), json={"is_resolved": True}
    )
    assert resolved.status_code == 200 and resolved.json()["is_resolved"] is True
    assert await ids(filter="unresolved") == [weekly["id"], unanswered["id"]]

    page = await client.get(_threads_url(c), headers=auth(asker), params={"page_size": 2})
    assert page.json()["total"] == 3 and page.json()["has_next"] is True


# ── پاسخ‌دادن ──────────────────────────────────────────────────────────
async def test_official_flag_comes_from_the_server_not_the_body(client, db_session) -> None:  # type: ignore[no-untyped-def]
    c = await _class(client, db_session)
    thread = await _ask(client, c, c["s"][0]["token"])

    student = await _reply(client, c["s"][1]["token"], thread["id"])
    assistant = await _reply(client, c["ta"], thread["id"], "دستیار: به جزوهٔ هفتهٔ اول نگاه کن.")
    teacher = await _reply(client, c["instructor"], thread["id"], "استاد: لایهٔ آب علت اصلی است.")
    assert (student["is_official"], assistant["is_official"], teacher["is_official"]) == (
        False,
        False,
        True,
    )

    response = await client.post(
        f"/api/v1/qa/threads/{thread['id']}/replies",
        headers=auth(c["s"][2]["token"]),
        json={"body": ANSWER, "is_official": True},
    )
    assert response.status_code == 422

    detail = (
        await client.get(f"/api/v1/qa/threads/{thread['id']}", headers=auth(c["s"][0]["token"]))
    ).json()
    # پاسخ استاد بالاست؛ سپس بقیه به ترتیب ثبت.
    assert detail["replies"][0]["id"] == teacher["id"]
    assert detail["has_official_answer"] is True and detail["reply_count"] == 3

    too_short = await client.post(
        f"/api/v1/qa/threads/{thread['id']}/replies",
        headers=auth(c["s"][2]["token"]),
        json={"body": "ب"},
    )
    assert too_short.status_code == 422


async def test_asker_is_notified_of_a_reply_but_not_of_their_own(client, db_session) -> None:  # type: ignore[no-untyped-def]
    from silp.models.messaging import Notification

    c = await _class(client, db_session)
    thread = await _ask(client, c, c["s"][0]["token"])
    await _reply(client, c["s"][0]["token"], thread["id"], "افزودن توضیح به پرسش خودم.")
    assert "QA_REPLY_POSTED" not in await _kinds(db_session, c["s"][0]["id"])

    await _reply(client, c["s"][1]["token"], thread["id"])
    assert (await _kinds(db_session, c["s"][0]["id"])).count("QA_REPLY_POSTED") == 1
    assert "QA_REPLY_POSTED" not in await _kinds(db_session, c["s"][1]["id"])

    row = await db_session.scalar(
        select(Notification).where(
            Notification.user_id == uuid.UUID(c["s"][0]["id"]),
            Notification.kind == "QA_REPLY_POSTED",
        )
    )
    assert row is not None
    assert row.action_url == f"/courses/{c['offering_id']}/qa?thread={thread['id']}"
    assert TITLE in row.title and ANSWER[:20] in row.body


async def test_resolve_and_delete_permissions(client, db_session) -> None:  # type: ignore[no-untyped-def]
    c = await _class(client, db_session)
    asker, other = c["s"][0]["token"], c["s"][1]["token"]
    thread = await _ask(client, c, asker)

    url = f"/api/v1/qa/threads/{thread['id']}"
    assert (
        await client.patch(url, headers=auth(other), json={"is_resolved": True})
    ).status_code == 403
    assert (await client.delete(url, headers=auth(other))).status_code == 403
    assert (
        await client.patch(url, headers=auth(c["instructor"]), json={"is_resolved": True})
    ).status_code == 200

    await _reply(client, other, thread["id"])
    blocked = await client.delete(url, headers=auth(asker))
    assert blocked.status_code == 409, "پرسنده پرسش پاسخ‌گرفته را حذف نمی‌کند"
    assert (await client.delete(url, headers=auth(c["instructor"]))).status_code == 204
    assert (await client.get(url, headers=auth(asker))).status_code == 404

    alone = await _ask(client, c, asker)
    assert (
        await client.delete(f"/api/v1/qa/threads/{alone['id']}", headers=auth(asker))
    ).status_code == 204


# ── رأی «مفید» ─────────────────────────────────────────────────────────
async def test_vote_rules(client, db_session) -> None:  # type: ignore[no-untyped-def]
    c = await _class(client, db_session)
    _, reply = await _question_with_answer(client, c)
    author, voter = c["s"][1]["token"], c["s"][2]["token"]

    own = await _vote(client, author, reply["id"])
    assert own.status_code == 409

    first = await _vote(client, voter, reply["id"])
    assert first.status_code == 200, first.text
    assert first.json()["helpful_count"] == 1 and first.json()["voted_by_me"] is True
    again = await _vote(client, voter, reply["id"])
    assert again.status_code == 409 and again.json()["error"]["code"] == "DUPLICATE_VOTE"

    assert (await _vote(client, c["outsider"], reply["id"])).status_code == 404

    gone = await client.delete(f"/api/v1/qa/replies/{reply['id']}/vote", headers=auth(voter))
    assert gone.status_code == 200 and gone.json()["helpful_count"] == 0
    nothing = await client.delete(f"/api/v1/qa/replies/{reply['id']}/vote", headers=auth(voter))
    assert nothing.status_code == 404


async def test_third_student_vote_earns_ten_not_the_second(client, db_session) -> None:  # type: ignore[no-untyped-def]
    c = await _class(client, db_session)
    _, reply = await _question_with_answer(client, c)
    answerer = c["s"][1]["token"]

    for voter in (c["s"][0], c["s"][2]):
        assert (await _vote(client, voter["token"], reply["id"])).status_code == 200
    assert _active(await _ledger(client, answerer), HELPFUL) == []

    third = await _vote(client, c["s"][3]["token"], reply["id"])
    assert third.json()["helpful_count"] == 3
    [entry] = _active(await _ledger(client, answerer), HELPFUL)
    assert D(entry["amount"]) == D(10) and entry["category"] == "COMMUNITY"
    assert _active(await _ledger(client, answerer), OFFICIAL) == []

    # رأی چهارم امتیاز دوباره نمی‌دهد.
    await _vote(client, c["s"][4]["token"], reply["id"])
    assert len(_active(await _ledger(client, answerer), HELPFUL)) == 1


async def test_staff_votes_count_as_helpful_but_never_cross_the_threshold(
    client, db_session
) -> None:  # type: ignore[no-untyped-def]
    """«دو دستیار نباید بی‌نظر استاد امتیاز بسازند» — بند ۱۴."""
    c = await _class(client, db_session)
    _, reply = await _question_with_answer(client, c)
    answerer = c["s"][1]["token"]

    await _vote(client, c["instructor"], reply["id"])
    await _vote(client, c["ta"], reply["id"])
    await _vote(client, c["s"][0]["token"], reply["id"])
    response = await _vote(client, c["s"][2]["token"], reply["id"])
    assert response.json()["helpful_count"] == 4
    assert _active(await _ledger(client, answerer), HELPFUL) == [], "فقط ۲ رأی دانشجو"

    await _vote(client, c["s"][3]["token"], reply["id"])
    assert len(_active(await _ledger(client, answerer), HELPFUL)) == 1


async def test_withdrawing_a_vote_does_not_take_the_points_back(client, db_session) -> None:  # type: ignore[no-untyped-def]
    """بند ۱۷ — مثل `IDEA_VOTES_*`: رأی‌های دیگران را نمی‌شود پس گرفت."""
    c = await _class(client, db_session)
    _, reply = await _question_with_answer(client, c)
    for voter in (c["s"][0], c["s"][2], c["s"][3]):
        await _vote(client, voter["token"], reply["id"])
    answerer = c["s"][1]["token"]
    assert len(_active(await _ledger(client, answerer), HELPFUL)) == 1

    await client.delete(f"/api/v1/qa/replies/{reply['id']}/vote", headers=auth(c["s"][3]["token"]))
    assert len(_active(await _ledger(client, answerer), HELPFUL)) == 1
    # و با رأی تازه هم دوباره ثبت نمی‌شود.
    await _vote(client, c["s"][4]["token"], reply["id"])
    assert len(_active(await _ledger(client, answerer), HELPFUL)) == 1


# ── تأیید استاد ────────────────────────────────────────────────────────
async def test_endorsement_earns_both_rules_and_tells_the_answerer(client, db_session) -> None:  # type: ignore[no-untyped-def]
    from silp.models.messaging import Notification

    c = await _class(client, db_session)
    _, reply = await _question_with_answer(client, c)
    answerer = c["s"][1]["token"]

    response = await _endorse(client, c["instructor"], reply["id"])
    assert response.status_code == 200, response.text
    assert response.json()["is_endorsed"] is True and response.json()["endorsed_at"] is not None

    ledger = await _ledger(client, answerer)
    assert D(_active(ledger, HELPFUL)[0]["amount"]) == D(10)
    assert D(_active(ledger, OFFICIAL)[0]["amount"]) == D(20)
    assert _net(ledger, HELPFUL) + _net(ledger, OFFICIAL) == D(30)

    note = await db_session.scalar(
        select(Notification).where(
            Notification.user_id == uuid.UUID(c["s"][1]["id"]),
            Notification.kind == "QA_REPLY_ENDORSED",
        )
    )
    assert note is not None
    assert "۳۰ امتیاز" in note.body, "ارقام فارسی و امتیاز خالص همان لحظه"
    assert note.action_url is not None and note.action_url.startswith(
        f"/courses/{c['offering_id']}/qa"
    )


async def test_only_the_teacher_endorses_and_only_a_students_answer(client, db_session) -> None:  # type: ignore[no-untyped-def]
    c = await _class(client, db_session)
    thread, reply = await _question_with_answer(client, c)
    official = await _reply(client, c["instructor"], thread["id"], "پاسخ رسمی استاد به همین پرسش.")

    for token in (c["ta"], c["s"][0]["token"], c["s"][1]["token"]):
        response = await _endorse(client, token, reply["id"])
        assert response.status_code == 403, "دستیار و دانشجو تأیید نمی‌کنند (D-28)"
    assert (await _endorse(client, c["outsider"], reply["id"])).status_code == 404

    assert (await _endorse(client, c["instructor"], official["id"])).status_code == 409
    assert (await _endorse(client, c["instructor"], reply["id"])).status_code == 200
    assert (await _endorse(client, c["instructor"], reply["id"])).status_code == 409

    lonely = await client.delete(
        f"/api/v1/qa/replies/{official['id']}/endorse", headers=auth(c["instructor"])
    )
    assert lonely.status_code == 404
    assert (
        await client.delete(f"/api/v1/qa/replies/{reply['id']}/endorse", headers=auth(c["ta"]))
    ).status_code == 403


async def test_unendorsing_takes_back_twenty_and_keeps_ten_only_with_three_votes(
    client, db_session
) -> None:  # type: ignore[no-untyped-def]
    c = await _class(client, db_session)
    thread, with_votes = await _question_with_answer(client, c)
    without = await _reply(client, c["s"][2]["token"], thread["id"], "پاسخ دوم بدون رأی کافی.")
    for voter in (c["s"][0], c["s"][3], c["s"][4]):
        await _vote(client, voter["token"], with_votes["id"])
    for reply in (with_votes, without):
        assert (await _endorse(client, c["instructor"], reply["id"])).status_code == 200

    voted_ledger = await _ledger(client, c["s"][1]["token"])
    assert (len(_active(voted_ledger, HELPFUL)), len(_active(voted_ledger, OFFICIAL))) == (1, 1)

    for reply in (with_votes, without):
        response = await client.delete(
            f"/api/v1/qa/replies/{reply['id']}/endorse", headers=auth(c["instructor"])
        )
        assert response.status_code == 200 and response.json()["is_endorsed"] is False

    kept = await _ledger(client, c["s"][1]["token"])
    assert (len(_active(kept, HELPFUL)), len(_active(kept, OFFICIAL))) == (1, 0), "۳ رأی هنوز هست"
    dropped = await _ledger(client, c["s"][2]["token"])
    assert (len(_active(dropped, HELPFUL)), len(_active(dropped, OFFICIAL))) == (0, 0)


async def test_endorsing_again_restores_the_points_without_a_second_notice(
    client, db_session
) -> None:  # type: ignore[no-untyped-def]
    c = await _class(client, db_session)
    _, reply = await _question_with_answer(client, c)
    answerer = c["s"][1]["token"]

    await _endorse(client, c["instructor"], reply["id"])
    await client.delete(f"/api/v1/qa/replies/{reply['id']}/endorse", headers=auth(c["instructor"]))
    assert _active(await _ledger(client, answerer), OFFICIAL) == []
    await _endorse(client, c["instructor"], reply["id"])

    ledger = await _ledger(client, answerer)
    assert (len(_active(ledger, HELPFUL)), len(_active(ledger, OFFICIAL))) == (1, 1)
    assert (await _kinds(db_session, c["s"][1]["id"])).count("QA_REPLY_ENDORSED") == 1


async def test_endorsing_a_non_students_reply_earns_nothing(client, db_session) -> None:  # type: ignore[no-untyped-def]
    """پاسخ دستیار تأیید می‌شود ولی امتیاز جامعهٔ دانشجویی نمی‌سازد (بند ۱۸)."""
    c = await _class(client, db_session)
    thread = await _ask(client, c, c["s"][0]["token"])
    assistant = await _reply(client, c["ta"], thread["id"], "پاسخ دستیار آموزشی به این پرسش.")

    assert (await _endorse(client, c["instructor"], assistant["id"])).status_code == 200
    assert _active(await _ledger(client, c["ta"]), HELPFUL) == []
    assert _active(await _ledger(client, c["ta"]), OFFICIAL) == []


async def test_dropped_student_answer_earns_nothing(client, db_session) -> None:  # type: ignore[no-untyped-def]
    from silp.models.education import Enrollment

    c = await _class(client, db_session)
    _, reply = await _question_with_answer(client, c)
    enrollment = await db_session.scalar(
        select(Enrollment).where(
            Enrollment.offering_id == uuid.UUID(c["offering_id"]),
            Enrollment.student_id == uuid.UUID(c["s"][1]["id"]),
        )
    )
    enrollment.status = "DROPPED"
    await db_session.flush()

    assert (await _endorse(client, c["instructor"], reply["id"])).status_code == 200
    assert _active(await _ledger(client, c["s"][1]["token"]), OFFICIAL) == []


# ── حذف ────────────────────────────────────────────────────────────────
async def test_deleting_a_reply_reverses_everything_it_earned(client, db_session) -> None:  # type: ignore[no-untyped-def]
    c = await _class(client, db_session)
    _, reply = await _question_with_answer(client, c)
    await _endorse(client, c["instructor"], reply["id"])
    answerer = c["s"][1]["token"]
    assert len(_active(await _ledger(client, answerer), OFFICIAL)) == 1

    assert (
        await client.delete(f"/api/v1/qa/replies/{reply['id']}", headers=auth(c["s"][2]["token"]))
    ).status_code == 403
    assert (
        await client.delete(f"/api/v1/qa/replies/{reply['id']}", headers=auth(answerer))
    ).status_code == 204

    ledger = await _ledger(client, answerer)
    assert _active(ledger, HELPFUL) == [] and _active(ledger, OFFICIAL) == []
    assert _net(ledger, HELPFUL) == D(0) and _net(ledger, OFFICIAL) == D(0)
    assert (await _endorse(client, c["instructor"], reply["id"])).status_code == 404


async def test_instructor_can_delete_a_reply_and_a_thread_takes_its_points_along(
    client, db_session
) -> None:  # type: ignore[no-untyped-def]
    c = await _class(client, db_session)
    thread, reply = await _question_with_answer(client, c)
    await _endorse(client, c["instructor"], reply["id"])
    answerer = c["s"][1]["token"]

    assert (
        await client.delete(f"/api/v1/qa/threads/{thread['id']}", headers=auth(c["instructor"]))
    ).status_code == 204
    ledger = await _ledger(client, answerer)
    assert _active(ledger, HELPFUL) == [] and _active(ledger, OFFICIAL) == []
    listing = await client.get(_threads_url(c), headers=auth(answerer))
    assert listing.json()["items"] == []


# ── نشان «یاریگر» ──────────────────────────────────────────────────────
async def test_five_helpful_answers_unlock_the_helper_badge(client, db_session) -> None:  # type: ignore[no-untyped-def]
    """`HELPER` تا پیش از ADR-0024 قفل می‌ماند: `QA_ANSWER_HELPFUL` منبع نداشت."""
    from silp.services.badge_service import BadgeService

    c = await _class(client, db_session)
    answerer = c["s"][1]
    for n in range(5):
        thread = await _ask(client, c, c["s"][0]["token"], title=f"پرسش شمارهٔ {n + 1} دربارهٔ ترمز")
        reply = await _reply(client, answerer["token"], thread["id"])
        assert (await _endorse(client, c["instructor"], reply["id"])).status_code == 200

    badges = (await client.get("/api/v1/me/badges", headers=auth(answerer["token"]))).json()
    assert "HELPER" not in {b["code"] for b in badges["earned"]}, "ارزیابی نشان کار پس‌زمینه است"
    progress = next(b for b in badges["locked"] if b["code"] == "HELPER")
    assert (D(progress["progress_current"]), D(progress["progress_target"])) == (D(5), D(5))

    assert await BadgeService(db_session).evaluate_user(uuid.UUID(answerer["id"])) != []
    badges = (await client.get("/api/v1/me/badges", headers=auth(answerer["token"]))).json()
    assert "HELPER" in {b["code"] for b in badges["earned"]}
