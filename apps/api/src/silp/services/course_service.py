"""سمت خواندن آموزش — ویترین درس، ارائه، هفته، کتابخانه و پیشرفت.

مرجع: §5.5، FR-EDU-01 تا FR-EDU-04.

سه قاعده که در همهٔ توابع این فایل رعایت شده‌اند:

۱. **فیلتر در سطح کوئری** (§6.4 قاعدهٔ ۳) — هفتهٔ `DRAFT` برای دانشجو
   اصلاً از پایگاه‌داده بیرون نمی‌آید، نه اینکه بیرون بیاید و در پایتون
   حذف شود.
۲. **بدون N+1** (§5.14) — شمارش منابع، پیشرفت، و سنجش دسترسی همه
   دسته‌ای‌اند.
۳. **سنجش دسترسی همیشه همراه داده می‌آید** — هر مادهٔ کتابخانه با
   `AccessDecision` خودش برمی‌گردد، تا رابط کاربری قفل و دلیلش را
   نسازد، فقط نشان دهد (ADR-0009).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import Select, and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from silp.core.exceptions import NotFound, WeekNotPublished
from silp.core.permissions import CurrentUser
from silp.models.education import (
    Announcement,
    Course,
    CourseMaterial,
    CourseOffering,
    CourseWeek,
    Enrollment,
    Resource,
    ResourceProgress,
    Term,
    WeekMaterial,
)
from silp.services.entitlement_service import (
    AccessDecision,
    EntitlementService,
    decide,
)


@dataclass(frozen=True, slots=True)
class CourseCard:
    """یک درس در ویترین — §3.2."""

    course: Course
    material_count: int
    free_material_count: int
    open_offering_count: int


@dataclass(frozen=True, slots=True)
class MaterialView:
    """مادهٔ کتابخانه به‌همراه سنجش دسترسی همین کاربر."""

    material: CourseMaterial
    access: AccessDecision
    section: str | None = None
    is_required: bool = True


@dataclass(frozen=True, slots=True)
class WeekCard:
    week: CourseWeek
    resource_count: int
    material_count: int
    completed_count: int

    @property
    def progress_percent(self) -> int:
        if self.resource_count == 0:
            return 0
        return round(100 * self.completed_count / self.resource_count)


@dataclass(frozen=True, slots=True)
class WeekDetail:
    week: CourseWeek
    resources: list[tuple[Resource, ResourceProgress | None]]
    materials: list[MaterialView]


@dataclass(frozen=True, slots=True)
class OfferingOverview:
    offering: CourseOffering
    course: Course
    term: Term
    enrollment: Enrollment | None
    weeks: list[WeekCard]
    announcements: list[Announcement]
    active_students: int

    @property
    def progress_percent(self) -> int:
        total = sum(w.resource_count for w in self.weeks)
        if total == 0:
            return 0
        done = sum(w.completed_count for w in self.weeks)
        return round(100 * done / total)

    @property
    def current_week(self) -> CourseWeek | None:
        """آخرین هفتهٔ منتشرشده — «از کجا ادامه بدهم» روی داشبورد."""
        published = [w.week for w in self.weeks if w.week.status == "PUBLISHED"]
        return published[-1] if published else None


class CourseService:
    def __init__(self, session: AsyncSession, entitlements: EntitlementService) -> None:
        self.session = session
        self.entitlements = entitlements

    # ── ویترین عمومی — §5.5 `GET /courses` ─────────────────────────────
    async def list_courses(
        self,
        *,
        q: str | None = None,
        degree_level: str | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[CourseCard], int]:
        """دروس فعال، با شمار محتوا. برای مهمان هم کار می‌کند."""
        base = select(Course).where(Course.deleted_at.is_(None), Course.is_active.is_(True))
        if degree_level:
            base = base.where(Course.degree_level == degree_level)
        if q and q.strip():
            # جستجوی فارسی روی ستون تولیدشده — §4.11، نه ILIKE '%…%'.
            base = base.where(Course.title_norm.op("%")(func.fa_normalize(q.strip())))

        total = await self.session.scalar(select(func.count()).select_from(base.subquery()))
        rows = await self.session.scalars(
            base.order_by(Course.title_fa).offset(offset).limit(limit)
        )
        courses = list(rows)
        if not courses:
            return [], int(total or 0)

        counts = await self._material_counts([c.id for c in courses])
        offerings = await self._open_offering_counts([c.id for c in courses])
        cards = [
            CourseCard(
                course=course,
                material_count=counts.get(course.id, (0, 0))[0],
                free_material_count=counts.get(course.id, (0, 0))[1],
                open_offering_count=offerings.get(course.id, 0),
            )
            for course in courses
        ]
        return cards, int(total or 0)

    async def _material_counts(
        self, course_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, tuple[int, int]]:
        """(همهٔ مواد منتشرشده، موادی که برای همه آزادند) — یک کوئری."""
        rows = await self.session.execute(
            select(
                CourseMaterial.course_id,
                func.count(),
                func.count().filter(CourseMaterial.access_tier == "PUBLIC"),
            )
            .where(
                CourseMaterial.course_id.in_(course_ids),
                CourseMaterial.status == "PUBLISHED",
                CourseMaterial.deleted_at.is_(None),
            )
            .group_by(CourseMaterial.course_id)
        )
        return {course_id: (int(total), int(free)) for course_id, total, free in rows}

    async def _open_offering_counts(self, course_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
        rows = await self.session.execute(
            select(CourseOffering.course_id, func.count())
            .where(
                CourseOffering.course_id.in_(course_ids),
                CourseOffering.status.in_(("OPEN", "IN_PROGRESS")),
                CourseOffering.deleted_at.is_(None),
            )
            .group_by(CourseOffering.course_id)
        )
        return {course_id: int(count) for course_id, count in rows}

    # ── جزئیات درس — §5.5 `GET /courses/{slug}` ────────────────────────
    async def course_by_slug(self, slug: str) -> Course:
        course = await self.session.scalar(
            select(Course).where(
                Course.slug == slug, Course.deleted_at.is_(None), Course.is_active.is_(True)
            )
        )
        if course is None:
            raise NotFound("درسی با این نشانی پیدا نشد.")
        return course

    async def library_of(self, course: Course, user: CurrentUser | None) -> list[MaterialView]:
        """کتابخانهٔ درس، هر ماده با سنجش دسترسی همین کاربر — ADR-0008/0009.

        مادهٔ بی‌دسترسی **حذف نمی‌شود**: کاربر باید ببیند چه چیزی هست و
        با اشتراک چه چیزی باز می‌شود. عنوان و توضیح آزادند؛ چیزی که پشت
        قفل می‌ماند فقط لینک دانلود است.
        """
        materials = list(
            await self.session.scalars(
                select(CourseMaterial)
                .where(
                    CourseMaterial.course_id == course.id,
                    CourseMaterial.status == "PUBLISHED",
                    CourseMaterial.deleted_at.is_(None),
                )
                .order_by(CourseMaterial.sort_order, CourseMaterial.title_fa)
            )
        )
        ctx = await self.entitlements.context_for(user, course_ids=[course.id])
        return [
            MaterialView(
                material=m,
                access=decide(course_id=course.id, tier=m.access_tier, ctx=ctx),
            )
            for m in materials
        ]

    async def offerings_of(self, course_id: uuid.UUID) -> list[tuple[CourseOffering, Term]]:
        rows = await self.session.execute(
            select(CourseOffering, Term)
            .join(Term, Term.id == CourseOffering.term_id)
            .where(
                CourseOffering.course_id == course_id,
                CourseOffering.status.in_(("OPEN", "IN_PROGRESS")),
                CourseOffering.deleted_at.is_(None),
            )
            .order_by(Term.starts_on.desc())
        )
        return list(rows.tuples())

    # ── ارائه‌ها — §5.5 `GET /offerings` ───────────────────────────────
    async def open_offerings(
        self, *, term_id: uuid.UUID | None = None
    ) -> list[tuple[CourseOffering, Course, Term]]:
        stmt = (
            select(CourseOffering, Course, Term)
            .join(Course, Course.id == CourseOffering.course_id)
            .join(Term, Term.id == CourseOffering.term_id)
            .where(
                CourseOffering.status == "OPEN",
                CourseOffering.deleted_at.is_(None),
                Course.deleted_at.is_(None),
            )
        )
        if term_id:
            stmt = stmt.where(CourseOffering.term_id == term_id)
        rows = await self.session.execute(stmt.order_by(Term.starts_on.desc(), Course.title_fa))
        return list(rows.tuples())

    async def my_offerings(self, user_id: uuid.UUID) -> list[OfferingOverview]:
        """«دروس من» — §3.4. هر درس با نوار پیشرفت، بدون N+1."""
        rows = await self.session.execute(
            select(Enrollment, CourseOffering, Course, Term)
            .join(CourseOffering, CourseOffering.id == Enrollment.offering_id)
            .join(Course, Course.id == CourseOffering.course_id)
            .join(Term, Term.id == CourseOffering.term_id)
            .where(
                Enrollment.student_id == user_id,
                Enrollment.status.in_(("PENDING", "ACTIVE", "COMPLETED")),
                CourseOffering.deleted_at.is_(None),
            )
            .order_by(Term.starts_on.desc(), Course.title_fa)
        )
        records = list(rows)
        if not records:
            return []

        offering_ids = [o.id for _, o, _, _ in records]
        weeks_by_offering = await self._week_cards(offering_ids, user_id, published_only=True)
        counts = await self.active_student_counts(offering_ids)

        return [
            OfferingOverview(
                offering=offering,
                course=course,
                term=term,
                enrollment=enrollment,
                weeks=weeks_by_offering.get(offering.id, []),
                announcements=[],
                active_students=counts.get(offering.id, 0),
            )
            for enrollment, offering, course, term in records
        ]

    async def offering_overview(
        self, offering_id: uuid.UUID, user: CurrentUser
    ) -> OfferingOverview:
        """نمای کلی یک ارائه — §5.5 `GET /offerings/{id}`.

        پیش‌نیاز دسترسی را اینجا اعمال نمی‌کند؛ مسیر با
        `require_enrollment` این کار را می‌کند تا بررسی یک‌جا بماند.
        """
        row = (
            await self.session.execute(
                select(CourseOffering, Course, Term)
                .join(Course, Course.id == CourseOffering.course_id)
                .join(Term, Term.id == CourseOffering.term_id)
                .where(CourseOffering.id == offering_id, CourseOffering.deleted_at.is_(None))
            )
        ).first()
        if row is None:
            raise NotFound("این ارائه پیدا نشد.")
        offering, course, term = row

        enrollment = await self.enrollment_of(offering_id, user.id)
        # استاد و دستیار همهٔ هفته‌ها را می‌بینند، دانشجو فقط منتشرشده‌ها.
        published_only = not await self._may_see_drafts(offering, user)
        weeks = (await self._week_cards([offering_id], user.id, published_only=published_only)).get(
            offering_id, []
        )
        announcements = await self.announcements_of(offering_id)
        counts = await self.active_student_counts([offering_id])

        return OfferingOverview(
            offering=offering,
            course=course,
            term=term,
            enrollment=enrollment,
            weeks=weeks,
            announcements=announcements,
            active_students=counts.get(offering_id, 0),
        )

    async def _may_see_drafts(self, offering: CourseOffering, user: CurrentUser) -> bool:
        from silp.core.permissions import Permission
        from silp.services import authz

        if offering.instructor_id == user.id:
            return True
        return await authz.has_permission(
            self.session, user, Permission.COURSE_WEEK_VIEW_DRAFT, offering.id
        )

    async def enrollment_of(self, offering_id: uuid.UUID, user_id: uuid.UUID) -> Enrollment | None:
        enrollment: Enrollment | None = await self.session.scalar(
            select(Enrollment).where(
                Enrollment.offering_id == offering_id, Enrollment.student_id == user_id
            )
        )
        return enrollment

    async def active_student_counts(self, offering_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
        """شمار دانشجوی فعال هر ارائه — یک کوئری برای یک فهرست (§5.14)."""
        if not offering_ids:
            return {}
        rows = await self.session.execute(
            select(Enrollment.offering_id, func.count())
            .where(
                Enrollment.offering_id.in_(offering_ids),
                Enrollment.status.in_(("ACTIVE", "COMPLETED")),
            )
            .group_by(Enrollment.offering_id)
        )
        return {offering_id: int(count) for offering_id, count in rows}

    # ── هفته‌ها ────────────────────────────────────────────────────────
    def _visible_weeks(
        self, offering_ids: list[uuid.UUID], *, published_only: bool
    ) -> Select[tuple[CourseWeek]]:
        stmt = select(CourseWeek).where(CourseWeek.offering_id.in_(offering_ids))
        if published_only:
            stmt = stmt.where(CourseWeek.status == "PUBLISHED")
        else:
            stmt = stmt.where(CourseWeek.status != "ARCHIVED")
        return stmt.order_by(CourseWeek.offering_id, CourseWeek.week_number)

    async def _week_cards(
        self, offering_ids: list[uuid.UUID], user_id: uuid.UUID, *, published_only: bool
    ) -> dict[uuid.UUID, list[WeekCard]]:
        weeks = list(
            await self.session.scalars(
                self._visible_weeks(offering_ids, published_only=published_only)
            )
        )
        if not weeks:
            return {}
        week_ids = [w.id for w in weeks]

        resource_counts = {
            week_id: int(count)
            for week_id, count in await self.session.execute(
                select(Resource.week_id, func.count())
                .where(Resource.week_id.in_(week_ids))
                .group_by(Resource.week_id)
            )
        }
        material_counts = {
            week_id: int(count)
            for week_id, count in await self.session.execute(
                select(WeekMaterial.week_id, func.count())
                .where(WeekMaterial.week_id.in_(week_ids))
                .group_by(WeekMaterial.week_id)
            )
        }
        # پیشرفت: تعداد منابع تکمیل‌شدهٔ همین کاربر در هر هفته — یک کوئری.
        completed = {
            week_id: int(count)
            for week_id, count in await self.session.execute(
                select(Resource.week_id, func.count())
                .join(
                    ResourceProgress,
                    and_(
                        ResourceProgress.resource_id == Resource.id,
                        ResourceProgress.user_id == user_id,
                    ),
                )
                .where(Resource.week_id.in_(week_ids), ResourceProgress.status == "COMPLETED")
                .group_by(Resource.week_id)
            )
        }

        result: dict[uuid.UUID, list[WeekCard]] = {}
        for week in weeks:
            result.setdefault(week.offering_id, []).append(
                WeekCard(
                    week=week,
                    resource_count=resource_counts.get(week.id, 0),
                    material_count=material_counts.get(week.id, 0),
                    completed_count=completed.get(week.id, 0),
                )
            )
        return result

    async def week_cards(
        self, offering_id: uuid.UUID, user_id: uuid.UUID, *, include_drafts: bool = False
    ) -> list[WeekCard]:
        """هفته‌های یک ارائه با شمار و پیشرفت — نمای استاد یا دانشجو."""
        cards = await self._week_cards([offering_id], user_id, published_only=not include_drafts)
        return cards.get(offering_id, [])

    async def week_detail(
        self, offering_id: uuid.UUID, week_number: int, user: CurrentUser
    ) -> WeekDetail:
        """محتوای یک هفته — §5.5 `GET /offerings/{id}/weeks/{n}`."""
        offering = await self.session.get(CourseOffering, offering_id)
        if offering is None or offering.deleted_at is not None:
            raise NotFound("این ارائه پیدا نشد.")

        week = await self.session.scalar(
            select(CourseWeek).where(
                CourseWeek.offering_id == offering_id, CourseWeek.week_number == week_number
            )
        )
        if week is None:
            raise NotFound("این هفته پیدا نشد.")
        if week.status != "PUBLISHED" and not await self._may_see_drafts(offering, user):
            raise WeekNotPublished

        resources = list(
            await self.session.scalars(
                select(Resource)
                .where(Resource.week_id == week.id)
                .order_by(Resource.sort_order, Resource.title_fa)
            )
        )
        progress = await self._progress_map(user.id, [r.id for r in resources])

        materials = await self._week_materials(week.id, offering.course_id, user)
        return WeekDetail(
            week=week,
            resources=[(r, progress.get(r.id)) for r in resources],
            materials=materials,
        )

    async def _progress_map(
        self, user_id: uuid.UUID, resource_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, ResourceProgress]:
        if not resource_ids:
            return {}
        rows = await self.session.scalars(
            select(ResourceProgress).where(
                ResourceProgress.user_id == user_id,
                ResourceProgress.resource_id.in_(resource_ids),
            )
        )
        return {row.resource_id: row for row in rows}

    async def _week_materials(
        self, week_id: uuid.UUID, course_id: uuid.UUID, user: CurrentUser | None
    ) -> list[MaterialView]:
        rows = await self.session.execute(
            select(CourseMaterial, WeekMaterial)
            .join(WeekMaterial, WeekMaterial.material_id == CourseMaterial.id)
            .where(
                WeekMaterial.week_id == week_id,
                CourseMaterial.status == "PUBLISHED",
                CourseMaterial.deleted_at.is_(None),
            )
            .order_by(WeekMaterial.sort_order, CourseMaterial.title_fa)
        )
        pairs = list(rows)
        if not pairs:
            return []
        ctx = await self.entitlements.context_for(user, course_ids=[course_id])
        return [
            MaterialView(
                material=material,
                access=decide(course_id=course_id, tier=material.access_tier, ctx=ctx),
                section=link.section,
                is_required=link.is_required,
            )
            for material, link in pairs
        ]

    # ── اعلانات — FR-EDU-06 ────────────────────────────────────────────
    async def announcements_of(
        self, offering_id: uuid.UUID, *, limit: int = 20
    ) -> list[Announcement]:
        now = datetime.now(UTC)
        rows = await self.session.scalars(
            select(Announcement)
            .where(
                Announcement.offering_id == offering_id,
                (Announcement.expires_at.is_(None)) | (Announcement.expires_at > now),
            )
            .order_by(Announcement.published_at.desc())
            .limit(limit)
        )
        return list(rows)

    # ── دسترسی به یک ماده برای دانلود ──────────────────────────────────
    async def material_with_course(self, material_id: uuid.UUID) -> tuple[CourseMaterial, Course]:
        row = (
            await self.session.execute(
                select(CourseMaterial, Course)
                .join(Course, Course.id == CourseMaterial.course_id)
                .where(
                    CourseMaterial.id == material_id,
                    CourseMaterial.deleted_at.is_(None),
                    CourseMaterial.status == "PUBLISHED",
                )
            )
        ).first()
        if row is None:
            raise NotFound("این محتوا پیدا نشد.")
        material, course = row
        return material, course


__all__ = [
    "CourseCard",
    "CourseService",
    "MaterialView",
    "OfferingOverview",
    "WeekCard",
    "WeekDetail",
]
