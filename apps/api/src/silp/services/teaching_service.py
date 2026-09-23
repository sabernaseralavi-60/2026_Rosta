"""سمت نوشتن آموزش — هفته، منبع، اعلان، حضور، و کپی از ارائهٔ قبلی.

مرجع: §5.11 (`/teach`)، FR-EDU-01 تا FR-EDU-06.

مجوز در لایهٔ مسیر با `require(..., scope=offering_from_path)` بررسی
می‌شود و اینجا **دوباره** (§6.4 قاعدهٔ ۲): هر متد شناسهٔ ارائه را
می‌گیرد و خودش تأیید می‌کند که موجودیت به همان ارائه تعلق دارد. بدون
آن، یک شناسهٔ هفته از ارائهٔ دیگر کافی است تا مجوز قلمرودار دور بخورد.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from silp.core.exceptions import Conflict, NotFound, ValidationFailed
from silp.core.logging import get_logger
from silp.models.education import (
    MAX_WEEK_NUMBER,
    Announcement,
    AttendanceRecord,
    ClassSession,
    CourseMaterial,
    CourseOffering,
    CourseWeek,
    Enrollment,
    Resource,
    WeekMaterial,
)
from silp.services import events

log = get_logger("silp.teaching")

GRADING_POLICY_KEYS = ("quiz", "project", "attendance", "participation")
GRADING_POLICY_TOTAL = 100


@dataclass(frozen=True, slots=True)
class WeekDraft:
    week_number: int
    title_fa: str
    description: str | None = None
    objectives: list[str] | None = None
    publish_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class ResourceDraft:
    kind: str
    title_fa: str
    description: str | None = None
    file_id: uuid.UUID | None = None
    external_url: str | None = None
    duration_sec: int | None = None
    is_downloadable: bool = True
    is_required: bool = True
    sort_order: int = 0


@dataclass(frozen=True, slots=True)
class AttendanceEntry:
    student_id: uuid.UUID
    status: str
    note: str | None = None


class TeachingService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ── ارائه ──────────────────────────────────────────────────────────
    async def offering(self, offering_id: uuid.UUID) -> CourseOffering:
        offering = await self.session.get(CourseOffering, offering_id)
        if offering is None or offering.deleted_at is not None:
            raise NotFound("این ارائه پیدا نشد.")
        return offering

    async def my_offerings(self, instructor_id: uuid.UUID) -> list[CourseOffering]:
        rows = await self.session.scalars(
            select(CourseOffering)
            .where(
                CourseOffering.instructor_id == instructor_id,
                CourseOffering.deleted_at.is_(None),
            )
            .order_by(CourseOffering.created_at.desc())
        )
        return list(rows)

    async def set_status(self, *, offering_id: uuid.UUID, status: str) -> CourseOffering:
        """گذار وضعیت ارائه. حذف ارائهٔ دارای ثبت‌نام فعال ممنوع است (FR-EDU-01)."""
        offering = await self.offering(offering_id)
        if status == "ARCHIVED":
            active = int(
                await self.session.scalar(
                    select(func.count()).where(
                        Enrollment.offering_id == offering_id,
                        Enrollment.status == "ACTIVE",
                    )
                )
                or 0
            )
            if active:
                raise Conflict(f"این ارائه {active} دانشجوی فعال دارد؛ اول درس را ببندید.")
        offering.status = status
        await self.session.commit()
        return offering

    async def set_grading_policy(
        self, *, offering_id: uuid.UUID, policy: dict[str, int]
    ) -> CourseOffering:
        """§4.4 — مجموع وزن‌ها باید ۱۰۰ باشد. قید در اپلیکیشن است، نه SQL."""
        unknown = set(policy) - set(GRADING_POLICY_KEYS)
        if unknown:
            raise ValidationFailed(f"کلید ناشناخته در سیاست نمره: {', '.join(sorted(unknown))}")
        total = sum(policy.values())
        if total != GRADING_POLICY_TOTAL:
            raise ValidationFailed(f"مجموع وزن‌ها باید ۱۰۰ باشد، نه {total}.")
        offering = await self.offering(offering_id)
        offering.grading_policy = dict(policy)
        await self.session.commit()
        return offering

    # ── هفته — FR-EDU-02 ───────────────────────────────────────────────
    async def upsert_week(self, *, offering_id: uuid.UUID, draft: WeekDraft) -> CourseWeek:
        """ساخت یا ویرایش هفته. شمارهٔ هفته کلید است، نه شناسه.

        استاد در ذهنش «هفتهٔ ۵» دارد، نه یک UUID؛ همین باعث می‌شود
        ویرایش و همگام‌سازی برنامهٔ درسی بی‌اثر در تکرار باشد.
        """
        if not 1 <= draft.week_number <= MAX_WEEK_NUMBER:
            raise ValidationFailed(f"شمارهٔ هفته باید بین ۱ تا {MAX_WEEK_NUMBER} باشد.")
        await self.offering(offering_id)

        week = await self.session.scalar(
            select(CourseWeek).where(
                CourseWeek.offering_id == offering_id,
                CourseWeek.week_number == draft.week_number,
            )
        )
        if week is None:
            week = CourseWeek(
                offering_id=offering_id, week_number=draft.week_number, title_fa=draft.title_fa
            )
            self.session.add(week)

        week.title_fa = draft.title_fa
        week.description = draft.description
        week.objectives = draft.objectives
        week.publish_at = draft.publish_at
        await self.session.commit()
        return week

    async def week_of(self, offering_id: uuid.UUID, week_id: uuid.UUID) -> CourseWeek:
        week = await self.session.get(CourseWeek, week_id)
        # §6.4 قاعدهٔ ۴: هفتهٔ ارائهٔ دیگر برای این استاد وجود ندارد.
        if week is None or week.offering_id != offering_id:
            raise NotFound("این هفته پیدا نشد.")
        return week

    async def publish_week(self, *, week_id: uuid.UUID, at: datetime | None = None) -> CourseWeek:
        """انتشار فوری یا زمان‌بندی‌شده — FR-EDU-02.

        `at` در آینده یعنی «فعلاً پیش‌نویس بماند، کار پس‌زمینه منتشرش
        کند»؛ گذشته یا خالی یعنی همین حالا.
        """
        week = await self.session.get(CourseWeek, week_id)
        if week is None:
            raise NotFound("این هفته پیدا نشد.")

        now = _now()
        first_time = week.published_at is None
        if at is not None and at > now:
            week.publish_at = at
            week.status = "DRAFT"
        else:
            week.status = "PUBLISHED"
            week.published_at = week.published_at or now
            week.publish_at = None
            # بازانتشار هفته‌ای که یک بار منتشر شده، کلاس را دوباره خبر نمی‌کند.
            if first_time:
                await events.publish(self.session, events.WeekPublished(week_id=week.id))
        await self.session.commit()
        log.info("week_published", week_id=str(week_id), status=week.status)
        return week

    async def due_weeks(self, *, now: datetime | None = None) -> list[CourseWeek]:
        """هفته‌هایی که زمان انتشارشان رسیده — ورودی کار پس‌زمینه."""
        moment = now or _now()
        rows = await self.session.scalars(
            select(CourseWeek).where(
                CourseWeek.status == "DRAFT",
                CourseWeek.publish_at.is_not(None),
                CourseWeek.publish_at <= moment,
            )
        )
        return list(rows)

    # ── منبع — FR-EDU-03 ───────────────────────────────────────────────
    async def add_resource(
        self, *, offering_id: uuid.UUID, week_id: uuid.UUID, draft: ResourceDraft
    ) -> Resource:
        await self.week_of(offering_id, week_id)
        if draft.file_id is None and not draft.external_url:
            raise ValidationFailed("منبع باید فایل یا نشانی بیرونی داشته باشد.")
        resource = Resource(
            week_id=week_id,
            kind=draft.kind,
            title_fa=draft.title_fa,
            description=draft.description,
            file_id=draft.file_id,
            external_url=draft.external_url,
            duration_sec=draft.duration_sec,
            is_downloadable=draft.is_downloadable,
            is_required=draft.is_required,
            sort_order=draft.sort_order,
        )
        self.session.add(resource)
        await self.session.commit()
        return resource

    async def remove_resource(self, *, offering_id: uuid.UUID, resource_id: uuid.UUID) -> None:
        resource = await self.session.get(Resource, resource_id)
        if resource is None:
            raise NotFound("این منبع پیدا نشد.")
        await self.week_of(offering_id, resource.week_id)
        await self.session.delete(resource)
        await self.session.commit()

    # ── پیوند کتابخانه به هفته — ADR-0008 ──────────────────────────────
    async def link_material(
        self,
        *,
        offering_id: uuid.UUID,
        week_id: uuid.UUID,
        material_id: uuid.UUID,
        section: str | None = None,
        is_required: bool = True,
        sort_order: int = 0,
    ) -> None:
        """بستن یک کتاب یا جزوهٔ کتابخانه به یک هفته.

        ماده باید از **همان درس** باشد: کتابخانهٔ درس الف در هفتهٔ درس ب
        جایی ندارد.
        """
        week = await self.week_of(offering_id, week_id)
        offering = await self.offering(week.offering_id)
        material = await self.session.get(CourseMaterial, material_id)
        if material is None or material.deleted_at is not None:
            raise NotFound("این محتوا در کتابخانه پیدا نشد.")
        if material.course_id != offering.course_id:
            raise ValidationFailed("این محتوا به کتابخانهٔ همین درس تعلق ندارد.")

        await self.session.execute(
            insert(WeekMaterial)
            .values(
                week_id=week_id,
                material_id=material_id,
                section=section,
                is_required=is_required,
                sort_order=sort_order,
            )
            .on_conflict_do_update(
                index_elements=["week_id", "material_id"],
                set_={"section": section, "is_required": is_required, "sort_order": sort_order},
            )
        )
        await self.session.commit()

    async def unlink_material(
        self, *, offering_id: uuid.UUID, week_id: uuid.UUID, material_id: uuid.UUID
    ) -> None:
        await self.week_of(offering_id, week_id)
        await self.session.execute(
            delete(WeekMaterial).where(
                WeekMaterial.week_id == week_id, WeekMaterial.material_id == material_id
            )
        )
        await self.session.commit()

    # ── کپی از ارائهٔ قبلی — FR-EDU-01 ─────────────────────────────────
    async def copy_weeks_from(
        self, *, target_offering_id: uuid.UUID, source_offering_id: uuid.UUID
    ) -> int:
        """«کپی از ارائهٔ قبلی» — یک دکمه، همان چیزی که سند خواسته.

        چه کپی می‌شود: ساختار هفته‌ها، منابع، و پیوند کتابخانه.
        چه کپی **نمی‌شود**: وضعیت انتشار و تاریخ‌ها — محتوای نیم‌سال
        گذشته نباید روز اول ترم تازه یک‌جا منتشر شود؛ و پیشرفت
        دانشجویان، که به آن‌ها تعلق دارد نه به ارائه.

        هفته‌ای که در مقصد هست، دست‌نخورده می‌ماند: کپی افزودنی است.
        """
        target = await self.offering(target_offering_id)
        source = await self.offering(source_offering_id)
        if target.course_id != source.course_id:
            raise ValidationFailed("فقط از ارائهٔ دیگری از همین درس می‌توان کپی کرد.")

        existing = set(
            await self.session.scalars(
                select(CourseWeek.week_number).where(CourseWeek.offering_id == target_offering_id)
            )
        )
        source_weeks = list(
            await self.session.scalars(
                select(CourseWeek)
                .where(CourseWeek.offering_id == source_offering_id)
                .order_by(CourseWeek.week_number)
            )
        )

        copied = 0
        for src in source_weeks:
            if src.week_number in existing:
                continue
            new_week = CourseWeek(
                offering_id=target_offering_id,
                week_number=src.week_number,
                title_fa=src.title_fa,
                description=src.description,
                objectives=src.objectives,
                status="DRAFT",
            )
            self.session.add(new_week)
            await self.session.flush()

            for resource in await self.session.scalars(
                select(Resource).where(Resource.week_id == src.id)
            ):
                self.session.add(
                    Resource(
                        week_id=new_week.id,
                        kind=resource.kind,
                        title_fa=resource.title_fa,
                        description=resource.description,
                        file_id=resource.file_id,
                        external_url=resource.external_url,
                        duration_sec=resource.duration_sec,
                        is_downloadable=resource.is_downloadable,
                        is_required=resource.is_required,
                        sort_order=resource.sort_order,
                    )
                )
            for link in await self.session.scalars(
                select(WeekMaterial).where(WeekMaterial.week_id == src.id)
            ):
                self.session.add(
                    WeekMaterial(
                        week_id=new_week.id,
                        material_id=link.material_id,
                        section=link.section,
                        is_required=link.is_required,
                        sort_order=link.sort_order,
                    )
                )
            copied += 1

        await self.session.commit()
        log.info(
            "offering_content_copied",
            target=str(target_offering_id),
            source=str(source_offering_id),
            weeks=copied,
        )
        return copied

    # ── اعلان — FR-EDU-06 ──────────────────────────────────────────────
    async def publish_announcement(
        self,
        *,
        offering_id: uuid.UUID,
        author_id: uuid.UUID,
        title: str,
        body: str,
        priority: str = "NORMAL",
        expires_at: datetime | None = None,
    ) -> Announcement:
        await self.offering(offering_id)
        announcement = Announcement(
            offering_id=offering_id,
            author_id=author_id,
            title=title,
            body=body,
            priority=priority,
            expires_at=expires_at,
        )
        self.session.add(announcement)
        await self.session.flush()
        # FR-EDU-06 — URGENT علاوه بر اعلان داخلی، پیامک و پیام‌رسان هم دارد.
        await events.publish(
            self.session, events.AnnouncementPublished(announcement_id=announcement.id)
        )
        await self.session.commit()
        log.info("announcement_published", offering_id=str(offering_id), priority=priority)
        return announcement

    # ── حضور و غیاب — FR-EDU-05 ────────────────────────────────────────
    async def record_attendance(
        self,
        *,
        offering_id: uuid.UUID,
        held_on: date,
        entries: list[AttendanceEntry],
        recorded_by: uuid.UUID,
        week_number: int | None = None,
        topic: str | None = None,
    ) -> int:
        """ثبت گروهی حضور یک جلسه — یک درخواست برای کل کلاس.

        جلسه با (ارائه، تاریخ) یکتاست، پس ثبت دوبارهٔ همان روز اصلاح
        است نه جلسهٔ دوم؛ و هر ردیف حضور با `ON CONFLICT` به‌روز می‌شود.
        """
        await self.offering(offering_id)

        session_id = await self.session.scalar(
            insert(ClassSession)
            .values(offering_id=offering_id, held_on=held_on, week_number=week_number, topic=topic)
            .on_conflict_do_update(
                constraint="uq_class_sessions_offering_held_on",
                set_={"week_number": week_number, "topic": topic},
            )
            .returning(ClassSession.id)
        )
        if session_id is None:  # pragma: no cover — DO UPDATE همیشه برمی‌گرداند
            raise Conflict("ثبت جلسه انجام نشد.")

        if not entries:
            await self.session.commit()
            return 0

        enrolled = set(
            await self.session.scalars(
                select(Enrollment.student_id).where(
                    Enrollment.offering_id == offering_id,
                    Enrollment.status.in_(("ACTIVE", "COMPLETED")),
                )
            )
        )
        outsiders = [e.student_id for e in entries if e.student_id not in enrolled]
        if outsiders:
            raise ValidationFailed("برای دانشجویی که در این درس نیست، حضور ثبت نمی‌شود.")

        await self.session.execute(
            insert(AttendanceRecord)
            .values(
                [
                    {
                        "session_id": session_id,
                        "student_id": e.student_id,
                        "status": e.status,
                        "note": e.note,
                        "recorded_by": recorded_by,
                    }
                    for e in entries
                ]
            )
            .on_conflict_do_update(
                index_elements=["session_id", "student_id"],
                set_={
                    "status": insert(AttendanceRecord).excluded.status,
                    "note": insert(AttendanceRecord).excluded.note,
                    "recorded_by": recorded_by,
                },
            )
        )
        await events.publish(
            self.session,
            events.AttendanceRecorded(
                offering_id=offering_id,
                student_ids=tuple(dict.fromkeys(e.student_id for e in entries)),
            ),
        )
        await self.session.commit()
        log.info("attendance_recorded", offering_id=str(offering_id), count=len(entries))
        return len(entries)


def _now() -> datetime:
    return datetime.now(UTC)


__all__ = [
    "GRADING_POLICY_KEYS",
    "AttendanceEntry",
    "ResourceDraft",
    "TeachingService",
    "WeekDraft",
]
