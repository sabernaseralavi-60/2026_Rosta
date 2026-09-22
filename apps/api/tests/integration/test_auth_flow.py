"""تست یکپارچهٔ احراز هویت — FR-AUTH-01/03، §7.1.

این تست‌ها PostgreSQL واقعی می‌خواهند (D-14). بدون آن `skip` می‌شوند،
نه `fail` — تا بتوان بدون داکر روی منطق خالص کار کرد.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration

MOBILE = "09121234567"
OTHER_MOBILE = "09129876543"


async def request_code(client, destination: str = MOBILE) -> str:  # type: ignore[no-untyped-def]
    response = await client.post(
        "/api/v1/auth/otp/request",
        json={"destination": destination, "channel": "SMS", "purpose": "LOGIN"},
    )
    assert response.status_code == 200, response.text
    return response.json()["challenge_id"]


async def login(client, destination: str = MOBILE) -> dict:  # type: ignore[no-untyped-def]
    challenge_id = await request_code(client, destination)
    response = await client.post(
        "/api/v1/auth/otp/verify",
        json={"challenge_id": challenge_id, "code": "111111"},
    )
    assert response.status_code == 200, response.text
    return response.json()


# ── درخواست کد ─────────────────────────────────────────────────────────
async def test_otp_request_masks_destination(client) -> None:  # type: ignore[no-untyped-def]
    """NFR-01 — پاسخ نباید شمارهٔ کامل را برگرداند."""
    response = await client.post(
        "/api/v1/auth/otp/request",
        json={"destination": MOBILE, "channel": "SMS"},
    )
    body = response.json()
    assert response.status_code == 200
    assert body["masked_destination"] == "0912***4567"
    assert MOBILE not in response.text
    assert body["expires_in"] == 120
    assert body["resend_after"] == 60


@pytest.mark.parametrize("bad", ["0812345678", "not-a-number", "0912123456"])
async def test_invalid_destination_is_rejected(client, bad: str) -> None:  # type: ignore[no-untyped-def]
    response = await client.post(
        "/api/v1/auth/otp/request", json={"destination": bad, "channel": "SMS"}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_DESTINATION"


async def test_any_mobile_format_reaches_the_same_account(client) -> None:  # type: ignore[no-untyped-def]
    """«+989121234567» و «09121234567» باید یک حساب باشند."""
    first = await login(client, "09121234567")
    second = await login(client, "+989121234567")
    assert first["user"]["id"] == second["user"]["id"]


# ── تأیید کد — FR-AUTH-01 ──────────────────────────────────────────────
async def test_verify_creates_user_with_student_role(client) -> None:  # type: ignore[no-untyped-def]
    body = await login(client)
    assert body["user"]["roles"] == ["STUDENT"]
    assert body["token_type"] == "Bearer"
    assert body["expires_in"] == 900
    assert body["access_token"]
    assert body["refresh_token"]


async def test_new_user_starts_at_basic_info_required(client) -> None:  # type: ignore[no-untyped-def]
    """§7.1 — کاربر بدون نیمرخ به /onboarding/basic هدایت می‌شود."""
    body = await login(client)
    assert body["user"]["onboarding_state"] == "BASIC_INFO_REQUIRED"


async def test_second_login_does_not_create_a_second_user(client) -> None:  # type: ignore[no-untyped-def]
    first = await login(client)
    second = await login(client)
    assert first["user"]["id"] == second["user"]["id"]


async def test_wrong_code_is_rejected(client) -> None:  # type: ignore[no-untyped-def]
    challenge_id = await request_code(client)
    response = await client.post(
        "/api/v1/auth/otp/verify",
        json={"challenge_id": challenge_id, "code": "000000"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "OTP_INVALID"


async def test_three_wrong_codes_burn_the_challenge(client) -> None:  # type: ignore[no-untyped-def]
    """FR-AUTH-01 — سه بار اشتباه ⇒ چالش باطل و کد جدید لازم است."""
    challenge_id = await request_code(client)

    for _ in range(3):
        await client.post(
            "/api/v1/auth/otp/verify",
            json={"challenge_id": challenge_id, "code": "000000"},
        )

    # حتی کد درست هم دیگر کار نمی‌کند.
    response = await client.post(
        "/api/v1/auth/otp/verify",
        json={"challenge_id": challenge_id, "code": "111111"},
    )
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "OTP_TOO_MANY_ATTEMPTS"


async def test_challenge_cannot_be_reused(client) -> None:  # type: ignore[no-untyped-def]
    """یک کد، یک ورود. کد مصرف‌شده دوباره کار نمی‌کند."""
    challenge_id = await request_code(client)
    payload = {"challenge_id": challenge_id, "code": "111111"}

    assert (await client.post("/api/v1/auth/otp/verify", json=payload)).status_code == 200
    replay = await client.post("/api/v1/auth/otp/verify", json=payload)
    assert replay.status_code == 400
    assert replay.json()["error"]["code"] == "OTP_INVALID"


async def test_unknown_challenge_id_looks_like_a_wrong_code(client) -> None:  # type: ignore[no-untyped-def]
    """شناسهٔ ناموجود نباید از کد غلط قابل تفکیک باشد."""
    response = await client.post(
        "/api/v1/auth/otp/verify",
        json={"challenge_id": "018f0000-0000-7000-8000-000000000000", "code": "111111"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "OTP_INVALID"


async def test_requesting_a_new_code_invalidates_the_previous_one(client) -> None:  # type: ignore[no-untyped-def]
    """کد قدیمی نباید تا انقضا زنده بماند و پنجرهٔ حمله را باز نگه دارد."""
    old_challenge = await request_code(client)
    await request_code(client)

    response = await client.post(
        "/api/v1/auth/otp/verify",
        json={"challenge_id": old_challenge, "code": "111111"},
    )
    assert response.status_code == 400


# ── چرخش توکن — FR-AUTH-03 ─────────────────────────────────────────────
async def test_refresh_returns_a_new_pair(client) -> None:  # type: ignore[no-untyped-def]
    body = await login(client)
    response = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": body["refresh_token"]}
    )
    assert response.status_code == 200

    rotated = response.json()
    assert rotated["refresh_token"] != body["refresh_token"]
    assert rotated["access_token"] != body["access_token"]


async def test_old_refresh_token_stops_working_immediately(client) -> None:  # type: ignore[no-untyped-def]
    """چرخش اجباری: توکن قبلی بلافاصله باطل می‌شود."""
    body = await login(client)
    old = body["refresh_token"]

    await client.post("/api/v1/auth/refresh", json={"refresh_token": old})
    replay = await client.post("/api/v1/auth/refresh", json={"refresh_token": old})

    assert replay.status_code == 401
    assert replay.json()["error"]["code"] == "TOKEN_REUSE_DETECTED"


async def test_token_reuse_burns_the_whole_family(client) -> None:  # type: ignore[no-untyped-def]
    """FR-AUTH-03 — استفادهٔ دوباره ⇒ کل خانواده باطل، ورود مجدد لازم."""
    body = await login(client)
    first = body["refresh_token"]

    second = (await client.post("/api/v1/auth/refresh", json={"refresh_token": first})).json()[
        "refresh_token"
    ]

    # مهاجم از توکن دزدیده‌شدهٔ قدیمی استفاده می‌کند.
    await client.post("/api/v1/auth/refresh", json={"refresh_token": first})

    # قربانی هم باید بیرون انداخته شده باشد.
    victim = await client.post("/api/v1/auth/refresh", json={"refresh_token": second})
    assert victim.status_code == 401
    assert victim.json()["error"]["code"] == "TOKEN_REUSE_DETECTED"


async def test_garbage_refresh_token_is_rejected(client) -> None:  # type: ignore[no-untyped-def]
    response = await client.post("/api/v1/auth/refresh", json={"refresh_token": "x" * 44})
    assert response.status_code == 401


# ── خروج و نشست‌ها ─────────────────────────────────────────────────────
async def test_logout_revokes_the_refresh_token(client) -> None:  # type: ignore[no-untyped-def]
    body = await login(client)
    token = body["refresh_token"]

    assert (
        await client.post("/api/v1/auth/logout", json={"refresh_token": token})
    ).status_code == 204

    after = await client.post("/api/v1/auth/refresh", json={"refresh_token": token})
    assert after.status_code == 401


async def test_logout_is_idempotent(client) -> None:  # type: ignore[no-untyped-def]
    body = await login(client)
    payload = {"refresh_token": body["refresh_token"]}
    assert (await client.post("/api/v1/auth/logout", json=payload)).status_code == 204
    assert (await client.post("/api/v1/auth/logout", json=payload)).status_code == 204


async def test_sessions_list_marks_the_current_one(client) -> None:  # type: ignore[no-untyped-def]
    body = await login(client)
    headers = {"Authorization": f"Bearer {body['access_token']}"}

    response = await client.get("/api/v1/auth/sessions", headers=headers)
    assert response.status_code == 200

    sessions = response.json()
    assert len(sessions) >= 1
    assert sum(1 for s in sessions if s["is_current"]) == 1


async def test_user_cannot_revoke_another_users_session(client) -> None:  # type: ignore[no-untyped-def]
    """§6.4 قاعدهٔ ۴ — ۴۰۴، نه ۴۰۳: وجود نشست دیگری نباید افشا شود."""
    victim = await login(client, MOBILE)
    attacker = await login(client, OTHER_MOBILE)

    victim_session = (
        await client.get(
            "/api/v1/auth/sessions",
            headers={"Authorization": f"Bearer {victim['access_token']}"},
        )
    ).json()[0]["id"]

    response = await client.delete(
        f"/api/v1/auth/sessions/{victim_session}",
        headers={"Authorization": f"Bearer {attacker['access_token']}"},
    )
    assert response.status_code == 404


# ── /me ────────────────────────────────────────────────────────────────
async def test_me_requires_authentication(client) -> None:  # type: ignore[no-untyped-def]
    response = await client.get("/api/v1/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"


async def test_me_masks_contact_details(client) -> None:  # type: ignore[no-untyped-def]
    body = await login(client)
    response = await client.get(
        "/api/v1/me", headers={"Authorization": f"Bearer {body['access_token']}"}
    )
    assert response.status_code == 200

    me = response.json()
    assert me["mobile"] == "0912***4567"
    assert MOBILE not in response.text
    assert me["mobile_verified"] is True
    assert me["onboarding"]["state"] == "BASIC_INFO_REQUIRED"
    assert me["onboarding"]["next_route"] == "/onboarding/basic"
    assert [r["code"] for r in me["roles"]] == ["STUDENT"]


async def test_malformed_token_is_rejected(client) -> None:  # type: ignore[no-untyped-def]
    response = await client.get("/api/v1/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "TOKEN_INVALID"


# ── قالب خطا و ردیابی — §5.1، NFR-12 ───────────────────────────────────
async def test_every_error_carries_a_trace_id(client) -> None:  # type: ignore[no-untyped-def]
    response = await client.get("/api/v1/me")
    error = response.json()["error"]
    assert error["trace_id"]
    assert error["trace_id"] == response.headers["X-Trace-Id"]
    assert set(error) == {"code", "message", "details", "trace_id"}


async def test_error_message_is_persian(client) -> None:  # type: ignore[no-untyped-def]
    """پیام باید مستقیماً قابل نمایش به کاربر باشد، بدون اصطلاح فنی."""
    response = await client.get("/api/v1/me")
    message = response.json()["error"]["message"]
    assert any("؀" <= ch <= "ۿ" for ch in message)


async def test_validation_error_names_the_field(client) -> None:  # type: ignore[no-untyped-def]
    response = await client.post("/api/v1/auth/otp/request", json={})
    assert response.status_code == 422

    error = response.json()["error"]
    assert error["code"] == "VALIDATION_FAILED"
    assert "destination" in error["details"]["fields"]
