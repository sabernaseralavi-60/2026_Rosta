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


async def test_admin_writes_and_impersonated_reads_leave_an_audit_trail(  # type: ignore[no-untyped-def]
    committing_client, committing_session, account
) -> None:
    """M7 بخش د — نقش، لاگ حسابرسی و لاگ درخواست جعل هویت.

    لاگ درخواستِ جعل هویت روی مسیر `GET` نوشته می‌شود که خودش هرگز
    commit نمی‌زند؛ بدون commit صریح در `get_current_user` این ردیف با
    بسته شدن نشست بی‌صدا برمی‌گشت و فقط همین تست آن را می‌بیند.
    """
    from silp.core.permissions import Role
    from silp.models.admin import AuditLog
    from silp.models.identity import User, UserRole
    from silp.services import authz

    await authz.grant_role(committing_session, user_id=account["user_id"], role=Role.ADMIN)
    await committing_session.commit()
    await authz.invalidate_roles(account["user_id"])

    mobile = f"0913{uuid.uuid4().int % 10_000_000:07d}"
    response = await committing_client.post(
        "/api/v1/auth/otp/request", json={"destination": mobile, "channel": "SMS"}
    )
    response = await committing_client.post(
        "/api/v1/auth/otp/verify",
        json={"challenge_id": response.json()["challenge_id"], "code": "111111"},
    )
    assert response.status_code == 200, response.text
    target_id = uuid.UUID(response.json()["user"]["id"])
    try:
        granted = await committing_client.post(
            f"/api/v1/admin/users/{target_id}/roles", headers=auth(account), json={"role": "MENTOR"}
        )
        assert granted.status_code == 201, granted.text
        token = await committing_client.post(
            f"/api/v1/admin/users/{target_id}/impersonate", headers=auth(account)
        )
        assert token.status_code == 200, token.text
        seen = await committing_client.get(
            "/api/v1/me", headers={"Authorization": f"Bearer {token.json()['access_token']}"}
        )
        assert seen.status_code == 200, seen.text

        async with other_connection() as verifier:
            role = await verifier.scalar(
                select(UserRole.role_code).where(
                    UserRole.user_id == target_id, UserRole.role_code == "MENTOR"
                )
            )
            assert role == "MENTOR", "اعطای نقش commit نشده است"
            actions = set(
                await verifier.scalars(
                    select(AuditLog.action).where(
                        (AuditLog.entity_id == target_id) | (AuditLog.actor_id == target_id)
                    )
                )
            )
            assert {
                "ROLE_GRANTED",
                "IMPERSONATION_STARTED",
                "IMPERSONATED_REQUEST",
            } <= actions, f"لاگ حسابرسی commit نشده است: {actions}"
    finally:
        await committing_session.execute(delete(User).where(User.id == target_id))
        await committing_session.commit()


async def test_public_profile_privacy_survives_the_request(  # type: ignore[no-untyped-def]
    committing_client, committing_session, account
) -> None:
    from silp.models.profile import Profile

    response = await committing_client.patch(
        "/api/v1/me/profile",
        headers=auth(account),
        json={
            "first_name": "سارا",
            "last_name": "محمدی",
            "is_public": True,
            "privacy": {"points": False},
        },
    )
    assert response.status_code == 200, response.text

    async with other_connection() as verifier:
        stored = await verifier.get(Profile, account["user_id"])
        assert stored is not None and stored.is_public, "نیمرخ عمومی commit نشده است"
        assert stored.privacy_settings == {"points": False}


async def test_offering_settings_and_attendance_survive_the_request(  # type: ignore[no-untyped-def]
    committing_client, committing_session, account
) -> None:
    """ADR-0019 — تنظیمات ارائه و جلسهٔ حضور از ناحیهٔ استاد."""
    from datetime import date

    from silp.models.education import ClassSession, Course, CourseOffering, Term

    marker = uuid.uuid4().hex[:8]
    term = Term(
        code=f"T-{marker}",
        title_fa="نیم‌سال آزمایشی",
        starts_on=date(2026, 9, 23),
        ends_on=date(2027, 2, 4),
    )
    course = Course(code=f"C-{marker}", slug=f"course-{marker}", title_fa="برنامه‌ریزی حمل‌ونقل")
    committing_session.add_all([term, course])
    await committing_session.flush()
    offering = CourseOffering(
        course_id=course.id, term_id=term.id, instructor_id=account["user_id"], status="DRAFT"
    )
    committing_session.add(offering)
    await committing_session.commit()
    from silp.services import authz

    await authz.invalidate_roles(account["user_id"])
    try:
        response = await committing_client.patch(
            f"/api/v1/teach/offerings/{offering.id}",
            headers=auth(account),
            json={"status": "OPEN", "requires_approval": True, "enrollment_code": "ROAD-05"},
        )
        assert response.status_code == 200, response.text
        response = await committing_client.post(
            f"/api/v1/teach/offerings/{offering.id}/attendance",
            headers=auth(account),
            json={"held_on": "2026-10-04", "week_number": 2, "entries": []},
        )
        assert response.status_code == 200, response.text

        async with other_connection() as verifier:
            stored = await verifier.get(CourseOffering, offering.id)
            assert stored is not None and stored.status == "OPEN", "وضعیت ارائه commit نشده است"
            assert stored.requires_approval and stored.enrollment_code == "ROAD-05"
            held = await verifier.scalar(
                select(ClassSession.week_number).where(ClassSession.offering_id == offering.id)
            )
            assert held == 2, "جلسهٔ حضور commit نشده است"
    finally:
        await committing_session.execute(
            delete(CourseOffering).where(CourseOffering.id == offering.id)
        )
        await committing_session.execute(delete(Course).where(Course.id == course.id))
        await committing_session.execute(delete(Term).where(Term.id == term.id))
        await committing_session.commit()


