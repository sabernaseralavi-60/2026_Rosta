"""وارد کردن فهرست به دیتابیس — ADR-0035.

خودِ `run()` از `session_scope` خودش commit می‌کند و به تراکنش تست برنمی‌گردد؛ پس اینجا
هستهٔ `_import_sheet` روی نشست تست اجرا می‌شود (commit ندارد، پایان تست برمی‌گردد).
"""

from __future__ import annotations

import secrets
import uuid
from datetime import date
from typing import Any

import pytest
from sqlalchemy import select

from silp.content.roster_file import RosterRow, SheetRoster
from silp.core.config import get_settings
from silp.domain.identity import roster as rules
from silp.models.education import Course, CourseOffering, Term
from silp.models.identity import User
from silp.models.roster import RosterEntry
from silp.scripts.import_roster import _import_sheet, _resolve_offering

pytestmark = pytest.mark.integration

SECRET = get_settings().secret_key


async def _offering(session: Any, title: str) -> uuid.UUID:
    marker = uuid.uuid4().hex[:8]
    instructor = User(mobile=f"09{secrets.randbelow(10**9):09d}")
    session.add(instructor)
    term = Term(
        code=f"T-{marker}",
        title_fa="نیم‌سال آزمایشی",
        starts_on=date(2026, 9, 23),
        ends_on=date(2027, 2, 4),
        is_current=False,
    )
    course = Course(code=f"C-{marker}", slug=f"course-{marker}", title_fa=title)
    session.add_all([term, course])
    await session.flush()
    offering = CourseOffering(
        course_id=course.id, term_id=term.id, instructor_id=instructor.id, status="OPEN"
    )
    session.add(offering)
    await session.flush()
    return offering.id


def _sheet(*rows: RosterRow, name: str = "درس آزمایشی") -> SheetRoster:
    return SheetRoster(name=name, rows=list(rows), skipped=0, bad_emails=0)


def _row(number: str, email: str | None = None, first: str = "علی") -> RosterRow:
    return RosterRow(first_name=first, last_name="رضایی", student_no_raw=number, email=email)


async def _entries(session: Any, offering_id: uuid.UUID) -> list[RosterEntry]:
    return list(
        await session.scalars(select(RosterEntry).where(RosterEntry.offering_id == offering_id))
    )


async def test_import_counts_and_stores_only_the_hash(db_session) -> None:  # type: ignore[no-untyped-def]
    offering_id = await _offering(db_session, "درس آزمایشی")
    report = await _import_sheet(
        db_session,
        _sheet(
            _row("402123456", "a@x.ac.ir"),
            _row("۴۰۲۱۲۳۴۵۷"),  # ارقام فارسی، بی‌ایمیل
            _row("402123456"),  # تکراری در همین برگه
            _row("12"),  # نامعتبر
        ),
        offering_id,
        secret=SECRET,
    )
    assert (report.inserted, report.updated) == (2, 0)
    assert report.invalid_number == 1 and report.duplicate_in_sheet == 1
    assert report.without_email == 1

    stored = await _entries(db_session, offering_id)
    assert len(stored) == 2
    assert all("402123456" not in e.student_no_hash for e in stored)
    assert rules.digest("402123457", SECRET) in {e.student_no_hash for e in stored}


async def test_reimport_is_idempotent_and_a_new_email_fills_the_gap(db_session) -> None:  # type: ignore[no-untyped-def]
    offering_id = await _offering(db_session, "درس آزمایشی")
    await _import_sheet(db_session, _sheet(_row("402123456")), offering_id, secret=SECRET)

    again = await _import_sheet(
        db_session, _sheet(_row("402123456", "late@x.ac.ir")), offering_id, secret=SECRET
    )
    assert (again.inserted, again.updated) == (0, 1)
    (entry,) = await _entries(db_session, offering_id)
    assert entry.email == "late@x.ac.ir"

    # فایلی که ایمیل ندارد، ایمیل ثبت‌شده را پاک نمی‌کند.
    await _import_sheet(db_session, _sheet(_row("402123456")), offering_id, secret=SECRET)
    await db_session.refresh(entry)
    assert entry.email == "late@x.ac.ir"


async def test_reimport_keeps_the_claim(db_session) -> None:  # type: ignore[no-untyped-def]
    offering_id = await _offering(db_session, "درس آزمایشی")
    await _import_sheet(db_session, _sheet(_row("402123456")), offering_id, secret=SECRET)
    (entry,) = await _entries(db_session, offering_id)
    user = User(mobile="09121991000")
    db_session.add(user)
    await db_session.flush()
    entry.user_id = user.id
    await db_session.flush()

    await _import_sheet(
        db_session, _sheet(_row("402123456", first="نام اصلاح‌شده")), offering_id, secret=SECRET
    )
    await db_session.refresh(entry)
    assert entry.user_id == user.id and entry.first_name == "نام اصلاح‌شده"


async def test_the_same_student_in_two_courses_is_two_entries_one_hash(db_session) -> None:  # type: ignore[no-untyped-def]
    first = await _offering(db_session, "درس یک")
    second = await _offering(db_session, "درس دو")
    await _import_sheet(db_session, _sheet(_row("402123456")), first, secret=SECRET)
    await _import_sheet(db_session, _sheet(_row("402123456")), second, secret=SECRET)
    (a,) = await _entries(db_session, first)
    (b,) = await _entries(db_session, second)
    assert a.student_no_hash == b.student_no_hash


async def test_a_sheet_is_matched_to_the_course_by_normalised_title(db_session) -> None:  # type: ignore[no-untyped-def]
    unique = f"تحلیل ایمنی {uuid.uuid4().hex[:6]}"
    offering_id = await _offering(db_session, unique.replace(" ", "‌"))  # با نیم‌فاصله ذخیره شده
    found, _note = await _resolve_offering(db_session, unique)  # برگه با فاصله
    assert found == offering_id

    missing, why = await _resolve_offering(db_session, "درسی که وجود ندارد")
    assert missing is None and "پیدا نشد" in why
