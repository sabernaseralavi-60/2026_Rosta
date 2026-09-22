"""تست یکپارچهٔ نیمرخ و توصیه‌گر — FR-PROF-01، §5.3، §5.4، §5.7.

PostgreSQL واقعی لازم است (D-14): طبقه‌بندی‌ها با مهاجرت ۰۰۳ درج می‌شوند،
کوئری نامزد §8.12 به `LATERAL`/`EXISTS` تکیه دارد، و ستون `search_norm`
تولیدشدهٔ دیتابیس است. بدون دیتابیس این تست‌ها `skip` می‌شوند.
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import select, text

pytestmark = pytest.mark.integration

MOBILE = "09121110001"


async def login(client) -> str:  # type: ignore[no-untyped-def]
    response = await client.post(
        "/api/v1/auth/otp/request", json={"destination": MOBILE, "channel": "SMS"}
    )
    challenge_id = response.json()["challenge_id"]
    response = await client.post(
        "/api/v1/auth/otp/verify", json={"challenge_id": challenge_id, "code": "111111"}
    )
    assert response.status_code == 200, response.text
    return str(response.json()["access_token"])


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def taxonomy(client, path: str) -> Any:  # type: ignore[no-untyped-def]
    response = await client.get(f"/api/v1/taxonomy/{path}")
    assert response.status_code == 200, response.text
    return response.json()


async def code_to_id(client, path: str, code: str) -> str:
    payload = await taxonomy(client, path)
    items = payload["items"] if isinstance(payload, dict) else payload
    return str(next(i["id"] for i in items if i["code"] == code))


# ── §5.4 طبقه‌بندی‌ها ──────────────────────────────────────────────────
async def test_taxonomy_is_seeded_by_migration(client) -> None:  # type: ignore[no-untyped-def]
    """دادهٔ §14.1 تا §14.3 بخشی از اسکیماست، نه دادهٔ نمونه (ADR-0004)."""
    skills = await taxonomy(client, "skills")
    assets = await taxonomy(client, "assets")
    interests = await taxonomy(client, "interests")

    assert len(skills["items"]) == 17
    assert len(assets) == 9
    assert len(interests["items"]) == 12


async def test_core_skills_are_capped_at_ten(client) -> None:  # type: ignore[no-untyped-def]
    """§4.3 — گام ۱ باید زیر ۹۰ ثانیه بماند، پس حداکثر ده مهارت هسته."""
    skills = await taxonomy(client, "skills")
    assert sum(1 for s in skills["items"] if s["is_core"]) <= 10


async def test_skill_level_labels_come_from_the_server(client) -> None:  # type: ignore[no-untyped-def]
    """FR-PROF-01 — مقیاس باید توصیفی باشد، نه عددی خالی."""
    skills = await taxonomy(client, "skills")
    labels = {item["level"]: item["label"] for item in skills["level_labels"]}
    assert set(labels) == {1, 2, 3, 4, 5}
    assert labels[1] and labels[5]


async def test_taxonomy_is_public_and_cacheable(client) -> None:  # type: ignore[no-untyped-def]
    response = await client.get("/api/v1/taxonomy/skills")
    assert response.status_code == 200  # بدون توکن
    assert "max-age=3600" in response.headers["Cache-Control"]


async def test_university_search_normalizes_arabic_letters(client) -> None:  # type: ignore[no-untyped-def]
    """کاربر «شهيد» با «ي» عربی می‌نویسد و باید همان نتیجه را بگیرد."""
    arabic = await client.get("/api/v1/taxonomy/universities", params={"q": "شهيد باهنر"})
    persian = await client.get("/api/v1/taxonomy/universities", params={"q": "شهید باهنر"})

    assert arabic.status_code == 200
    assert [u["id"] for u in arabic.json()] == [u["id"] for u in persian.json()]
    assert arabic.json()


# ── §5.3 نیمرخ ─────────────────────────────────────────────────────────
async def test_new_user_needs_basic_info(client) -> None:  # type: ignore[no-untyped-def]
    """§7.1 — تصمیم با سرور است، نه کلاینت."""
    token = await login(client)
    response = await client.get("/api/v1/me", headers=auth(token))

    body = response.json()
    assert body["profile"] is None
    assert body["onboarding"]["state"] == "BASIC_INFO_REQUIRED"
    assert body["onboarding"]["next_route"] == "/onboarding/basic"


async def test_creating_profile_advances_onboarding(client) -> None:  # type: ignore[no-untyped-def]
    token = await login(client)
    response = await client.patch(
        "/api/v1/me/profile",
        headers=auth(token),
        json={"first_name": "مریم", "last_name": "کریمی", "degree_level": "BACHELOR"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["degree_level_fa"] == "کارشناسی"

    me = (await client.get("/api/v1/me", headers=auth(token))).json()
    assert me["onboarding"]["state"] == "SURVEY_REQUIRED"
    assert me["profile"]["first_name"] == "مریم"


async def test_profile_patch_leaves_untouched_fields_alone(client) -> None:  # type: ignore[no-untyped-def]
    """§5.3 — `None` یعنی «دست نزن»، نه «خالی کن»."""
    token = await login(client)
    await client.patch(
        "/api/v1/me/profile",
        headers=auth(token),
        json={"first_name": "مریم", "last_name": "کریمی", "field_of_study": "عمران"},
    )
    response = await client.patch(
        "/api/v1/me/profile", headers=auth(token), json={"bio": "دانشجوی سال آخر"}
    )

    body = response.json()
    assert body["field_of_study"] == "عمران"
    assert body["bio"] == "دانشجوی سال آخر"


async def test_profile_cannot_be_created_without_a_name(client) -> None:  # type: ignore[no-untyped-def]
    token = await login(client)
    response = await client.patch(
        "/api/v1/me/profile", headers=auth(token), json={"field_of_study": "عمران"}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"


# ── FR-PROF-01 چهار گام ────────────────────────────────────────────────
async def created_profile(client) -> str:  # type: ignore[no-untyped-def]
    token = await login(client)
    await client.patch(
        "/api/v1/me/profile",
        headers=auth(token),
        json={"first_name": "سارا", "last_name": "محمدی"},
    )
    return token


async def test_step_one_returns_recommendations_immediately(client) -> None:  # type: ignore[no-untyped-def]
    """«لحظهٔ طلایی» §01 — سه پیشنهاد پس از گام ۱، با نیمرخ ۲۵٪ کامل."""
    token = await created_profile(client)
    skill_id = await code_to_id(client, "skills", "MARKETING_SKILL")

    response = await client.patch(
        "/api/v1/me/survey/skills",
        headers=auth(token),
        json={"skills": [{"skill_id": skill_id, "level": 4}]},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["completed_steps"] == 1
    assert body["total_steps"] == 4
    assert len(body["preview_recommendations"]) >= 1
    assert body["preview_recommendations"][0]["reasons"]


async def test_each_step_saves_independently(client) -> None:  # type: ignore[no-untyped-def]
    """FR-PROF-01 — بستن مرورگر وسط فرم، داده را از بین نمی‌برد."""
    token = await created_profile(client)
    skill_id = await code_to_id(client, "skills", "PYTHON")
    asset_id = await code_to_id(client, "assets", "LAPTOP")
    interest_id = await code_to_id(client, "interests", "SALES")

    await client.patch(
        "/api/v1/me/survey/skills",
        headers=auth(token),
        json={"skills": [{"skill_id": skill_id, "level": 3}]},
    )
    await client.patch(
        "/api/v1/me/survey/assets", headers=auth(token), json={"asset_ids": [asset_id]}
    )
    await client.patch(
        "/api/v1/me/survey/interests",
        headers=auth(token),
        json={"interests": [{"interest_id": interest_id, "level": 5}]},
    )
    response = await client.patch(
        "/api/v1/me/survey/preferences",
        headers=auth(token),
        json={"work_style": "TEAM", "primary_goal": "INCOME", "weekly_hours": 12},
    )
    assert response.json()["completed_steps"] == 4

    survey = (await client.get("/api/v1/me/survey", headers=auth(token))).json()
    assert survey["skills"] == [{"skill_id": skill_id, "level": 3, "is_verified": False}]
    assert survey["asset_ids"] == [asset_id]
    assert survey["interests"] == [{"interest_id": interest_id, "level": 5}]
    assert survey["primary_goal"] == "INCOME"

    me = (await client.get("/api/v1/me", headers=auth(token))).json()
    assert me["onboarding"]["state"] == "COMPLETE"


async def test_editing_an_early_step_does_not_reduce_progress(client) -> None:  # type: ignore[no-untyped-def]
    """ویرایش گام ۱ نباید «۴ گام» را به «۱ گام» برگرداند."""
    token = await created_profile(client)
    skill_id = await code_to_id(client, "skills", "PYTHON")

    await client.patch(
        "/api/v1/me/survey/preferences",
        headers=auth(token),
        json={"work_style": "SOLO", "primary_goal": "LEARNING", "weekly_hours": 6},
    )
    response = await client.patch(
        "/api/v1/me/survey/skills",
        headers=auth(token),
        json={"skills": [{"skill_id": skill_id, "level": 5}]},
    )
    assert response.json()["completed_steps"] == 4


async def test_assets_step_replaces_the_whole_set(client) -> None:  # type: ignore[no-untyped-def]
    """گام ۲ جایگزینی کامل است: فهرست خالی یعنی «هیچ امکانی ندارم»."""
    token = await created_profile(client)
    laptop = await code_to_id(client, "assets", "LAPTOP")
    car = await code_to_id(client, "assets", "CAR")

    await client.patch(
        "/api/v1/me/survey/assets", headers=auth(token), json={"asset_ids": [laptop, car]}
    )
    await client.patch(
        "/api/v1/me/survey/assets", headers=auth(token), json={"asset_ids": [laptop]}
    )

    survey = (await client.get("/api/v1/me/survey", headers=auth(token))).json()
    assert survey["asset_ids"] == [laptop]


async def test_unknown_taxonomy_id_is_a_validation_error(client) -> None:  # type: ignore[no-untyped-def]
    """شناسهٔ ناموجود باید ۴۲۲ بدهد، نه ۵۰۰ از کلید خارجی."""
    token = await created_profile(client)
    response = await client.patch(
        "/api/v1/me/survey/skills",
        headers=auth(token),
        json={"skills": [{"skill_id": "00000000-0000-0000-0000-0000000000ff", "level": 3}]},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"


@pytest.mark.parametrize("level", [0, 6, -1])
async def test_skill_level_is_bounded(client, level: int) -> None:  # type: ignore[no-untyped-def]
    token = await created_profile(client)
    skill_id = await code_to_id(client, "skills", "PYTHON")
    response = await client.patch(
        "/api/v1/me/survey/skills",
        headers=auth(token),
        json={"skills": [{"skill_id": skill_id, "level": level}]},
    )
    assert response.status_code == 422


async def test_editing_survey_keeps_a_version(client, db_session) -> None:  # type: ignore[no-untyped-def]
    """FR-PROF-01 — نسخهٔ قبلی برای تحلیل رشد مهارت می‌ماند."""
    from silp.models.profile import ProfileSurveyVersion

    token = await created_profile(client)
    me = (await client.get("/api/v1/me", headers=auth(token))).json()
    user_id = me["id"]
    skill_id = await code_to_id(client, "skills", "PYTHON")

    await client.patch(
        "/api/v1/me/survey/skills",
        headers=auth(token),
        json={"skills": [{"skill_id": skill_id, "level": 2}]},
    )
    await client.patch(
        "/api/v1/me/survey/skills",
        headers=auth(token),
        json={"skills": [{"skill_id": skill_id, "level": 5}]},
    )

    # کوئری به همین کاربر محدود است: جدول مشترک است و تست نباید فرض کند
    # خالی شروع شده.
    versions = (
        await db_session.scalars(
            select(ProfileSurveyVersion)
            .where(ProfileSurveyVersion.user_id == user_id)
            .order_by(ProfileSurveyVersion.created_at)
        )
    ).all()
    # اولین ذخیره آرشیو نمی‌شود (نیمرخ خالی بود)؛ دومی می‌شود.
    assert len(versions) == 1
    assert versions[0].snapshot["skills"][0]["level"] == 2


# ── §5.7 پیشنهاد ───────────────────────────────────────────────────────
async def test_recommendations_require_authentication(client) -> None:  # type: ignore[no-untyped-def]
    response = await client.get("/api/v1/projects/recommended")
    assert response.status_code == 401


async def test_recommendations_carry_reasons_and_breakdown(client) -> None:  # type: ignore[no-untyped-def]
    token = await created_profile(client)
    await client.patch(
        "/api/v1/me/survey/preferences",
        headers=auth(token),
        json={"work_style": "TEAM", "primary_goal": "INCOME", "weekly_hours": 10},
    )

    response = await client.get("/api/v1/projects/recommended", headers=auth(token))
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["items"], "بانک پروژه خالی است — داده‌های نمونه اجرا نشده‌اند"
    first = body["items"][0]
    assert 0 <= first["match_score"] <= 100
    assert set(first["breakdown"]) == {"skill", "asset", "interest", "time", "style", "goal"}
    assert first["reasons"]
    # §8.10 — متن فارسی از سرور می‌آید، نه کلید ترجمه.
    assert any("؀" <= ch <= "ۿ" for ch in first["reasons"][0]["text"])


async def test_mandatory_asset_gate_hides_the_project(client, db_session) -> None:  # type: ignore[no-untyped-def]
    """§8.3 — بدون خودرو، پروژهٔ نیازمند خودرو اصلاً پیشنهاد نمی‌شود."""
    from silp.models.project import Project

    token = await created_profile(client)
    laptop = await code_to_id(client, "assets", "LAPTOP")
    await client.patch(
        "/api/v1/me/survey/assets", headers=auth(token), json={"asset_ids": [laptop]}
    )

    # پروژهٔ P-04 خودرو را الزامی کرده است (§14.5).
    blocked = await db_session.scalar(
        select(Project.id).where(Project.slug == "p-04-agri-software-rollout")
    )
    if blocked is None:
        pytest.skip("بانک پروژهٔ نمونه اجرا نشده است.")

    body = (await client.get("/api/v1/projects/recommended", headers=auth(token))).json()
    assert str(blocked) not in {item["project"]["id"] for item in body["items"]}


async def test_dismissed_project_disappears_from_recommendations(client) -> None:  # type: ignore[no-untyped-def]
    """§8.9 — «دیگر نشانم نده» باید فوراً اثر کند."""
    token = await created_profile(client)
    body = (await client.get("/api/v1/projects/recommended", headers=auth(token))).json()
    if not body["items"]:
        pytest.skip("بانک پروژهٔ نمونه اجرا نشده است.")

    target = body["items"][0]["project"]["id"]
    response = await client.post(
        f"/api/v1/recommendations/{target}/feedback",
        headers=auth(token),
        json={"verdict": "DISMISSED"},
    )
    assert response.status_code == 204, response.text

    after = (await client.get("/api/v1/projects/recommended", headers=auth(token))).json()
    assert target not in {item["project"]["id"] for item in after["items"]}


async def test_feedback_on_unknown_project_is_404(client) -> None:  # type: ignore[no-untyped-def]
    token = await created_profile(client)
    response = await client.post(
        "/api/v1/recommendations/00000000-0000-0000-0000-0000000000ff/feedback",
        headers=auth(token),
        json={"verdict": "INTERESTED"},
    )
    assert response.status_code == 404


async def test_project_list_is_public(client) -> None:  # type: ignore[no-untyped-def]
    response = await client.get("/api/v1/projects")
    assert response.status_code == 200
    assert "items" in response.json()


async def test_project_search_uses_normalized_persian(client) -> None:  # type: ignore[no-untyped-def]
    """§4.11 — جستجو روی `search_norm` با trigram، نه ILIKE خام."""
    arabic = await client.get("/api/v1/projects", params={"q": "خرماي"})
    persian = await client.get("/api/v1/projects", params={"q": "خرمای"})

    assert arabic.status_code == 200
    assert [p["id"] for p in arabic.json()["items"]] == [p["id"] for p in persian.json()["items"]]


async def test_project_detail_includes_my_match_when_logged_in(client) -> None:  # type: ignore[no-untyped-def]
    token = await created_profile(client)
    listing = (await client.get("/api/v1/projects")).json()
    if not listing["items"]:
        pytest.skip("بانک پروژهٔ نمونه اجرا نشده است.")
    project_id = listing["items"][0]["id"]

    anonymous = (await client.get(f"/api/v1/projects/{project_id}")).json()
    assert anonymous["match"] is None
    assert anonymous["description"]

    mine = (await client.get(f"/api/v1/projects/{project_id}", headers=auth(token))).json()
    assert mine["match"] is not None
    assert 0 <= mine["match"]["match_score"] <= 100


async def test_generated_search_column_is_populated(db_session) -> None:  # type: ignore[no-untyped-def]
    """ستون `search_norm` را دیتابیس می‌سازد، نه پایتون — §4.6."""
    row = await db_session.execute(
        text("SELECT title_fa, search_norm FROM projects WHERE deleted_at IS NULL LIMIT 1")
    )
    record = row.first()
    if record is None:
        pytest.skip("بانک پروژهٔ نمونه اجرا نشده است.")
    assert record.search_norm
    assert record.search_norm == record.search_norm.lower()
