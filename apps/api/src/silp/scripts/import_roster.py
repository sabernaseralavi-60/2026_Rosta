"""وارد کردن فهرست دانشجویان از اکسل — ADR-0035.

    python -m silp.scripts.import_roster students/students.xlsx --dry-run
    python -m silp.scripts.import_roster students/students.xlsx
    python -m silp.scripts.import_roster students/students.xlsx --offering "نام برگه=<شناسهٔ ارائه>"

هر برگه یک درس است. نام برگه با عنوان درس تطبیق می‌خورد و ارائهٔ نیم‌سال جاری برگزیده
می‌شود؛ اگر درس پیدا نشد یا چند ارائه داشت، آن برگه **رد می‌شود** و با `--offering`
صریح باید گفت (حدس‌زدنِ درس، دانشجو را در درس اشتباه ثبت‌نام می‌کرد).

**هیچ نام، شمارهٔ دانشجویی یا ایمیلی چاپ یا لاگ نمی‌شود** — فقط شمارش. شمارهٔ دانشجویی
فقط به‌صورت HMAC ذخیره می‌شود. بی‌اثر در تکرار: ردیف موجود به‌روز می‌شود و ایمیلِ تازه
جای خالی را پر می‌کند (راهی برای «به استاد گفتم ایمیلم را اضافه کند»).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import func, literal_column, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from silp.content.roster_file import SheetRoster, normalize_title, read_rosters
from silp.core.config import get_settings
from silp.core.logging import configure_logging
from silp.db.session import dispose_engine, session_scope
from silp.domain.identity import roster as rules
from silp.models.education import Course, CourseOffering, Term
from silp.models.roster import RosterEntry


@dataclass
class SheetReport:
    sheet: str
    offering: str = "—"
    read: int = 0
    inserted: int = 0
    updated: int = 0
    invalid_number: int = 0
    duplicate_in_sheet: int = 0
    without_email: int = 0
    bad_email: int = 0
    skipped_rows: int = 0
    problem: str | None = None


@dataclass
class ImportReport:
    sheets: list[SheetReport] = field(default_factory=list)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="import_roster", description=__doc__)
    parser.add_argument("file", type=Path, help="فایل .xlsx")
    parser.add_argument("--dry-run", action="store_true", help="فقط شمارش؛ چیزی نوشته نمی‌شود")
    parser.add_argument(
        "--offering",
        action="append",
        default=[],
        metavar="برگه=شناسه",
        help="نگاشت صریح نام برگه به شناسهٔ ارائه (می‌توان چندبار داد)",
    )
    return parser.parse_args(argv)


def _explicit(pairs: list[str]) -> dict[str, uuid.UUID]:
    mapping: dict[str, uuid.UUID] = {}
    for pair in pairs:
        name, sep, raw = pair.rpartition("=")
        if not sep:
            raise SystemExit(f"قالب --offering باید «برگه=شناسه» باشد: {pair!r}")
        try:
            mapping[normalize_title(name)] = uuid.UUID(raw.strip())
        except ValueError:
            raise SystemExit(f"شناسهٔ ارائه معتبر نیست: {raw!r}") from None
    return mapping


async def _resolve_offering(session: AsyncSession, sheet: str) -> tuple[uuid.UUID | None, str]:
    """ارائهٔ نیم‌سال جاری درسی که عنوانش با نام برگه یکی است."""
    wanted = normalize_title(sheet)
    rows = (
        await session.execute(
            select(CourseOffering.id, Course.title_fa, Term.is_current, Term.starts_on)
            .join(Course, Course.id == CourseOffering.course_id)
            .join(Term, Term.id == CourseOffering.term_id)
            .where(CourseOffering.deleted_at.is_(None), Course.deleted_at.is_(None))
        )
    ).all()
    matches = [row for row in rows if normalize_title(row.title_fa) == wanted]
    if not matches:
        return None, "درسی با این عنوان پیدا نشد"
    current = [row for row in matches if row.is_current]
    pool = current or matches
    if len(pool) > 1:
        return None, f"{len(pool)} ارائه با این عنوان هست؛ با --offering مشخص کنید"
    return pool[0].id, "نیم‌سال جاری" if current else "آخرین نیم‌سال"


async def _import_sheet(
    session: AsyncSession, roster: SheetRoster, offering_id: uuid.UUID, *, secret: str
) -> SheetReport:
    report = SheetReport(sheet=roster.name, offering=str(offering_id))
    report.read = len(roster.rows)
    report.skipped_rows = roster.skipped
    report.bad_email = roster.bad_emails
    seen: set[str] = set()
    for row in roster.rows:
        number = rules.normalize_student_no(row.student_no_raw)
        if number is None:
            report.invalid_number += 1
            continue
        digest = rules.digest(number, secret)
        if digest in seen:
            report.duplicate_in_sheet += 1
            continue
        seen.add(digest)
        if row.email is None:
            report.without_email += 1
        insert = pg_insert(RosterEntry).values(
            offering_id=offering_id,
            first_name=row.first_name,
            last_name=row.last_name,
            student_no_hash=digest,
            email=row.email,
        )
        stmt = insert.on_conflict_do_update(
            index_elements=[RosterEntry.offering_id, RosterEntry.student_no_hash],
            set_={
                "first_name": insert.excluded.first_name,
                "last_name": insert.excluded.last_name,
                # ایمیل تازه جای خالی را پر می‌کند؛ فایلِ بی‌ایمیل ایمیل موجود را پاک نمی‌کند.
                "email": func.coalesce(insert.excluded.email, RosterEntry.email),
            },
        ).returning(literal_column("(xmax = 0)").label("inserted"))
        result = (await session.execute(stmt)).one()
        if result.inserted:
            report.inserted += 1
        else:
            report.updated += 1
    return report


async def run(args: argparse.Namespace) -> ImportReport:
    if not args.file.is_file():
        raise SystemExit(f"فایل پیدا نشد: {args.file}")
    rosters = read_rosters(args.file)
    explicit = _explicit(args.offering)
    secret = get_settings().secret_key

    report = ImportReport()
    async with session_scope() as session:
        for roster in rosters:
            if not roster.rows:
                # برگهٔ بی‌سرستون (مثل «Sheet2» خالی) گزارش می‌شود، ولی خطا نیست.
                report.sheets.append(SheetReport(sheet=roster.name, problem="ردیف دانشجویی ندارد"))
                continue
            offering_id = explicit.get(normalize_title(roster.name))
            note = "صریح"
            if offering_id is None:
                offering_id, note = await _resolve_offering(session, roster.name)
            if offering_id is None:
                report.sheets.append(SheetReport(sheet=roster.name, problem=note))
                continue
            sheet_report = await _import_sheet(session, roster, offering_id, secret=secret)
            sheet_report.offering = f"{offering_id} ({note})"
            report.sheets.append(sheet_report)
        if args.dry_run:
            await session.rollback()
        else:
            await session.commit()
    return report


def _print(report: ImportReport, *, dry_run: bool) -> None:
    print("")
    if dry_run:
        print("  «آزمایشی» — هیچ چیزی نوشته نشد.")
    for sheet in report.sheets:
        print(f"  برگه «{sheet.sheet}»")
        if sheet.problem:
            print(f"      ! رد شد: {sheet.problem}")
            continue
        print(f"      ارائه: {sheet.offering}")
        print(
            f"      {sheet.read} ردیف: {sheet.inserted} تازه، {sheet.updated} به‌روز، "
            f"{sheet.without_email} بی‌ایمیل"
        )
        for label, count in (
            ("شمارهٔ دانشجویی نامعتبر", sheet.invalid_number),
            ("تکراری در همین برگه", sheet.duplicate_in_sheet),
            ("ردیف ناقص", sheet.skipped_rows),
            ("ایمیل نامعتبر", sheet.bad_email),
        ):
            if count:
                print(f"      ! {count} {label}")
    print("")


async def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    configure_logging(get_settings().log_level, renderer="console")
    try:
        report = await run(args)
    finally:
        await dispose_engine()
    _print(report, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
