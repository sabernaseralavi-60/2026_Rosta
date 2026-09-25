"""چرخهٔ کامل آزمون — از ساخت تا اعتراض به نمره.

مرجع: FR-QUIZ-01 تا FR-QUIZ-05، §5.6، §7.3، §7.12، ADR-0011.

**فهرست تست‌های اجباری §13 برای M4.** چهارتایشان منطق خالص‌اند و در
`tests/unit/test_quiz_grading.py` هستند؛ چهارتای باقی‌مانده اینجا:

* `test_answer_after_expiry_is_rejected`
* `test_offline_sync_preserves_pre_expiry_answers`
* `test_concurrent_submit_does_not_double_grade`
* `test_auto_close_job_is_idempotent`

چیزی که هیچ تست واحدی نشان نمی‌دهد و اینجا نشان داده می‌شود: قیدهای
پایگاه‌داده زیر رقابت واقعی، تریگر `total_points`، و اینکه کلید پاسخ
واقعاً از مسیر HTTP بیرون نمی‌آید.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from tests.integration.helpers import auth, grant_role, invalidate, login, me

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

INSTRUCTOR_MOBILE = "09121220001"
STUDENT_MOBILE = "09121220002"
OTHER_STUDENT_MOBILE = "09121220003"
OUTSIDER_MOBILE = "09121220004"

SINGLE_PAYLOAD = {
    "options": [
        {"id": "a", "text": "پواسون"},
        {"id": "b", "text": "دوجمله‌ای منفی"},
    ],
    "correct": ["b"],
}
MULTI_PAYLOAD = {
    "options": [
        {"id": "a", "text": "TTC"},
        {"id": "b", "text": "PET"},
        {"id": "c", "text": "AADT"},
    ],
    "correct": ["a", "b"],
}
ESSAY_PAYLOAD = {"min_words": 10, "max_words": 200, "rubric": "سه معیار"}


# ── ساخت صحنه ──────────────────────────────────────────────────────────
async def _scene(
    client: Any,
    session: Any,
    *,
    duration_min: int = 30,
    max_attempts: int = 1,
    opens_delta: timedelta = timedelta(minutes=-5),
    closes_delta: timedelta = timedelta(hours=3),
    result_visibility: str = "IMMEDIATE",
    shuffle: bool = False,
) -> dict[str, Any]:
    """استاد + درس + ارائه + دانشجوی ثبت‌نام‌شده + آزمون منتشرشده."""
    from silp.models.education import Course, CourseOffering, Enrollment, Term

    instructor_token = await login(client, INSTRUCTOR_MOBILE)
    instructor = await me(client, instructor_token)
    await grant_role(session, instructor["id"], "INSTRUCTOR")
    instructor_token = await login(client, INSTRUCTOR_MOBILE)

    student_token = await login(client, STUDENT_MOBILE)
    student = await me(client, student_token)

    marker = uuid.uuid4().hex[:8]
    term = Term(
        code=f"T-{marker}",
        title_fa="نیم‌سال آزمایشی",
        starts_on=date(2026, 9, 23),
        ends_on=date(2027, 2, 4),
    )
    course = Course(code=f"C-{marker}", slug=f"course-{marker}", title_fa="ایمنی راه")
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
    await invalidate(instructor["id"])

    session.add(
        Enrollment(offering_id=offering.id, student_id=uuid.UUID(student["id"]), status="ACTIVE")
    )
    await session.flush()

    now = datetime.now(UTC)
    response = await client.post(
        f"/api/v1/teach/offerings/{offering.id}/quizzes",
        headers=auth(instructor_token),
        json={
            "title_fa": "آزمون هفتهٔ پنجم",
            "duration_min": duration_min,
            "opens_at": (now + opens_delta).isoformat(),
            "closes_at": (now + closes_delta).isoformat(),
            "max_attempts": max_attempts,
            "result_visibility": result_visibility,
            "shuffle_questions": shuffle,
            "shuffle_options": shuffle,
        },
    )
    assert response.status_code == 201, response.text
    quiz_id = response.json()["id"]

    return {
        "instructor_token": instructor_token,
        "instructor_id": instructor["id"],
        "student_token": student_token,
        "student_id": student["id"],
        "offering": offering,
        "course": course,
        "quiz_id": quiz_id,
    }


async def _add_question(
    client: Any,
    scene: dict[str, Any],
    *,
    kind: str,
    payload: dict,
    points: str = "1",
    body: str = "سؤال",
) -> str:
    response = await client.post(
        f"/api/v1/teach/quizzes/{scene['quiz_id']}/questions",
        headers=auth(scene["instructor_token"]),
        json={"kind": kind, "body": body, "payload": payload, "points": points},
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


async def _publish(client: Any, scene: dict[str, Any]) -> None:
    response = await client.post(
        f"/api/v1/teach/quizzes/{scene['quiz_id']}/publish",
        headers=auth(scene["instructor_token"]),
    )
    assert response.status_code == 200, response.text


async def _start(client: Any, scene: dict[str, Any], token: str | None = None) -> dict[str, Any]:
    response = await client.post(
        f"/api/v1/quizzes/{scene['quiz_id']}/attempts",
        headers=auth(token or scene["student_token"]),
    )
    assert response.status_code == 201, response.text
    return dict(response.json())


# ── ساخت آزمون — FR-QUIZ-01 ────────────────────────────────────────────
async def test_total_points_is_kept_by_the_database_trigger(client: Any, db_session: Any) -> None:
    """§7.12 — `total_points` مشتق است و اپلیکیشن نمی‌نویسدش."""
    scene = await _scene(client, db_session)
    await _add_question(client, scene, kind="SINGLE_CHOICE", payload=SINGLE_PAYLOAD, points="2.5")
    await _add_question(client, scene, kind="MULTI_CHOICE", payload=MULTI_PAYLOAD, points="1.5")

    response = await client.get(
        f"/api/v1/teach/quizzes/{scene['quiz_id']}", headers=auth(scene["instructor_token"])
    )
    assert response.status_code == 200, response.text
    assert float(response.json()["total_points"]) == 4.0


async def test_quiz_without_questions_cannot_be_published(client: Any, db_session: Any) -> None:
    scene = await _scene(client, db_session)
    response = await client.post(
        f"/api/v1/teach/quizzes/{scene['quiz_id']}/publish",
        headers=auth(scene["instructor_token"]),
    )
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "QUIZ_HAS_NO_QUESTIONS"


async def test_bad_payload_is_rejected_with_a_useful_message(client: Any, db_session: Any) -> None:
    scene = await _scene(client, db_session)
    response = await client.post(
        f"/api/v1/teach/quizzes/{scene['quiz_id']}/questions",
        headers=auth(scene["instructor_token"]),
        json={
            "kind": "SINGLE_CHOICE",
            "body": "سؤال",
            "payload": {"options": SINGLE_PAYLOAD["options"], "correct": ["a", "b"]},
            "points": "1",
        },
    )
    assert response.status_code == 422, response.text
    assert "دقیقاً یک" in response.json()["error"]["message"]


async def test_questions_are_frozen_once_someone_has_attempted(
    client: Any, db_session: Any
) -> None:
    scene = await _scene(client, db_session)
    await _add_question(client, scene, kind="SINGLE_CHOICE", payload=SINGLE_PAYLOAD)
    await _publish(client, scene)
    await _start(client, scene)

    response = await client.post(
        f"/api/v1/teach/quizzes/{scene['quiz_id']}/questions",
        headers=auth(scene["instructor_token"]),
        json={"kind": "TRUE_FALSE", "body": "سؤال تازه", "payload": {"correct": True}},
    )
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "QUIZ_HAS_ATTEMPTS"


# ── دسترسی ─────────────────────────────────────────────────────────────
async def test_non_enrolled_user_cannot_start(client: Any, db_session: Any) -> None:
    """ADR-0009 — آزمون نمره‌دار فروختنی نیست؛ اشتراک بازش نمی‌کند."""
    scene = await _scene(client, db_session)
    await _add_question(client, scene, kind="SINGLE_CHOICE", payload=SINGLE_PAYLOAD)
    await _publish(client, scene)

    outsider_token = await login(client, OUTSIDER_MOBILE)
    response = await client.post(
        f"/api/v1/quizzes/{scene['quiz_id']}/attempts", headers=auth(outsider_token)
    )
    assert response.status_code == 403, response.text


async def test_another_students_attempt_is_not_found_not_forbidden(
    client: Any, db_session: Any
) -> None:
    """§6.4 قاعدهٔ ۴ — وجود تلاش دیگری از راه کد خطا لو نمی‌رود."""
    scene = await _scene(client, db_session)
    await _add_question(client, scene, kind="SINGLE_CHOICE", payload=SINGLE_PAYLOAD)
    await _publish(client, scene)
    started = await _start(client, scene)

    other_token = await login(client, OTHER_STUDENT_MOBILE)
    response = await client.get(
        f"/api/v1/attempts/{started['attempt_id']}", headers=auth(other_token)
    )
    assert response.status_code == 404, response.text


async def test_draft_quiz_is_invisible_to_students(client: Any, db_session: Any) -> None:
    scene = await _scene(client, db_session)
    await _add_question(client, scene, kind="SINGLE_CHOICE", payload=SINGLE_PAYLOAD)
    response = await client.get(
        f"/api/v1/quizzes/{scene['quiz_id']}", headers=auth(scene["student_token"])
    )
    assert response.status_code == 404, response.text


# ── کلید پاسخ نشت نمی‌کند — الزام امنیتی §5.6 ─────────────────────────
async def test_correct_answers_never_leak_over_http(client: Any, db_session: Any) -> None:
    scene = await _scene(client, db_session)
    await _add_question(client, scene, kind="SINGLE_CHOICE", payload=SINGLE_PAYLOAD)
    await _add_question(client, scene, kind="MULTI_CHOICE", payload=MULTI_PAYLOAD)
    await _publish(client, scene)
    started = await _start(client, scene)

    response = await client.get(
        f"/api/v1/attempts/{started['attempt_id']}", headers=auth(scene["student_token"])
    )
    assert response.status_code == 200, response.text
    raw = response.text
    for question in response.json()["questions"]:
        assert "correct" not in question["payload"]
    assert '"correct"' not in raw


# ── شروع و قیدها — §7.12 ───────────────────────────────────────────────
async def test_second_active_attempt_is_refused(client: Any, db_session: Any) -> None:
    scene = await _scene(client, db_session, max_attempts=3)
    await _add_question(client, scene, kind="SINGLE_CHOICE", payload=SINGLE_PAYLOAD)
    await _publish(client, scene)
    await _start(client, scene)

    response = await client.post(
        f"/api/v1/quizzes/{scene['quiz_id']}/attempts", headers=auth(scene["student_token"])
    )
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "ACTIVE_ATTEMPT_EXISTS"


async def test_attempts_are_exhausted_after_the_limit(client: Any, db_session: Any) -> None:
    scene = await _scene(client, db_session, max_attempts=1)
    await _add_question(client, scene, kind="SINGLE_CHOICE", payload=SINGLE_PAYLOAD)
    await _publish(client, scene)
    started = await _start(client, scene)

    response = await client.post(
        f"/api/v1/attempts/{started['attempt_id']}/submit",
        headers=auth(scene["student_token"]),
        json={"confirm_unanswered": 1},
    )
    assert response.status_code == 200, response.text

    response = await client.post(
        f"/api/v1/quizzes/{scene['quiz_id']}/attempts", headers=auth(scene["student_token"])
    )
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "ATTEMPTS_EXHAUSTED"


async def test_quiz_not_open_yet(client: Any, db_session: Any) -> None:
    scene = await _scene(
        client,
        db_session,
        opens_delta=timedelta(hours=1),
        closes_delta=timedelta(hours=4),
    )
    await _add_question(client, scene, kind="SINGLE_CHOICE", payload=SINGLE_PAYLOAD)
    await _publish(client, scene)

    response = await client.post(
        f"/api/v1/quizzes/{scene['quiz_id']}/attempts", headers=auth(scene["student_token"])
    )
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "QUIZ_NOT_OPEN"


async def test_late_start_gets_only_the_time_that_is_left(client: Any, db_session: Any) -> None:
    """ADR-0011 مسئلهٔ ۳ — `expires_at` از `closes_at` جلو نمی‌زند."""
    scene = await _scene(
        client,
        db_session,
        duration_min=60,
        closes_delta=timedelta(minutes=5),
    )
    await _add_question(client, scene, kind="SINGLE_CHOICE", payload=SINGLE_PAYLOAD)
    await _publish(client, scene)
    started = await _start(client, scene)

    assert started["seconds_remaining"] <= 5 * 60


# ── ذخیرهٔ پاسخ و زمان — §7.3 ─────────────────────────────────────────
async def test_saving_the_same_answer_twice_is_idempotent(client: Any, db_session: Any) -> None:
    scene = await _scene(client, db_session)
    question_id = await _add_question(client, scene, kind="SINGLE_CHOICE", payload=SINGLE_PAYLOAD)
    await _publish(client, scene)
    started = await _start(client, scene)

    url = f"/api/v1/attempts/{started['attempt_id']}/answers/{question_id}"
    for _ in range(3):
        response = await client.put(
            url, headers=auth(scene["student_token"]), json={"response": {"selected": ["b"]}}
        )
        assert response.status_code == 200, response.text

    from sqlalchemy import func, select

    from silp.models.quiz import QuizAnswer

    count = await db_session.scalar(
        select(func.count())
        .select_from(QuizAnswer)
        .where(QuizAnswer.attempt_id == uuid.UUID(started["attempt_id"]))
    )
    assert count == 1


async def test_answer_after_expiry_is_rejected(client: Any, db_session: Any) -> None:
    """تست اجباری §13 — پس از انقضا، پاسخ تازه پذیرفته نمی‌شود."""
    scene = await _scene(client, db_session)
    question_id = await _add_question(client, scene, kind="SINGLE_CHOICE", payload=SINGLE_PAYLOAD)
    await _publish(client, scene)
    started = await _start(client, scene)

    await _expire(db_session, started["attempt_id"])

    response = await client.put(
        f"/api/v1/attempts/{started['attempt_id']}/answers/{question_id}",
        headers=auth(scene["student_token"]),
        json={"response": {"selected": ["b"]}},
    )
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "ATTEMPT_EXPIRED"


async def test_offline_sync_preserves_pre_expiry_answers(client: Any, db_session: Any) -> None:
    """تست اجباری §13 — کسی که اینترنتش قطع شد، کارش را از دست نمی‌دهد."""
    scene = await _scene(client, db_session)
    q1 = await _add_question(
        client, scene, kind="SINGLE_CHOICE", payload=SINGLE_PAYLOAD, body="سؤال ۱"
    )
    q2 = await _add_question(
        client, scene, kind="SINGLE_CHOICE", payload=SINGLE_PAYLOAD, body="سؤال ۲"
    )
    await _publish(client, scene)
    started = await _start(client, scene)

    expires_at = await _expire(db_session, started["attempt_id"])
    before = expires_at - timedelta(seconds=30)
    after = expires_at + timedelta(seconds=30)

    response = await client.post(
        f"/api/v1/attempts/{started['attempt_id']}/sync",
        headers=auth(scene["student_token"]),
        json={
            "answers": [
                {
                    "question_id": q1,
                    "response": {"selected": ["b"]},
                    "client_ts": before.isoformat(),
                },
                {
                    "question_id": q2,
                    "response": {"selected": ["b"]},
                    "client_ts": after.isoformat(),
                },
            ]
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()

    # پاسخِ پیش از انقضا پذیرفته، پاسخِ پس از آن رد.
    assert q1 in body["accepted"]
    assert q2 in body["rejected"]


async def test_sync_keeps_the_newest_client_timestamp(client: Any, db_session: Any) -> None:
    scene = await _scene(client, db_session)
    question_id = await _add_question(client, scene, kind="SINGLE_CHOICE", payload=SINGLE_PAYLOAD)
    await _publish(client, scene)
    started = await _start(client, scene)

    now = datetime.now(UTC)
    response = await client.post(
        f"/api/v1/attempts/{started['attempt_id']}/sync",
        headers=auth(scene["student_token"]),
        json={
            "answers": [
                {
                    "question_id": question_id,
                    "response": {"selected": ["a"]},
                    "client_ts": (now - timedelta(minutes=2)).isoformat(),
                },
                {
                    "question_id": question_id,
                    "response": {"selected": ["b"]},
                    "client_ts": (now - timedelta(seconds=5)).isoformat(),
                },
            ]
        },
    )
    assert response.status_code == 200, response.text

    view = await client.get(
        f"/api/v1/attempts/{started['attempt_id']}", headers=auth(scene["student_token"])
    )
    answer = view.json()["questions"][0]["my_answer"]
    assert answer == {"selected": ["b"]}


# ── ارسال و تصحیح ──────────────────────────────────────────────────────
async def test_submit_grades_closed_questions_immediately(client: Any, db_session: Any) -> None:
    scene = await _scene(client, db_session)
    q1 = await _add_question(
        client, scene, kind="SINGLE_CHOICE", payload=SINGLE_PAYLOAD, points="2"
    )
    q2 = await _add_question(client, scene, kind="MULTI_CHOICE", payload=MULTI_PAYLOAD, points="2")
    await _publish(client, scene)
    started = await _start(client, scene)

    await _answer(client, scene, started, q1, {"selected": ["b"]})
    await _answer(client, scene, started, q2, {"selected": ["a"]})  # یک از دو ⇒ ۱

    response = await client.post(
        f"/api/v1/attempts/{started['attempt_id']}/submit",
        headers=auth(scene["student_token"]),
        json={"confirm_unanswered": 0},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert float(body["auto_score"]) == 3.0
    assert body["is_provisional"] is False
    assert body["status"] == "GRADED"


async def test_essay_makes_the_score_provisional(client: Any, db_session: Any) -> None:
    scene = await _scene(client, db_session)
    q1 = await _add_question(
        client, scene, kind="SINGLE_CHOICE", payload=SINGLE_PAYLOAD, points="2"
    )
    q2 = await _add_question(
        client, scene, kind="ESSAY", payload=ESSAY_PAYLOAD, points="5", body="تشریحی"
    )
    await _publish(client, scene)
    started = await _start(client, scene)

    await _answer(client, scene, started, q1, {"selected": ["b"]})
    await _answer(client, scene, started, q2, {"text": "پاسخ تشریحی من دربارهٔ ایمنی راه."})

    response = await client.post(
        f"/api/v1/attempts/{started['attempt_id']}/submit",
        headers=auth(scene["student_token"]),
        json={"confirm_unanswered": 0},
    )
    assert response.status_code == 200, response.text
    assert response.json()["is_provisional"] is True


async def test_concurrent_submit_does_not_double_grade(client: Any, db_session: Any) -> None:
    """تست اجباری §13 — دو کلیک روی «ارسال» یک نمره می‌دهد، نه دو تا."""
    scene = await _scene(client, db_session)
    question_id = await _add_question(
        client, scene, kind="SINGLE_CHOICE", payload=SINGLE_PAYLOAD, points="2"
    )
    await _publish(client, scene)
    started = await _start(client, scene)
    await _answer(client, scene, started, question_id, {"selected": ["b"]})

    url = f"/api/v1/attempts/{started['attempt_id']}/submit"
    headers = auth(scene["student_token"])
    first = await client.post(url, headers=headers, json={"confirm_unanswered": 0})
    second = await client.post(url, headers=headers, json={"confirm_unanswered": 0})

    assert first.status_code == 200, first.text
    # دومی باید رد شود، نه اینکه دوباره تصحیح کند.
    assert second.status_code == 409, second.text
    assert second.json()["error"]["code"] == "ATTEMPT_ALREADY_SUBMITTED"

    from silp.models.quiz import QuizAttempt

    attempt = await db_session.get(QuizAttempt, uuid.UUID(started["attempt_id"]))
    await db_session.refresh(attempt)
    assert float(attempt.total_score) == 2.0


async def test_auto_close_job_is_idempotent(client: Any, db_session: Any) -> None:
    """تست اجباری §13 — دو اجرای کار پس‌زمینه، یک بار می‌بندد."""
    scene = await _scene(client, db_session)
    question_id = await _add_question(
        client, scene, kind="SINGLE_CHOICE", payload=SINGLE_PAYLOAD, points="2"
    )
    await _publish(client, scene)
    started = await _start(client, scene)
    await _answer(client, scene, started, question_id, {"selected": ["b"]})
    await _expire(db_session, started["attempt_id"])

    from silp.services.attempt_service import AttemptService

    service = AttemptService(db_session)
    first = await service.auto_close_expired()
    second = await service.auto_close_expired()

    assert first == 1
    assert second == 0  # چیزی برای بستن نمانده

    from silp.models.quiz import QuizAttempt

    attempt = await db_session.get(QuizAttempt, uuid.UUID(started["attempt_id"]))
    await db_session.refresh(attempt)
    assert attempt.status == "GRADED"
    assert float(attempt.total_score) == 2.0


async def test_auto_closed_attempt_is_marked_as_such(client: Any, db_session: Any) -> None:
    """ADR-0011 مسئلهٔ ۵ — «زمانت تمام شد» با «ارسال کردی» یکی نیست."""
    scene = await _scene(client, db_session)
    await _add_question(client, scene, kind="SINGLE_CHOICE", payload=SINGLE_PAYLOAD)
    await _publish(client, scene)
    started = await _start(client, scene)
    await _expire(db_session, started["attempt_id"])

    from silp.services.attempt_service import AttemptService

    await AttemptService(db_session).auto_close_expired()

    response = await client.get(
        f"/api/v1/attempts/{started['attempt_id']}/result",
        headers=auth(scene["student_token"]),
    )
    assert response.status_code == 200, response.text
    assert response.json()["auto_closed"] is True


async def test_unanswered_question_appears_in_the_result(client: Any, db_session: Any) -> None:
    scene = await _scene(client, db_session)
    await _add_question(client, scene, kind="SINGLE_CHOICE", payload=SINGLE_PAYLOAD, points="2")
    await _publish(client, scene)
    started = await _start(client, scene)

    await client.post(
        f"/api/v1/attempts/{started['attempt_id']}/submit",
        headers=auth(scene["student_token"]),
        json={"confirm_unanswered": 1},
    )
    response = await client.get(
        f"/api/v1/attempts/{started['attempt_id']}/result",
        headers=auth(scene["student_token"]),
    )
    assert response.status_code == 200, response.text
    questions = response.json()["questions"]
    assert len(questions) == 1
    assert float(questions[0]["score"]) == 0.0
    assert questions[0]["my_answer"] is None


# ── نتیجه — FR-QUIZ-04 ─────────────────────────────────────────────────
async def test_result_is_hidden_until_the_quiz_closes(client: Any, db_session: Any) -> None:
    scene = await _scene(client, db_session, result_visibility="AFTER_CLOSE")
    question_id = await _add_question(client, scene, kind="SINGLE_CHOICE", payload=SINGLE_PAYLOAD)
    await _publish(client, scene)
    started = await _start(client, scene)
    await _answer(client, scene, started, question_id, {"selected": ["b"]})
    await client.post(
        f"/api/v1/attempts/{started['attempt_id']}/submit",
        headers=auth(scene["student_token"]),
        json={"confirm_unanswered": 0},
    )

    response = await client.get(
        f"/api/v1/attempts/{started['attempt_id']}/result",
        headers=auth(scene["student_token"]),
    )
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "RESULT_NOT_AVAILABLE"


async def test_class_average_is_withheld_for_a_tiny_cohort(client: Any, db_session: Any) -> None:
    """میانگین کلاس با دو نفر، نمرهٔ نفر دیگر را لو می‌دهد."""
    scene = await _scene(client, db_session)
    question_id = await _add_question(client, scene, kind="SINGLE_CHOICE", payload=SINGLE_PAYLOAD)
    await _publish(client, scene)
    started = await _start(client, scene)
    await _answer(client, scene, started, question_id, {"selected": ["b"]})
    await client.post(
        f"/api/v1/attempts/{started['attempt_id']}/submit",
        headers=auth(scene["student_token"]),
        json={"confirm_unanswered": 0},
    )

    response = await client.get(
        f"/api/v1/attempts/{started['attempt_id']}/result",
        headers=auth(scene["student_token"]),
    )
    assert response.status_code == 200, response.text
    assert response.json()["class_average"] is None


# ── تصحیح دستی و صف — M4-10 ────────────────────────────────────────────
async def test_essay_reaches_the_queue_and_grading_finalises_the_score(
    client: Any, db_session: Any
) -> None:
    scene = await _scene(client, db_session)
    q1 = await _add_question(
        client, scene, kind="SINGLE_CHOICE", payload=SINGLE_PAYLOAD, points="2"
    )
    q2 = await _add_question(
        client, scene, kind="ESSAY", payload=ESSAY_PAYLOAD, points="5", body="تشریحی"
    )
    await _publish(client, scene)
    started = await _start(client, scene)
    await _answer(client, scene, started, q1, {"selected": ["b"]})
    await _answer(client, scene, started, q2, {"text": "پاسخ من دربارهٔ ایمنی راه."})
    await client.post(
        f"/api/v1/attempts/{started['attempt_id']}/submit",
        headers=auth(scene["student_token"]),
        json={"confirm_unanswered": 0},
    )

    queue = await client.get(
        f"/api/v1/teach/quizzes/{scene['quiz_id']}/grading-queue",
        headers=auth(scene["instructor_token"]),
    )
    assert queue.status_code == 200, queue.text
    entries = queue.json()
    assert len(entries) == 1
    assert entries[0]["question_id"] == q2
    assert len(entries[0]["pending"]) == 1

    graded = await client.put(
        f"/api/v1/teach/quizzes/{scene['quiz_id']}/attempts/{started['attempt_id']}"
        f"/answers/{q2}",
        headers=auth(scene["instructor_token"]),
        json={"score": "4", "feedback": "استدلال خوب، منبع کم."},
    )
    assert graded.status_code == 200, graded.text
    assert graded.json()["attempt_is_provisional"] is False
    assert float(graded.json()["attempt_total"]) == 6.0


async def test_instructor_cannot_grade_an_attempt_still_in_progress(
    client: Any, db_session: Any
) -> None:
    """نمره روی تلاشی که دانشجو هنوز در آن است، نمی‌نشیند.

    این را اجرای زنده پیدا کرد، نه تست: استاد می‌توانست وسط آزمون
    نمرهٔ یک پاسخ را بنویسد و `total_score` روی تلاشِ تمام‌نشده بنشیند.
    """
    scene = await _scene(client, db_session)
    question_id = await _add_question(
        client, scene, kind="ESSAY", payload=ESSAY_PAYLOAD, points="5", body="تشریحی"
    )
    await _publish(client, scene)
    started = await _start(client, scene)
    await _answer(client, scene, started, question_id, {"text": "پاسخ نیمه‌کاره"})

    response = await client.put(
        f"/api/v1/teach/quizzes/{scene['quiz_id']}/attempts/{started['attempt_id']}"
        f"/answers/{question_id}",
        headers=auth(scene["instructor_token"]),
        json={"score": "5"},
    )
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "ATTEMPT_STILL_RUNNING"


async def test_instructor_can_still_void_an_attempt_in_progress(
    client: Any, db_session: Any
) -> None:
    """ابطال استثناست: گاهی باید آزمونِ در جریان را قطع کرد."""
    scene = await _scene(client, db_session)
    await _add_question(client, scene, kind="SINGLE_CHOICE", payload=SINGLE_PAYLOAD)
    await _publish(client, scene)
    started = await _start(client, scene)

    response = await client.post(
        f"/api/v1/teach/quizzes/{scene['quiz_id']}/attempts/{started['attempt_id']}/void",
        headers=auth(scene["instructor_token"]),
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "VOIDED"


async def test_instructor_cannot_grade_above_the_question_points(
    client: Any, db_session: Any
) -> None:
    scene = await _scene(client, db_session)
    q1 = await _add_question(
        client, scene, kind="ESSAY", payload=ESSAY_PAYLOAD, points="5", body="تشریحی"
    )
    await _publish(client, scene)
    started = await _start(client, scene)
    await _answer(client, scene, started, q1, {"text": "پاسخ."})
    await client.post(
        f"/api/v1/attempts/{started['attempt_id']}/submit",
        headers=auth(scene["student_token"]),
        json={"confirm_unanswered": 0},
    )

    response = await client.put(
        f"/api/v1/teach/quizzes/{scene['quiz_id']}/attempts/{started['attempt_id']}"
        f"/answers/{q1}",
        headers=auth(scene["instructor_token"]),
        json={"score": "9"},
    )
    assert response.status_code == 422, response.text


async def test_voided_attempt_does_not_burn_a_students_allowance(
    client: Any, db_session: Any
) -> None:
    scene = await _scene(client, db_session, max_attempts=1)
    question_id = await _add_question(client, scene, kind="SINGLE_CHOICE", payload=SINGLE_PAYLOAD)
    await _publish(client, scene)
    started = await _start(client, scene)
    await _answer(client, scene, started, question_id, {"selected": ["b"]})
    await client.post(
        f"/api/v1/attempts/{started['attempt_id']}/submit",
        headers=auth(scene["student_token"]),
        json={"confirm_unanswered": 0},
    )

    voided = await client.post(
        f"/api/v1/teach/quizzes/{scene['quiz_id']}/attempts/{started['attempt_id']}/void",
        headers=auth(scene["instructor_token"]),
    )
    assert voided.status_code == 200, voided.text

    retry = await client.post(
        f"/api/v1/quizzes/{scene['quiz_id']}/attempts", headers=auth(scene["student_token"])
    )
    assert retry.status_code == 201, retry.text


# ── مجوز — §6.4 ────────────────────────────────────────────────────────
async def test_student_cannot_reach_the_teaching_endpoints(client: Any, db_session: Any) -> None:
    scene = await _scene(client, db_session)
    response = await client.get(
        f"/api/v1/teach/quizzes/{scene['quiz_id']}", headers=auth(scene["student_token"])
    )
    assert response.status_code == 403, response.text


async def test_instructor_of_another_offering_is_locked_out(client: Any, db_session: Any) -> None:
    """ADR-0010 — اختیار استاد به ارائهٔ خودش محدود است."""
    scene = await _scene(client, db_session)

    other_token = await login(client, OTHER_STUDENT_MOBILE)
    other = await me(client, other_token)
    await grant_role(db_session, other["id"], "INSTRUCTOR")
    other_token = await login(client, OTHER_STUDENT_MOBILE)

    response = await client.get(
        f"/api/v1/teach/quizzes/{scene['quiz_id']}", headers=auth(other_token)
    )
    assert response.status_code == 403, response.text


# ── اعتراض — §7.3 ──────────────────────────────────────────────────────
async def test_appeal_flow_changes_the_score(client: Any, db_session: Any) -> None:
    scene = await _scene(client, db_session)
    question_id = await _add_question(
        client, scene, kind="SHORT_ANSWER", payload={"accepted": ["پواسون"]}, points="2"
    )
    await _publish(client, scene)
    started = await _start(client, scene)
    await _answer(client, scene, started, question_id, {"text": "دوجمله‌ای منفی"})
    await client.post(
        f"/api/v1/attempts/{started['attempt_id']}/submit",
        headers=auth(scene["student_token"]),
        json={"confirm_unanswered": 0},
    )

    appeal = await client.post(
        f"/api/v1/attempts/{started['attempt_id']}/appeal",
        headers=auth(scene["student_token"]),
        json={"reason": "پاسخ من هم درست است.", "question_id": question_id},
    )
    assert appeal.status_code == 201, appeal.text
    appeal_id = appeal.json()["id"]

    resolved = await client.post(
        f"/api/v1/teach/appeals/{appeal_id}/resolve",
        headers=auth(scene["instructor_token"]),
        json={"accept": True, "response": "حق با شماست؛ کلید ناقص بود.", "new_score": "2"},
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["status"] == "ACCEPTED"

    result = await client.get(
        f"/api/v1/attempts/{started['attempt_id']}/result",
        headers=auth(scene["student_token"]),
    )
    assert float(result.json()["total_score"]) == 2.0


async def test_second_open_appeal_on_the_same_question_is_refused(
    client: Any, db_session: Any
) -> None:
    scene = await _scene(client, db_session)
    question_id = await _add_question(client, scene, kind="SINGLE_CHOICE", payload=SINGLE_PAYLOAD)
    await _publish(client, scene)
    started = await _start(client, scene)
    await _answer(client, scene, started, question_id, {"selected": ["a"]})
    await client.post(
        f"/api/v1/attempts/{started['attempt_id']}/submit",
        headers=auth(scene["student_token"]),
        json={"confirm_unanswered": 0},
    )

    body = {"reason": "اعتراض دارم.", "question_id": question_id}
    first = await client.post(
        f"/api/v1/attempts/{started['attempt_id']}/appeal",
        headers=auth(scene["student_token"]),
        json=body,
    )
    assert first.status_code == 201, first.text

    second = await client.post(
        f"/api/v1/attempts/{started['attempt_id']}/appeal",
        headers=auth(scene["student_token"]),
        json=body,
    )
    assert second.status_code == 409, second.text


async def test_rejecting_an_appeal_requires_a_written_answer(client: Any, db_session: Any) -> None:
    scene = await _scene(client, db_session)
    question_id = await _add_question(client, scene, kind="SINGLE_CHOICE", payload=SINGLE_PAYLOAD)
    await _publish(client, scene)
    started = await _start(client, scene)
    await _answer(client, scene, started, question_id, {"selected": ["a"]})
    await client.post(
        f"/api/v1/attempts/{started['attempt_id']}/submit",
        headers=auth(scene["student_token"]),
        json={"confirm_unanswered": 0},
    )
    appeal = await client.post(
        f"/api/v1/attempts/{started['attempt_id']}/appeal",
        headers=auth(scene["student_token"]),
        json={"reason": "اعتراض دارم.", "question_id": question_id},
    )
    appeal_id = appeal.json()["id"]

    response = await client.post(
        f"/api/v1/teach/appeals/{appeal_id}/resolve",
        headers=auth(scene["instructor_token"]),
        json={"accept": False, "response": "   "},
    )
    assert response.status_code == 422, response.text


# ── تمامیت — FR-QUIZ-05 ────────────────────────────────────────────────
async def test_integrity_events_are_recorded_without_affecting_the_attempt(
    client: Any, db_session: Any
) -> None:
    """«این رویدادها فقط گزارش می‌شوند» — §02."""
    scene = await _scene(client, db_session)
    await _add_question(client, scene, kind="SINGLE_CHOICE", payload=SINGLE_PAYLOAD)
    await _publish(client, scene)
    started = await _start(client, scene)

    response = await client.post(
        f"/api/v1/attempts/{started['attempt_id']}/integrity",
        headers=auth(scene["student_token"]),
        json={"kind": "TAB_BLUR", "detail": {"seconds": 12}},
    )
    assert response.status_code == 200, response.text
    assert response.json()["recorded"] == 1

    view = await client.get(
        f"/api/v1/attempts/{started['attempt_id']}", headers=auth(scene["student_token"])
    )
    assert view.json()["status"] == "IN_PROGRESS"


# ── تحلیل سؤال — M4-13 ─────────────────────────────────────────────────
async def test_question_stats_report_difficulty_and_hold_back_discrimination(
    client: Any, db_session: Any
) -> None:
    """ضریب دشواری از یک تلاش هم درمی‌آید؛ ضریب تمیز نه.

    زیر ده تلاش، تمیز `null` می‌ماند — نویزی که شکل شاخص دارد، بدتر از
    نبودن شاخص است.
    """
    scene = await _scene(client, db_session)
    easy = await _add_question(
        client, scene, kind="SINGLE_CHOICE", payload=SINGLE_PAYLOAD, points="2", body="آسان"
    )
    hard = await _add_question(
        client, scene, kind="SINGLE_CHOICE", payload=SINGLE_PAYLOAD, points="2", body="سخت"
    )
    await _publish(client, scene)
    started = await _start(client, scene)
    await _answer(client, scene, started, easy, {"selected": ["b"]})  # درست
    await _answer(client, scene, started, hard, {"selected": ["a"]})  # غلط
    await client.post(
        f"/api/v1/attempts/{started['attempt_id']}/submit",
        headers=auth(scene["student_token"]),
        json={"confirm_unanswered": 0},
    )

    response = await client.get(
        f"/api/v1/teach/quizzes/{scene['quiz_id']}/question-stats",
        headers=auth(scene["instructor_token"]),
    )
    assert response.status_code == 200, response.text
    by_body = {row["body"]: row for row in response.json()}

    assert float(by_body["آسان"]["difficulty"]) == 1.0
    assert float(by_body["سخت"]["difficulty"]) == 0.0
    assert by_body["آسان"]["discrimination"] is None
    # جملهٔ فارسی هم می‌آید — عدد خالی برای استاد یعنی هیچ.
    assert by_body["سخت"]["note_fa"]


# ── تحلیل پیشرفته — ADR-0028 ───────────────────────────────────────────
async def _graded_class(db_session: Any, scene: dict[str, Any], questions: list[str]) -> None:
    """دوازده تلاش تصحیح‌شده، مستقیم در دیتابیس (ورود OTP بیش از ۱۰ نفر را نمی‌دهد).

    سؤال ۱: همه جز دو نفر ته‌جدول درست؛ سؤال ۲: شش نفر اول درست؛ سؤال ۳
    (معکوس): فقط شش نفر ته‌جدول درست — یعنی سؤالی که قوی‌ها را غلط می‌کند.
    """
    from silp.models.identity import User
    from silp.models.quiz import QuizAnswer, QuizAttempt

    correct_when = [
        lambda i: i < 10,
        lambda i: i < 6,
        lambda i: i >= 6,
    ]
    now = datetime.now(UTC)
    for i in range(12):
        user = User(mobile=f"0912{uuid.uuid4().int % 10_000_000:07d}")
        db_session.add(user)
        await db_session.flush()
        hits = [rule(i) for rule in correct_when]
        attempt = QuizAttempt(
            quiz_id=uuid.UUID(scene["quiz_id"]),
            student_id=user.id,
            attempt_no=1,
            status="GRADED",
            started_at=now - timedelta(minutes=20),
            expires_at=now - timedelta(minutes=5),
            submitted_at=now - timedelta(minutes=10),
            auto_score=Decimal(sum(hits)),
            total_score=Decimal(sum(hits)),
        )
        db_session.add(attempt)
        await db_session.flush()
        for question_id, hit in zip(questions, hits, strict=True):
            db_session.add(
                QuizAnswer(
                    attempt_id=attempt.id,
                    question_id=uuid.UUID(question_id),
                    response={"selected": ["b" if hit else "a"]},
                    auto_score=Decimal(1 if hit else 0),
                )
            )
    await db_session.flush()


async def test_quiz_analytics_with_a_small_class_gives_counts_but_no_reliability(
    client: Any, db_session: Any
) -> None:
    """یک تلاش: توزیع گزینه هست، پایایی و همبستگی نیست — نویز شکل شاخص ندارد."""
    scene = await _scene(client, db_session)
    first = await _add_question(client, scene, kind="SINGLE_CHOICE", payload=SINGLE_PAYLOAD)
    second = await _add_question(client, scene, kind="SINGLE_CHOICE", payload=SINGLE_PAYLOAD)
    await _publish(client, scene)
    started = await _start(client, scene)
    await _answer(client, scene, started, first, {"selected": ["b"]})
    await _answer(client, scene, started, second, {"selected": ["a"]})
    await client.post(
        f"/api/v1/attempts/{started['attempt_id']}/submit",
        headers=auth(scene["student_token"]),
        json={"confirm_unanswered": 0},
    )

    response = await client.get(
        f"/api/v1/teach/quizzes/{scene['quiz_id']}/analytics",
        headers=auth(scene["instructor_token"]),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["summary"]["n"] == 1
    assert body["summary"]["mean_percent"] == 50.0
    assert body["summary"]["sd_percent"] is None
    assert body["reliability"] is None
    by_id = {item["question_id"]: item for item in body["items"]}
    assert by_id[first]["item_rest"] is None
    options = {o["option_id"]: o for o in by_id[first]["options"]}
    assert options["b"]["is_correct"] is True
    assert options["b"]["chosen"] == 1
    assert options["a"]["chosen"] == 0
    # زیر ده تلاش سهم گروه‌ها و جمله نمی‌آید.
    assert options["a"]["top_share"] is None
    assert options["a"]["note_fa"] is None


async def test_quiz_analytics_with_twelve_attempts_reports_reliability_and_flags(
    client: Any, db_session: Any
) -> None:
    scene = await _scene(client, db_session)
    questions = [
        await _add_question(
            client, scene, kind="SINGLE_CHOICE", payload=SINGLE_PAYLOAD, body=f"سؤال {n}"
        )
        for n in (1, 2, 3)
    ]
    await _publish(client, scene)
    await _graded_class(db_session, scene, questions)

    response = await client.get(
        f"/api/v1/teach/quizzes/{scene['quiz_id']}/analytics",
        headers=auth(scene["instructor_token"]),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["summary"]["n"] == 12
    assert sum(body["summary"]["histogram"]) == 12
    assert body["reliability"] is not None
    assert body["reliability"]["label_fa"]
    by_id = {item["question_id"]: item for item in body["items"]}
    # سؤال معکوس: هرچه بقیهٔ آزمون را بهتر زده‌ای، این را بدتر.
    assert by_id[questions[2]]["item_rest"] < 0
    first = {o["option_id"]: o for o in by_id[questions[0]]["options"]}
    assert first["a"]["chosen"] == 2
    assert first["b"]["chosen"] == 10
    assert first["a"]["top_share"] is not None


async def test_quiz_analytics_is_not_visible_to_students(client: Any, db_session: Any) -> None:
    """کلید پاسخ در `is_correct` است؛ دانشجو نباید ببیند."""
    scene = await _scene(client, db_session)
    await _add_question(client, scene, kind="SINGLE_CHOICE", payload=SINGLE_PAYLOAD)
    await _publish(client, scene)

    response = await client.get(
        f"/api/v1/teach/quizzes/{scene['quiz_id']}/analytics",
        headers=auth(scene["student_token"]),
    )

    assert response.status_code in (403, 404), response.text


async def test_instructor_sees_the_attempt_list_with_names(client: Any, db_session: Any) -> None:
    scene = await _scene(client, db_session)
    question_id = await _add_question(client, scene, kind="SINGLE_CHOICE", payload=SINGLE_PAYLOAD)
    await _publish(client, scene)
    started = await _start(client, scene)
    await _answer(client, scene, started, question_id, {"selected": ["b"]})
    await client.post(
        f"/api/v1/attempts/{started['attempt_id']}/submit",
        headers=auth(scene["student_token"]),
        json={"confirm_unanswered": 0},
    )

    response = await client.get(
        f"/api/v1/teach/quizzes/{scene['quiz_id']}/attempts",
        headers=auth(scene["instructor_token"]),
    )
    assert response.status_code == 200, response.text
    rows = response.json()
    assert len(rows) == 1
    assert rows[0]["status"] == "GRADED"
    assert rows[0]["auto_closed"] is False
    assert float(rows[0]["total_score"]) == 1.0


async def test_open_appeals_are_listed_for_the_instructor(client: Any, db_session: Any) -> None:
    scene = await _scene(client, db_session)
    question_id = await _add_question(client, scene, kind="SINGLE_CHOICE", payload=SINGLE_PAYLOAD)
    await _publish(client, scene)
    started = await _start(client, scene)
    await _answer(client, scene, started, question_id, {"selected": ["a"]})
    await client.post(
        f"/api/v1/attempts/{started['attempt_id']}/submit",
        headers=auth(scene["student_token"]),
        json={"confirm_unanswered": 0},
    )
    await client.post(
        f"/api/v1/attempts/{started['attempt_id']}/appeal",
        headers=auth(scene["student_token"]),
        json={"reason": "گزینهٔ الف هم درست است.", "question_id": question_id},
    )

    response = await client.get(
        f"/api/v1/teach/quizzes/{scene['quiz_id']}/appeals",
        headers=auth(scene["instructor_token"]),
    )
    assert response.status_code == 200, response.text
    assert len(response.json()) == 1
    assert response.json()[0]["status_fa"] == "در انتظار رسیدگی"


# ── بانک سؤال — M4-03 ──────────────────────────────────────────────────
async def test_bank_question_is_copied_not_referenced(client: Any, db_session: Any) -> None:
    """ویرایش بعدیِ سؤال بانک، آزمون برگزارشده را تکان نمی‌دهد."""
    scene = await _scene(client, db_session)

    created = await client.post(
        "/api/v1/teach/question-bank",
        headers=auth(scene["instructor_token"]),
        json={
            "kind": "SINGLE_CHOICE",
            "body": "متن اصلی سؤال",
            "payload": SINGLE_PAYLOAD,
            "category": "مدل‌سازی",
            "difficulty": 3,
        },
    )
    assert created.status_code == 201, created.text
    bank_id = created.json()["id"]

    copied = await client.post(
        f"/api/v1/teach/quizzes/{scene['quiz_id']}/questions/from-bank",
        headers=auth(scene["instructor_token"]),
        json={"bank_ids": [bank_id], "points": "2"},
    )
    assert copied.status_code == 201, copied.text
    assert copied.json()[0]["body"] == "متن اصلی سؤال"
    assert copied.json()[0]["bank_id"] == bank_id

    # ADR-0021 — ویرایش از خود API، نه دست بردن در ردیف.
    edited = await client.put(
        f"/api/v1/teach/question-bank/{bank_id}",
        headers=auth(scene["instructor_token"]),
        json={
            "kind": "SINGLE_CHOICE",
            "body": "متن ویرایش‌شده",
            "payload": SINGLE_PAYLOAD,
            "explanation": "توضیح تازه",
            "category": "مدل‌سازی",
            "difficulty": 4,
        },
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["body"] == "متن ویرایش‌شده"
    assert edited.json()["explanation"] == "توضیح تازه"
    assert edited.json()["payload"] == SINGLE_PAYLOAD
    assert edited.json()["usage_count"] == 1

    detail = await client.get(
        f"/api/v1/teach/quizzes/{scene['quiz_id']}", headers=auth(scene["instructor_token"])
    )
    assert detail.json()["questions"][0]["body"] == "متن اصلی سؤال"


async def test_bank_is_private_and_deletion_keeps_quiz_copies(client: Any, db_session: Any) -> None:
    """بانک شخصی است (۴۰۴ برای دیگری)؛ حذف نرم، کپی آزمون و منشأش می‌مانند."""
    scene = await _scene(client, db_session)
    teacher = auth(scene["instructor_token"])
    bank_id = (
        await client.post(
            "/api/v1/teach/question-bank",
            headers=teacher,
            json={"kind": "SINGLE_CHOICE", "body": "سؤال بانک", "payload": SINGLE_PAYLOAD},
        )
    ).json()["id"]
    copied = await client.post(
        f"/api/v1/teach/quizzes/{scene['quiz_id']}/questions/from-bank",
        headers=teacher,
        json={"bank_ids": [bank_id]},
    )
    assert copied.status_code == 201, copied.text

    outsider = auth(await login(client, OUTSIDER_MOBILE))
    body = {"kind": "SINGLE_CHOICE", "body": "ربودن", "payload": SINGLE_PAYLOAD}
    path = f"/api/v1/teach/question-bank/{bank_id}"
    assert (await client.put(path, headers=outsider, json=body)).status_code == 404
    assert (await client.delete(path, headers=outsider)).status_code == 404

    bad = await client.put(path, headers=teacher, json={**body, "payload": {"options": []}})
    assert bad.status_code == 422

    assert (await client.delete(path, headers=teacher)).status_code == 204
    assert (await client.delete(path, headers=teacher)).status_code == 404
    listed = await client.get("/api/v1/teach/question-bank", headers=teacher)
    assert bank_id not in {item["id"] for item in listed.json()}
    detail = await client.get(f"/api/v1/teach/quizzes/{scene['quiz_id']}", headers=teacher)
    [question] = detail.json()["questions"]
    assert question["body"] == "سؤال بانک" and question["bank_id"] == bank_id


# ── کمکی ───────────────────────────────────────────────────────────────
async def _answer(
    client: Any, scene: dict[str, Any], started: dict[str, Any], question_id: str, response: dict
) -> None:
    result = await client.put(
        f"/api/v1/attempts/{started['attempt_id']}/answers/{question_id}",
        headers=auth(scene["student_token"]),
        json={"response": response},
    )
    assert result.status_code == 200, result.text


async def _expire(session: Any, attempt_id: str) -> datetime:
    """تلاش را منقضی می‌کند — بدون خواباندن تست.

    کل پنجره به گذشته منتقل می‌شود، نه فقط `expires_at`: قید
    `expires_at > started_at` در دیتابیس زنده است و جابه‌جا کردن یک سر
    پنجره، همان قید را می‌شکند. (این را خودِ قید به ما یاد داد.)

    جایگزینش انتظار واقعی بود، که مجموعهٔ تست را دقیقه‌ها طولانی می‌کرد.
    """
    from silp.models.quiz import QuizAttempt

    attempt = await session.get(QuizAttempt, uuid.UUID(attempt_id))
    now = datetime.now(UTC)
    attempt.started_at = now - timedelta(hours=1)
    attempt.expires_at = now - timedelta(seconds=5)
    await session.flush()
    return attempt.expires_at
