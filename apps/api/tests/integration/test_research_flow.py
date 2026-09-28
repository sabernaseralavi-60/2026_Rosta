"""پژوهش — M7-05 و M7-06، FR-RES-01/02/03، ADR-0015.

مسیر اصلی: راهنمای عمومی ← تحویل ناقص (۴۲۲ با کمبودها) ← تحویل ← اصلاح
کن ← نسخهٔ دوم ← تأیید ← امتیاز و باز شدن سطح بعد. به‌علاوهٔ بانک موضوع
(پیشنهاد، تأیید، رزرو اتمی، آزادسازی بی‌تحرکی) و خروجی پژوهشی با
راستی‌آزمایی.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import func, select, update
from tests.integration.helpers import auth, complete_profile, grant_role, login, me

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

STUDENT = "09121230001"
OTHER = "09121230002"
MENTOR = "09121230003"
TEACHER = "09121230004"

LEVEL_ONE = {
    "summary": "ماتریس مرور ۲۴ منبع دربارهٔ ایمنی عابر پیاده در تقاطع‌های بی‌چراغ.",
    "links": ["https://example.org/matrix.xlsx"],
    "evidence": {
        "source_count": 24,
        "gap_summary": "هیچ پژوهشی ایمنی عابر پیاده را در تقاطع‌های بی‌چراغ شهرهای"
        " متوسط ایران با دادهٔ تصادف و حجم تردد با هم نسنجیده است.",
    },
}


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


async def _kinds(db_session: Any, user_id: str) -> list[str]:
    from silp.models.messaging import Notification

    rows = await db_session.scalars(
        select(Notification.kind).where(Notification.user_id == user_id)
    )
    return list(rows)


async def _track(client: Any, token: str | None = None) -> dict[str, Any]:
    response = await client.get("/api/v1/research/tracks", headers=auth(token) if token else {})
    assert response.status_code == 200, response.text
    return dict(response.json())


# ── مسیر چهارسطحی ──────────────────────────────────────────────────────
async def test_guide_is_public_and_levels_unlock_one_at_a_time(client, db_session) -> None:  # type: ignore[no-untyped-def]
    guest = await _track(client)
    assert [lvl["state"] for lvl in guest["levels"]] == [
        "AVAILABLE",
        "LOCKED",
        "LOCKED",
        "LOCKED",
    ]
    first = guest["levels"][0]
    assert first["points"] == "80.00"
    assert len(first["template_columns"]) >= 8
    assert {f["key"] for f in first["evidence_fields"]} == {"source_count", "gap_summary"}
    assert guest["can_participate"] is False

    student, _ = await _person(client, STUDENT, "سارا")
    response = await client.post(
        "/api/v1/research/tracks/2/submit", headers=auth(student), json=LEVEL_ONE
    )
    assert response.status_code == 409  # سطح ۲ هنوز قفل است

    response = await client.post(
        "/api/v1/research/tracks/1/submit",
        headers=auth(student),
        json={**LEVEL_ONE, "links": [], "evidence": {"source_count": 12}},
    )
    assert response.status_code == 422
    assert len(response.json()["error"]["details"]["missing"]) == 3


async def test_submit_changes_resubmit_approve(client, db_session) -> None:  # type: ignore[no-untyped-def]
    student, student_id = await _person(client, STUDENT, "سارا")
    mentor, mentor_id = await _person(client, MENTOR, "منتور")
    submit = "/api/v1/research/tracks/1/submit"

    response = await client.post(submit, headers=auth(student), json=LEVEL_ONE)
    assert response.status_code == 201, response.text
    first = response.json()
    assert first["version"] == 1 and first["status"] == "SUBMITTED"
    response = await client.post(submit, headers=auth(student), json=LEVEL_ONE)
    assert response.status_code == 409  # تحویل قبلی در انتظار است
    assert (await _track(client, student))["levels"][0]["state"] == "SUBMITTED"

    # صف بررسی فقط برای بازبین.
    response = await client.get("/api/v1/research/review-queue", headers=auth(mentor))
    assert response.status_code == 403
    await grant_role(db_session, mentor_id, "MENTOR")
    queue = (await client.get("/api/v1/research/review-queue", headers=auth(mentor))).json()
    assert [item["id"] for item in queue] == [first["id"]]
    assert queue[0]["student"]["name"] == "سارا رستمی"
    assert queue[0]["level_title_fa"] == "مرور ادبیات"

    review = f"/api/v1/research/submissions/{first['id']}/review"
    response = await client.post(
        review, headers=auth(mentor), json={"decision": "CHANGES_REQUESTED"}
    )
    assert response.status_code == 422  # اصلاح بدون بازخورد پذیرفته نیست
    response = await client.post(
        review,
        headers=auth(mentor),
        json={"decision": "CHANGES_REQUESTED", "feedback": "منابع انگلیسی را هم بیفزا."},
    )
    assert response.status_code == 200, response.text
    assert "RESEARCH_REVIEWED" in await _kinds(db_session, student_id)
    level = (await _track(client, student))["levels"][0]
    assert level["state"] == "IN_PROGRESS"
    assert level["mentor"]["id"] == mentor_id
    assert level["submissions"][0]["feedback"] == "منابع انگلیسی را هم بیفزا."

    # نسخهٔ دوم به منتور همین سطح خبر داده می‌شود.
    response = await client.post(submit, headers=auth(student), json=LEVEL_ONE)
    assert response.status_code == 201, response.text
    second = response.json()
    assert second["version"] == 2
    assert "RESEARCH_SUBMITTED" in await _kinds(db_session, mentor_id)
    queue = (await client.get("/api/v1/research/review-queue", headers=auth(mentor))).json()
    assert queue[0]["previous"][0]["feedback"] == "منابع انگلیسی را هم بیفزا."

    response = await client.post(
        f"/api/v1/research/submissions/{second['id']}/review",
        headers=auth(mentor),
        json={"decision": "APPROVED"},
    )
    assert response.status_code == 200, response.text
    assert await _points(db_session, student_id, "RESEARCH_L1_APPROVED") == Decimal(80)
    states = [lvl["state"] for lvl in (await _track(client, student))["levels"]]
    assert states == ["APPROVED", "IN_PROGRESS", "LOCKED", "LOCKED"]
    response = await client.post(submit, headers=auth(student), json=LEVEL_ONE)
    assert response.status_code == 409  # سطح تأییدشده تحویل نمی‌پذیرد


async def test_nobody_reviews_their_own_submission(client, db_session) -> None:  # type: ignore[no-untyped-def]
    mentor, mentor_id = await _person(client, MENTOR, "منتور")
    await grant_role(db_session, mentor_id, "MENTOR")
    response = await client.post(
        "/api/v1/research/tracks/1/submit", headers=auth(mentor), json=LEVEL_ONE
    )
    assert response.status_code == 201, response.text
    queue = (await client.get("/api/v1/research/review-queue", headers=auth(mentor))).json()
    assert queue == []
    response = await client.post(
        f"/api/v1/research/submissions/{response.json()['id']}/review",
        headers=auth(mentor),
        json={"decision": "APPROVED"},
    )
    assert response.status_code == 403


# ── بانک موضوع ─────────────────────────────────────────────────────────
TOPIC = {
    "title": "ایمنی عابر پیاده در تقاطع‌های کرمان",
    "description": "تحلیل تصادف‌های عابر پیاده در تقاطع‌های بی‌چراغ کرمان با دادهٔ پلیس راه.",
    "level": 2,
}


async def test_proposal_approval_reservation_and_taken(client, db_session) -> None:  # type: ignore[no-untyped-def]
    student, student_id = await _person(client, STUDENT, "سارا")
    other, _ = await _person(client, OTHER, "نگار")
    teacher, teacher_id = await _person(client, TEACHER, "استاد")
    await grant_role(db_session, teacher_id, "INSTRUCTOR")
    await grant_role(db_session, teacher_id, "MENTOR")

    # پیشنهاد دانشجو تا تأیید پنهان است.
    response = await client.post("/api/v1/research/topics", headers=auth(student), json=TOPIC)
    assert response.status_code == 201, response.text
    proposal = response.json()
    assert proposal["status"] == "PROPOSED"
    listing = (await client.get("/api/v1/research/topics", headers=auth(other))).json()
    assert listing["total"] == 0
    response = await client.get(f"/api/v1/research/topics/{proposal['id']}", headers=auth(other))
    assert response.status_code == 404

    response = await client.post(
        f"/api/v1/research/topics/{proposal['id']}/review",
        headers=auth(teacher),
        json={"decision": "APPROVE"},
    )
    assert response.status_code == 200, response.text
    assert await _points(db_session, student_id, "TOPIC_PROPOSED") == Decimal(30)
    assert "TOPIC_REVIEWED" in await _kinds(db_session, student_id)

    # موضوع کادر مستقیم باز است و امتیاز پیشنهاد ندارد.
    response = await client.post(
        "/api/v1/research/topics", headers=auth(teacher), json={**TOPIC, "title": "تقاضای سفر"}
    )
    assert response.status_code == 201
    staff_topic = response.json()
    assert staff_topic["status"] == "OPEN"
    assert await _points(db_session, teacher_id, "TOPIC_PROPOSED") == Decimal(0)

    # رزرو اتمی: اولی می‌برد، دومی ۴۰۹ می‌گیرد.
    reserve = f"/api/v1/research/topics/{proposal['id']}/reserve"
    response = await client.post(reserve, headers=auth(student))
    assert response.status_code == 200, response.text
    assert response.json()["reserved_by_me"] is True
    response = await client.post(reserve, headers=auth(other))
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "TOPIC_ALREADY_RESERVED"
    seen = (
        await client.get(f"/api/v1/research/topics/{proposal['id']}", headers=auth(other))
    ).json()
    assert seen["reserved_by"] is None and seen["status"] == "RESERVED"
    staff_view = (
        await client.get(f"/api/v1/research/topics/{proposal['id']}", headers=auth(teacher))
    ).json()
    assert staff_view["reserved_by"]["id"] == student_id

    # یک رزرو باز برای هر نفر.
    response = await client.post(
        f"/api/v1/research/topics/{staff_topic['id']}/reserve", headers=auth(student)
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "RESERVATION_LIMIT"

    # تحویل سطح ۱ موضوع را با خود دارد؛ تأییدش موضوع را «در حال انجام» می‌کند.
    response = await client.post(
        "/api/v1/research/tracks/1/submit", headers=auth(student), json=LEVEL_ONE
    )
    assert response.status_code == 201
    submission = response.json()
    assert submission["topic_title"] == TOPIC["title"]
    response = await client.post(
        f"/api/v1/research/submissions/{submission['id']}/review",
        headers=auth(teacher),
        json={"decision": "APPROVED"},
    )
    assert response.status_code == 200
    topic = (await client.get(f"/api/v1/research/topics/{proposal['id']}")).json()
    assert topic["status"] == "TAKEN"
    response = await client.post(
        f"/api/v1/research/topics/{proposal['id']}/release", headers=auth(student)
    )
    assert response.status_code == 409  # در حال انجام را فقط کادر باز می‌کند


async def test_idle_reservation_is_warned_then_released(client, db_session) -> None:  # type: ignore[no-untyped-def]
    from silp.models.research import ResearchTopic
    from silp.services.topic_service import TopicService

    student, student_id = await _person(client, STUDENT, "سارا")
    teacher, teacher_id = await _person(client, TEACHER, "استاد")
    await grant_role(db_session, teacher_id, "INSTRUCTOR")
    created = (
        await client.post("/api/v1/research/topics", headers=auth(teacher), json=TOPIC)
    ).json()
    response = await client.post(
        f"/api/v1/research/topics/{created['id']}/reserve", headers=auth(student)
    )
    assert response.status_code == 200

    async def idle(days: int) -> None:
        await db_session.execute(
            update(ResearchTopic)
            .where(ResearchTopic.id == created["id"])
            .values(last_activity_at=datetime.now(UTC) - timedelta(days=days))
        )
        await db_session.flush()

    await idle(26)
    stats = await TopicService(db_session).release_stale()
    assert (stats.warned, stats.released) == (1, 0)
    again = await TopicService(db_session).release_stale()
    assert again.warned == 0  # یک هشدار برای هر دورهٔ بی‌تحرکی
    assert "TOPIC_RELEASE_WARNING" in await _kinds(db_session, student_id)

    await idle(31)
    stats = await TopicService(db_session).release_stale()
    assert stats.released == 1
    topic = (await client.get(f"/api/v1/research/topics/{created['id']}")).json()
    assert topic["status"] == "OPEN"
    assert "TOPIC_RELEASED" in await _kinds(db_session, student_id)


# ── خروجی پژوهشی ───────────────────────────────────────────────────────
PAPER = {
    "kind": "JOURNAL",
    "title": "Pedestrian safety at unsignalized intersections",
    "authors": "S. Karimi, S. Ahmadi",
    "venue": "Accident Analysis & Prevention",
    "quartile": "Q1",
    "status": "DRAFT",
}


async def test_output_points_come_only_from_verification(client, db_session) -> None:  # type: ignore[no-untyped-def]
    from silp.services.badge_service import BadgeService

    student, student_id = await _person(client, STUDENT, "سارا")
    mentor, mentor_id = await _person(client, MENTOR, "منتور")
    await grant_role(db_session, mentor_id, "MENTOR")

    response = await client.post("/api/v1/research/outputs", headers=auth(student), json=PAPER)
    assert response.status_code == 201, response.text
    paper = response.json()
    assert paper["review_status"] == "NONE"
    url = f"/api/v1/research/outputs/{paper['id']}"

    response = await client.patch(
        url,
        headers=auth(student),
        json={**PAPER, "status": "ACCEPTED", "doi": "https://doi.org/10.1016/j.aap.2026.1"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["review_status"] == "PENDING"
    assert response.json()["doi"] == "10.1016/j.aap.2026.1"
    assert await _points(db_session, student_id, "OUTPUT_ACCEPTED") == Decimal(0)

    queue = (await client.get("/api/v1/research/outputs/review-queue", headers=auth(mentor))).json()
    assert [item["id"] for item in queue] == [paper["id"]]
    response = await client.post(
        f"{url}/review", headers=auth(mentor), json={"decision": "VERIFIED"}
    )
    assert response.status_code == 200, response.text
    verified = response.json()
    assert verified["verified_stage"] == "ACCEPTED" and verified["verified_quartile"] == "Q1"
    assert verified["points"] == "450.00"  # ۵۰ ارسال + ۲۰۰ × ۲ پذیرش Q1
    assert "OUTPUT_REVIEWED" in await _kinds(db_session, student_id)

    awarded = await BadgeService(db_session).evaluate_user(student_id)  # type: ignore[arg-type]
    assert {"PUBLISHED", "Q1_AUTHOR"} <= set(awarded)

    # ادعای انتشار دوباره به صف می‌رود؛ رد، امتیاز را دست نمی‌زند.
    response = await client.patch(url, headers=auth(student), json={**PAPER, "status": "PUBLISHED"})
    assert response.json()["review_status"] == "PENDING"
    response = await client.post(
        f"{url}/review", headers=auth(mentor), json={"decision": "REJECTED"}
    )
    assert response.status_code == 422
    response = await client.post(
        f"{url}/review",
        headers=auth(mentor),
        json={"decision": "REJECTED", "note": "صفحهٔ مقالهٔ منتشرشده را پیوند بده."},
    )
    assert response.status_code == 200
    assert response.json()["points"] == "450.00"

    response = await client.delete(url, headers=auth(student))
    assert response.status_code == 409  # راستی‌آزمایی‌شده حذف نمی‌شود

    # چارک اشتباه اصلاح می‌شود و امتیاز پذیرش با آن.
    response = await client.patch(
        url, headers=auth(student), json={**PAPER, "status": "ACCEPTED", "quartile": "Q3"}
    )
    assert response.json()["review_status"] == "PENDING"
    response = await client.post(
        f"{url}/review", headers=auth(mentor), json={"decision": "VERIFIED"}
    )
    assert response.json()["points"] == "290.00"  # ۵۰ + ۲۰۰ × ۱٫۲


async def test_unscored_outputs_never_queue(client, db_session) -> None:  # type: ignore[no-untyped-def]
    student, _ = await _person(client, STUDENT, "سارا")
    response = await client.post(
        "/api/v1/research/outputs",
        headers=auth(student),
        json={**PAPER, "kind": "THESIS", "status": "PUBLISHED"},
    )
    assert response.status_code == 201
    thesis = response.json()
    assert thesis["review_status"] == "NONE" and thesis["is_scored"] is False
    assert thesis["quartile"] is None
    response = await client.delete(
        f"/api/v1/research/outputs/{thesis['id']}", headers=auth(student)
    )
    assert response.status_code == 204
