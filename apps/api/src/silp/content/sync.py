"""همگام‌سازی پوشهٔ `Courses/` با کتابخانهٔ سامانه — ADR-0008.

جریان کار برای کاربر یک جمله است:

> یک کتاب یا جزوه در `Courses/<نام درس>/` بگذار و `make courses-sync`
> بزن.

و برای سامانه شش گام:

۱. پوشه‌ها کشف می‌شوند و مانیفست هر کدام خوانده (یا حدس زده) می‌شود.
۲. ردیف `courses` با کلید `source_dir` ساخته یا به‌روز می‌شود.
۳. برای هر فایل، `sha256` گرفته می‌شود.
۴. فایل تازه یا تغییرکرده روی فضای ذخیره‌سازی می‌رود و یک ردیف `files`
   می‌گیرد؛ فایل دست‌نخورده **آپلود نمی‌شود** — هفت مگابایت را دو بار
   نمی‌فرستیم.
۵. ردیف `course_materials` با کلید `(course_id, source_path)` ساخته یا
   به‌روز می‌شود.
۶. مادهٔ بی‌فایل (کسی فایل را پاک کرده) `ARCHIVED` می‌شود، نه حذف.

**چرا آرشیو و نه حذف؟** پاک شدن یک فایل روی دیسک ممکن است اشتباه باشد
یا موقت (جابه‌جایی، ویرایش با Word). حذف ردیف یعنی از دست رفتن پیوند
هفته‌ها و تاریخچهٔ دسترسی. آرشیو برگشت‌پذیر است؛ حذف نیست.

همگام‌سازی **بی‌اثر در تکرار** است: اجرای دوباره روی پوشهٔ دست‌نخورده
هیچ نوشتنی انجام نمی‌دهد.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from silp.content.manifest import (
    CourseManifest,
    content_type_of,
    discover_courses,
    load_manifest,
    write_manifest,
)
from silp.core.logging import get_logger
from silp.domain.files import policy
from silp.integrations.storage import StorageBackend
from silp.models.education import (
    MAX_WEEK_NUMBER,
    Course,
    CourseMaterial,
    CourseOffering,
    CourseWeek,
    WeekMaterial,
)
from silp.models.file import File

log = get_logger("silp.content.sync")

# اندازهٔ تکه هنگام هش‌گیری — فایل ۵۰۰ مگابایتی نباید یک‌جا در حافظه بیاید.
HASH_CHUNK_BYTES = 1024 * 1024


@dataclass(slots=True)
class CourseSyncResult:
    slug: str
    title_fa: str
    course_created: bool = False
    materials_created: int = 0
    materials_updated: int = 0
    materials_unchanged: int = 0
    materials_archived: int = 0
    bytes_uploaded: int = 0
    skipped: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SyncReport:
    results: list[CourseSyncResult] = field(default_factory=list)

    @property
    def courses(self) -> int:
        return len(self.results)

    @property
    def created(self) -> int:
        return sum(r.materials_created for r in self.results)

    @property
    def updated(self) -> int:
        return sum(r.materials_updated for r in self.results)

    @property
    def unchanged(self) -> int:
        return sum(r.materials_unchanged for r in self.results)

    @property
    def archived(self) -> int:
        return sum(r.materials_archived for r in self.results)

    @property
    def bytes_uploaded(self) -> int:
        return sum(r.bytes_uploaded for r in self.results)


class CourseSync:
    """موتور همگام‌سازی. یک نمونه برای یک اجرا."""

    def __init__(
        self,
        session: AsyncSession,
        storage: StorageBackend,
        *,
        uploader_id: uuid.UUID,
        dry_run: bool = False,
    ) -> None:
        self.session = session
        self.storage = storage
        self.uploader_id = uploader_id
        self.dry_run = dry_run

    # ── ورودی اصلی ─────────────────────────────────────────────────────
    async def sync_root(self, root: Path, *, write_manifests: bool = True) -> SyncReport:
        report = SyncReport()
        for directory in discover_courses(root):
            manifest = load_manifest(directory)
            if write_manifests and not self.dry_run:
                # مانیفست بازنویسی می‌شود تا فایل‌های تازه‌کشف‌شده در آن
                # بنشینند و کاربر بتواند عنوان و سطح دسترسی را ویرایش کند.
                write_manifest(manifest)
            report.results.append(await self.sync_course(manifest))
        return report

    async def sync_course(self, manifest: CourseManifest) -> CourseSyncResult:
        course, created = await self._upsert_course(manifest)
        result = CourseSyncResult(
            slug=manifest.slug, title_fa=manifest.title_fa, course_created=created
        )

        seen_paths: set[str] = set()
        for index, entry in enumerate(manifest.materials):
            file_path = manifest.directory / entry.file
            if not file_path.is_file():
                result.skipped.append(entry.file)
                log.warning("material_file_missing", course=manifest.slug, file=entry.file)
                continue
            if file_path.suffix.lower() not in policy_extensions():
                result.skipped.append(entry.file)
                log.warning("material_type_unsupported", course=manifest.slug, file=entry.file)
                continue

            seen_paths.add(entry.file)
            await self._sync_material(course, manifest, entry, file_path, index, result)

        await self._archive_missing(course, seen_paths, result)
        if not self.dry_run:
            await self.session.commit()
        return result

    # ── درس ────────────────────────────────────────────────────────────
    async def _upsert_course(self, manifest: CourseManifest) -> tuple[Course, bool]:
        """درس را با `source_dir` پیدا می‌کند، وگرنه با `code`، وگرنه می‌سازد.

        ترتیب مهم است: پوشه ممکن است تغییر نام بدهد ولی کد درس بماند، و
        برعکس. پیدا کردن با هر دو، همگام‌سازی را در برابر تغییر نام
        مقاوم می‌کند.
        """
        course = await self.session.scalar(
            select(Course).where(Course.source_dir == manifest.source_dir)
        )
        if course is None:
            course = await self.session.scalar(select(Course).where(Course.code == manifest.code))
        created = course is None
        if course is None:
            course = Course(code=manifest.code, slug=manifest.slug, title_fa=manifest.title_fa)
            self.session.add(course)

        course.source_dir = manifest.source_dir
        course.slug = manifest.slug
        course.title_fa = manifest.title_fa
        course.title_en = manifest.title_en
        course.description = manifest.description
        course.degree_level = manifest.degree_level
        course.credits = manifest.credits
        course.is_public = manifest.is_public
        course.is_active = manifest.is_active
        course.default_access_tier = manifest.default_access_tier
        course.topics = list(manifest.topics)
        course.deleted_at = None
        await self.session.flush()
        return course, created

    # ── ماده ───────────────────────────────────────────────────────────
    async def _sync_material(
        self,
        course: Course,
        manifest: CourseManifest,
        entry: object,
        file_path: Path,
        index: int,
        result: CourseSyncResult,
    ) -> None:
        from silp.content.manifest import MaterialEntry

        assert isinstance(entry, MaterialEntry)
        digest = sha256_of(file_path)
        size = file_path.stat().st_size

        material = await self.session.scalar(
            select(CourseMaterial).where(
                CourseMaterial.course_id == course.id,
                CourseMaterial.source_path == entry.file,
            )
        )
        unchanged = (
            material is not None
            and material.content_sha256 == digest
            and material.file_id is not None
            and material.deleted_at is None
        )

        if material is None:
            result.materials_created += 1
        elif unchanged:
            result.materials_unchanged += 1
        else:
            result.materials_updated += 1

        if self.dry_run:
            # هیچ ردیفی ساخته نمی‌شود: مادهٔ تازه بدون فایل، قید
            # `source_required` را در همان flush بعدی می‌شکند.
            return

        # **فایل اول، ماده دوم.** `_store_file` خودش flush می‌کند و آن
        # flush هر ردیف معلقِ دیگری را هم می‌نویسد؛ اگر ماده پیش از
        # گرفتن `file_id` معلق باشد، با `file_id IS NULL` نوشته می‌شود و
        # قید `source_required` می‌شکند.
        if not unchanged:
            file_row = await self._store_file(file_path, size)
            result.bytes_uploaded += size

        if material is None:
            material = CourseMaterial(
                course_id=course.id,
                kind=entry.kind,
                title_fa=entry.title_fa,
                source_path=entry.file,
                file_id=file_row.id,
                content_sha256=digest,
                size_bytes=size,
            )
            self.session.add(material)
        elif not unchanged:
            material.file_id = file_row.id
            material.content_sha256 = digest
            material.size_bytes = size

        # فراداده همیشه به‌روز می‌شود، حتی اگر فایل دست‌نخورده باشد:
        # ویرایش عنوان در مانیفست نباید نیاز به عوض کردن فایل داشته باشد.
        material.kind = entry.kind
        material.title_fa = entry.title_fa
        material.description = entry.description
        material.authors = list(entry.authors)
        material.edition = entry.edition
        material.language = entry.language
        material.access_tier = entry.access_tier or course.default_access_tier
        material.is_downloadable = entry.is_downloadable
        material.status = entry.status
        material.sort_order = entry.sort_order or index
        material.page_count = entry.page_count
        material.duration_sec = entry.duration_sec
        material.deleted_at = None
        material.added_by = material.added_by or self.uploader_id
        await self.session.flush()

    async def _store_file(self, file_path: Path, size: int) -> File:
        """آپلود فایل و ساخت ردیف `files` — تکمیل‌شده از لحظهٔ اول.

        برخلاف آپلود کاربر، اینجا مرحلهٔ «رزرو» معنا ندارد: فایل روی
        دیسک همین ماشین است، سرور خودش می‌نویسد، و لحظه‌ای که نوشتن
        تمام شد، فایل واقعاً تکمیل‌شده است.
        """
        from datetime import UTC, datetime

        content_type = content_type_of(file_path)
        max_bytes = policy.max_bytes_for(content_type)
        if size > max_bytes:
            raise ValueError(
                f"«{file_path.name}» {size} بایت است و از سقف {max_bytes} بایت می‌گذرد."
            )

        file_row = File(
            storage_key="",
            bucket=self.storage.bucket,
            original_name=file_path.name,
            content_type=content_type,
            size_bytes=size,
            uploaded_by=self.uploader_id,
            purpose=policy.FilePurpose.RESOURCE.value,
        )
        self.session.add(file_row)
        await self.session.flush()

        file_row.storage_key = policy.storage_key(
            purpose=policy.FilePurpose.RESOURCE,
            file_id=str(file_row.id),
            original_name=file_path.name,
        )
        await self.storage.upload_bytes(
            file_row.storage_key, file_path.read_bytes(), content_type=content_type
        )
        file_row.uploaded_at = datetime.now(UTC)
        # ClamAV در فاز ۱ نیست (§11.1). این فایل از دیسک خودمان آمده،
        # نه از اینترنت؛ ولی وضعیت همچنان «بررسی نشد» است، نه «پاک».
        file_row.scan_status = "SKIPPED"
        await self.session.flush()
        return file_row

    async def _archive_missing(
        self, course: Course, seen_paths: set[str], result: CourseSyncResult
    ) -> None:
        rows = await self.session.scalars(
            select(CourseMaterial).where(
                CourseMaterial.course_id == course.id,
                CourseMaterial.source_path.is_not(None),
                CourseMaterial.status != "ARCHIVED",
            )
        )
        for material in rows:
            if material.source_path in seen_paths:
                continue
            material.status = "ARCHIVED"
            result.materials_archived += 1
            log.info(
                "material_archived",
                course=course.slug,
                source_path=material.source_path,
            )


# ── برنامهٔ درسی ← هفته‌های یک ارائه ────────────────────────────────────
async def apply_syllabus(
    session: AsyncSession, *, offering_id: uuid.UUID, manifest: CourseManifest
) -> int:
    """ساخت هفته‌های یک ارائه از روی برنامهٔ درسی مانیفست.

    هفته‌ها **پیش‌نویس** ساخته می‌شوند: برنامهٔ درسی می‌گوید ترم چه شکلی
    است، نه اینکه دانشجو امروز چه ببیند. انتشار تصمیم استاد است
    (FR-EDU-02).

    هفتهٔ موجود بازنویسی نمی‌شود؛ استادی که عنوان هفتهٔ ۵ را عوض کرده،
    نباید با اجرای دوبارهٔ همگام‌سازی آن را از دست بدهد.
    """
    offering = await session.get(CourseOffering, offering_id)
    if offering is None:
        raise ValueError("ارائه پیدا نشد.")

    existing = {
        week.week_number: week
        for week in await session.scalars(
            select(CourseWeek).where(CourseWeek.offering_id == offering_id)
        )
    }
    created = 0
    for item in manifest.syllabus:
        if not 1 <= item.week <= MAX_WEEK_NUMBER:
            continue
        if item.week in existing:
            continue
        week = CourseWeek(
            offering_id=offering_id,
            week_number=item.week,
            title_fa=item.title_fa,
            description=item.description,
            objectives=list(item.objectives) or None,
            status="DRAFT",
        )
        session.add(week)
        existing[item.week] = week
        created += 1
    await session.flush()

    await _link_manifest_materials(session, offering.course_id, manifest, existing)
    return created


async def _link_manifest_materials(
    session: AsyncSession,
    course_id: uuid.UUID,
    manifest: CourseManifest,
    weeks: dict[int, CourseWeek],
) -> None:
    """پیوند `weeks:` مانیفست به `week_materials`."""
    by_path = {
        material.source_path: material
        for material in await session.scalars(
            select(CourseMaterial).where(
                CourseMaterial.course_id == course_id,
                CourseMaterial.source_path.is_not(None),
            )
        )
        if material.source_path
    }
    existing_links = {
        (link.week_id, link.material_id)
        for link in await session.scalars(
            select(WeekMaterial).where(
                WeekMaterial.week_id.in_([w.id for w in weeks.values()] or [uuid.UUID(int=0)])
            )
        )
    }

    for entry in manifest.materials:
        material = by_path.get(entry.file)
        if material is None:
            continue
        for order, week_number in enumerate(entry.weeks):
            week = weeks.get(week_number)
            if week is None or (week.id, material.id) in existing_links:
                continue
            session.add(
                WeekMaterial(
                    week_id=week.id,
                    material_id=material.id,
                    section=entry.section,
                    sort_order=order,
                )
            )
    await session.flush()


# ── کمکی ───────────────────────────────────────────────────────────────
def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(HASH_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def policy_extensions() -> frozenset[str]:
    """پسوندهایی که سیاست فایل (§5.9) می‌پذیرد."""
    return frozenset(ext for spec in policy.CONTENT_SPECS for ext in spec.extensions)


__all__ = [
    "CourseSync",
    "CourseSyncResult",
    "SyncReport",
    "apply_syllabus",
    "sha256_of",
]
