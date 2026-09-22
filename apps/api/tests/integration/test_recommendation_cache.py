"""کش موتور توصیه‌گر — PRD §8.12.

| کلید | TTL | باطل‌سازی |
|------|-----|-----------|
| `rec:{user_id}` | ۳۰ دقیقه | تغییر نیمرخ، پروژهٔ جدید `OPEN`، ثبت درخواست |

بدون Redis این تست‌ها رد می‌شوند: کش طبق NFR-11 اختیاری است و نبودش
نباید مجموعهٔ تست را قرمز کند.
"""

from __future__ import annotations

import uuid

import pytest
from redis.exceptions import RedisError
from sqlalchemy import select

pytestmark = pytest.mark.integration

MOBILE = "09121115555"


async def redis_available() -> bool:
    from silp.core.redis import get_redis

    try:
        return bool(await get_redis().ping())
    except (RedisError, OSError):
        return False


async def student(client) -> tuple[str, uuid.UUID]:  # type: ignore[no-untyped-def]
    """کاربر واردشده با نیمرخ ساخته‌شده — پیش‌نیاز هر پیشنهادی."""
    response = await client.post(
        "/api/v1/auth/otp/request", json={"destination": MOBILE, "channel": "SMS"}
    )
    challenge_id = response.json()["challenge_id"]
    response = await client.post(
        "/api/v1/auth/otp/verify", json={"challenge_id": challenge_id, "code": "111111"}
    )
    assert response.status_code == 200, response.text
    token = str(response.json()["access_token"])
    user_id = uuid.UUID(response.json()["user"]["id"])

    await client.patch(
        "/api/v1/me/profile",
        headers={"Authorization": f"Bearer {token}"},
        json={"first_name": "نگار", "last_name": "احمدی"},
    )
    return token, user_id


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_recommendations_are_cached_with_the_documented_ttl(client, db_session) -> None:  # type: ignore[no-untyped-def]
    """§8.12 — کلید `silp:rec:{user_id}` با TTL سی دقیقه."""
    if not await redis_available():
        pytest.skip("Redis در دسترس نیست — کش اختیاری است (NFR-11).")

    from silp.core.redis import get_redis
    from silp.domain.recommendation.service import REC_CACHE_TTL_SECONDS, key_recommendations

    token, user_id = await student(client)
    await client.get("/api/v1/projects/recommended", headers=auth(token))

    ttl = await get_redis().ttl(key_recommendations(user_id))
    assert 0 < ttl <= REC_CACHE_TTL_SECONDS


async def test_second_call_is_served_from_cache(client) -> None:  # type: ignore[no-untyped-def]
    """`computed_at` بین دو فراخوانی پیاپی عوض نمی‌شود."""
    if not await redis_available():
        pytest.skip("Redis در دسترس نیست — کش اختیاری است (NFR-11).")

    token, _ = await student(client)
    first = (await client.get("/api/v1/projects/recommended", headers=auth(token))).json()
    second = (await client.get("/api/v1/projects/recommended", headers=auth(token))).json()

    assert first["computed_at"] == second["computed_at"]
    assert [i["project"]["id"] for i in first["items"]] == [
        i["project"]["id"] for i in second["items"]
    ]


async def test_changing_the_profile_invalidates_the_cache(client) -> None:  # type: ignore[no-untyped-def]
    """§8.12 — گام تازهٔ ارزیابی باید کش را بیندازد، وگرنه دانشجو تا نیم
    ساعت اثر کارش را نمی‌بیند و گمان می‌کند فرم بی‌فایده است."""
    if not await redis_available():
        pytest.skip("Redis در دسترس نیست — کش اختیاری است (NFR-11).")

    from silp.core.redis import get_redis
    from silp.domain.recommendation.service import key_recommendations

    token, user_id = await student(client)
    await client.get("/api/v1/projects/recommended", headers=auth(token))
    assert await get_redis().exists(key_recommendations(user_id))

    skills = (await client.get("/api/v1/taxonomy/skills")).json()["items"]
    skill_id = next(s["id"] for s in skills if s["code"] == "PYTHON")
    await client.patch(
        "/api/v1/me/survey/skills",
        headers=auth(token),
        json={"skills": [{"skill_id": skill_id, "level": 5}]},
    )

    assert not await get_redis().exists(key_recommendations(user_id))


async def test_feedback_invalidates_the_cache(client, db_session) -> None:  # type: ignore[no-untyped-def]
    if not await redis_available():
        pytest.skip("Redis در دسترس نیست — کش اختیاری است (NFR-11).")

    from silp.core.redis import get_redis
    from silp.domain.recommendation.service import key_recommendations
    from silp.models.project import Project

    token, user_id = await student(client)
    await client.get("/api/v1/projects/recommended", headers=auth(token))

    project_id = await db_session.scalar(
        select(Project.id).where(Project.status == "OPEN", Project.deleted_at.is_(None)).limit(1)
    )
    if project_id is None:
        pytest.skip("بانک پروژهٔ نمونه اجرا نشده است.")

    await client.post(
        f"/api/v1/recommendations/{project_id}/feedback",
        headers=auth(token),
        json={"verdict": "INTERESTED"},
    )

    assert not await get_redis().exists(key_recommendations(user_id))


async def test_preview_never_reads_the_cache(client) -> None:  # type: ignore[no-untyped-def]
    """پیش‌نمایش هر گام باید وضعیت همین لحظه را بدهد، نه نسخهٔ کش‌شده."""
    if not await redis_available():
        pytest.skip("Redis در دسترس نیست — کش اختیاری است (NFR-11).")

    from silp.core.redis import get_redis
    from silp.domain.recommendation.service import key_recommendations

    token, user_id = await student(client)
    skills = (await client.get("/api/v1/taxonomy/skills")).json()["items"]
    skill_id = next(s["id"] for s in skills if s["code"] == "MARKETING_SKILL")

    # کش را با مقدار خراب پر می‌کنیم: اگر پیش‌نمایش از آن بخواند، می‌شکند.
    await get_redis().set(key_recommendations(user_id), "not-json")

    response = await client.patch(
        "/api/v1/me/survey/skills",
        headers=auth(token),
        json={"skills": [{"skill_id": skill_id, "level": 4}]},
    )
    assert response.status_code == 200, response.text
    assert response.json()["preview_recommendations"]


async def test_corrupt_cache_is_ignored_not_fatal(client) -> None:  # type: ignore[no-untyped-def]
    """شکل ذخیره‌شده اگر با نسخهٔ کد نخواند، دوباره محاسبه می‌شود."""
    if not await redis_available():
        pytest.skip("Redis در دسترس نیست — کش اختیاری است (NFR-11).")

    from silp.core.redis import get_redis
    from silp.domain.recommendation.service import key_recommendations

    token, user_id = await student(client)
    await get_redis().set(key_recommendations(user_id), '{"computed_at": "nope", "items": []}')

    response = await client.get("/api/v1/projects/recommended", headers=auth(token))
    assert response.status_code == 200, response.text
