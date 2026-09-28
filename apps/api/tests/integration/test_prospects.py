"""کد شخصی برای مشتریِ بی‌حساب — ADR-0034.

PostgreSQL واقعی لازم است: دنبالهٔ مشترک `person_code_seq`، ایندکس‌های یکتای شرطی
و `ON CONFLICT` در حافظه شبیه‌سازی نمی‌شوند.
"""

from __future__ import annotations

import re
import uuid
from typing import Any

import pytest
from sqlalchemy import func, select
from tests.integration.helpers import auth, grant_role, login, me

from silp.models.intake import IntakeRequest, Prospect

pytestmark = pytest.mark.integration

OWNER = "09121880001"
CLIENT = "09121880002"
OTHER = "09121880003"
SIGNS_UP_LATER = "09121880004"


def _intake(**overrides: Any) -> dict[str, Any]:
    return {
        "need_type": "Commercial",
        "services": ["Website / Web App"],
        "summary": "برای کسب‌وکارم به یک وب‌سایت فروش نیاز دارم.",
        "name": "رضا محمدی",
        "mobile": CLIENT,
        **overrides,
    }


def _collab(**overrides: Any) -> dict[str, Any]:
    return {
        "name": "رضا محمدی",
        "mobile": CLIENT,
        "intro": "می‌خواهم در تحلیل داده همکاری کنم.",
        "ways": ["Research"],
        **overrides,
    }


async def _post(client: Any, path: str, body: dict[str, Any]) -> dict[str, Any]:
    response = await client.post(f"/api/v1/public/{path}", json=body)
    assert response.status_code == 201, response.text
    return dict(response.json())


async def _prospects(session: Any, **where: Any) -> list[Prospect]:
    stmt = select(Prospect)
    for column, value in where.items():
        stmt = stmt.where(getattr(Prospect, column) == value)
    return list((await session.scalars(stmt)).all())


async def test_an_account_less_client_gets_a_personal_code(client, db_session) -> None:  # type: ignore[no-untyped-def]
    body = await _post(client, "intake", _intake())
    assert re.fullmatch(r"P-\d{5,}", body["person_code"])
    assert body["account_linked"] is False

    (prospect,) = await _prospects(db_session, mobile=CLIENT)
    assert prospect.person_code == body["person_code"]
    assert prospect.user_id is None
    stored = await db_session.scalar(
        select(IntakeRequest).where(IntakeRequest.tracking_code == body["tracking_code"])
    )
    assert stored is not None and stored.prospect_id == prospect.id and stored.user_id is None


async def test_the_same_contact_keeps_one_code_across_requests_and_kinds(
    client, db_session
) -> None:  # type: ignore[no-untyped-def]
    first = await _post(client, "intake", _intake())
    second = await _post(client, "intake", _intake(summary="نیاز دومِ من: گزارش هوشمند."))
    collab = await _post(client, "collaboration", _collab())
    assert first["person_code"] == second["person_code"] == collab["person_code"]
    assert len(await _prospects(db_session, mobile=CLIENT)) == 1

    other = await _post(client, "intake", _intake(mobile=OTHER))
    assert other["person_code"] != first["person_code"]


async def test_prospect_and_user_codes_never_collide(client, db_session) -> None:  # type: ignore[no-untyped-def]
    """هر دو از یک دنباله می‌آیند؛ پس فردِ بی‌حساب و فردِ دارای حساب هم‌کد نمی‌شوند."""
    prospect_code = (await _post(client, "intake", _intake()))["person_code"]
    user_code = (await me(client, await login(client, OTHER)))["person_code"]
    assert prospect_code != user_code


async def test_an_email_only_contact_gets_a_code_and_a_later_mobile_joins_it(
    client, db_session
) -> None:  # type: ignore[no-untyped-def]
    first = await _post(client, "collaboration", _collab(mobile=None, email="reza@example.com"))
    (prospect,) = await _prospects(db_session, email="reza@example.com")
    assert prospect.mobile is None

    # همان ایمیل با شمارهٔ تازه: همان شخص، کد یکسان، شماره ثبت می‌شود.
    again = await _post(client, "collaboration", _collab(mobile=CLIENT, email="reza@example.com"))
    assert again["person_code"] == first["person_code"]
    await db_session.refresh(prospect)
    assert prospect.email == "reza@example.com"


