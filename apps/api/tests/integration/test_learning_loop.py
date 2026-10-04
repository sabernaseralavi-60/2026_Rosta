"""حلقهٔ یادگیری روزانه — ADR-0036: درس‌نامه، چالش با استخر، شایستگی، استمرار، امتیاز.

از HTTP تا دیتابیس واقعی: چالش از بانکِ مفهوم‌دار ساخته می‌شود، هر دانشجو n سؤال از استخر
می‌گیرد، پاسخ‌ها شایستگی و استمرار را می‌سازند و امتیاز فقط از قواعد چالش می‌آید.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select
from tests.integration.helpers import auth, grant_role, invalidate, login, me

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

INSTRUCTOR_MOBILE = "09122320001"
STUDENT_MOBILE = "09122320002"
SECOND_STUDENT_MOBILE = "09122320003"
OUTSIDER_MOBILE = "09122320004"

SINGLE = {
    "options": [{"id": "a", "text": "الف"}, {"id": "b", "text": "ب"}],
    "correct": ["b"],
}


async def _scene(client: Any, session: Any) -> dict[str, Any]:
    from silp.models.education import Course, CourseOffering, Enrollment, Term

    instructor_token = await login(client, INSTRUCTOR_MOBILE)
    instructor = await me(client, instructor_token)
    await grant_role(session, instructor["id"], "INSTRUCTOR")

    users: dict[str, dict[str, str]] = {}
    for key, mobile in (
        ("a", STUDENT_MOBILE),
        ("b", SECOND_STUDENT_MOBILE),
        ("outsider", OUTSIDER_MOBILE),
    ):
        token = await login(client, mobile)
        users[key] = {"token": token, "id": (await me(client, token))["id"]}

    marker = uuid.uuid4().hex[:8]
    term = Term(
        code=f"T-{marker}",
        title_fa="نیم‌سال آزمایشی",
        starts_on=date(2026, 9, 23),
        ends_on=date(2027, 2, 4),
    )
    course = Course(code=f"C-{marker}", slug=f"course-{marker}", title_fa="درس آزمایشی")
    session.add_all([term, course])
    await session.flush()
    offering = CourseOffering(
        course_id=course.id,
        term_id=term.id,
        instructor_id=uuid.UUID(instructor["id"]),
        status="OPEN",
    )
    session.add(offering)
    await session.flush()
    for key in ("a", "b"):
        session.add(
            Enrollment(
                offering_id=offering.id, student_id=uuid.UUID(users[key]["id"]), status="ACTIVE"
            )
        )
    await session.flush()
    await invalidate(instructor["id"])
    return {
        "offering": str(offering.id),
        "staff": auth(await login(client, INSTRUCTOR_MOBILE)),
        "users": users,
    }


def _h(scene: dict[str, Any], key: str) -> dict[str, str]:
    return auth(scene["users"][key]["token"])


async def _taxonomy(client: Any, scene: dict[str, Any]) -> dict[str, str]:
    """دو شایستگی، هرکدام یک مفهوم، و شش سؤال بانک برای هر مفهوم."""
    suffix = uuid.uuid4().hex[:6]
    concepts: dict[str, str] = {}
    for name in ("capacity", "flow"):
        comp = await client.post(
            "/api/v1/learning/competencies",
            headers=scene["staff"],
            json={"code": f"{name}-{suffix}", "title_fa": f"شایستگی {name}"},
        )
        assert comp.status_code == 201, comp.text
        concept = await client.post(
            f"/api/v1/learning/competencies/{comp.json()['id']}/concepts",
            headers=scene["staff"],
            json={"code": f"{name}-c-{suffix}", "title_fa": f"مفهوم {name}"},
        )
        assert concept.status_code == 201, concept.text
        concepts[name] = concept.json()["id"]
        for index in range(6):
            item = await client.post(
                "/api/v1/teach/question-bank",
                headers=scene["staff"],
                json={
                    "kind": "SINGLE_CHOICE",
                    "body": f"سؤال {name} شمارهٔ {index}",
                    "payload": SINGLE,
                    "concept_id": concepts[name],
                },
            )
            assert item.status_code == 201, item.text
            assert item.json()["concept_id"] == concepts[name]
    return concepts


async def _checkpoint(
    client: Any, scene: dict[str, Any], concepts: dict[str, str], **overrides: Any
) -> dict[str, Any]:
    now = datetime.now(UTC)
    body = {
        "title_fa": "چالش امروز",
        "concept_ids": list(concepts.values()),
        "draw_count": 4,
        "opens_at": (now - timedelta(minutes=5)).isoformat(),
        "closes_at": (now + timedelta(hours=3)).isoformat(),
        "duration_min": 8,
        "publish": True,
        **overrides,
    }
    response = await client.post(
        f"/api/v1/learning/teach/offerings/{scene['offering']}/checkpoints",
        headers=scene["staff"],
        json=body,
    )
    assert response.status_code == 201, response.text
    return dict(response.json())


async def _take(
    client: Any, scene: dict[str, Any], key: str, quiz_id: str, *, wrong: int = 0
) -> dict[str, Any]:
    started = await client.post(f"/api/v1/quizzes/{quiz_id}/attempts", headers=_h(scene, key))
    assert started.status_code == 201, started.text
    attempt_id = started.json()["attempt_id"]
    view = (await client.get(f"/api/v1/attempts/{attempt_id}", headers=_h(scene, key))).json()
    questions = view["questions"]
    for index, question in enumerate(questions):
        choice = "a" if index < wrong else "b"
        saved = await client.put(
            f"/api/v1/attempts/{attempt_id}/answers/{question['id']}",
            headers=_h(scene, key),
            json={"response": {"selected": [choice]}},
        )
        assert saved.status_code == 200, saved.text
    done = await client.post(
        f"/api/v1/attempts/{attempt_id}/submit",
        headers=_h(scene, key),
        json={"confirm_unanswered": 0},
    )
    assert done.status_code == 200, done.text
    return {"attempt_id": attempt_id, "question_ids": [q["id"] for q in questions]}


async def test_lessons_draft_is_hidden_and_outsiders_are_blocked(
    client: Any, db_session: Any
) -> None:
    scene = await _scene(client, db_session)
    offering = scene["offering"]
    base = f"/api/v1/learning/teach/offerings/{offering}/lessons"

    draft = await client.post(
        base, headers=scene["staff"], json={"title_fa": "پیش‌نویس", "body_md": "# متن"}
    )
    assert draft.status_code == 201, draft.text
    assert draft.json()["status"] == "DRAFT"
    live = await client.post(
        base,
        headers=scene["staff"],
        json={
            "title_fa": "جریان آزاد",
            "body_md": "متن **درس**",
            "est_minutes": 7,
            "publish": True,
        },
    )
    assert live.status_code == 201, live.text

    listed = (
        await client.get(f"/api/v1/learning/offerings/{offering}/lessons", headers=_h(scene, "a"))
    ).json()
    assert [row["title_fa"] for row in listed] == ["جریان آزاد"]
    assert "body_md" not in listed[0]

    detail = await client.get(
        f"/api/v1/learning/lessons/{live.json()['id']}", headers=_h(scene, "a")
    )
    assert detail.status_code == 200
    assert detail.json()["body_md"] == "متن **درس**"
    hidden = await client.get(
        f"/api/v1/learning/lessons/{draft.json()['id']}", headers=_h(scene, "a")
    )
    assert hidden.status_code == 404

    outsider = await client.get(
        f"/api/v1/learning/lessons/{live.json()['id']}", headers=_h(scene, "outsider")
    )
    assert outsider.status_code == 403
    student_write = await client.post(
        base, headers=_h(scene, "a"), json={"title_fa": "نفوذ", "body_md": "x"}
    )
    assert student_write.status_code == 403

    # برگرداندن به پیش‌نویس، درس را از دید دانشجو برمی‌دارد.
    back = await client.post(
        f"{base}/{live.json()['id']}/publish", headers=scene["staff"], json={"published": False}
    )
    assert back.status_code == 200
    again = (
        await client.get(f"/api/v1/learning/offerings/{offering}/lessons", headers=_h(scene, "a"))
    ).json()
    assert again == []


async def test_future_dated_lesson_is_not_visible_yet(client: Any, db_session: Any) -> None:
    scene = await _scene(client, db_session)
    offering = scene["offering"]
    soon = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    created = await client.post(
        f"/api/v1/learning/teach/offerings/{offering}/lessons",
        headers=scene["staff"],
        json={"title_fa": "فردا", "body_md": "متن", "publish": True, "publish_at": soon},
    )
    assert created.status_code == 201, created.text
    listed = (
        await client.get(f"/api/v1/learning/offerings/{offering}/lessons", headers=_h(scene, "a"))
    ).json()
    assert listed == []


async def test_checkpoint_draws_from_pool_and_builds_skills_streak_and_points(
    client: Any, db_session: Any
) -> None:
    from silp.models.gamification import PointEntry
    from silp.models.learning import CompetencyMastery, Streak
    from silp.services.learning_service import LearningService

    scene = await _scene(client, db_session)
    concepts = await _taxonomy(client, scene)
    lesson = await client.post(
        f"/api/v1/learning/teach/offerings/{scene['offering']}/lessons",
        headers=scene["staff"],
        json={"title_fa": "ظرفیت", "body_md": "متن", "publish": True},
    )
    checkpoint = await _checkpoint(client, scene, concepts, lesson_id=lesson.json()["id"])
    assert checkpoint["draw_count"] == 4
    assert checkpoint["pool_size"] == 12

    today = (await client.get("/api/v1/learning/today", headers=_h(scene, "a"))).json()
    card = today["offerings"][0]
    assert card["checkpoint"]["state"] == "AVAILABLE"
    assert card["checkpoint"]["question_count"] == 4
    assert card["lesson"]["title"] == "ظرفیت"
    assert card["streak"] == {"current": 0, "longest": 0, "alive": False}

    first = await _take(client, scene, "a", checkpoint["id"], wrong=1)
    assert len(first["question_ids"]) == 4  # نه ۱۲

    second = await _take(client, scene, "b", checkpoint["id"], wrong=0)
    assert len(second["question_ids"]) == 4

    after = (await client.get("/api/v1/learning/today", headers=_h(scene, "a"))).json()
    card = after["offerings"][0]
    assert card["checkpoint"]["state"] == "DONE"
    assert card["streak"]["current"] == 1
    assert card["last_result"]["total"] == 4
    assert card["last_result"]["correct"] == 3
    assert sum(s["total"] for s in card["last_result"]["skills"]) == 4
    assert {m["level"] for m in after["mastery"]} == {"LOW_DATA"}  # شاهد کم

    user_id = uuid.UUID(scene["users"]["a"]["id"])
    rows = (
        await db_session.scalars(
            select(CompetencyMastery).where(CompetencyMastery.user_id == user_id)
        )
    ).all()
    assert sum(r.evidence_n for r in rows) == 4
    streak = await db_session.get(Streak, (user_id, uuid.UUID(scene["offering"])))
    assert streak is not None
    assert streak.current == 1

    codes = set(
        await db_session.scalars(select(PointEntry.rule_code).where(PointEntry.user_id == user_id))
    )
    assert "CHECKPOINT_DONE" in codes
    assert "CHECKPOINT_HIGH" not in codes  # ۳ از ۴ = ۷۵٪ < ۸۰٪
    assert codes.isdisjoint({"QUIZ_ATTEMPTED", "QUIZ_SCORE", "QUIZ_PERFECT", "QUIZ_FIRST_TRY"})

    perfect_codes = set(
        await db_session.scalars(
            select(PointEntry.rule_code).where(
                PointEntry.user_id == uuid.UUID(scene["users"]["b"]["id"])
            )
        )
    )
    assert {"CHECKPOINT_DONE", "CHECKPOINT_HIGH"} <= perfect_codes

    # پردازش دوباره‌ی همان تلاش (مثلاً تصحیح دستی) شاهد را دوبار نمی‌شمارد.
    from silp.models.quiz import Quiz, QuizAttempt

    attempt = await db_session.get(QuizAttempt, uuid.UUID(first["attempt_id"]))
    quiz = await db_session.get(Quiz, attempt.quiz_id)
    assert await LearningService(db_session).process_checkpoint_attempt(attempt, quiz) is None
    rows_again = (
        await db_session.scalars(
            select(CompetencyMastery).where(CompetencyMastery.user_id == user_id)
        )
    ).all()
    assert sum(r.evidence_n for r in rows_again) == 4


async def test_checkpoint_rules_are_enforced(client: Any, db_session: Any) -> None:
    scene = await _scene(client, db_session)
    concepts = await _taxonomy(client, scene)
    base = f"/api/v1/learning/teach/offerings/{scene['offering']}/checkpoints"
    now = datetime.now(UTC)
    window = {
        "opens_at": now.isoformat(),
        "closes_at": (now + timedelta(hours=1)).isoformat(),
    }

    too_big = await client.post(
        base,
        headers=scene["staff"],
        json={
            "title_fa": "بزرگ",
            "concept_ids": list(concepts.values()),
            "draw_count": 30,
            **window,
        },
    )
    assert too_big.status_code == 409
    assert too_big.json()["error"]["code"] == "POOL_TOO_SMALL"

    no_concepts = await client.post(
        base, headers=scene["staff"], json={"title_fa": "بی‌مفهوم", "concept_ids": [], **window}
    )
    assert no_concepts.status_code == 422

    student = await client.post(
        base,
        headers=_h(scene, "a"),
        json={"title_fa": "نفوذ", "concept_ids": list(concepts.values()), **window},
    )
    assert student.status_code == 403

    duplicate = await client.post(
        "/api/v1/learning/competencies",
        headers=scene["staff"],
        json={"code": "dup-code", "title_fa": "الف"},
    )
    assert duplicate.status_code == 201
    again = await client.post(
        "/api/v1/learning/competencies",
        headers=scene["staff"],
        json={"code": "dup-code", "title_fa": "ب"},
    )
    assert again.status_code == 409

    student_taxonomy = await client.post(
        "/api/v1/learning/competencies",
        headers=_h(scene, "a"),
        json={"code": "student-made", "title_fa": "نفوذ"},
    )
    assert student_taxonomy.status_code == 403
