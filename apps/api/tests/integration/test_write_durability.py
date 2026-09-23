"""پایداری نوشتن — آیا داده پس از پایان درخواست هم هست؟

این تست‌ها با `committing_client` اجرا می‌شوند، نه `client`: در فیکسچر
معمولی، `commit` سرویس به savepoint تبدیل می‌شود و سرویسی که اصلاً
`commit` نزده هم سبز می‌شود. دو اشکال واقعی از همین جنس (نیمرخ و بازخورد
پیشنهاد) فقط در اجرای واقعی سرور دیده شدند.

قرارداد `db/session.py`: «commit صریح در لایهٔ سرویس انجام می‌شود، نه
خودکار». این فایل همان قرارداد را می‌پاید.

**نکتهٔ کلیدی:** راستی‌آزمایی از یک **اتصال دیگر** انجام می‌شود، نه از
نشست خود درخواست. نشست درخواست، نوشتنِ flush‌شده ولی commit‌نشده را هم
می‌بیند؛ فقط اتصال دوم می‌تواند بگوید داده واقعاً تثبیت شده است.

هر تست داده‌اش را خودش پاک می‌کند، چون تراکنش پوششی ندارد.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import pytest
from sqlalchemy import delete, select

pytestmark = pytest.mark.integration


@pytest.fixture
async def account(committing_client, committing_session) -> AsyncIterator[dict[str, Any]]:
    """حساب یک‌بارمصرف با شمارهٔ یکتا؛ در پایان فیزیکی حذف می‌شود."""
    from silp.models.identity import User

    mobile = f"0912{uuid.uuid4().int % 10_000_000:07d}"

    response = await committing_client.post(
        "/api/v1/auth/otp/request", json={"destination": mobile, "channel": "SMS"}
    )
    challenge_id = response.json()["challenge_id"]
    response = await committing_client.post(
        "/api/v1/auth/otp/verify", json={"challenge_id": challenge_id, "code": "111111"}
    )
    assert response.status_code == 200, response.text

    user_id = uuid.UUID(response.json()["user"]["id"])
    yield {"token": response.json()["access_token"], "user_id": user_id, "mobile": mobile}

    # پاک‌سازی: حذف کاربر، بقیه با ON DELETE CASCADE می‌روند.
    await committing_session.execute(delete(User).where(User.id == user_id))
    await committing_session.commit()


def auth(account: dict[str, Any]) -> dict[str, str]:
    return {"Authorization": f"Bearer {account['token']}"}


@asynccontextmanager
async def other_connection() -> AsyncIterator[Any]:
    """نشستی روی اتصالی جدا — فقط دادهٔ commit‌شده را می‌بیند."""
    from silp.db.session import get_session_factory

    async with get_session_factory()() as session:
        yield session


async def test_profile_survives_the_request(committing_client, committing_session, account) -> None:  # type: ignore[no-untyped-def]
    """`PATCH /me/profile` باید واقعاً بنویسد، نه فقط در نشست جاری."""
    from silp.models.profile import Profile

    response = await committing_client.patch(
        "/api/v1/me/profile",
        headers=auth(account),
        json={"first_name": "سارا", "last_name": "محمدی"},
    )
    assert response.status_code == 200, response.text

    async with other_connection() as verifier:
        stored = await verifier.get(Profile, account["user_id"])
        assert stored is not None, "نیمرخ commit نشده است — سرویس فقط flush کرده"
        assert stored.first_name == "سارا"


async def test_survey_step_survives_the_request(
    committing_client, committing_session, account
) -> None:  # type: ignore[no-untyped-def]
    """هر گام ارزیابی یک تراکنش کامل است — پاسخ‌ها و شمارنده با هم."""
    from silp.models.profile import Profile, ProfileSkill
    from silp.models.taxonomy import Skill

    await committing_client.patch(
        "/api/v1/me/profile",
        headers=auth(account),
        json={"first_name": "امیر", "last_name": "رضایی"},
    )
    skill_id = await committing_session.scalar(select(Skill.id).where(Skill.code == "PYTHON"))

    response = await committing_client.patch(
        "/api/v1/me/survey/skills",
        headers=auth(account),
        json={"skills": [{"skill_id": str(skill_id), "level": 4}]},
    )
    assert response.status_code == 200, response.text

    async with other_connection() as verifier:
        level = await verifier.scalar(
            select(ProfileSkill.level).where(
                ProfileSkill.user_id == account["user_id"], ProfileSkill.skill_id == skill_id
            )
        )
        profile = await verifier.get(Profile, account["user_id"])

    assert level == 4, "پاسخ گام commit نشده است"
    assert profile is not None
    assert profile.survey_completed_steps >= 1


async def test_recommendation_feedback_survives_the_request(  # type: ignore[no-untyped-def]
    committing_client, committing_session, account
) -> None:
    """§8.9 — «دیگر نشانم نده» باید ماندگار باشد، وگرنه بی‌معناست."""
    from silp.models.project import Project, RecommendationFeedback

    project_id = await committing_session.scalar(
        select(Project.id).where(Project.status == "OPEN", Project.deleted_at.is_(None)).limit(1)
    )
    if project_id is None:
        pytest.skip("بانک پروژهٔ نمونه اجرا نشده است.")

    response = await committing_client.post(
        f"/api/v1/recommendations/{project_id}/feedback",
        headers=auth(account),
        json={"verdict": "DISMISSED"},
    )
    assert response.status_code == 204, response.text

    async with other_connection() as verifier:
        stored = await verifier.get(RecommendationFeedback, (account["user_id"], project_id))
        assert stored is not None, "بازخورد commit نشده است"
        assert stored.verdict == "DISMISSED"


# ── M2 ─────────────────────────────────────────────────────────────────
async def test_project_creation_survives_the_request(  # type: ignore[no-untyped-def]
    committing_client, committing_session, account
) -> None:
    """پروژه و مشخصات تطابقش باید با هم تثبیت شوند، نه فقط ردیف اصلی."""
    from silp.models.project import Project, ProjectRequiredSkill
    from silp.models.taxonomy import Skill

    skill_id = await committing_session.scalar(select(Skill.id).where(Skill.code == "PYTHON"))
    response = await committing_client.post(
        "/api/v1/projects",
        headers=auth(account),
        json={
            "title_fa": "پروژهٔ پایداری نوشتن",
            "summary": "پروژه‌ای که فقط برای آزمون تثبیت داده ساخته می‌شود.",
            "description": "شرح کامل پروژه با جزئیات کافی برای تصمیم دانشجو.",
            "kind": "D_PERSONAL",
            "expected_output": "گزارش",
            "required_skills": [{"skill_id": str(skill_id), "min_level": 3}],
        },
    )
    assert response.status_code == 201, response.text
    project_id = uuid.UUID(response.json()["id"])

    try:
        async with other_connection() as verifier:
            stored = await verifier.get(Project, project_id)
            assert stored is not None, "پروژه commit نشده است"
            requirement = await verifier.scalar(
                select(ProjectRequiredSkill.min_level).where(
                    ProjectRequiredSkill.project_id == project_id
                )
            )
        assert requirement == 3, "مهارت لازم در همان تراکنش تثبیت نشده است"
    finally:
        await committing_session.execute(delete(Project).where(Project.id == project_id))
        await committing_session.commit()


async def test_publish_persists_team_and_lead_membership(  # type: ignore[no-untyped-def]
    committing_client, committing_session, account
) -> None:
    """§7.12 — تیم و عضویت مدیر در همان تراکنش انتشار نوشته می‌شوند."""
    from silp.models.project import Project, Team, TeamMember
    from silp.models.taxonomy import Skill

    skill_id = await committing_session.scalar(select(Skill.id).where(Skill.code == "PYTHON"))
    created = await committing_client.post(
        "/api/v1/projects",
        headers=auth(account),
        json={
            "title_fa": "پروژهٔ انتشار پایدار",
            "summary": "پروژه‌ای برای آزمون ساخت تیم هنگام انتشار.",
            "description": "شرح کامل پروژه با جزئیات کافی برای تصمیم دانشجو.",
            "kind": "D_PERSONAL",
            "expected_output": "گزارش",
            "required_skills": [{"skill_id": str(skill_id), "min_level": 3}],
        },
    )
    project_id = uuid.UUID(created.json()["id"])

    try:
        await committing_client.post(
            f"/api/v1/projects/{project_id}/milestones",
            headers=auth(account),
            json={"title_fa": "مرحلهٔ اول", "points": 10},
        )
        published = await committing_client.post(
            f"/api/v1/projects/{project_id}/publish", headers=auth(account)
        )
        assert published.status_code == 200, published.text

        async with other_connection() as verifier:
            team_id = await verifier.scalar(select(Team.id).where(Team.project_id == project_id))
            assert team_id is not None, "تیم commit نشده است"
            is_lead = await verifier.scalar(
                select(TeamMember.is_lead).where(
                    TeamMember.team_id == team_id, TeamMember.user_id == account["user_id"]
                )
            )
        assert is_lead is True, "عضویت مدیر در تیم تثبیت نشده است"
    finally:
        await committing_session.execute(delete(Project).where(Project.id == project_id))
        await committing_session.commit()


async def test_completed_upload_survives_the_request(  # type: ignore[no-untyped-def]
    committing_client, committing_session, account, storage
) -> None:
    """§5.9 — بدون تثبیت `uploaded_at`، فایل برای درخواست بعدی ناتمام است."""
    from silp.models.file import File

    body = b"%PDF-1.7\n"
    reserved = await committing_client.post(
        "/api/v1/files/upload-url",
        headers=auth(account),
        json={
            "original_name": "durable.pdf",
            "content_type": "application/pdf",
            "size_bytes": len(body),
            "purpose": "DELIVERABLE",
        },
    )
    assert reserved.status_code == 200, reserved.text
    payload = reserved.json()
    file_id = uuid.UUID(payload["file_id"])

    try:
        storage.put_object(payload["upload_url"].split("/", 3)[-1], body, "application/pdf")
        completed = await committing_client.post(
            f"/api/v1/files/{file_id}/complete", headers=auth(account)
        )
        assert completed.status_code == 200, completed.text

        async with other_connection() as verifier:
            stored = await verifier.get(File, file_id)
            assert stored is not None, "ردیف فایل commit نشده است"
            assert stored.uploaded_at is not None, "تکمیل آپلود commit نشده است"
            assert stored.size_bytes == len(body)
    finally:
        await committing_session.execute(delete(File).where(File.id == file_id))
        await committing_session.commit()


async def test_points_from_a_listener_survive_the_request(  # type: ignore[no-untyped-def]
    committing_client, committing_session, account
) -> None:
    """M5 — امتیاز را شنونده در savepoint می‌نویسد و `commit` سرویس تثبیتش می‌کند.

    اگر رویداد پس از `commit` منتشر می‌شد، یا شنونده تراکنش خودش را
    می‌خواست، ردیف امتیاز فقط در نشست درخواست دیده می‌شد و این تست
    شکست می‌خورد.
    """
    from tests.integration.helpers import complete_profile

    from silp.models.gamification import PointEntry

    await complete_profile(committing_client, account["token"])

    async with other_connection() as verifier:
        rules = list(
            await verifier.scalars(
                select(PointEntry.rule_code).where(PointEntry.user_id == account["user_id"])
            )
        )
    assert rules == ["PROFILE_COMPLETED"]


async def test_notification_and_its_outbox_survive_the_request(  # type: ignore[no-untyped-def]
    committing_client, committing_session, account
) -> None:
    """M6 — اعلان و ردیف صف را شنونده در همان تراکنش درخواست می‌نویسد (D-08).

    حساب تازه با ورود اول اعلان «خوش‌آمد» می‌گیرد؛ اگر شنونده پس از commit
    اجرا می‌شد یا commit نمی‌خورد، اتصال دوم آن را نمی‌دید.
    """
    from silp.models.messaging import Notification

    async with other_connection() as verifier:
        kinds = list(
            await verifier.scalars(
                select(Notification.kind).where(Notification.user_id == account["user_id"])
            )
        )
    assert kinds == ["WELCOME"]

    response = await committing_client.post("/api/v1/notifications/read-all", headers=auth(account))
    assert response.status_code == 200, response.text
    async with other_connection() as verifier:
        unread = await verifier.scalar(
            select(Notification.id).where(
                Notification.user_id == account["user_id"], Notification.read_at.is_(None)
            )
        )
    assert unread is None, "«همه خوانده شد» commit نشده است"


async def test_notification_preferences_survive_the_request(  # type: ignore[no-untyped-def]
    committing_client, committing_session, account
) -> None:
    from silp.models.messaging import NotificationPreference

    response = await committing_client.put(
        "/api/v1/notifications/preferences",
        headers=auth(account),
        json={"groups": {"COURSE": ["SMS"]}},
    )
    assert response.status_code == 200, response.text
    async with other_connection() as verifier:
        stored = await verifier.get(NotificationPreference, (account["user_id"], "COURSE"))
    assert stored is not None, "ترجیح commit نشده است"
    assert stored.channels == ["IN_APP", "SMS"]


async def test_idea_and_its_points_survive_the_request(  # type: ignore[no-untyped-def]
    committing_client, committing_session, account
) -> None:
    """M7 — ایده، امتیاز ثبتش (شنونده) و نظر با شمارندهٔ تریگری."""
    from silp.models.gamification import PointEntry
    from silp.models.idea import Idea

    created = await committing_client.post(
        "/api/v1/ideas",
        headers=auth(account),
        json={"title": "ایدهٔ پایدار", "body": "شرح کافی برای یک ایدهٔ آزمایشی."},
    )
    assert created.status_code == 201, created.text
    idea_id = uuid.UUID(created.json()["id"])
    try:
        comment = await committing_client.post(
            f"/api/v1/ideas/{idea_id}/comments", headers=auth(account), json={"body": "نظر"}
        )
        assert comment.status_code == 201, comment.text
        async with other_connection() as verifier:
            stored = await verifier.get(Idea, idea_id)
            assert stored is not None, "ایده commit نشده است"
            assert stored.comment_count == 1, "شمارندهٔ نظر commit نشده است"
            rules = list(
                await verifier.scalars(
                    select(PointEntry.rule_code).where(PointEntry.user_id == account["user_id"])
                )
            )
        assert "IDEA_SUBMITTED" in rules
    finally:
        await committing_session.execute(delete(Idea).where(Idea.id == idea_id))
        await committing_session.commit()


async def test_username_and_venture_with_team_survive_the_request(  # type: ignore[no-untyped-def]
    committing_client, committing_session, account
) -> None:
    """نام کاربری با نام نیمرخ ساخته می‌شود؛ کسب‌وکار و تیمش در یک تراکنش."""
    from tests.integration.helpers import complete_profile

    from silp.models.identity import User
    from silp.models.project import Team, TeamMember
    from silp.models.venture import Venture, VentureMetric

    await complete_profile(committing_client, account["token"], first_name="مریم")
    async with other_connection() as verifier:
        username = await verifier.scalar(select(User.username).where(User.id == account["user_id"]))
    assert username == "marim-rastami", username

    created = await committing_client.post(
        "/api/v1/ventures",
        headers=auth(account),
        json={"name": "کسب‌وکار پایدار", "pitch": "معرفی یک‌خطی کسب‌وکار آزمایشی."},
    )
    assert created.status_code == 201, created.text
    venture_id = uuid.UUID(created.json()["id"])
    try:
        metric = await committing_client.post(
            f"/api/v1/ventures/{venture_id}/metrics",
            headers=auth(account),
            json={"metric": "CALLS", "value": 2, "occurred_on": "2026-09-01"},
        )
        assert metric.status_code == 201, metric.text
        async with other_connection() as verifier:
            team_id = await verifier.scalar(select(Team.id).where(Team.venture_id == venture_id))
            assert team_id is not None, "تیم کسب‌وکار commit نشده است"
            founder = await verifier.scalar(
                select(TeamMember.is_lead).where(TeamMember.team_id == team_id)
            )
            assert founder is True
            assert await verifier.get(VentureMetric, uuid.UUID(metric.json()["id"])) is not None
    finally:
        await committing_session.execute(delete(Venture).where(Venture.id == venture_id))
        await committing_session.commit()


async def test_research_writes_survive_the_request(  # type: ignore[no-untyped-def]
    committing_client, committing_session, account
) -> None:
    """M7 بخش ب — تحویل سطح (با ردیف مسیر)، پیشنهاد موضوع، خروجی و نیمرخ عمومی."""
    from tests.integration.helpers import complete_profile

    from silp.models.profile import Profile
    from silp.models.research import (
        ResearchOutput,
        ResearchSubmission,
        ResearchTopic,
        ResearchTrack,
    )

    await complete_profile(committing_client, account["token"])
    response = await committing_client.patch(
        "/api/v1/me/profile", headers=auth(account), json={"is_public": True}
    )
    assert response.status_code == 200, response.text
    submission = await committing_client.post(
        "/api/v1/research/tracks/1/submit",
        headers=auth(account),
        json={
            "summary": "ماتریس مرور ۲۴ منبع دربارهٔ ایمنی عابر پیاده در تقاطع‌ها.",
            "links": ["https://example.org/matrix.xlsx"],
            "evidence": {
                "source_count": 24,
                "gap_summary": "هیچ پژوهشی ایمنی عابر پیاده را در تقاطع‌های بی‌چراغ"
                " شهرهای متوسط ایران با دادهٔ تصادف و حجم تردد نسنجیده است.",
            },
        },
    )
    assert submission.status_code == 201, submission.text
    topic = await committing_client.post(
        "/api/v1/research/topics",
        headers=auth(account),
        json={"title": "موضوع پایدار آزمایشی", "description": "شرح کافی برای یک موضوع آزمایشی."},
    )
    assert topic.status_code == 201, topic.text
    output = await committing_client.post(
        "/api/v1/research/outputs",
        headers=auth(account),
        json={
            "kind": "JOURNAL",
            "title": "Durable paper",
            "authors": "A. B.",
            "status": "SUBMITTED",
        },
    )
    assert output.status_code == 201, output.text
    try:
        async with other_connection() as verifier:
            assert (await verifier.get(Profile, account["user_id"])).is_public is True  # type: ignore[union-attr]
            track = await verifier.get(ResearchTrack, (account["user_id"], 1))
            assert track is not None and track.status == "SUBMITTED", "مسیر commit نشده است"
            stored = await verifier.get(ResearchSubmission, uuid.UUID(submission.json()["id"]))
            assert stored is not None, "تحویل commit نشده است"
            proposal = await verifier.get(ResearchTopic, uuid.UUID(topic.json()["id"]))
            assert proposal is not None and proposal.status == "PROPOSED"
            paper = await verifier.get(ResearchOutput, uuid.UUID(output.json()["id"]))
            assert paper is not None and paper.review_status == "PENDING"
    finally:
        await committing_session.execute(
            delete(ResearchTopic).where(ResearchTopic.proposer_id == account["user_id"])
        )
        await committing_session.execute(
            delete(ResearchOutput).where(ResearchOutput.owner_id == account["user_id"])
        )
        await committing_session.commit()


async def test_venture_opening_survives_the_request(  # type: ignore[no-untyped-def]
    committing_client, committing_session, account
) -> None:
    """آگهی کسب‌وکار باید با پایان درخواست بماند — ثبتش شنوندهٔ اعلان هدفمند هم دارد."""
    from tests.integration.helpers import complete_profile

    from silp.models.delivery import TeamOpening
    from silp.models.venture import Venture

    await complete_profile(committing_client, account["token"])
    venture = await committing_client.post(
        "/api/v1/ventures",
        headers=auth(account),
        json={"name": "آگهی پایدار", "pitch": "معرفی یک‌خطی کسب‌وکار آزمایشی."},
    )
    assert venture.status_code == 201, venture.text
    venture_id = uuid.UUID(venture.json()["id"])
    try:
        opening = await committing_client.post(
            "/api/v1/teams/openings",
            headers=auth(account),
            json={
                "venture_id": str(venture_id),
                "title": "بازاریاب",
                "description": "یک هم‌تیمی برای بازاریابی آنلاین.",
            },
        )
        assert opening.status_code == 201, opening.text
        async with other_connection() as verifier:
            stored = await verifier.get(TeamOpening, uuid.UUID(opening.json()["id"]))
            assert stored is not None, "آگهی commit نشده است"
            assert stored.venture_id == venture_id
    finally:
        await committing_session.execute(delete(Venture).where(Venture.id == venture_id))
        await committing_session.commit()


async def test_city_workflow_writes_survive_the_request(  # type: ignore[no-untyped-def]
    committing_client, committing_session, account
) -> None:
    """M7 بخش ج — پروژهٔ شهری با هشت مرحله، مسئول مرحله و تحویل با شاهد."""
    from tests.integration.helpers import complete_profile, taxonomy_ids

    from silp.core.permissions import Role
    from silp.models.delivery import Deliverable, Milestone
    from silp.models.project import Project
    from silp.services import authz

    await complete_profile(committing_client, account["token"])
    await authz.grant_role(committing_session, user_id=account["user_id"], role=Role.INSTRUCTOR)
    await committing_session.commit()
    await authz.invalidate_roles(account["user_id"])

    skills = await taxonomy_ids(committing_client, "skills", limit=1)
    created = await committing_client.post(
        "/api/v1/projects",
        headers=auth(account),
        json={
            "title_fa": "پروژهٔ شهری پایدار آزمایشی",
            "summary": "خلاصهٔ کافی برای یک پروژهٔ شهری آزمایشی.",
            "description": "شرح کافی برای یک پروژهٔ شهری آزمایشی.",
            "kind": "C_PROBLEM",
            "expected_output": "مدل SUMO",
            "required_skills": [{"skill_id": skills[0], "min_level": 2}],
            "workflow": "CITY",
        },
    )
    assert created.status_code == 201, created.text
    project_id = uuid.UUID(created.json()["id"])
    try:
        for action in ("publish", "start"):
            response = await committing_client.post(
                f"/api/v1/projects/{project_id}/{action}", headers=auth(account)
            )
            assert response.status_code == 200, response.text
        await authz.invalidate_roles(account["user_id"])

        extra = await committing_client.post(
            f"/api/v1/projects/{project_id}/milestones",
            headers=auth(account),
            json={"title_fa": "جلسه با شهرداری", "sort_order": 9},
        )
        assert extra.status_code == 201, extra.text
        owned = await committing_client.put(
            f"/api/v1/milestones/{extra.json()['id']}/owner",
            headers=auth(account),
            json={"owner_id": str(account["user_id"])},
        )
        assert owned.status_code == 200, owned.text

        board = await committing_client.get(
            f"/api/v1/projects/{project_id}/city", headers=auth(account)
        )
        stage_one = board.json()["stages"][0]["milestone"]["id"]
        corner = [[57.07, 30.28], [57.08, 30.28], [57.08, 30.29], [57.07, 30.29], [57.07, 30.28]]
        submitted = await committing_client.post(
            f"/api/v1/milestones/{stage_one}/deliverables",
            headers=auth(account),
            json={
                "body": "محدودهٔ محور اصلی با مرز تا تقاطع‌های اثرگذار بالادست.",
                "evidence": {
                    "area": {"type": "Polygon", "coordinates": [corner]},
                    "justification": "محور بیشترین صف و شکایت را در گزارش شهرداری دارد و"
                    " داده‌اش در دسترس است.",
                },
            },
        )
        assert submitted.status_code == 201, submitted.text

        async with other_connection() as verifier:
            project = await verifier.get(Project, project_id)
            assert project is not None and project.workflow == "CITY", "الگو commit نشده است"
            stages = list(
                await verifier.scalars(
                    select(Milestone.workflow_stage).where(
                        Milestone.project_id == project_id, Milestone.workflow_stage.is_not(None)
                    )
                )
            )
            assert sorted(stages) == list(range(1, 9))
            free = await verifier.get(Milestone, uuid.UUID(extra.json()["id"]))
            assert free is not None and free.owner_id == account["user_id"], "مسئول commit نشده"
            stored = await verifier.get(Deliverable, uuid.UUID(submitted.json()["id"]))
            assert stored is not None and stored.evidence is not None, "شاهد commit نشده است"
            assert stored.evidence["area"]["type"] == "MultiPolygon"
    finally:
        await committing_session.execute(delete(Project).where(Project.id == project_id))
        await committing_session.commit()
