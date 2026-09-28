"""همگام‌سازی `12_Content` با پایگاه‌داده — ADR-0030.

قواعد (همان سه قاعدهٔ ADR-0008):

۱. کلید همگام‌سازی `source_path` است و `content_sha256` می‌گوید فایل عوض شده یا نه؛
   اجرای دوباره روی Vault دست‌نخورده هیچ نوشتنی ندارد.
۲. یادداشتِ خراب فقط خودش را رد می‌کند؛ بقیه منتشر می‌شوند و گزارش خطا برمی‌گردد.
۳. فایلِ ناپدیدشده `ARCHIVED` می‌شود، حذف نمی‌شود.

`publish_notes` فقط فهرست `Note` می‌گیرد و به دیسک وابسته نیست؛ همین
تابع را بعداً یک مسیر آپلود API هم می‌تواند صدا بزند (استقرار روی سرور
جدا از رایانهٔ مالک). تراکنش را فراخواننده commit می‌کند.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path, PurePath, PurePosixPath

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from silp.models.content import ContentItem
from silp.vault.notes import CONTENT_DIR, Note, NoteError, parse_note


@dataclass(slots=True)
class PublishReport:
    created: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    archived: list[str] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)
    warnings: dict[str, tuple[str, ...]] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.errors


def _ignored(relative_to_content: PurePath) -> bool:
    """فایل‌ها و پوشه‌های شروع‌شده با «.» یا «_» (قالب‌ها، پنهان‌ها) منتشر نمی‌شوند."""
    return any(part.startswith((".", "_")) for part in relative_to_content.parts)


def parse_files(files: Iterable[tuple[str, str]]) -> tuple[list[Note], dict[str, str]]:
    """`(مسیر نسبت به Vault، متن خام)` ← یادداشت‌ها و خطاها. به دیسک دست نمی‌زند."""
    notes: list[Note] = []
    errors: dict[str, str] = {}
    for relative, raw in files:
        if _ignored(PurePosixPath(relative).relative_to(CONTENT_DIR)):
            continue
        try:
            notes.append(parse_note(raw, source_path=relative))
        except NoteError as exc:
            errors[relative] = str(exc)
    return notes, errors


def collect(vault: Path) -> tuple[list[tuple[str, str]], dict[str, str]]:
    """`(مسیر، متن)`ِ همهٔ `.md`های `12_Content` و خطای فایل‌های نخواندنی.

    پوشهٔ محتوا نبود ← خطا زیر کلید `12_Content` (فراخوان نباید چیزی آرشیو کند).
    """
    root = vault / CONTENT_DIR
    if not root.is_dir():
        return [], {CONTENT_DIR: "پوشهٔ 12_Content در Vault نیست؛ اول `vault init` را اجرا کنید."}
    files: list[tuple[str, str]] = []
    unreadable: dict[str, str] = {}
    for path in sorted(root.rglob("*.md")):
        relative = path.relative_to(vault).as_posix()
        if _ignored(path.relative_to(root)):
            continue
        try:
            files.append((relative, path.read_text(encoding="utf-8")))
        except UnicodeDecodeError:
            unreadable[relative] = "فایل UTF-8 نیست."
    return files, unreadable


def scan(vault: Path) -> tuple[list[Note], dict[str, str]]:
    """همهٔ `.md`های `12_Content` (به‌جز فایل‌های پنهان و «_…»)."""
    files, unreadable = collect(vault)
    notes, errors = parse_files(files)
    return notes, {**errors, **unreadable}


async def publish_notes(
    session: AsyncSession,
    notes: Iterable[Note],
    *,
    seen_errors: dict[str, str] | None = None,
    archive_missing: bool = True,
) -> PublishReport:
    report = PublishReport(errors=dict(seen_errors or {}))
    notes = list(notes)
    by_path = {n.source_path: n for n in notes}

    existing = list(await session.scalars(select(ContentItem)))
    by_source = {row.source_path: row for row in existing if row.source_path}
    by_slug = {row.slug: row for row in existing}
    claimed: dict[str, str] = {}
    now = datetime.now(UTC)

    for note in notes:
        if note.warnings:
            report.warnings[note.source_path] = note.warnings
        owner_path = claimed.get(note.slug)
        if owner_path is not None and owner_path != note.source_path:
            report.errors[note.source_path] = (
                f"نشانی «{note.slug}» را «{owner_path}» هم دارد؛ «slug» یکی را عوض کنید."
            )
            continue
        clash = by_slug.get(note.slug)
        row = by_source.get(note.source_path)
        if clash is not None and clash is not row:
            report.errors[note.source_path] = (
                f"نشانی «{note.slug}» برای یادداشت دیگری ({clash.source_path or 'بدون فایل'}) است."
            )
            continue
        claimed[note.slug] = note.source_path

        published_at = None
        if note.status == "PUBLISHED":
            published_at = note.published_at or (row.published_at if row else None) or now

        if row is None:
            row = ContentItem(source_path=note.source_path)
            session.add(row)
            _apply(row, note, published_at)
            report.created.append(note.source_path)
        elif row.content_sha256 == note.sha256 and row.status != "ARCHIVED":
            report.unchanged.append(note.source_path)
        else:
            _apply(row, note, published_at)
            report.updated.append(note.source_path)
        by_slug[note.slug] = row

    if archive_missing:
        for row in existing:
            if (
                row.source_path
                and row.source_path.startswith(f"{CONTENT_DIR}/")
                and row.source_path not in by_path
                and row.source_path not in report.errors
                and row.status != "ARCHIVED"
            ):
                row.status = "ARCHIVED"
                report.archived.append(row.source_path)

    await session.flush()
    return report


def _apply(row: ContentItem, note: Note, published_at: datetime | None) -> None:
    row.slug = note.slug
    row.kind = note.kind
    row.title_fa = note.title_fa
    row.summary = note.summary
    row.body_md = note.body_md
    row.cover = note.cover
    row.access = note.access
    row.topics = list(note.topics)
    row.skills = list(note.skills)
    row.course_slug = note.course_slug
    row.status = note.status
    row.published_at = published_at
    row.reading_minutes = note.reading_minutes
    row.content_sha256 = note.sha256


async def publish_vault(
    session: AsyncSession, vault: Path, *, archive_missing: bool = True
) -> PublishReport:
    notes, errors = scan(vault)
    # پوشهٔ محتوا پیدا نشد (Vault جابه‌جا یا دیسک وصل نیست): همه‌چیز را آرشیو نکن.
    safe_to_archive = archive_missing and CONTENT_DIR not in errors
    return await publish_notes(session, notes, seen_errors=errors, archive_missing=safe_to_archive)


__all__ = ["PublishReport", "collect", "parse_files", "publish_notes", "publish_vault", "scan"]
