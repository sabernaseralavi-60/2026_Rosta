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