async def test_announcement_and_bank_edits_survive_the_request(  # type: ignore[no-untyped-def]
    committing_client, committing_session, account
) -> None:
    """ADR-0021 — ویرایش و حذف اعلان، و ویرایش و حذف نرم سؤال بانک."""
    from datetime import date

    from silp.models.education import Announcement, Course, CourseOffering, Term
    from silp.models.quiz import QuestionBankItem
    from silp.services import authz

    marker = uuid.uuid4().hex[:8]
    term = Term(
        code=f"T-{marker}",
        title_fa="نیم‌سال آزمایشی",
        starts_on=date(2026, 9, 23),
        ends_on=date(2027, 2, 4),
    )
    course = Course(code=f"C-{marker}", slug=f"course-{marker}", title_fa="ایمنی راه")
    committing_session.add_all([term, course])
    await committing_session.flush()
    offering = CourseOffering(
        course_id=course.id, term_id=term.id, instructor_id=account["user_id"], status="OPEN"
    )
    committing_session.add(offering)
    await committing_session.commit()
    await authz.invalidate_roles(account["user_id"])

    base = f"/api/v1/teach/offerings/{offering.id}/announcements"
    question = {
        "kind": "TRUE_FALSE",
        "body": "پواسون برای داده‌های بیش‌پراکنده مناسب است.",
        "payload": {"correct": False},
    }
    bank_id: uuid.UUID | None = None
    try:
        kept = await committing_client.post(
            base, headers=auth(account), json={"title": "امتحان جمعه", "body": "ساعت ۱۰"}
        )
        dropped = await committing_client.post(
            base, headers=auth(account), json={"title": "اشتباهی", "body": "نادیده بگیرید"}
        )
        assert kept.status_code == dropped.status_code == 201, kept.text
        response = await committing_client.patch(
            f"{base}/{kept.json()['id']}", headers=auth(account), json={"title": "امتحان شنبه"}
        )
        assert response.status_code == 200, response.text
        response = await committing_client.delete(
            f"{base}/{dropped.json()['id']}", headers=auth(account)
        )
        assert response.status_code == 204, response.text

        created = await committing_client.post(
            "/api/v1/teach/question-bank", headers=auth(account), json=question
        )
        assert created.status_code == 201, created.text
        bank_id = uuid.UUID(created.json()["id"])
        response = await committing_client.put(
            f"/api/v1/teach/question-bank/{bank_id}",
            headers=auth(account),
            json={**question, "difficulty": 2},
        )
        assert response.status_code == 200, response.text
        response = await committing_client.delete(
            f"/api/v1/teach/question-bank/{bank_id}", headers=auth(account)
        )
        assert response.status_code == 204, response.text

        async with other_connection() as verifier:
            stored = await verifier.get(Announcement, uuid.UUID(kept.json()["id"]))
            assert stored is not None and stored.title == "امتحان شنبه", "ویرایش commit نشده است"
            assert stored.edited_at is not None
            gone = await verifier.get(Announcement, uuid.UUID(dropped.json()["id"]))
            assert gone is None, "حذف اعلان commit نشده است"
            item = await verifier.get(QuestionBankItem, bank_id)
            assert item is not None and item.difficulty == 2, "ویرایش بانک commit نشده است"
            assert item.deleted_at is not None, "حذف نرم بانک commit نشده است"
    finally:
        if bank_id is not None:
            await committing_session.execute(
                delete(QuestionBankItem).where(QuestionBankItem.id == bank_id)
            )
        await committing_session.execute(
            delete(CourseOffering).where(CourseOffering.id == offering.id)
        )
        await committing_session.execute(delete(Course).where(Course.id == course.id))
        await committing_session.execute(delete(Term).where(Term.id == term.id))
        await committing_session.commit()


