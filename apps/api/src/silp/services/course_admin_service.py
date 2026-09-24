"""تعریف درس، نیم‌سال و ارائه — `/admin/courses` §3.6، FR-EDU-01، ADR-0020.

تا امروز ارائهٔ تازه فقط با `seed_launch` ساخته می‌شد؛ یعنی مدیر آموزشی برای
هر ترم به کسی نیاز داشت که روی سرور اسکریپت اجرا کند. این سرویس همان کار را
پشت پنل می‌برد، با سه مرز:

* **درسِ پوشه‌ای مال پوشه است.** درسی که `source_dir` دارد را
  `sync_courses` در هر اجرا از `course.yml` بازنویسی می‌کند؛ ویرایشش در پنل
  یعنی تغییری که بی‌صدا در همگام‌سازی بعدی برمی‌گردد. پس فقط درسی که در پنل
  ساخته شده در پنل ویرایش می‌شود (۴۰۹ `COURSE_MANAGED_BY_FOLDER`).
* **ارائه را مدیر می‌سازد و به استاد می‌سپارد.** وضعیت، ظرفیت، کد و
  هفته‌ها پس از آن با خود استاد است (`/teach`، ADR-0019). اینجا فقط آنچه
  استاد نمی‌تواند: درس، نیم‌سال و **چه کسی** استاد است.
* **حذف فقط برای اشتباه.** ارائه‌ای که ثبت‌نام، آزمون، جلسه، اعلان، پروژه یا
  امتیاز دارد حذف نمی‌شود — بایگانی می‌شود (FR-EDU-01). نیم‌سالی که ارائه یا
  امتیاز دارد هم.

هر نوشتن یک ردیف حسابرسی در همان تراکنش دارد: سپردن ارائه به استاد، اختیار
نمرهٔ نهایی دادن است.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from silp.content.manifest import ManifestError, load_manifest
from silp.content.sync import apply_syllabus
from silp.core.exceptions import Conflict, NotFound, ValidationFailed
from silp.core.logging import get_logger
from silp.core.permissions import CurrentUser, ScopeType
from silp.domain import audit as audit_codes
from silp.domain.gamification.formulas import LOCAL_TZ
from silp.models.education import (
    Announcement,
    ClassSession,
    Course,
    CourseMaterial,
    CourseOffering,
    CourseWeek,
    Enrollment,
    Term,
)
from silp.models.gamification import PointEntry
from silp.models.identity import User, UserRole
from silp.models.project import Project
from silp.models.quiz import Quiz
from silp.services import authz
from silp.services.audit_service import AuditService
from silp.services.teaching_service import (
    MIN_ENROLLMENT_CODE,
    TeachingService,
    validate_grading_policy,
)

log = get_logger("silp.course_admin")

#: وزن پیش‌فرض نمره — همان که `seed_courses` برای بیشتر دروس گذاشته. استاد در
#: تنظیمات ارائه عوضش می‌کند.
DEFAULT_GRADING_POLICY: dict[str, int] = {
    "quiz": 30,
    "project": 50,
    "attendance": 10,
    "participation": 10,
}

WEEK_SOURCES = ("SYLLABUS", "OFFERING", "NONE")

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


def slug_from_code(code: str) -> str:
    """`TRAFFIC-ENG` ← `traffic-eng` — نشانی پیش‌فرض درس تازه."""
    return _SLUG_STRIP.sub("-", code.lower()).strip("-")


# ── ورودی‌ها ───────────────────────────────────────────────────────────
@dataclass(frozen=True, slots=True)
class TermDraft:
    code: str
    title_fa: str
    starts_on: date
    ends_on: date
    is_current: bool = False


@dataclass(frozen=True, slots=True)
class CourseDraft:
    code: str
    title_fa: str
    slug: str | None = None
    title_en: str | None = None
    description: str | None = None
    degree_level: str | None = None
    credits: int | None = None
    is_public: bool = False
    is_active: bool = True
    default_access_tier: str = "SUBSCRIBER"
    topics: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class OfferingDraft:
    course_id: uuid.UUID
    term_id: uuid.UUID
    instructor_id: uuid.UUID
    status: str = "DRAFT"
    capacity: int | None = None
    enrollment_code: str | None = None
    requires_approval: bool = False
    grading_policy: dict[str, int] | None = None
    weeks_from: str = "NONE"
    copy_from_offering_id: uuid.UUID | None = None


# ── خروجی‌ها ───────────────────────────────────────────────────────────
@dataclass(frozen=True, slots=True)
class TermRow:
    term: Term
    offering_count: int


@dataclass(frozen=True, slots=True)
class CourseRow:
    course: Course
    offering_count: int
    material_count: int
    #: شمار هفته‌های برنامهٔ درسی `course.yml`؛ `None` یعنی درس پوشه ندارد
    #: یا پوشه‌اش روی این سرور نیست.
    syllabus_weeks: int | None


@dataclass(frozen=True, slots=True)
class OfferingRow:
    offering: CourseOffering
    course: Course
    term: Term
    active_students: int
    pending_students: int
    week_count: int
    published_weeks: int


@dataclass(frozen=True, slots=True)
class CreatedOffering:
    offering: CourseOffering
    weeks_created: int


class CourseAdminService:
    def __init__(self, session: AsyncSession, *, courses_root: Path | None = None) -> None:
        self.session = session
        self.courses_root = courses_root
        self.audit = AuditService(session)

    # ── نیم‌سال ────────────────────────────────────────────────────────
    async def terms(self) -> list[TermRow]:
        counts = dict(
            (
                await self.session.execute(
                    select(CourseOffering.term_id, func.count())
                    .where(CourseOffering.deleted_at.is_(None))
                    .group_by(CourseOffering.term_id)
                )
            )
            .tuples()
            .all()
        )
        terms = await self.session.scalars(select(Term).order_by(Term.starts_on.desc()))
        return [TermRow(term=t, offering_count=int(counts.get(t.id, 0))) for t in terms]

    async def create_term(self, draft: TermDraft, *, actor: CurrentUser) -> Term:
        code = draft.code.strip()
        _check_dates(draft.starts_on, draft.ends_on)
        if await self.session.scalar(select(Term.id).where(Term.code == code)):
            raise Conflict(f"نیم‌سالی با کد «{code}» از قبل هست.", code="TERM_CODE_TAKEN")
        if draft.is_current:
            await self._clear_current()
        term = Term(
            code=code,
            title_fa=draft.title_fa.strip(),
            starts_on=draft.starts_on,
            ends_on=draft.ends_on,
            is_current=draft.is_current,
        )
        self.session.add(term)
        await self.session.flush()
        self.audit.stage(
            audit_codes.TERM_CREATED,
            actor=actor,
            entity_type="TERM",
            entity_id=term.id,
            after=_term_snapshot(term),
        )
        await self.session.commit()
        log.info("term_created", term_id=str(term.id), code=code)
        return term

    async def update_term(
        self, term_id: uuid.UUID, changes: dict[str, Any], *, actor: CurrentUser
    ) -> Term:
        term = await self._term(term_id)
        before = _term_snapshot(term)

        if "code" in changes and changes["code"].strip() != term.code:
            code = changes["code"].strip()
            taken = await self.session.scalar(
                select(Term.id).where(Term.code == code, Term.id != term.id)
            )
            if taken:
                raise Conflict(f"نیم‌سالی با کد «{code}» از قبل هست.", code="TERM_CODE_TAKEN")
            term.code = code
        if "title_fa" in changes:
            term.title_fa = changes["title_fa"].strip()
        starts_on = changes.get("starts_on", term.starts_on)
        ends_on = changes.get("ends_on", term.ends_on)
        _check_dates(starts_on, ends_on)
        term.starts_on, term.ends_on = starts_on, ends_on

        if changes.get("is_current") is True and not term.is_current:
            # ایندکس یکتای جزئی «فقط یک جاری» را می‌پاید؛ جاری قبلی باید پیش
            # از این ردیف در دیتابیس خاموش شود، نه در همان flush.
            await self._clear_current(except_id=term.id)
            term.is_current = True
        elif changes.get("is_current") is False:
            term.is_current = False

        after = _term_snapshot(term)
        if after != before:
            self.audit.stage(
                audit_codes.TERM_UPDATED,
                actor=actor,
                entity_type="TERM",
                entity_id=term.id,
                before={k: v for k, v in before.items() if after[k] != v},
                after={k: v for k, v in after.items() if before[k] != v},
            )
        await self.session.commit()
        await self.session.refresh(term)
        return term

    async def delete_term(self, term_id: uuid.UUID, *, actor: CurrentUser) -> None:
        term = await self._term(term_id)
        offerings = int(
            await self.session.scalar(select(func.count()).where(CourseOffering.term_id == term.id))
            or 0
        )
        points = int(
            await self.session.scalar(select(func.count()).where(PointEntry.term_id == term.id))
            or 0
        )
        if offerings or points:
            raise Conflict(
                "این نیم‌سال ارائه یا امتیاز ثبت‌شده دارد و حذف نمی‌شود.",
                code="TERM_IN_USE",
                details={"offerings": offerings, "point_entries": points},
            )
        self.audit.stage(
            audit_codes.TERM_DELETED,
            actor=actor,
            entity_type="TERM",
            entity_id=term.id,
            before=_term_snapshot(term),
        )
        await self.session.delete(term)
        await self.session.commit()

    async def _term(self, term_id: uuid.UUID) -> Term:
        term = await self.session.get(Term, term_id)
        if term is None:
            raise NotFound("این نیم‌سال پیدا نشد.")
        return term

    async def _clear_current(self, *, except_id: uuid.UUID | None = None) -> None:
        stmt = update(Term).where(Term.is_current.is_(True)).values(is_current=False)
        if except_id is not None:
            stmt = stmt.where(Term.id != except_id)
        await self.session.execute(stmt)

    # ── درس ────────────────────────────────────────────────────────────
    async def courses(
        self, *, q: str | None = None, course_id: uuid.UUID | None = None
    ) -> list[CourseRow]:
        stmt = select(Course).where(Course.deleted_at.is_(None))
        if course_id is not None:
            stmt = stmt.where(Course.id == course_id)
        if q and q.strip():
            raw = q.strip()
            stmt = stmt.where(
                Course.title_norm.like(func.concat("%", func.fa_normalize(raw), "%"))
                | Course.code.ilike(f"%{raw}%")
                | Course.slug.ilike(f"%{raw}%")
            )
        courses = list(
            await self.session.scalars(stmt.order_by(Course.is_active.desc(), Course.title_fa))
        )
        ids = [c.id for c in courses] or [uuid.UUID(int=0)]
        offerings = dict(
            (
                await self.session.execute(
                    select(CourseOffering.course_id, func.count())
                    .where(CourseOffering.course_id.in_(ids), CourseOffering.deleted_at.is_(None))
                    .group_by(CourseOffering.course_id)
                )
            )
            .tuples()
            .all()
        )
        materials = dict(
            (
                await self.session.execute(
                    select(CourseMaterial.course_id, func.count())
                    .where(
                        CourseMaterial.course_id.in_(ids),
                        CourseMaterial.deleted_at.is_(None),
                        CourseMaterial.status != "ARCHIVED",
                    )
                    .group_by(CourseMaterial.course_id)
                )
            )
            .tuples()
            .all()
        )
        return [
            CourseRow(
                course=c,
                offering_count=int(offerings.get(c.id, 0)),
                material_count=int(materials.get(c.id, 0)),
                syllabus_weeks=self._syllabus_size(c),
            )
            for c in courses
        ]

    async def create_course(self, draft: CourseDraft, *, actor: CurrentUser) -> Course:
        code = draft.code.strip().upper()
        slug = (draft.slug or slug_from_code(code)).strip().lower()
        await self._check_course_keys(code=code, slug=slug)
        course = Course(
            code=code,
            slug=slug,
            title_fa=draft.title_fa.strip(),
            title_en=_blank_to_none(draft.title_en),
            description=_blank_to_none(draft.description),
            degree_level=draft.degree_level,
            credits=draft.credits,
            is_public=draft.is_public,
            is_active=draft.is_active,
            default_access_tier=draft.default_access_tier,
            topics=[t.strip() for t in draft.topics if t.strip()],
        )
        self.session.add(course)
        await self.session.flush()
        self.audit.stage(
            audit_codes.COURSE_CREATED,
            actor=actor,
            entity_type="COURSE",
            entity_id=course.id,
            after=_course_snapshot(course),
        )
        await self.session.commit()
        await self.session.refresh(course)
        log.info("course_created", course_id=str(course.id), code=code)
        return course

    async def update_course(
        self, course_id: uuid.UUID, changes: dict[str, Any], *, actor: CurrentUser
    ) -> Course:
        course = await self._course(course_id)
        if course.source_dir:
            raise Conflict(
                f"این درس از پوشهٔ «Courses/{course.source_dir}» همگام می‌شود و هر تغییری "
                "اینجا در همگام‌سازی بعدی برمی‌گردد. course.yml همان پوشه را ویرایش کنید.",
                code="COURSE_MANAGED_BY_FOLDER",
            )
        before = _course_snapshot(course)
        code = changes["code"].strip().upper() if "code" in changes else course.code
        slug = changes["slug"].strip().lower() if "slug" in changes else course.slug
        if code != course.code or slug != course.slug:
            await self._check_course_keys(
                code=code if code != course.code else None,
                slug=slug if slug != course.slug else None,
                exclude=course.id,
            )
        course.code, course.slug = code, slug
        for name in ("title_fa",):
            if name in changes:
                setattr(course, name, changes[name].strip())
        for name in ("title_en", "description"):
            if name in changes:
                setattr(course, name, _blank_to_none(changes[name]))
        for name in ("degree_level", "credits", "is_public", "is_active", "default_access_tier"):
            if name in changes:
                setattr(course, name, changes[name])
        if "topics" in changes:
            course.topics = [t.strip() for t in changes["topics"] if t.strip()]

        after = _course_snapshot(course)
        if after != before:
            self.audit.stage(
                audit_codes.COURSE_UPDATED,
                actor=actor,
                entity_type="COURSE",
                entity_id=course.id,
                before={k: v for k, v in before.items() if after[k] != v},
                after={k: v for k, v in after.items() if before[k] != v},
            )
        await self.session.commit()
        await self.session.refresh(course)
        return course

    async def _course(self, course_id: uuid.UUID) -> Course:
        course = await self.session.get(Course, course_id)
        if course is None or course.deleted_at is not None:
            raise NotFound("این درس پیدا نشد.")
        return course

    async def _check_course_keys(
        self, *, code: str | None, slug: str | None, exclude: uuid.UUID | None = None
    ) -> None:
        """یکتایی کد و نشانی — روی **همهٔ** ردیف‌ها، چون قید دیتابیس هم حذف‌شده‌ها را می‌شمارد."""

        async def taken(column: Any, value: str) -> bool:
            stmt = select(Course.id).where(column == value)
            if exclude is not None:
                stmt = stmt.where(Course.id != exclude)
            return await self.session.scalar(stmt) is not None

        if code is not None and await taken(Course.code, code):
            raise Conflict(f"درسی با کد «{code}» از قبل هست.", code="COURSE_CODE_TAKEN")
        if slug is not None and await taken(Course.slug, slug):
            raise Conflict(f"درسی با نشانی «{slug}» از قبل هست.", code="COURSE_SLUG_TAKEN")

    def _course_dir(self, course: Course) -> Path | None:
        if not course.source_dir or self.courses_root is None:
            return None
        directory = self.courses_root / course.source_dir
        return directory if directory.is_dir() else None

    def _syllabus_size(self, course: Course) -> int | None:
        directory = self._course_dir(course)
        if directory is None:
            return None
        try:
            return len(load_manifest(directory).syllabus)
        except ManifestError as exc:  # مانیفست خراب نباید فهرست دروس را بخواباند.
            log.warning("manifest_unreadable", course=course.slug, error=str(exc))
            return None

    # ── ارائه ──────────────────────────────────────────────────────────
    async def offerings(
        self,
        *,
        term_id: uuid.UUID | None = None,
        course_id: uuid.UUID | None = None,
        status: str | None = None,
        offering_id: uuid.UUID | None = None,
    ) -> list[OfferingRow]:
        stmt = (
            select(CourseOffering, Course, Term)
            .join(Course, Course.id == CourseOffering.course_id)
            .join(Term, Term.id == CourseOffering.term_id)
            .where(CourseOffering.deleted_at.is_(None))
        )
        if offering_id is not None:
            stmt = stmt.where(CourseOffering.id == offering_id)
        if term_id is not None:
            stmt = stmt.where(CourseOffering.term_id == term_id)
        if course_id is not None:
            stmt = stmt.where(CourseOffering.course_id == course_id)
        if status:
            stmt = stmt.where(CourseOffering.status == status)
        rows = [
            row._tuple()
            for row in await self.session.execute(
                stmt.order_by(Term.starts_on.desc(), Course.title_fa, CourseOffering.created_at)
            )
        ]
        ids = [o.id for o, _, _ in rows] or [uuid.UUID(int=0)]
        students = {
            oid: (int(active), int(pending))
            for oid, active, pending in (
                await self.session.execute(
                    select(
                        Enrollment.offering_id,
                        func.count().filter(Enrollment.status.in_(("ACTIVE", "COMPLETED"))),
                        func.count().filter(Enrollment.status == "PENDING"),
                    )
                    .where(Enrollment.offering_id.in_(ids))
                    .group_by(Enrollment.offering_id)
                )
            ).tuples()
        }
        weeks = {
            oid: (int(total), int(published))
            for oid, total, published in (
                await self.session.execute(
                    select(
                        CourseWeek.offering_id,
                        func.count(),
                        func.count().filter(CourseWeek.status == "PUBLISHED"),
                    )
                    .where(CourseWeek.offering_id.in_(ids))
                    .group_by(CourseWeek.offering_id)
                )
            ).tuples()
        }
        return [
            OfferingRow(
                offering=offering,
                course=course,
                term=term,
                active_students=students.get(offering.id, (0, 0))[0],
                pending_students=students.get(offering.id, (0, 0))[1],
                week_count=weeks.get(offering.id, (0, 0))[0],
                published_weeks=weeks.get(offering.id, (0, 0))[1],
            )
            for offering, course, term in rows
        ]

    async def create_offering(self, draft: OfferingDraft, *, actor: CurrentUser) -> CreatedOffering:
        course = await self._course(draft.course_id)
        if not course.is_active:
            raise ValidationFailed("این درس غیرفعال است؛ اول فعالش کنید.", code="COURSE_INACTIVE")
        term = await self._term(draft.term_id)
        if term.ends_on < _today():
            raise ValidationFailed(
                f"«{term.title_fa}» تمام شده است؛ ارائه برای نیم‌سال جاری یا آینده تعریف می‌شود.",
                code="TERM_ENDED",
            )
        await self._require_instructor(draft.instructor_id)
        await self._check_unique(course.id, term.id, draft.instructor_id)
        if draft.status not in ("DRAFT", "OPEN"):
            raise ValidationFailed("ارائهٔ تازه پیش‌نویس یا باز برای ثبت‌نام است.")
        code = (draft.enrollment_code or "").strip() or None
        if code is not None and len(code) < MIN_ENROLLMENT_CODE:
            raise ValidationFailed(f"کد ثبت‌نام دست‌کم {MIN_ENROLLMENT_CODE} نویسه است.")
        policy = dict(draft.grading_policy or DEFAULT_GRADING_POLICY)
        validate_grading_policy(policy)

        # منبع هفته‌ها پیش از هر نوشتن سنجیده می‌شود تا خطا ارائهٔ نیمه‌کاره نگذارد.
        manifest = None
        if draft.weeks_from == "SYLLABUS":
            directory = self._course_dir(course)
            manifest = load_manifest(directory) if directory is not None else None
            if manifest is None or not manifest.syllabus:
                raise ValidationFailed(
                    "این درس برنامهٔ درسی در course.yml ندارد؛ هفته‌ها را از ارائهٔ قبلی "
                    "کپی کنید یا خالی بسازید.",
                    code="SYLLABUS_UNAVAILABLE",
                )
        elif draft.weeks_from == "OFFERING":
            if draft.copy_from_offering_id is None:
                raise ValidationFailed("ارائهٔ مبدأ را برای کپی هفته‌ها انتخاب کنید.")
            source = await self._offering(draft.copy_from_offering_id)
            if source.course_id != course.id:
                raise ValidationFailed("فقط از ارائهٔ دیگری از همین درس می‌توان کپی کرد.")
        elif draft.weeks_from != "NONE":
            raise ValidationFailed("منبع هفته‌ها نامعتبر است.")

        offering = CourseOffering(
            course_id=course.id,
            term_id=term.id,
            instructor_id=draft.instructor_id,
            status=draft.status,
            capacity=draft.capacity,
            enrollment_code=code,
            requires_approval=draft.requires_approval,
            grading_policy=policy,
        )
        self.session.add(offering)
        await self.session.flush()

        weeks_created = 0
        if manifest is not None:
            weeks_created = await apply_syllabus(
                self.session, offering_id=offering.id, manifest=manifest
            )
        elif draft.weeks_from == "OFFERING" and draft.copy_from_offering_id is not None:
            weeks_created = await TeachingService(self.session).stage_copy_weeks(
                target_offering_id=offering.id, source_offering_id=draft.copy_from_offering_id
            )

        self.audit.stage(
            audit_codes.OFFERING_CREATED,
            actor=actor,
            entity_type="OFFERING",
            entity_id=offering.id,
            after={**_offering_snapshot(offering), "weeks_created": weeks_created},
        )
        await self.session.commit()
        await self.session.refresh(offering)
        # نقش استاد از همین ردیف مشتق می‌شود و کش نقش ۶۰ ثانیه عمر دارد (§6.1).
        await authz.invalidate_roles(draft.instructor_id)
        log.info(
            "offering_created",
            offering_id=str(offering.id),
            instructor_id=str(draft.instructor_id),
            weeks=weeks_created,
        )
        return CreatedOffering(offering=offering, weeks_created=weeks_created)

    async def update_offering(
        self,
        offering_id: uuid.UUID,
        *,
        instructor_id: uuid.UUID | None = None,
        term_id: uuid.UUID | None = None,
        actor: CurrentUser,
    ) -> CourseOffering:
        """سپردن ارائه به استاد دیگر، یا بردنش به نیم‌سال دیگر.

        نیم‌سال فقط تا وقتی عوض می‌شود که کسی ثبت‌نام نکرده: دانشجویی که در
        «نیم‌سال اول» ثبت‌نام کرده، نباید درسش بی‌خبر به نیم‌سال دیگری برود.
        """
        offering = await self._offering(offering_id)
        before = _offering_snapshot(offering)
        previous_instructor = offering.instructor_id

        target_term = offering.term_id
        if term_id is not None and term_id != offering.term_id:
            term = await self._term(term_id)
            if term.ends_on < _today():
                raise ValidationFailed(f"«{term.title_fa}» تمام شده است.", code="TERM_ENDED")
            enrolled = int(
                await self.session.scalar(
                    select(func.count()).where(Enrollment.offering_id == offering.id)
                )
                or 0
            )
            if enrolled:
                raise Conflict(
                    f"این ارائه {enrolled} ثبت‌نام دارد و نیم‌سالش عوض نمی‌شود.",
                    code="OFFERING_HAS_ENROLLMENTS",
                )
            target_term = term.id

        target_instructor = offering.instructor_id
        if instructor_id is not None and instructor_id != offering.instructor_id:
            await self._require_instructor(instructor_id)
            target_instructor = instructor_id

        if (target_term, target_instructor) != (offering.term_id, offering.instructor_id):
            await self._check_unique(
                offering.course_id, target_term, target_instructor, exclude=offering.id
            )
        offering.term_id = target_term
        offering.instructor_id = target_instructor

        after = _offering_snapshot(offering)
        if after != before:
            self.audit.stage(
                audit_codes.OFFERING_UPDATED,
                actor=actor,
                entity_type="OFFERING",
                entity_id=offering.id,
                before={k: v for k, v in before.items() if after[k] != v},
                after={k: v for k, v in after.items() if before[k] != v},
            )
        await self.session.commit()
        await self.session.refresh(offering)
        if previous_instructor != offering.instructor_id:
            await authz.invalidate_roles(previous_instructor)
            await authz.invalidate_roles(offering.instructor_id)
        return offering

    async def delete_offering(self, offering_id: uuid.UUID, *, actor: CurrentUser) -> None:
        """حذف ارائه‌ای که به اشتباه ساخته شده — نه بایگانی (FR-EDU-01).

        هر ردی از کار واقعی (ثبت‌نام در هر وضعیتی، آزمون، جلسهٔ حضور، اعلان،
        پروژه، امتیاز) حذف را ۴۰۹ می‌کند. هفته‌ها و منابعشان با
        `ON DELETE CASCADE` می‌روند؛ اعطای نقش قلمرودار همین ارائه هم، چون
        قلمرویش دیگر وجود ندارد.
        """
        offering = await self._offering(offering_id)

        async def count(column: Any) -> int:
            return int(
                await self.session.scalar(select(func.count()).where(column == offering.id)) or 0
            )

        usage = {
            "enrollments": await count(Enrollment.offering_id),
            "quizzes": await count(Quiz.offering_id),
            "sessions": await count(ClassSession.offering_id),
            "announcements": await count(Announcement.offering_id),
            "projects": await count(Project.offering_id),
            "point_entries": await count(PointEntry.offering_id),
        }
        used = {k: v for k, v in usage.items() if v}
        if used:
            raise Conflict(
                "این ارائه استفاده شده و حذف نمی‌شود؛ به‌جایش از تنظیمات ارائه بایگانی‌اش کنید.",
                code="OFFERING_IN_USE",
                details=used,
            )

        scoped_holders = list(
            await self.session.scalars(
                select(UserRole.user_id).where(
                    UserRole.scope_type == ScopeType.OFFERING.value,
                    UserRole.scope_id == offering.id,
                )
            )
        )
        self.audit.stage(
            audit_codes.OFFERING_DELETED,
            actor=actor,
            entity_type="OFFERING",
            entity_id=offering.id,
            before={**_offering_snapshot(offering), "scoped_grants": len(scoped_holders)},
        )
        await self.session.execute(
            delete(UserRole).where(
                UserRole.scope_type == ScopeType.OFFERING.value,
                UserRole.scope_id == offering.id,
            )
        )
        instructor_id = offering.instructor_id
        await self.session.execute(delete(CourseOffering).where(CourseOffering.id == offering.id))
        await self.session.commit()
        for user_id in {instructor_id, *scoped_holders}:
            await authz.invalidate_roles(user_id)
        log.info("offering_deleted", offering_id=str(offering_id))

    async def _offering(self, offering_id: uuid.UUID) -> CourseOffering:
        offering = await self.session.get(CourseOffering, offering_id)
        if offering is None or offering.deleted_at is not None:
            raise NotFound("این ارائه پیدا نشد.")
        return offering

    async def _require_instructor(self, user_id: uuid.UUID) -> None:
        user = await self.session.get(User, user_id)
        if user is None or user.deleted_at is not None:
            raise NotFound("این کاربر پیدا نشد.")
        if user.status != "ACTIVE":
            raise ValidationFailed(
                "حساب این کاربر فعال نیست و ارائه به او سپرده نمی‌شود.",
                code="INSTRUCTOR_INACTIVE",
            )

    async def _check_unique(
        self,
        course_id: uuid.UUID,
        term_id: uuid.UUID,
        instructor_id: uuid.UUID,
        *,
        exclude: uuid.UUID | None = None,
    ) -> None:
        stmt = select(CourseOffering.id).where(
            CourseOffering.course_id == course_id,
            CourseOffering.term_id == term_id,
            CourseOffering.instructor_id == instructor_id,
        )
        if exclude is not None:
            stmt = stmt.where(CourseOffering.id != exclude)
        if await self.session.scalar(stmt) is not None:
            raise Conflict(
                "این استاد در همین نیم‌سال از قبل ارائه‌ای از این درس دارد.",
                code="OFFERING_EXISTS",
            )

    # ── گزینش استاد ────────────────────────────────────────────────────
    async def offering_counts_by_instructor(
        self, user_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, int]:
        if not user_ids:
            return {}
        rows = await self.session.execute(
            select(CourseOffering.instructor_id, func.count())
            .where(
                CourseOffering.instructor_id.in_(user_ids),
                CourseOffering.deleted_at.is_(None),
                CourseOffering.status.in_(("DRAFT", "OPEN", "IN_PROGRESS")),
            )
            .group_by(CourseOffering.instructor_id)
        )
        return {uid: int(n) for uid, n in rows.tuples()}


# ── کمکی‌ها ────────────────────────────────────────────────────────────
def _today() -> date:
    """«امروز» به وقت تهران — نیم‌سال در تقویم دانشگاه تمام می‌شود، نه UTC."""
    return datetime.now(LOCAL_TZ).date()


def _check_dates(starts_on: date, ends_on: date) -> None:
    if ends_on <= starts_on:
        raise ValidationFailed("پایان نیم‌سال باید بعد از شروعش باشد.")


def _blank_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _term_snapshot(term: Term) -> dict[str, Any]:
    return {
        "code": term.code,
        "title_fa": term.title_fa,
        "starts_on": term.starts_on.isoformat(),
        "ends_on": term.ends_on.isoformat(),
        "is_current": term.is_current,
    }


def _course_snapshot(course: Course) -> dict[str, Any]:
    return {
        "code": course.code,
        "slug": course.slug,
        "title_fa": course.title_fa,
        "title_en": course.title_en,
        "description": course.description,
        "degree_level": course.degree_level,
        "credits": course.credits,
        "is_public": course.is_public,
        "is_active": course.is_active,
        "default_access_tier": course.default_access_tier,
        "topics": list(course.topics or []),
    }


def _offering_snapshot(offering: CourseOffering) -> dict[str, Any]:
    return {
        "course_id": str(offering.course_id),
        "term_id": str(offering.term_id),
        "instructor_id": str(offering.instructor_id),
        "status": offering.status,
    }


__all__ = [
    "DEFAULT_GRADING_POLICY",
    "WEEK_SOURCES",
    "CourseAdminService",
    "CourseDraft",
    "CourseRow",
    "CreatedOffering",
    "OfferingDraft",
    "OfferingRow",
    "TermDraft",
    "TermRow",
    "slug_from_code",
]
