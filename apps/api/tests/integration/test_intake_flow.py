"""طرح مسئله، همکاری با ما و کد شخصی — ADR-0030.

PostgreSQL واقعی لازم است: دنبالهٔ کد پیگیری، تابع `next_person_code()` و قیدهای
CHECK جدول `intake_requests` در حافظه شبیه‌سازی نمی‌شوند.
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import delete, select, text
from tests.integration.helpers import auth, login, me

from silp.models.identity import User
from silp.models.intake import IntakeRequest
from silp.vault.exporter import export_vault
from silp.vault.skeleton import init_vault

pytestmark = pytest.mark.integration

VERIFIED = "09121990001"


def _intake(**overrides: Any) -> dict[str, Any]:
    return {
        "need_type": "Commercial",
        "services": ["Website / Web App", "AI"],
        "summary": "برای کسب‌وکارم به یک وب‌سایت فروش و گزارش هوشمند نیاز دارم.",
        "sector": "کشاورزی",
        "has_data": "YES",
        "timeline": "۱ تا ۳ ماه",
        "budget": "هنوز نمی‌دانم",
        "name": "رضا محمدی",
        "mobile": "۰۹۱۲-۳۴۵-۶۷۸۹",
        "organization": "شرکت نمونه",
        **overrides,
    }


# ── کد شخصی ────────────────────────────────────────────────────────────
async def test_every_user_gets_a_permanent_unique_person_code(client, db_session) -> None:  # type: ignore[no-untyped-def]
    token = await login(client, VERIFIED)
    profile = await me(client, token)
    assert re.fullmatch(r"P-\d{5,}", profile["person_code"])

    again = await me(client, token)
    assert again["person_code"] == profile["person_code"]

    other = await me(client, await login(client, "09121990002"))
    assert other["person_code"] != profile["person_code"]


async def test_person_code_survives_a_role_change(client, db_session) -> None:  # type: ignore[no-untyped-def]
    from tests.integration.helpers import grant_role

    token = await login(client, VERIFIED)
    before = (await me(client, token))["person_code"]
    await grant_role(db_session, (await me(client, token))["id"], "COORDINATOR")
    assert (await me(client, token))["person_code"] == before


async def test_next_person_code_is_not_truncated_past_five_digits(db_session) -> None:  # type: ignore[no-untyped-def]
    """`lpad` رقم اضافه را می‌برد و کد تکراری می‌ساخت؛ تابع باید سالم بماند."""
    await db_session.execute(text("SELECT setval('person_code_seq', 99999, true)"))
    codes = [await db_session.scalar(text("SELECT next_person_code()")) for _ in range(3)]
    assert codes == ["P-100000", "P-100001", "P-100002"]


# ── طرح مسئله ──────────────────────────────────────────────────────────
async def test_anonymous_visitor_can_submit_a_problem(client, db_session) -> None:  # type: ignore[no-untyped-def]
    response = await client.post("/api/v1/public/intake", json=_intake())
    assert response.status_code == 201, response.text
    body = response.json()
    assert re.fullmatch(r"Q-\d+", body["tracking_code"])
    assert re.fullmatch(r"P-\d{5,}", body["person_code"])  # کد شخصِ بی‌حساب — ADR-0034
    assert body["account_linked"] is False
    assert body["tracking_code"] in body["message"]
    assert response.headers["cache-control"] == "no-store"

    stored = await db_session.scalar(
        select(IntakeRequest).where(IntakeRequest.tracking_code == body["tracking_code"])
    )
    assert stored is not None
    assert stored.kind == "INTAKE" and stored.status == "NEW"
    assert stored.contact_mobile == "09123456789"  # ارقام فارسی و جداکننده نرمال شد
    assert stored.services == ["Website / Web App", "AI"]
    assert stored.payload["has_data"] == "YES"
    assert stored.user_id is None


async def test_tracking_codes_are_sequential_and_distinct(client, db_session) -> None:  # type: ignore[no-untyped-def]
    first = (await client.post("/api/v1/public/intake", json=_intake(mobile="09120001111"))).json()
    second = (await client.post("/api/v1/public/intake", json=_intake(mobile="09120002222"))).json()
    assert int(second["tracking_code"][2:]) == int(first["tracking_code"][2:]) + 1


async def test_a_verified_contact_is_linked_to_the_existing_person(client, db_session) -> None:  # type: ignore[no-untyped-def]
    token = await login(client, VERIFIED)  # ورود با OTP، شماره را تأییدشده می‌کند
    profile = await me(client, token)

    response = await client.post("/api/v1/public/intake", json=_intake(mobile=VERIFIED))
    assert response.status_code == 201, response.text
    assert response.json()["person_code"] == profile["person_code"]

    stored = await db_session.scalar(
        select(IntakeRequest).where(IntakeRequest.tracking_code == response.json()["tracking_code"])
    )
    assert stored is not None and str(stored.user_id) == profile["id"]
    _ = auth(token)


async def test_an_unverified_number_is_never_linked(client, db_session) -> None:  # type: ignore[no-untyped-def]
    """هر کسی می‌تواند شمارهٔ دیگری را تایپ کند؛ فقط تأییدشده وصل می‌شود."""
    token = await login(client, VERIFIED)
    user_id = uuid.UUID((await me(client, token))["id"])
    await db_session.execute(
        text("UPDATE users SET mobile_verified_at = NULL WHERE id = :id"), {"id": user_id}
    )

    response = await client.post("/api/v1/public/intake", json=_intake(mobile=VERIFIED))
    assert response.status_code == 201
    assert response.json()["account_linked"] is False
    assert response.json()["person_code"] != (await me(client, token))["person_code"]


@pytest.mark.parametrize(
    ("overrides", "fragment"),
    [
        ({"mobile": None, "email": None}, "__root__"),
        ({"mobile": "12345"}, "mobile"),
        ({"mobile": None, "email": "not-an-email"}, "email"),
        ({"need_type": "Nonsense"}, "need_type"),
        ({"services": ["Magic"]}, "services"),
        ({"summary": "کم"}, "summary"),
        ({"name": "ر"}, "name"),
    ],
)
async def test_invalid_submissions_are_rejected(
    client, overrides: dict[str, Any], fragment: str
) -> None:  # type: ignore[no-untyped-def]
    response = await client.post("/api/v1/public/intake", json=_intake(**overrides))
    assert response.status_code == 422, response.text
    assert fragment in response.text


async def test_the_hidden_honeypot_field_stores_nothing(client, db_session) -> None:  # type: ignore[no-untyped-def]
    before = len(list(await db_session.scalars(select(IntakeRequest.id))))
    response = await client.post(
        "/api/v1/public/intake", json=_intake(website="http://spam.example", mobile="09125550000")
    )
    assert response.status_code == 201  # ربات نباید بفهمد گیر افتاده
    assert len(list(await db_session.scalars(select(IntakeRequest.id)))) == before


async def test_the_same_contact_is_rate_limited(client, db_session) -> None:  # type: ignore[no-untyped-def]
    for _ in range(3):
        ok = await client.post("/api/v1/public/intake", json=_intake(mobile="09127770000"))
        assert ok.status_code == 201, ok.text
    blocked = await client.post("/api/v1/public/intake", json=_intake(mobile="09127770000"))
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "RATE_LIMITED"
    assert "retry-after" in blocked.headers


# ── همکاری ─────────────────────────────────────────────────────────────
def _collab(**overrides: Any) -> dict[str, Any]:
    return {
        "name": "نیما رحیمی",
        "email": "Nima@Example.org",
        "intro": "تحلیلگر داده‌ام و به همکاری در پروژه‌های حمل‌ونقل علاقه دارم.",
        "specialty": "تحلیل داده حمل‌ونقل",
        "skills": "Python، R، GIS",
        "ways": ["Data Science", "پژوهش مشترک"],
        "hours_per_week": "5_10",
        "portfolio_url": "https://example.org/nima",
        **overrides,
    }


async def test_collaboration_request_is_stored_with_its_own_prefix(client, db_session) -> None:  # type: ignore[no-untyped-def]
    response = await client.post("/api/v1/public/collaboration", json=_collab())
    assert response.status_code == 201, response.text
    code = response.json()["tracking_code"]
    assert code.startswith("C-")

    stored = await db_session.scalar(
        select(IntakeRequest).where(IntakeRequest.tracking_code == code)
    )
    assert stored is not None and stored.kind == "COLLABORATION"
    assert stored.contact_email == "nima@example.org"  # کوچک‌سازی
    assert stored.payload["ways"] == ["Data Science", "پژوهش مشترک"]
    assert stored.need_type == "Collaboration"


async def test_collaboration_portfolio_must_be_https(client) -> None:  # type: ignore[no-untyped-def]
    response = await client.post(
        "/api/v1/public/collaboration", json=_collab(portfolio_url="http://insecure.example")
    )
    assert response.status_code == 422
    assert "portfolio_url" in response.text


# ── آینهٔ Inbox ────────────────────────────────────────────────────────
async def test_export_mirrors_the_inbox_with_person_code(
    client, db_session, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    init_vault(tmp_path)
    token = await login(client, VERIFIED)
    profile = await me(client, token)
    await client.post("/api/v1/public/intake", json=_intake(mobile=VERIFIED))
    await client.post("/api/v1/public/collaboration", json=_collab())

    await export_vault(db_session, tmp_path, only=("inbox", "students"))
    notes = {p.name: p.read_text(encoding="utf-8") for p in (tmp_path / "00_Inbox").glob("*.md")}
    assert len(notes) == 2
    linked = next(text for text in notes.values() if "type: intake" in text)
    assert f"person_code: {profile['person_code']}" in linked
    assert "generated: true" in linked
    assert "وب‌سایت فروش" in linked

    students = "\n".join(
        p.read_text(encoding="utf-8") for p in (tmp_path / "02_Students").glob("*.md")
    )
    assert f"person_code: {profile['person_code']}" in students


# ── پایداری: ثبت واقعاً commit می‌شود ───────────────────────────────────
async def test_submission_survives_the_request(committing_client, committing_session) -> None:  # type: ignore[no-untyped-def]
    from silp.db.session import get_session_factory

    response = await committing_client.post(
        "/api/v1/public/intake", json=_intake(mobile="09128880000")
    )
    assert response.status_code == 201, response.text
    code = response.json()["tracking_code"]
    try:
        async with get_session_factory()() as verifier:  # اتصال جدا: فقط دادهٔ commit‌شده
            stored = await verifier.scalar(
                select(IntakeRequest).where(IntakeRequest.tracking_code == code)
            )
            assert stored is not None, "ثبت commit نشده است — سرویس فقط flush کرده"
    finally:
        await committing_session.execute(
            delete(IntakeRequest).where(IntakeRequest.tracking_code == code)
        )
        await committing_session.commit()


async def test_user_delete_keeps_the_request(committing_session) -> None:  # type: ignore[no-untyped-def]
    """`ON DELETE SET NULL`: حذف حساب درخواست ثبت‌شده را پاک نمی‌کند."""
    user = User(mobile="09129990000", email=None)
    committing_session.add(user)
    await committing_session.flush()
    request = IntakeRequest(
        kind="INTAKE",
        tracking_code=f"Q-T{uuid.uuid4().hex[:8]}",
        user_id=user.id,
        contact_name="آزمایشی",
        contact_mobile="09129990000",
        summary="خلاصهٔ آزمایشی طولانی‌تر از پنج نویسه",
    )
    committing_session.add(request)
    await committing_session.commit()
    try:
        await committing_session.execute(delete(User).where(User.id == user.id))
        await committing_session.commit()
        await committing_session.refresh(request)
        assert request.user_id is None
    finally:
        await committing_session.execute(
            delete(IntakeRequest).where(IntakeRequest.id == request.id)
        )
        await committing_session.commit()