async def test_subscription_activation_survives_with_audit_and_notice(  # type: ignore[no-untyped-def]
    committing_client, committing_session, account
) -> None:
    """ADR-0019 — فعال‌سازی، ردیف حسابرسی و اعلان در یک تراکنش."""
    from silp.core.permissions import Role
    from silp.models.access import Subscription
    from silp.models.admin import AuditLog
    from silp.models.messaging import Notification
    from silp.services import authz

    await authz.grant_role(committing_session, user_id=account["user_id"], role=Role.ADMIN)
    await committing_session.commit()
    await authz.invalidate_roles(account["user_id"])

    requested = await committing_client.post(
        "/api/v1/subscriptions", headers=auth(account), json={"plan_code": "MONTHLY_ALL"}
    )
    assert requested.status_code == 201, requested.text
    subscription_id = uuid.UUID(requested.json()["id"])
    response = await committing_client.post(
        f"/api/v1/subscriptions/{subscription_id}/activate",
        headers=auth(account),
        json={"payment_ref": "RRN-2201"},
    )
    assert response.status_code == 200, response.text

    async with other_connection() as verifier:
        stored = await verifier.get(Subscription, subscription_id)
        assert stored is not None and stored.status == "ACTIVE", "فعال‌سازی commit نشده است"
        assert stored.payment_ref == "RRN-2201"
        action = await verifier.scalar(
            select(AuditLog.action).where(AuditLog.entity_id == subscription_id)
        )
        assert action == "SUBSCRIPTION_ACTIVATED", "لاگ حسابرسی commit نشده است"
        notice = await verifier.scalar(
            select(Notification.id).where(
                Notification.user_id == account["user_id"],
                Notification.kind == "SUBSCRIPTION_ACTIVATED",
            )
        )
        assert notice is not None, "اعلان فعال شدن commit نشده است"


async def test_course_admin_writes_survive_the_request(  # type: ignore[no-untyped-def]
    committing_client, committing_session, account
) -> None:
    """ADR-0020 — نیم‌سال، درس و ارائه از پنل، هر کدام با ردیف حسابرسی؛ و
    ADR-0021 — اعلان استادی که ارائه به او سپرده شد."""
    from silp.core.permissions import Role
    from silp.models.admin import AuditLog
    from silp.models.education import Course, CourseOffering, Term
    from silp.models.identity import User
    from silp.models.messaging import Notification
    from silp.services import authz

    await authz.grant_role(committing_session, user_id=account["user_id"], role=Role.COORDINATOR)
    await committing_session.commit()
    await authz.invalidate_roles(account["user_id"])

    marker = uuid.uuid4().hex[:6].upper()
    ids: dict[str, uuid.UUID] = {}
    try:
        response = await committing_client.post(
            "/api/v1/admin/terms",
            headers=auth(account),
            json={
                "code": f"D{marker}",
                "title_fa": "نیم‌سال پایداری",
                "starts_on": "2026-09-01",
                "ends_on": "2099-02-01",
            },
        )
        assert response.status_code == 201, response.text
        ids["term"] = uuid.UUID(response.json()["id"])
        response = await committing_client.post(
            "/api/v1/admin/courses",
            headers=auth(account),
            json={"code": f"D-{marker}", "title_fa": "درس پایداری"},
        )
        assert response.status_code == 201, response.text
        ids["course"] = uuid.UUID(response.json()["id"])
        response = await committing_client.post(
            "/api/v1/admin/offerings",
            headers=auth(account),
            json={
                "course_id": str(ids["course"]),
                "term_id": str(ids["term"]),
                "instructor_id": str(account["user_id"]),
                "enrollment_code": "DUR-1405",
            },
        )
        assert response.status_code == 201, response.text
        ids["offering"] = uuid.UUID(response.json()["id"])

        mobile = f"0913{uuid.uuid4().int % 10_000_000:07d}"
        response = await committing_client.post(
            "/api/v1/auth/otp/request", json={"destination": mobile, "channel": "SMS"}
        )
        response = await committing_client.post(
            "/api/v1/auth/otp/verify",
            json={"challenge_id": response.json()["challenge_id"], "code": "111111"},
        )
        assert response.status_code == 200, response.text
        ids["instructor"] = uuid.UUID(response.json()["user"]["id"])
        response = await committing_client.patch(
            f"/api/v1/admin/offerings/{ids['offering']}",
            headers=auth(account),
            json={"instructor_id": str(ids["instructor"])},
        )
        assert response.status_code == 200, response.text

        async with other_connection() as verifier:
            assert await verifier.get(Term, ids["term"]) is not None, "نیم‌سال commit نشده است"
            assert await verifier.get(Course, ids["course"]) is not None, "درس commit نشده است"
            stored = await verifier.get(CourseOffering, ids["offering"])
            assert stored is not None, "ارائه commit نشده است"
            assert stored.enrollment_code == "DUR-1405"
            actions = set(
                await verifier.scalars(
                    select(AuditLog.action).where(AuditLog.entity_id.in_(list(ids.values())))
                )
            )
            assert actions == {
                "TERM_CREATED",
                "COURSE_CREATED",
                "OFFERING_CREATED",
                "OFFERING_UPDATED",
            }
            notice = await verifier.scalar(
                select(Notification.action_url).where(
                    Notification.user_id == ids["instructor"],
                    Notification.kind == "OFFERING_ASSIGNED",
                )
            )
            assert notice == f"/teach/offerings/{ids['offering']}", "اعلان سپردن commit نشده است"
    finally:
        if "offering" in ids:
            await committing_session.execute(
                delete(CourseOffering).where(CourseOffering.id == ids["offering"])
            )
        if "course" in ids:
            await committing_session.execute(delete(Course).where(Course.id == ids["course"]))
        if "term" in ids:
            await committing_session.execute(delete(Term).where(Term.id == ids["term"]))
        if "instructor" in ids:
            await committing_session.execute(delete(User).where(User.id == ids["instructor"]))
        await committing_session.commit()


