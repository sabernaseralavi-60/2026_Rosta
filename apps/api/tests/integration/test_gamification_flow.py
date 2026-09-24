"""امتیاز، نشان، رتبه‌بندی و داشبورد — M5، تعریف انجام‌شدهٔ §13.

«هر فعالیت امتیاز می‌دهد، دانشجو منشأ هر امتیاز را می‌بیند، نشان می‌گیرد،
و داشبوردش «قدم بعدی» را نشان می‌دهد.»

PostgreSQL واقعی لازم است: تغییرناپذیری دفتر کل یک تریگر است، بی‌اثری در
تکرار یک ایندکس یکتای جزئی، و جدول رتبه‌بندی از یک نمای تجمیعی می‌خواند.
هیچ‌کدام در حافظه شبیه‌سازی نمی‌شوند.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from tests.integration.helpers import (
    auth,
    complete_profile,
    grant_role,
    invalidate,
    login,
    me,
    milestone_payload,
)
from tests.integration.test_project_lifecycle import _actor, _published_project
from tests.integration.test_quiz_flow import (
    SINGLE_PAYLOAD,
    _add_question,
    _answer,
    _publish,
    _scene,
    _start,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

D = Decimal


# ── کمکی‌ها ────────────────────────────────────────────────────────────
async def _user(session: Any, mobile: str, *, name: str = "کاربر", public: bool = True) -> Any:
    from silp.models.identity import User
    from silp.models.profile import Profile

    user = User(mobile=mobile)
    session.add(user)
    await session.flush()
    session.add(
        Profile(user_id=user.id, first_name=name, last_name="آزمایشی", show_in_leaderboard=public)
    )
    await session.flush()
    return user


async def _ledger(client: Any, token: str, **params: Any) -> list[dict[str, Any]]:
    response = await client.get("/api/v1/me/points", headers=auth(token), params=params)
    assert response.status_code == 200, response.text
    return list(response.json()["items"])


def _active(items: list[dict[str, Any]], rule: str) -> list[dict[str, Any]]:
    """ردیف‌های اصلی و معکوس‌نشدهٔ یک قاعده."""
    return [
        i
        for i in items
        if i["rule_code"] == rule and i["reverses_id"] is None and not i["is_reversed"]
    ]


def _net(items: list[dict[str, Any]], rule: str | None = None) -> Decimal:
    return sum((D(i["amount"]) for i in items if rule is None or i["rule_code"] == rule), D(0))


async def _current_term(session: Any) -> Any:
    """نیم‌سال جاری تازه — نیم‌سال جاری قبلی (اگر بود) در این تراکنش کنار می‌رود."""
    from silp.models.education import Term

    await session.execute(text("UPDATE terms SET is_current = false WHERE is_current"))
    term = Term(
        code=f"T-{uuid.uuid4().hex[:8]}",
        title_fa="نیم‌سال جاری آزمایشی",
        starts_on=date(2026, 9, 1),
        ends_on=date(2027, 2, 1),
        is_current=True,
    )
    session.add(term)
    await session.flush()
    return term


# ── دفتر کل — FR-GAM-01 ────────────────────────────────────────────────
async def test_same_event_never_earns_twice(db_session: Any) -> None:
    from silp.services.points_service import Award, PointsService

    user = await _user(db_session, "09121500001")
    points = PointsService(db_session)
    award = Award("QUIZ_ATTEMPTED", "QUIZ", uuid.uuid4())

    first = await points.award(user.id, award)
    second = await points.award(user.id, award)
    assert first is not None and first.amount == D(5)
    assert second is None


async def test_ledger_rows_cannot_be_edited(db_session: Any) -> None:
    """D-09 — تغییرناپذیری در دیتابیس است، نه فقط در سرویس."""
    from silp.services.points_service import Award, PointsService

    user = await _user(db_session, "09121500002")
    entry = await PointsService(db_session).award(
        user.id, Award("QUIZ_ATTEMPTED", "QUIZ", uuid.uuid4())
    )
    assert entry is not None
    with pytest.raises(DBAPIError, match="append-only"):
        async with db_session.begin_nested():
            await db_session.execute(
                text("UPDATE point_entries SET amount = 500 WHERE id = :id"), {"id": entry.id}
            )


async def test_reversal_is_a_negative_row_and_happens_once(db_session: Any) -> None:
    from silp.core.exceptions import Conflict
    from silp.services.points_service import Award, PointsService

    user = await _user(db_session, "09121500003")
    points = PointsService(db_session)
    entry = await points.award(user.id, Award("PROFILE_COMPLETED", "PROFILE", user.id))
    assert entry is not None

    reversal = await points.reverse_by_id(entry.id, "ثبت اشتباه")
    assert reversal.amount == -entry.amount
    assert reversal.reverses_id == entry.id
    with pytest.raises(Conflict):
        await points.reverse_by_id(entry.id, "دوباره")
    assert (await points.summary(user.id)).level.total == 0


async def test_daily_cap_counts_awards_not_points(db_session: Any) -> None:
    """ADR-0012 — سقف «۳ در روز» یعنی سه اعطا، نه سه امتیاز."""
    from silp.services.points_service import Award, PointsService

    user = await _user(db_session, "09121500004")
    points = PointsService(db_session)
    results = [
        await points.award(user.id, Award("IDEA_SUBMITTED", "IDEA", uuid.uuid4())) for _ in range(4)
    ]
    assert [r is not None for r in results] == [True, True, True, False]
    assert (await points.summary(user.id)).by_category["COMMUNITY"] == D(15)


async def test_inactive_rule_awards_nothing(db_session: Any) -> None:
    from silp.services.points_service import Award, PointsService

    user = await _user(db_session, "09121500005")
    points = PointsService(db_session)
    await points.update_rule("QUIZ_ATTEMPTED", is_active=False)
    assert await points.award(user.id, Award("QUIZ_ATTEMPTED", "QUIZ", uuid.uuid4())) is None


# ── منبع و هفته ────────────────────────────────────────────────────────
async def _week_with_resource(client: Any, scene: dict[str, Any]) -> tuple[str, str]:
    offering_id = scene["offering"].id
    headers = auth(scene["instructor_token"])
    response = await client.put(
        f"/api/v1/teach/offerings/{offering_id}/weeks",
        headers=headers,
        json={"week_number": 3, "title_fa": "توزیع پواسون"},
    )
    assert response.status_code in (200, 201), response.text
    week_id = response.json()["id"]
    response = await client.post(
        f"/api/v1/teach/offerings/{offering_id}/weeks/{week_id}/resources",
        headers=headers,
        json={"kind": "LINK", "title_fa": "جزوهٔ هفته", "external_url": "https://example.invalid/n"},
    )
    assert response.status_code == 201, response.text
    resource_id = response.json()["id"]
    response = await client.post(f"/api/v1/teach/weeks/{week_id}/publish", headers=headers, json={})
    assert response.status_code == 200, response.text
    return week_id, resource_id


async def test_reading_the_required_resource_completes_the_week(
    client: Any, db_session: Any
) -> None:
    """ResourceCompleted ⇒ `RESOURCE_COMPLETED` و — چون هفته آزمون ندارد —
    `WEEK_COMPLETED`، هر دو یک‌بار، با منشأ خوانا."""
    scene = await _scene(client, db_session)
    week_id, resource_id = await _week_with_resource(client, scene)
    headers = auth(scene["student_token"])

    for _ in range(2):
        response = await client.post(
            f"/api/v1/resources/{resource_id}/progress", headers=headers, json={"completed": True}
        )
        assert response.status_code == 200, response.text

    items = await _ledger(client, scene["student_token"])
    [resource] = _active(items, "RESOURCE_COMPLETED")
    [week] = _active(items, "WEEK_COMPLETED")
    assert D(resource["amount"]) == D(2)
    assert resource["source_label"] == "جزوهٔ هفته"
    assert resource["source_href"] == f"/courses/{scene['offering'].id}/weeks/3"
    assert D(week["amount"]) == D(15)
    assert week["source_label"] == "هفتهٔ 3 — توزیع پواسون"
    assert week["category"] == "LEARNING"


async def test_instructor_reading_their_own_notes_earns_nothing(
    client: Any, db_session: Any
) -> None:
    scene = await _scene(client, db_session)
    _, resource_id = await _week_with_resource(client, scene)
    await client.post(
        f"/api/v1/resources/{resource_id}/progress",
        headers=auth(scene["instructor_token"]),
        json={"completed": True},
    )
    assert await _ledger(client, scene["instructor_token"]) == []


# ── آزمون — §7.12 «بهترین تلاش» ────────────────────────────────────────
async def _submit(client: Any, scene: dict[str, Any], answers: dict[str, list[str]]) -> str:
    started = await _start(client, scene)
    for question_id, selected in answers.items():
        await _answer(client, scene, started, question_id, {"selected": selected})
    response = await client.post(
        f"/api/v1/attempts/{started['attempt_id']}/submit",
        headers=auth(scene["student_token"]),
        json={"confirm_unanswered": 0},
    )
    assert response.status_code == 200, response.text
    return str(started["attempt_id"])


async def test_better_second_attempt_replaces_the_quiz_score(client: Any, db_session: Any) -> None:
    scene = await _scene(client, db_session, max_attempts=2)
    q1 = await _add_question(client, scene, kind="SINGLE_CHOICE", payload=SINGLE_PAYLOAD)
    q2 = await _add_question(client, scene, kind="SINGLE_CHOICE", payload=SINGLE_PAYLOAD)
    await _publish(client, scene)

    first = await _submit(client, scene, {q1: ["b"], q2: ["a"]})  # ۱ از ۲
    items = await _ledger(client, scene["student_token"])
    [score] = _active(items, "QUIZ_SCORE")
    assert score["source_id"] == first and D(score["amount"]) == D(15)
    assert _active(items, "QUIZ_ATTEMPTED") and _active(items, "QUIZ_FIRST_TRY")
    assert not _active(items, "QUIZ_PERFECT")

    second = await _submit(client, scene, {q1: ["b"], q2: ["b"]})  # کامل
    items = await _ledger(client, scene["student_token"])
    [score] = _active(items, "QUIZ_SCORE")
    assert score["source_id"] == second and D(score["amount"]) == D(30)
    assert len(_active(items, "QUIZ_ATTEMPTED")) == 1
    assert len(_active(items, "QUIZ_PERFECT")) == 1
    # دفتر کل تاریخ را نگه داشته: ۱۵ ثبت و معکوس شد، ۳۰ جایش آمد.
    assert _net(items, "QUIZ_SCORE") == D(30)
    assert any(i["rule_code"] == "QUIZ_SCORE" and D(i["amount"]) == D(-15) for i in items)
    assert _net(items) == D(5) + D(10) + D(30) + D(15)


async def test_voiding_the_best_attempt_hands_its_points_back(client: Any, db_session: Any) -> None:
    scene = await _scene(client, db_session, max_attempts=2)
    q1 = await _add_question(client, scene, kind="SINGLE_CHOICE", payload=SINGLE_PAYLOAD)
    await _publish(client, scene)
    attempt = await _submit(client, scene, {q1: ["b"]})

    response = await client.post(
        f"/api/v1/teach/quizzes/{scene['quiz_id']}/attempts/{attempt}/void",
        headers=auth(scene["instructor_token"]),
    )
    assert response.status_code == 200, response.text
    assert _net(await _ledger(client, scene["student_token"])) == D(0)


async def test_quiz_points_wait_until_the_result_is_visible(client: Any, db_session: Any) -> None:
    """ADR-0012 — Toast «+۳۰» نباید نمرهٔ پنهان را پیش از صفحهٔ نتیجه لو دهد."""
    from silp.services.point_listeners import LearningPoints

    scene = await _scene(client, db_session, result_visibility="AFTER_CLOSE")
    q1 = await _add_question(client, scene, kind="SINGLE_CHOICE", payload=SINGLE_PAYLOAD)
    await _publish(client, scene)
    await _submit(client, scene, {q1: ["b"]})

    items = await _ledger(client, scene["student_token"])
    assert {i["rule_code"] for i in items} == {"QUIZ_ATTEMPTED"}

    await db_session.execute(
        text(
            "UPDATE quizzes SET opens_at = now() - interval '2 hours',"
            " closes_at = now() - interval '1 minute' WHERE id = :id"
        ),
        {"id": scene["quiz_id"]},
    )
    assert await LearningPoints(db_session).release_closed_quizzes() == 1
    assert await LearningPoints(db_session).release_closed_quizzes() == 1  # بی‌اثر در تکرار

    items = await _ledger(client, scene["student_token"])
    assert {
        i["rule_code"] for i in _active(items, "QUIZ_SCORE") + _active(items, "QUIZ_PERFECT")
    } == {
        "QUIZ_SCORE",
        "QUIZ_PERFECT",
    }
    assert len(_active(items, "QUIZ_SCORE")) == 1


# ── حضور ───────────────────────────────────────────────────────────────
async def test_attendance_streak_follows_corrections(client: Any, db_session: Any) -> None:
    """چهار حضور پیاپی ⇒ ۴×۳ + ۲۰. اصلاح یکی به «غایب» هر دو را برمی‌گرداند."""
    scene = await _scene(client, db_session)
    offering_id = scene["offering"].id
    headers = auth(scene["instructor_token"])

    async def record(day: int, status: str) -> None:
        response = await client.post(
            f"/api/v1/teach/offerings/{offering_id}/attendance",
            headers=headers,
            json={
                "held_on": f"2026-10-{day:02d}",
                "entries": [{"student_id": scene["student_id"], "status": status}],
            },
        )
        assert response.status_code == 200, response.text

    for day in (3, 10, 17, 24):
        await record(day, "PRESENT")
    items = await _ledger(client, scene["student_token"])
    assert len(_active(items, "ATTENDANCE_PRESENT")) == 4
    assert len(_active(items, "ATTENDANCE_STREAK")) == 1
    assert _net(items) == D(32)

    await record(17, "ABSENT")
    items = await _ledger(client, scene["student_token"])
    assert len(_active(items, "ATTENDANCE_PRESENT")) == 3
    assert not _active(items, "ATTENDANCE_STREAK")
    assert _net(items) == D(9)


async def test_final_grade_awards_course_completion(client: Any, db_session: Any) -> None:
    from silp.models.education import Enrollment

    scene = await _scene(client, db_session)
    enrollment_id = await db_session.scalar(
        select(Enrollment.id).where(Enrollment.student_id == uuid.UUID(scene["student_id"]))
    )
    for _ in range(2):
        response = await client.patch(
            f"/api/v1/teach/enrollments/{enrollment_id}/grade",
            headers=auth(scene["instructor_token"]),
            json={"grade": 17.5},
        )
        assert response.status_code == 200, response.text
    items = await _ledger(client, scene["student_token"])
    [completed] = _active(items, "COURSE_COMPLETED")
    assert D(completed["amount"]) == D(100)


# ── پروژه ──────────────────────────────────────────────────────────────
async def test_project_loop_rewards_the_team_not_the_reviewer(client: Any, db_session: Any) -> None:
    """پذیرش ⇒ ۱۰ جامعه؛ تأیید مرحله ⇒ امتیاز مرحله به اعضا جز بازبین؛
    تکمیل ⇒ `150 × ضریب دشواری`، نوع D نصف (§9.2، §9.8)."""
    lead_token, lead_id = await _actor(client, db_session, "09121500011", first_name="صابر")
    student_token, student_id = await _actor(client, db_session, "09121500012", first_name="زهرا")
    project_id = await _published_project(client, db_session, lead_token)

    response = await client.post(
        f"/api/v1/projects/{project_id}/applications",
        headers=auth(student_token),
        json={"motivation": "به فروش علاقه دارم و وقت آزاد دارم."},
    )
    application_id = response.json()["id"]
    response = await client.post(
        f"/api/v1/applications/{application_id}/decide",
        headers=auth(lead_token),
        json={"decision": "ACCEPTED"},
    )
    assert response.status_code == 200, response.text
    await invalidate(student_id)
    await client.post(f"/api/v1/projects/{project_id}/start", headers=auth(lead_token))

    milestone = (
        await client.get(f"/api/v1/projects/{project_id}/milestones", headers=auth(student_token))
    ).json()[0]
    deliverable = (
        await client.post(
            f"/api/v1/milestones/{milestone['id']}/deliverables",
            headers=auth(student_token),
            json={"body": "گزارش ده مصاحبه"},
        )
    ).json()
    response = await client.post(
        f"/api/v1/deliverables/{deliverable['id']}/review",
        headers=auth(lead_token),
        json={
            "decision": "APPROVED",
            "feedback": "عالی",
            "rubric_scores": {"completeness": 5, "quality": 5},
        },
    )
    assert response.status_code == 200, response.text
    response = await client.post(
        f"/api/v1/projects/{project_id}/complete",
        headers=auth(lead_token),
        json={"final_report": "پروژه بسته شد."},
    )
    assert response.status_code == 200, response.text

    student_items = await _ledger(client, student_token)
    assert D(_active(student_items, "APPLICATION_ACCEPTED")[0]["amount"]) == D(10)
    [approved] = _active(student_items, "MILESTONE_APPROVED")
    assert D(approved["amount"]) == D(60)  # ۵۰ × ۱٫۲ کیفیت بالا
    assert approved["note"] == "کیفیت بالا ×1.2"
    assert approved["category"] == "LEARNING"  # D_PERSONAL ⇒ LEARNING
    # ۱۵۰ × (۰٫۷ + ۰٫۱۵×۲) × ۰٫۵ برای پروژهٔ شخصی
    assert D(_active(student_items, "PROJECT_COMPLETED")[0]["amount"]) == D(75)

    lead_items = await _ledger(client, lead_token)
    assert not _active(lead_items, "MILESTONE_APPROVED")  # بازبین خودش را تأیید نمی‌کند
    assert D(_active(lead_items, "PROJECT_COMPLETED")[0]["amount"]) == D(75)

    # FR-DASH-01 — «منشأ هر امتیاز» با فیلتر همان منبع.
    filtered = await _ledger(client, student_token, source_type="PROJECT", source_id=project_id)
    assert [i["rule_code"] for i in filtered] == ["PROJECT_COMPLETED"]
    assert filtered[0]["source_href"] == f"/projects/{project_id}"
    assert lead_id != student_id


# ── نیمرخ و نشان ───────────────────────────────────────────────────────
async def test_completing_the_profile_earns_points_and_the_first_badge(
    client: Any, db_session: Any
) -> None:
    from silp.services.badge_service import BadgeService

    token = await login(client, "09121500021")
    await complete_profile(client, token)
    user_id = uuid.UUID((await me(client, token))["id"])

    [profile] = _active(await _ledger(client, token), "PROFILE_COMPLETED")
    assert D(profile["amount"]) == D(20)

    # §9.5 — نشان در کار پس‌زمینه، نه در مسیر درخواست.
    badges = (await client.get("/api/v1/me/badges", headers=auth(token))).json()
    assert "FIRST_STEP" not in {b["code"] for b in badges["earned"]}

    assert await BadgeService(db_session).evaluate_recent() >= 1
    assert await BadgeService(db_session).evaluate_user(user_id) == []  # بی‌اثر در تکرار

    badges = (await client.get("/api/v1/me/badges", headers=auth(token))).json()
    [first] = [b for b in badges["earned"] if b["code"] == "FIRST_STEP"]
    assert first["seen"] is False
    assert len(badges["earned"]) + len(badges["locked"]) == 21
    sharp = next(b for b in badges["locked"] if b["code"] == "SHARP_MIND")
    assert (D(sharp["progress_current"]), D(sharp["progress_target"])) == (D(0), D(5))

    response = await client.post("/api/v1/me/badges/seen", headers=auth(token), json={})
    assert response.json()["updated"] == 1
    badges = (await client.get("/api/v1/me/badges", headers=auth(token))).json()
    assert all(b["seen"] for b in badges["earned"])

    response = await client.get("/api/v1/me", headers=auth(token))
    assert response.json()["points"] == {"total": "20.00", "level": 1, "next_level_at": 50}


async def test_every_seeded_badge_criterion_is_valid(db_session: Any) -> None:
    """۲۱ نشان §9.5 — معیار خراب فقط در زمان اجرا دیده می‌شد."""
    from silp.domain.gamification.badges import validate
    from silp.models.gamification import Badge

    badges = list(await db_session.scalars(select(Badge)))
    assert len(badges) == 21
    for badge in badges:
        validate(badge.criteria)


# ── رتبه‌بندی — §9.7 ───────────────────────────────────────────────────
async def test_leaderboard_hides_opted_out_users_but_not_from_themselves(
    client: Any, db_session: Any
) -> None:
    from silp.services.points_service import Award, PointsService

    term = await _current_term(db_session)
    points = PointsService(db_session)
    viewer = await _user(db_session, "09121500031", name="بیننده")
    ghost = await _user(db_session, "09121500032", name="پنهان", public=False)
    others = [await _user(db_session, f"091215004{i:02d}", name=f"نفر{i}") for i in range(12)]

    async def give(user: Any, amount: int) -> None:
        await points.award(
            user.id,
            Award("MILESTONE_APPROVED", "MILESTONE", uuid.uuid4(), multiplier=D(amount)),
            term_id=term.id,
        )

    await give(ghost, 1000)
    for i, user in enumerate(others):
        await give(user, 100 + 10 * i)
    await give(viewer, 105)
    await points.refresh_totals()

    token = await login(client, "09121500031")
    response = await client.get("/api/v1/leaderboard", headers=auth(token))
    assert response.status_code == 200, response.text
    board = response.json()
    names = [e["user"]["display_name"] for e in board["entries"]]
    assert len(names) == 10
    assert "پنهان آزمایشی" not in names
    assert board["entries"][0]["rank"] == 1 and board["entries"][0]["total"] == "210.00"
    # ۱۳ نفر در جدول؛ بیننده بالاتر از یک نفر (۱۰۰) است.
    assert board["me"]["rank"] == 12
    assert board["me"]["percentile"] == round(100 * 1 / 13)
    assert not any(e["is_me"] for e in board["entries"])

    ghost_token = await login(client, "09121500032")
    board = (await client.get("/api/v1/leaderboard", headers=auth(ghost_token))).json()
    assert board["me"]["rank"] == 1 and board["me"]["hidden"] is True
    assert board["me"]["excluded_reason"] == "OPTED_OUT"
    assert "پنهان آزمایشی" not in [e["user"]["display_name"] for e in board["entries"]]


async def test_offering_leaderboard_is_not_found_for_outsiders(
    client: Any, db_session: Any
) -> None:
    scene = await _scene(client, db_session)
    params = {"scope": "OFFERING", "scope_id": str(scene["offering"].id)}

    response = await client.get(
        "/api/v1/leaderboard", headers=auth(scene["student_token"]), params=params
    )
    assert response.status_code == 200, response.text

    outsider = await login(client, "09121500051")
    response = await client.get("/api/v1/leaderboard", headers=auth(outsider), params=params)
    assert response.status_code == 404, response.text


# ── داشبوردها ──────────────────────────────────────────────────────────
async def test_student_dashboard_points_to_the_open_quiz(client: Any, db_session: Any) -> None:
    scene = await _scene(client, db_session)
    await _add_question(client, scene, kind="SINGLE_CHOICE", payload=SINGLE_PAYLOAD)
    await _publish(client, scene)

    response = await client.get("/api/v1/me/dashboard", headers=auth(scene["student_token"]))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["next_step"]["kind"] == "QUIZ_OPEN"
    assert body["next_step"]["href"] == f"/courses/{scene['offering'].id}/quizzes"
    assert [c["offering_id"] for c in body["courses"]] == [str(scene["offering"].id)]
    assert len(body["trend"]) == 12
    assert any(e["kind"] == "QUIZ_CLOSES" for e in body["upcoming"])
    assert body["points"]["level"]["level"] == 1


async def test_teach_dashboard_surfaces_what_needs_action(client: Any, db_session: Any) -> None:
    from silp.models.education import Enrollment

    scene = await _scene(client, db_session)
    applicant = await login(client, "09121500061")
    applicant_id = uuid.UUID((await me(client, applicant))["id"])
    db_session.add(
        Enrollment(offering_id=scene["offering"].id, student_id=applicant_id, status="PENDING")
    )
    await db_session.flush()

    response = await client.get("/api/v1/teach/dashboard", headers=auth(scene["instructor_token"]))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["needs_attention"]["enrollment_requests"]["count"] == 1
    [stats] = [o for o in body["offerings"] if o["id"] == str(scene["offering"].id)]
    assert stats["students"] == 1

    # دانشجو هیچ ارائه‌ای ندارد و صف خالی می‌بیند — نه دادهٔ کلاس دیگری.
    response = await client.get("/api/v1/teach/dashboard", headers=auth(scene["student_token"]))
    assert response.status_code == 200, response.text
    assert response.json()["offerings"] == []


async def test_learning_scores_are_for_the_offerings_staff_only(
    client: Any, db_session: Any
) -> None:
    scene = await _scene(client, db_session)
    await _week_with_resource(client, scene)
    url = f"/api/v1/teach/offerings/{scene['offering'].id}/learning-scores"

    response = await client.get(url, headers=auth(scene["instructor_token"]))
    assert response.status_code == 200, response.text
    [row] = response.json()
    assert row["score"] == "0.0"  # یک منبع الزامی، خوانده‌نشده
    study = next(c for c in row["components"] if c["key"] == "study")
    assert (D(study["earned"]), D(study["possible"]), D(study["weight"])) == (D(0), D(1), D(100))

    response = await client.get(url, headers=auth(scene["student_token"]))
    assert response.status_code == 403, response.text


# ── مدیریت — §9.9 ──────────────────────────────────────────────────────
async def test_recalculation_reverses_and_reawards_without_deleting(
    client: Any, db_session: Any
) -> None:
    from silp.models.gamification import PointEntry
    from silp.services.points_service import Award, PointsService

    admin_token = await login(client, "09121500071")
    admin = await me(client, admin_token)
    await grant_role(db_session, admin["id"], "ADMIN")
    admin_token = await login(client, "09121500071")

    user = await _user(db_session, "09121500072")
    source = uuid.uuid4()
    await PointsService(db_session).award(user.id, Award("QUIZ_ATTEMPTED", "QUIZ", source))

    response = await client.patch(
        "/api/v1/admin/point-rules/QUIZ_ATTEMPTED",
        headers=auth(admin_token),
        json={"base_points": "8"},
    )
    assert response.status_code == 200, response.text
    # قاعده عوض شد ولی گذشته نه (FR-GAM-02).
    assert (await PointsService(db_session).summary(user.id)).level.total == D(5)

    response = await client.post(
        "/api/v1/admin/point-rules/recalculate",
        headers=auth(admin_token),
        json={"rule_code": "QUIZ_ATTEMPTED"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["reversed"] >= 1

    rows = list(
        await db_session.scalars(
            select(PointEntry).where(PointEntry.user_id == user.id).order_by(PointEntry.id)
        )
    )
    assert [(r.amount, r.revision) for r in rows] == [(D(5), 0), (D(-5), 0), (D(8), 1)]


async def test_students_cannot_touch_point_rules(client: Any, db_session: Any) -> None:
    token = await login(client, "09121500081")
    response = await client.get("/api/v1/admin/point-rules", headers=auth(token))
    assert response.status_code == 403
    response = await client.post(
        f"/api/v1/admin/point-entries/{uuid.uuid4()}/reverse",
        headers=auth(token),
        json={"reason": "تلاش برای حذف"},
    )
    assert response.status_code == 403


async def test_admin_reads_a_users_ledger_and_reverses_one_entry(
    client: Any, db_session: Any
) -> None:
    """§9.9 — مدیر دفتر کل کاربر را می‌بیند و ردیف را با رکورد معکوس اصلاح می‌کند."""
    from silp.services.points_service import Award, PointsService

    admin_token = await login(client, "09121500111")
    await grant_role(db_session, (await me(client, admin_token))["id"], "ADMIN")
    admin_token = await login(client, "09121500111")

    user = await _user(db_session, "09121500112")
    entry = await PointsService(db_session).award(
        user.id, Award("QUIZ_ATTEMPTED", "QUIZ", uuid.uuid4())
    )
    assert entry is not None

    url = f"/api/v1/admin/users/{user.id}/points"
    response = await client.get(url, headers=auth(admin_token))
    assert response.status_code == 200, response.text
    [row] = response.json()["items"]
    assert (row["id"], row["is_reversed"]) == (str(entry.id), False)

    response = await client.post(
        f"/api/v1/admin/point-entries/{entry.id}/reverse",
        headers=auth(admin_token),
        json={"reason": "ثبت اشتباه"},
    )
    assert response.status_code == 201, response.text

    items = (await client.get(url, headers=auth(admin_token))).json()["items"]
    assert [(i["reverses_id"], i["is_reversed"]) for i in items] == [
        (str(entry.id), False),
        (None, True),
    ]  # اصلاح، سپس اصلیِ خط‌خورده — هیچ ردیفی پاک نشد.


async def test_only_point_admins_read_another_users_ledger(client: Any, db_session: Any) -> None:
    admin_token = await login(client, "09121500121")
    await grant_role(db_session, (await me(client, admin_token))["id"], "ADMIN")
    admin_token = await login(client, "09121500121")
    target = await _user(db_session, "09121500122")
    url = f"/api/v1/admin/users/{target.id}/points"

    # دانشجو و استاد (که امتیاز دستی می‌دهد) دفتر دیگران را نمی‌خوانند.
    for phone, role in (("09121500123", None), ("09121500124", "INSTRUCTOR")):
        token = await login(client, phone)
        if role:
            await grant_role(db_session, (await me(client, token))["id"], role)
            token = await login(client, phone)
        assert (await client.get(url, headers=auth(token))).status_code == 403

    missing = f"/api/v1/admin/users/{uuid.uuid4()}/points"
    assert (await client.get(missing, headers=auth(admin_token))).status_code == 404


async def test_milestone_due_soon_becomes_the_next_step(client: Any, db_session: Any) -> None:
    lead_token, _ = await _actor(client, db_session, "09121500091", first_name="مدیر")
    project_id = await _published_project(client, db_session, lead_token)
    await client.post(f"/api/v1/projects/{project_id}/start", headers=auth(lead_token))
    due = (datetime.now(UTC) + timedelta(days=2)).date().isoformat()
    response = await client.post(
        f"/api/v1/projects/{project_id}/milestones",
        headers=auth(lead_token),
        json=milestone_payload(title_fa="مرحلهٔ فوری", sort_order=0, due_on=due),
    )
    assert response.status_code == 201, response.text

    body = (await client.get("/api/v1/me/dashboard", headers=auth(lead_token))).json()
    assert body["next_step"]["kind"] == "MILESTONE_DUE"
    assert "مرحلهٔ فوری" in body["next_step"]["title"]
    assert body["projects"][0]["next_milestone_title"] == "مرحلهٔ فوری"


async def test_staff_do_not_compete_with_students(client: Any, db_session: Any) -> None:
    """استاد و مدیر هم برای نیمرخ امتیاز می‌گیرند، ولی در جدول دانشجویان نیستند."""
    from silp.services.points_service import Award, PointsService

    term = await _current_term(db_session)
    points = PointsService(db_session)
    student = await _user(db_session, "09121500101", name="دانشجو")
    admin = await _user(db_session, "09121500102", name="مدیر")
    await grant_role(db_session, admin.id, "ADMIN")
    for user, amount in ((student, 10), (admin, 500)):
        await points.award(
            user.id,
            Award("MILESTONE_APPROVED", "MILESTONE", uuid.uuid4(), multiplier=D(amount)),
            term_id=term.id,
        )
    await points.refresh_totals()

    board = (
        await client.get("/api/v1/leaderboard", headers=auth(await login(client, "09121500101")))
    ).json()
    assert [e["user"]["display_name"] for e in board["entries"]] == ["دانشجو آزمایشی"]
    assert board["me"]["rank"] == 1

    staff_view = (
        await client.get("/api/v1/leaderboard", headers=auth(await login(client, "09121500102")))
    ).json()["me"]
    assert (staff_view["rank"], staff_view["excluded_reason"]) == (None, "STAFF")
