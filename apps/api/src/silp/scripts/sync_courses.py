"""همگام‌سازی پوشهٔ `Courses/` با کتابخانهٔ سامانه — ADR-0008.

اجرا::

    make courses-sync                    # همه‌چیز
    make courses-sync a="--dry-run"      # فقط گزارش، بدون نوشتن
    python -m silp.scripts.sync_courses --course "Traffic Safety"

این اسکریپت **بی‌اثر در تکرار** است و می‌تواند هر روز اجرا شود: فایل
دست‌نخورده دوباره آپلود نمی‌شود.

مسیر پوشه از `COURSES_DIR` خوانده می‌شود و پیش‌فرضش `Courses/` در ریشهٔ
مخزن است. در داکر، این پوشه باید به کانتینر mount شده باشد.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from pathlib import Path

from sqlalchemy import select

from silp.content.manifest import (
    ManifestError,
    discover_courses,
    load_manifest,
    write_manifest,
)
from silp.content.sync import CourseSync, SyncReport, apply_syllabus
from silp.core.config import get_settings
from silp.core.logging import configure_logging, get_logger
from silp.core.permissions import Role
from silp.db.session import dispose_engine, session_scope
from silp.integrations.storage import get_storage
from silp.models.education import Course, CourseOffering
from silp.models.identity import User, UserRole

log = get_logger("silp.scripts.sync_courses")

MB = 1024 * 1024


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="sync_courses", description="همگام‌سازی پوشهٔ دروس با کتابخانهٔ سامانه"
    )
    parser.add_argument("--root", type=Path, default=None, help="مسیر پوشهٔ دروس")
    parser.add_argument("--course", action="append", help="فقط این پوشه(ها) — نام پوشه")
    parser.add_argument(
        "--dry-run", action="store_true", help="فقط گزارش بده؛ چیزی ننویس و آپلود نکن"
    )
    parser.add_argument(
        "--no-manifest",
        action="store_true",
        help="فایل course.yml را بازنویسی نکن",
    )
    parser.add_argument(
        "--apply-syllabus",
        action="store_true",
        help="هفته‌های پیش‌نویس را هم برای ارائه‌های موجود بساز",
    )
    return parser.parse_args(argv)


def resolve_root(explicit: Path | None) -> Path:
    """مسیر پوشهٔ دروس: آرگومان، سپس پیکربندی، سپس ریشهٔ مخزن."""
    if explicit is not None:
        return explicit
    settings = get_settings()
    configured = Path(settings.courses_dir)
    if configured.is_absolute():
        return configured
    # از `src/silp/scripts/` تا ریشهٔ مخزن: پنج پله بالا.
    repo_root = Path(__file__).resolve().parents[5]
    return (repo_root / configured).resolve()


async def _uploader_id() -> uuid.UUID:
    """مالک فایل‌های همگام‌شده: اولین مدیر سامانه.

    فایل باید صاحب داشته باشد (قید `files.uploaded_by`) و صاحبش نباید
    یک حساب مصنوعی باشد که هیچ‌کس مسئولش نیست.
    """
    async with session_scope() as session:
        admin_id = await session.scalar(
            select(User.id)
            .join(UserRole, UserRole.user_id == User.id)
            .where(UserRole.role_code == Role.ADMIN.value, User.deleted_at.is_(None))
            .order_by(User.created_at)
            .limit(1)
        )
    if admin_id is None:
        raise SystemExit("هیچ حساب مدیری پیدا نشد. اول `make seed` را اجرا کنید یا یک مدیر بسازید.")
    return admin_id


async def run(args: argparse.Namespace) -> SyncReport:
    root = resolve_root(args.root)
    if not root.is_dir():
        raise SystemExit(f"پوشهٔ دروس پیدا نشد: {root}")

    directories = discover_courses(root)
    if args.course:
        wanted = {name.strip() for name in args.course}
        directories = [d for d in directories if d.name in wanted]
        missing = wanted - {d.name for d in directories}
        if missing:
            raise SystemExit(f"این پوشه(ها) پیدا نشد: {', '.join(sorted(missing))}")

    settings = get_settings()
    storage = get_storage(settings)
    uploader = await _uploader_id()

    report = SyncReport()
    async with session_scope() as session:
        syncer = CourseSync(session, storage, uploader_id=uploader, dry_run=args.dry_run)
        for directory in directories:
            manifest = load_manifest(directory)
            if not args.no_manifest and not args.dry_run:
                write_manifest(manifest)
            report.results.append(await syncer.sync_course(manifest))

            if args.apply_syllabus and not args.dry_run:
                await _apply_to_offerings(session, manifest)
        if not args.dry_run:
            await session.commit()
    return report


async def _apply_to_offerings(session, manifest) -> None:  # type: ignore[no-untyped-def]
    """برنامهٔ درسی را روی همهٔ ارائه‌های همین درس اعمال می‌کند."""
    course = await session.scalar(select(Course).where(Course.source_dir == manifest.source_dir))
    if course is None:
        return
    offerings = await session.scalars(
        select(CourseOffering.id).where(
            CourseOffering.course_id == course.id, CourseOffering.deleted_at.is_(None)
        )
    )
    for offering_id in offerings:
        created = await apply_syllabus(session, offering_id=offering_id, manifest=manifest)
        if created:
            log.info("syllabus_applied", offering_id=str(offering_id), weeks=created)


def _print(report: SyncReport, *, dry_run: bool) -> None:
    print("")
    if dry_run:
        print("  «آزمایشی» — هیچ چیزی نوشته یا آپلود نشد.")
    for result in report.results:
        line = (
            f"  {result.title_fa}: "
            f"{result.materials_created} تازه، "
            f"{result.materials_updated} به‌روز، "
            f"{result.materials_unchanged} بدون تغییر"
        )
        if result.materials_archived:
            line += f"، {result.materials_archived} آرشیو"
        print(line)
        for skipped in result.skipped:
            print(f"      ! رد شد: {skipped}")
    print("")
    print(
        f"  جمع: {report.courses} درس، {report.created} مادهٔ تازه، "
        f"{report.bytes_uploaded / MB:.1f} مگابایت آپلود."
    )
    print("")


async def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    settings = get_settings()
    configure_logging(settings.log_level, renderer="console")

    try:
        report = await run(args)
    except ManifestError as exc:
        print(f"خطای مانیفست: {exc}", file=sys.stderr)
        return 1
    finally:
        await dispose_engine()

    _print(report, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
