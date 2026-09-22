"""کمکی‌های مشترک تست یکپارچه — ورود، نیمرخ کامل، اعطای نقش.

اینجا هیچ ادعایی دربارهٔ رفتار سامانه تست نمی‌شود؛ فقط مقدمات یک سناریو
ساخته می‌شود. هر `assert` اینجا برای این است که شکست مقدمات با پیام روشن
دیده شود، نه اینکه تست اصلی در جای عجیبی بترکد.
"""

from __future__ import annotations

import uuid
from typing import Any

DEV_OTP = "111111"


async def login(client: Any, mobile: str) -> str:
    """ورود با OTP ثابت محیط توسعه و بازگرداندن access token."""
    response = await client.post(
        "/api/v1/auth/otp/request", json={"destination": mobile, "channel": "SMS"}
    )
    assert response.status_code == 200, response.text
    challenge_id = response.json()["challenge_id"]

    response = await client.post(
        "/api/v1/auth/otp/verify", json={"challenge_id": challenge_id, "code": DEV_OTP}
    )
    assert response.status_code == 200, response.text
    return str(response.json()["access_token"])


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def me(client: Any, token: str) -> dict[str, Any]:
    response = await client.get("/api/v1/me", headers=auth(token))
    assert response.status_code == 200, response.text
    return dict(response.json())


async def taxonomy_ids(client: Any, path: str, *, limit: int = 3) -> list[str]:
    response = await client.get(f"/api/v1/taxonomy/{path}")
    assert response.status_code == 200, response.text
    payload = response.json()
    items = payload["items"] if isinstance(payload, dict) else payload
    return [str(item["id"]) for item in items[:limit]]


async def complete_profile(
    client: Any,
    token: str,
    *,
    first_name: str = "نیلوفر",
    last_name: str = "رستمی",
    work_style: str = "EITHER",
    primary_goal: str = "LEARNING",
    weekly_hours: int = 10,
    skill_level: int = 4,
) -> None:
    """هر چهار گام ارزیابی — شرط §7.5 برای درخواست پیوستن."""
    response = await client.patch(
        "/api/v1/me/profile",
        headers=auth(token),
        json={"first_name": first_name, "last_name": last_name, "degree_level": "BACHELOR"},
    )
    assert response.status_code == 200, response.text

    skills = await taxonomy_ids(client, "skills", limit=3)
    response = await client.patch(
        "/api/v1/me/survey/skills",
        headers=auth(token),
        json={"skills": [{"skill_id": s, "level": skill_level} for s in skills]},
    )
    assert response.status_code == 200, response.text

    assets = await taxonomy_ids(client, "assets", limit=2)
    response = await client.patch(
        "/api/v1/me/survey/assets", headers=auth(token), json={"asset_ids": assets}
    )
    assert response.status_code == 200, response.text

    interests = await taxonomy_ids(client, "interests", limit=3)
    response = await client.patch(
        "/api/v1/me/survey/interests",
        headers=auth(token),
        json={"interests": [{"interest_id": i, "level": 4} for i in interests]},
    )
    assert response.status_code == 200, response.text

    response = await client.patch(
        "/api/v1/me/survey/preferences",
        headers=auth(token),
        json={
            "work_style": work_style,
            "primary_goal": primary_goal,
            "weekly_hours": weekly_hours,
        },
    )
    assert response.status_code == 200, response.text


async def grant_role(session: Any, user_id: str | uuid.UUID, role: str) -> None:
    """اعطای نقش سراسری — برای ساختن استاد یا مدیر در تست.

    کش نقش هم باطل می‌شود؛ وگرنه تستی که همین الان نقش داده، تا ۶۰ ثانیه
    همان نتیجهٔ قبلی را می‌گیرد.
    """
    from silp.core.permissions import Role
    from silp.services import authz

    await authz.grant_role(session, user_id=uuid.UUID(str(user_id)), role=Role(role))
    await session.flush()
    await authz.invalidate_roles(uuid.UUID(str(user_id)))


async def invalidate(user_id: str | uuid.UUID) -> None:
    """ابطال دستی کش نقش — پس از تغییر عضویت در خود تست."""
    from silp.services import authz

    await authz.invalidate_roles(uuid.UUID(str(user_id)))


def project_payload(**overrides: Any) -> dict[str, Any]:
    """بدنهٔ کمینهٔ معتبر برای ساخت پروژه."""
    payload: dict[str, Any] = {
        "title_fa": "فروش و بازاریابی خرمای صابر",
        "summary": "تیم فروش دانشجویی برای توزیع خرمای مضافتی در کرمان.",
        "description": "شرح کامل پروژه با جزئیات کافی برای تصمیم دانشجو.",
        "kind": "D_PERSONAL",
        "expected_output": "گزارش فروش ماهانه",
        "difficulty": 2,
        "work_style": "TEAM",
        "team_size_min": 1,
        "team_size_max": 3,
        "time_commitment_hpw": 8,
        "tags": ["فروش", "بازاریابی"],
    }
    payload.update(overrides)
    return payload


def milestone_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "title_fa": "مرحلهٔ اول — تحقیق بازار",
        "description": "ده مصاحبهٔ مشتری با گزارش کوتاه.",
        "sort_order": 1,
        "points": 50,
        "is_required": True,
        "output_kind": "DOCUMENT",
        "checklist": ["ده مصاحبه", "گزارش یک‌صفحه‌ای"],
    }
    payload.update(overrides)
    return payload


__all__ = [
    "DEV_OTP",
    "auth",
    "complete_profile",
    "grant_role",
    "invalidate",
    "login",
    "me",
    "milestone_payload",
    "project_payload",
    "taxonomy_ids",
]
