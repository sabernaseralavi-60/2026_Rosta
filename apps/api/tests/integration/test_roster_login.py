"""ورود دانشجوی درس با موبایل + شمارهٔ دانشجویی — ADR-0035.

PostgreSQL واقعی لازم است: HMAC ذخیره‌شده، قیدهای یکتا، `SELECT … FOR UPDATE` روی ادعا و
ثبت‌نام در درس در حافظه شبیه‌سازی نمی‌شوند.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select, text
from tests.integration.helpers import auth, login

from silp.core.config import get_settings
from silp.domain.identity import roster as rules
from silp.models.education import Course, CourseOffering, Enrollment, Term
from silp.models.identity import User
from silp.models.roster import RosterEntry

pytestmark = pytest.mark.integration

MOBILE = "09121990101"
NUMBER = "402123456"
EMAIL = "ali.rezaei@eng.example.ac.ir"
PASSWORD = "Kerman-1405-safe"
CODE = "111111"  # DEV_FIXED_OTP


async def _offering(session: Any, title: str = "مهندسی ترابری") -> uuid.UUID:
    marker = uuid.uuid4().hex[:8]
    owner = User(mobile=f"09{secrets.randbelow(10**9):09d}")
    session.add(owner)
    term = Term(
        code=f"T-{marker}",
        title_fa="نیم‌سال آزمایشی",
        starts_on=date(2026, 9, 23),
        ends_on=date(2027, 2, 4),
    )
    course = Course(code=f"C-{marker}", slug=f"course-{marker}", title_fa=title)
    session.add_all([term, course])
    await session.flush()
    offering = CourseOffering(
        course_id=course.id, term_id=term.id, instructor_id=owner.id, status="OPEN"
    )
    session.add(offering)
    await session.flush()
    return offering.id


async def _entry(
    session: Any,
    offering_id: uuid.UUID,
    *,
    number: str = NUMBER,
    email: str | None = EMAIL,
    first: str = "علی",
    last: str = "رضایی",
) -> RosterEntry:
    entry = RosterEntry(
        offering_id=offering_id,
        first_name=first,
        last_name=last,
        student_no_hash=rules.digest(number, get_settings().secret_key),
        email=email,
    )
    session.add(entry)
    await session.flush()
    return entry


async def _lookup(client: Any, *, mobile: str = MOBILE, number: str = NUMBER) -> Any:
    return await client.post(
        "/api/v1/public/roster/lookup", json={"mobile": mobile, "student_no": number}
    )


async def _confirm(client: Any, claim_id: str, accept: bool = True) -> Any:
    return await client.post(
        "/api/v1/public/roster/confirm", json={"claim_id": claim_id, "accept": accept}
    )


async def _complete(
    client: Any, claim_id: str, *, code: str = CODE, password: str = PASSWORD
) -> Any:
    return await client.post(
        "/api/v1/public/roster/complete",
        json={"claim_id": claim_id, "code": code, "password": password},
    )


async def _to_code_step(client: Any, **lookup: Any) -> str:
    found = await _lookup(client, **lookup)
    assert found.status_code == 200, found.text
    claim_id = str(found.json()["claim_id"])
    confirmed = await _confirm(client, claim_id)
    assert confirmed.status_code == 200, confirmed.text
    return claim_id


# ── مسیر اصلی ──────────────────────────────────────────────────────────
async def test_full_flow_creates_the_account_and_enrols_the_student(  # type: ignore[no-untyped-def]
    client, db_session, channels
) -> None:
    offering_id = await _offering(db_session)
    entry = await _entry(db_session, offering_id)

    found = await _lookup(client, number="۴۰۲۱۲۳۴۵۶")  # ارقام فارسی هم پذیرفته است
    assert found.status_code == 200, found.text
    body = found.json()
    assert body["display_name"] == "علی ر."  # نام کامل پیش از تأیید نشان داده نمی‌شود
    assert body["has_email"] is True
    assert "رضایی" not in found.text

    confirmed = await _confirm(client, body["claim_id"])
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["masked_email"] != EMAIL
    (mail,) = channels["EMAIL"].sent
    assert mail.recipient == EMAIL and CODE in mail.body

    done = await _complete(client, body["claim_id"])
    assert done.status_code == 200, done.text
    result = done.json()
    assert result["is_new_user"] is True and result["courses"] == ["مهندسی ترابری"]
    assert result["user"]["onboarding_state"] == "SURVEY_REQUIRED"  # پرسشنامه همین‌جا می‌آید
    assert "STUDENT" in result["user"]["roles"]

    user = await db_session.scalar(select(User).where(User.mobile == MOBILE))
    assert user is not None and user.email == EMAIL and user.email_verified_at is not None
    assert user.mobile_verified_at is None  # موبایل با OTP تأیید نشده، ادعا هم نمی‌شود
    enrollment = await db_session.scalar(
        select(Enrollment).where(
            Enrollment.offering_id == offering_id, Enrollment.student_id == user.id
        )
    )
    assert enrollment is not None and enrollment.status == "ACTIVE"
    await db_session.refresh(entry)
    assert entry.user_id == user.id and entry.claimed_at is not None

    # از این پس با موبایل + رمز خودش وارد می‌شود.
    relogin = await client.post(
        "/api/v1/auth/login", json={"identifier": MOBILE, "password": PASSWORD}
    )
    assert relogin.status_code == 200, relogin.text


async def test_one_claim_enrols_the_student_in_every_course_of_the_roster(  # type: ignore[no-untyped-def]
    client, db_session, channels
) -> None:
    first = await _offering(db_session, "مهندسی ترابری")
    second = await _offering(db_session, "تحلیل و مدل سازی ایمنی راه")
    await _entry(db_session, first)
    await _entry(db_session, second, email=None)  # ایمیل از ردیف دیگر گرفته می‌شود

    claim = await _to_code_step(client)
    done = (await _complete(client, claim)).json()
    assert sorted(done["courses"]) == ["تحلیل و مدل سازی ایمنی راه", "مهندسی ترابری"]
    user = await db_session.scalar(select(User).where(User.mobile == MOBILE))
    assert user is not None
    active = await db_session.scalars(
        select(Enrollment.offering_id).where(
            Enrollment.student_id == user.id, Enrollment.status == "ACTIVE"
        )
    )
    assert set(active) == {first, second}


# ── شمارهٔ دانشجویی رمز نیست ───────────────────────────────────────────
async def test_the_student_number_alone_gives_nothing(client, db_session, channels) -> None:  # type: ignore[no-untyped-def]
    offering_id = await _offering(db_session)
    await _entry(db_session, offering_id)
    claim = str((await _lookup(client)).json()["claim_id"])

    # بدون تأیید و کد ایمیلی: نه حساب، نه توکن.
    denied = await _complete(client, claim)
    assert denied.status_code == 409 and denied.json()["error"]["code"] == "ROSTER_CLAIM_CLOSED"
    assert await db_session.scalar(select(User).where(User.mobile == MOBILE)) is None
    assert channels["EMAIL"].sent == []


async def test_the_student_number_or_mobile_is_refused_as_a_password(  # type: ignore[no-untyped-def]
    client, db_session, channels
) -> None:
    offering_id = await _offering(db_session)
    await _entry(db_session, offering_id)
    claim = await _to_code_step(client)

    for weak in (NUMBER, "۴۰۲۱۲۳۴۵۶", MOBILE, "short1"):
        response = await _complete(client, claim, password=weak)
        assert response.status_code == 422, (weak, response.text)
        assert response.json()["error"]["code"] == "WEAK_PASSWORD"

    # رمز ضعیف کد را نسوزاند: با رمز درست همان کد کار می‌کند.
    assert (await _complete(client, claim)).status_code == 200


async def test_the_raw_student_number_is_never_stored(client, db_session, channels) -> None:  # type: ignore[no-untyped-def]
    offering_id = await _offering(db_session)
    await _entry(db_session, offering_id)
    claim = await _to_code_step(client)
    await _complete(client, claim)

    for table in ("roster_entries", "roster_claims", "profiles", "users"):
        query = f"SELECT string_agg(t::text, ' ') FROM {table} t"  # noqa: S608
        dump = await db_session.scalar(text(query))
        assert NUMBER not in (dump or ""), table


# ── هویت: کد فقط به ایمیلِ ثبت‌شدهٔ فهرست ─────────────────────────────
async def test_the_code_goes_only_to_the_email_on_the_roster(client, db_session, channels) -> None:  # type: ignore[no-untyped-def]
    offering_id = await _offering(db_session)
    await _entry(db_session, offering_id)
    found = await client.post(
        "/api/v1/public/roster/lookup",
        json={"mobile": MOBILE, "student_no": NUMBER, "email": "attacker@example.com"},
    )
    await _confirm(client, found.json()["claim_id"])
    assert [m.recipient for m in channels["EMAIL"].sent] == [EMAIL]


async def test_a_wrong_code_five_times_kills_the_claim(client, db_session, channels) -> None:  # type: ignore[no-untyped-def]
    offering_id = await _offering(db_session)
    await _entry(db_session, offering_id)
    claim = await _to_code_step(client)

    for _ in range(4):
        wrong = await _complete(client, claim, code="000000")
        assert wrong.json()["error"]["code"] == "OTP_INVALID"
    last = await _complete(client, claim, code="000000")
    assert last.status_code == 429

    # بعد از این، حتی کد درست هم پذیرفته نمی‌شود.
    assert (await _complete(client, claim)).status_code == 409
    assert await db_session.scalar(select(User).where(User.mobile == MOBILE)) is None


async def test_an_expired_code_is_refused(client, db_session, channels) -> None:  # type: ignore[no-untyped-def]
    offering_id = await _offering(db_session)
    await _entry(db_session, offering_id)
    claim = await _to_code_step(client)
    await db_session.execute(
        text("UPDATE roster_claims SET code_expires_at = :t WHERE id = :id"),
        {"t": datetime.now(UTC) - timedelta(seconds=1), "id": uuid.UUID(claim)},
    )
    response = await _complete(client, claim)
    assert response.status_code == 400 and response.json()["error"]["code"] == "OTP_EXPIRED"


async def test_an_old_claim_is_closed(client, db_session, channels) -> None:  # type: ignore[no-untyped-def]
    offering_id = await _offering(db_session)
    await _entry(db_session, offering_id)
    claim_id = (await _lookup(client)).json()["claim_id"]
    await db_session.execute(
        text("UPDATE roster_claims SET expires_at = :t WHERE id = :id"),
        {"t": datetime.now(UTC) - timedelta(minutes=1), "id": uuid.UUID(claim_id)},
    )
    assert (await _confirm(client, claim_id)).status_code == 409


async def test_resending_the_code_is_throttled(client, db_session, channels) -> None:  # type: ignore[no-untyped-def]
    offering_id = await _offering(db_session)
    await _entry(db_session, offering_id)
    claim = await _to_code_step(client)
    again = await _confirm(client, claim)
    assert again.status_code == 429 and "Retry-After" in again.headers
    assert len(channels["EMAIL"].sent) == 1


async def test_declining_cancels_the_claim(client, db_session, channels) -> None:  # type: ignore[no-untyped-def]
    offering_id = await _offering(db_session)
    await _entry(db_session, offering_id)
    claim_id = (await _lookup(client)).json()["claim_id"]
    declined = await _confirm(client, claim_id, accept=False)
    assert declined.json()["cancelled"] is True
    assert (await _confirm(client, claim_id)).status_code == 409
    assert channels["EMAIL"].sent == []


async def test_a_student_without_an_email_is_sent_to_the_instructor(  # type: ignore[no-untyped-def]
    client, db_session, channels
) -> None:
    offering_id = await _offering(db_session)
    await _entry(db_session, offering_id, email=None)
    found = await _lookup(client)
    assert found.json()["has_email"] is False
    blocked = await _confirm(client, found.json()["claim_id"])
    assert blocked.status_code == 409 and blocked.json()["error"]["code"] == "ROSTER_NO_EMAIL"
    assert channels["EMAIL"].sent == []


# ── نبود در فهرست و سهمیه ───────────────────────────────────────────────
async def test_unknown_and_malformed_numbers_look_identical(client, db_session) -> None:  # type: ignore[no-untyped-def]
    unknown = await _lookup(client, number="999999999")
    malformed = await _lookup(client, number="abc")
    bad_mobile = await _lookup(client, mobile="12345")
    for response in (unknown, malformed, bad_mobile):
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "ROSTER_NOT_FOUND"
    assert unknown.json()["error"]["message"] == malformed.json()["error"]["message"]


async def test_guessing_one_number_from_many_mobiles_is_capped(client, db_session) -> None:  # type: ignore[no-untyped-def]
    offering_id = await _offering(db_session)
    await _entry(db_session, offering_id)
    statuses = [(await _lookup(client, mobile=f"091219902{i:02d}")).status_code for i in range(12)]
    assert statuses[:10] == [200] * 10
    assert statuses[10:] == [429, 429]


# ── تعارض با حساب‌های موجود ─────────────────────────────────────────────
async def test_a_mobile_with_someone_elses_account_is_refused(  # type: ignore[no-untyped-def]
    client, db_session, channels
) -> None:
    offering_id = await _offering(db_session)
    await _entry(db_session, offering_id)
    await login(client, MOBILE)  # این موبایل قبلاً با OTP حساب دارد و به ردیف وصل نیست

    found = await _lookup(client)
    response = await _confirm(client, found.json()["claim_id"])
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ROSTER_ACCOUNT_CONFLICT"
    assert channels["EMAIL"].sent == []


async def test_an_email_owned_by_another_account_is_refused(client, db_session, channels) -> None:  # type: ignore[no-untyped-def]
    offering_id = await _offering(db_session)
    await _entry(db_session, offering_id)
    db_session.add(User(mobile="09121990199", email=EMAIL))
    await db_session.flush()

    found = await _lookup(client)
    response = await _confirm(client, found.json()["claim_id"])
    assert response.json()["error"]["code"] == "ROSTER_ACCOUNT_CONFLICT"


# ── دانشجوی برگشتی ──────────────────────────────────────────────────────
async def test_a_returning_student_gets_new_courses_and_a_new_password(  # type: ignore[no-untyped-def]
    client, db_session, channels
) -> None:
    first = await _offering(db_session, "مهندسی ترابری")
    await _entry(db_session, first)
    claim = await _to_code_step(client)
    original = (await _complete(client, claim)).json()["user"]["id"]

    # ترم بعد استاد درس دومی را به فهرست می‌افزاید.
    second = await _offering(db_session, "تحلیل و مدل سازی ایمنی راه")
    await _entry(db_session, second)
    channels["EMAIL"].reset()

    claim = await _to_code_step(client)
    again = await _complete(client, claim, password="Another-Pass-2026")
    assert again.status_code == 200, again.text
    body = again.json()
    assert body["is_new_user"] is False and body["user"]["id"] == original
    assert "تحلیل و مدل سازی ایمنی راه" in body["courses"]

    old = await client.post("/api/v1/auth/login", json={"identifier": MOBILE, "password": PASSWORD})
    assert old.status_code == 401
    new = await client.post(
        "/api/v1/auth/login", json={"identifier": MOBILE, "password": "Another-Pass-2026"}
    )
    assert new.status_code == 200


async def test_a_returning_claim_from_another_mobile_is_refused(  # type: ignore[no-untyped-def]
    client, db_session, channels
) -> None:
    """کسی که ایمیل ثبت‌شده را دارد نمی‌تواند حسابِ وصل‌شده را به شمارهٔ دیگری ببرد."""
    offering_id = await _offering(db_session)
    await _entry(db_session, offering_id)
    await _complete(client, await _to_code_step(client))

    other = await _lookup(client, mobile="09121990177")
    response = await _confirm(client, other.json()["claim_id"])
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ROSTER_ACCOUNT_CONFLICT"


async def test_the_new_user_can_reach_their_profile(client, db_session, channels) -> None:  # type: ignore[no-untyped-def]
    offering_id = await _offering(db_session)
    await _entry(db_session, offering_id)
    done = (await _complete(client, await _to_code_step(client))).json()
    profile = await client.get("/api/v1/me", headers=auth(done["access_token"]))
    assert profile.status_code == 200
    assert profile.json()["profile"]["first_name"] == "علی"
    assert profile.json()["email_verified"] is True