async def test_project_linked_to_an_offering_survives_the_request(  # type: ignore[no-untyped-def]
    committing_client, committing_session, account
) -> None:
    """ADR-0022 — پیوند پروژه به ارائه، و اینکه استادش بی‌نقش سراسری آن را می‌بیند."""
    from silp.core.permissions import Role
    from silp.models.education import Course, CourseOffering, Term
    from silp.models.identity import User
    from silp.models.project import Project
    from silp.services import authz

    await authz.grant_role(committing_session, user_id=account["user_id"], role=Role.COORDINATOR)
    await committing_session.commit()
    await authz.invalidate_roles(account["user_id"])

    marker = uuid.uuid4().hex[:6].upper()
    ids: dict[str, uuid.UUID] = {}
    try:
        response = await committing_client.post(
            "/api/v1/admin/terms",
            headers=auth(account),
            json={
                "code": f"P{marker}",
                "title_fa": "نیم‌سال پروژه",
                "starts_on": "2026-09-01",
                "ends_on": "2099-02-01",
            },
        )
        assert response.status_code == 201, response.text
        ids["term"] = uuid.UUID(response.json()["id"])
        response = await committing_client.post(
            "/api/v1/admin/courses",
            headers=auth(account),
            json={"code": f"P-{marker}", "title_fa": "درس پروژه"},
        )
        assert response.status_code == 201, response.text
        ids["course"] = uuid.UUID(response.json()["id"])
        response = await committing_client.post(
            "/api/v1/admin/offerings",
            headers=auth(account),
            json={
                "course_id": str(ids["course"]),
                "term_id": str(ids["term"]),
                "instructor_id": str(account["user_id"]),
                "enrollment_code": "PRJ-1405",
            },
        )
        assert response.status_code == 201, response.text
        ids["offering"] = uuid.UUID(response.json()["id"])

        response = await committing_client.post(
            "/api/v1/projects",
            headers=auth(account),
            json={
                "title_fa": "پروژهٔ پایداری ارائه",
                "summary": "پروژه‌ای که به ارائه وصل است و باید ماندگار باشد.",
                "description": "شرح کامل پروژه با جزئیات کافی برای آزمون پایداری.",
                "kind": "C_PROBLEM",
                "expected_output": "گزارش نهایی",
                "offering_id": str(ids["offering"]),
            },
        )
        assert response.status_code == 201, response.text
        ids["project"] = uuid.UUID(response.json()["id"])

        async with other_connection() as verifier:
            stored = await verifier.get(Project, ids["project"])
            assert stored is not None, "پروژه commit نشده است"
            assert stored.offering_id == ids["offering"], "پیوند ارائه commit نشده است"

        listed = await committing_client.get("/api/v1/teach/projects", headers=auth(account))
        assert listed.status_code == 200, listed.text
        assert [p["id"] for p in listed.json()] == [str(ids["project"])]
    finally:
        if "project" in ids:
            await committing_session.execute(delete(Project).where(Project.id == ids["project"]))
        if "offering" in ids:
            await committing_session.execute(
                delete(CourseOffering).where(CourseOffering.id == ids["offering"])
            )
        if "course" in ids:
            await committing_session.execute(delete(Course).where(Course.id == ids["course"]))
        if "term" in ids:
            await committing_session.execute(delete(Term).where(Term.id == ids["term"]))
        await committing_session.execute(delete(User).where(User.id == account["user_id"]))
        await committing_session.commit()