async def test_a_contact_held_by_someone_else_is_not_stolen(client, db_session) -> None:  # type: ignore[no-untyped-def]
    """ایمیلی که مال شخص دیگری است، به این شخص منتقل نمی‌شود (ایندکس یکتا)."""
    await _post(client, "collaboration", _collab(mobile=None, email="taken@example.com"))
    mine = await _post(client, "collaboration", _collab(mobile=CLIENT, email="taken@example.com"))
    # ایمیل با شخصِ پیشین یکی است، پس شخصِ پیشین برمی‌گردد؛ هیچ ردیف تکراری نمی‌سازد.
    assert len(await _prospects(db_session, email="taken@example.com")) == 1
    assert re.fullmatch(r"P-\d{5,}", mine["person_code"])


async def test_a_linked_account_gets_its_own_code_and_no_prospect(client, db_session) -> None:  # type: ignore[no-untyped-def]
    token = await login(client, OTHER)
    profile = await me(client, token)
    body = await _post(client, "intake", _intake(mobile=OTHER))
    assert body["person_code"] == profile["person_code"]
    assert body["account_linked"] is True
    assert await _prospects(db_session, mobile=OTHER) == []


async def test_verifying_the_number_claims_the_prospect_and_keeps_both_codes(
    client, db_session
) -> None:  # type: ignore[no-untyped-def]
    old = (await _post(client, "intake", _intake(mobile=SIGNS_UP_LATER)))["person_code"]

    token = await login(client, SIGNS_UP_LATER)  # ورود با OTP = مالکیت شماره
    profile = await me(client, token)
    assert profile["person_code"] != old  # کد خودِ کاربر عوض نمی‌شود، جایگزین هم نمی‌شود
    assert profile["person_code_aliases"] == [old]

    (prospect,) = await _prospects(db_session, mobile=SIGNS_UP_LATER)
    assert str(prospect.user_id) == profile["id"] and prospect.claimed_at is not None

    # درخواستِ بعدی به حساب وصل می‌شود، نه به شخصِ بی‌حساب؛ و کدِ دائمیِ خود کاربر برمی‌گردد.
    later = await _post(client, "intake", _intake(mobile=SIGNS_UP_LATER))
    assert later["account_linked"] is True and later["person_code"] == profile["person_code"]


async def test_typing_a_number_does_not_claim_it(client, db_session) -> None:  # type: ignore[no-untyped-def]
    """مالکیت فقط با OTP می‌آید؛ ورودِ کاربر دیگر شخصِ بی‌حسابِ این شماره را برنمی‌دارد."""
    await _post(client, "intake", _intake(mobile=CLIENT))
    stranger = await me(client, await login(client, OTHER))
    assert stranger["person_code_aliases"] == []
    (prospect,) = await _prospects(db_session, mobile=CLIENT)
    assert prospect.user_id is None


async def test_the_owner_inbox_shows_the_prospect_code(client, db_session) -> None:  # type: ignore[no-untyped-def]
    owner = await login(client, OWNER)
    await grant_role(db_session, uuid.UUID(str((await me(client, owner))["id"])), "ADMIN")
    body = await _post(client, "intake", _intake())
    row = await db_session.scalar(
        select(IntakeRequest).where(IntakeRequest.tracking_code == body["tracking_code"])
    )
    assert row is not None

    listing = (await client.get("/api/v1/admin/intake", headers=auth(owner))).json()
    item = next(i for i in listing["items"] if i["tracking_code"] == body["tracking_code"])
    assert item["person_code"] == body["person_code"]
    detail = (await client.get(f"/api/v1/admin/intake/{row.id}", headers=auth(owner))).json()
    assert detail["person_code"] == body["person_code"]


async def test_a_bot_decoy_stores_no_prospect(client, db_session) -> None:  # type: ignore[no-untyped-def]
    before = await db_session.scalar(select(func.count()).select_from(Prospect))
    response = await client.post(
        "/api/v1/public/intake", json=_intake(mobile="09121880009", website="http://spam")
    )
    assert response.status_code == 201
    assert response.json()["person_code"] is None
    assert await db_session.scalar(select(func.count()).select_from(Prospect)) == before
