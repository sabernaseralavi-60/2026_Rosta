"""دادهٔ اولیهٔ آموزش — نیم‌سال، طرح اشتراک، ارائه و هفته‌ها.

این اسکریپت **محتوا نمی‌سازد**. محتوا در `Courses/` است و
`silp.scripts.sync_courses` آن را می‌آورد (ADR-0008). کار اینجا فقط
چیزی است که پوشه نمی‌تواند بداند: چه نیم‌سالی جاری است، چه کسی درس را
ارائه می‌دهد، و اشتراک چند است.

بی‌اثر در تکرار: کلید یکتا `terms.code`، `subscription_plans.code` و
سه‌تایی (درس، نیم‌سال، استاد) است.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from silp.content.manifest import CourseManifest, discover_courses, load_manifest
from silp.content.sync import apply_syllabus
from silp.core.logging import get_logger
from silp.models.access import SubscriptionPlan
from silp.models.education import Course, CourseOffering, CourseWeek, Term
from silp.services import authz

log = get_logger("silp.seed.courses")

# چند هفتهٔ اول منتشر می‌شود تا کلاس در محیط توسعه خالی نباشد. بقیه
# پیش‌نویس می‌مانند — همان چیزی که FR-EDU-02 توصیف می‌کند.
PUBLISHED_WEEKS = 4


@dataclass(frozen=True, slots=True)
class TermSpec:
    code: str
    title_fa: str
    starts_on: date
    ends_on: date
    is_current: bool = False


TERMS: tuple[TermSpec, ...] = (
    TermSpec("1404-2", "نیم‌سال دوم ۱۴۰۴-۱۴۰۵", date(2026, 1, 21), date(2026, 7, 1)),
    TermSpec(
        "1405-1",
        "نیم‌سال اول ۱۴۰۵-۱۴۰۶",
        date(2026, 9, 23),
        date(2027, 2, 4),
        is_current=True,
    ),
)


@dataclass(frozen=True, slots=True)
class PlanSpec:
    code: str
    title_fa: str
    description: str
    scope: str
    duration_days: int
    price_irr: int
    sort_order: int


# قیمت‌ها به **ریال**. §02 «فاز ۱ فقط ثبت و گزارش است؛ پرداخت خارج از
# سامانه انجام می‌شود» — این اعداد نقطهٔ شروع‌اند و مدیر می‌تواند
# عوضشان کند بدون استقرار مجدد.
PLANS: tuple[PlanSpec, ...] = (
    PlanSpec(
        "MONTHLY_ALL",
        "اشتراک ماهانه — همهٔ دروس",
        "دسترسی یک‌ماهه به کتاب‌ها و جزوه‌های همهٔ دروس سامانه.",
        "ALL_COURSES",
        30,
        1_990_000,
        10,
    ),
    PlanSpec(
        "QUARTERLY_ALL",
        "اشتراک سه‌ماهه — همهٔ دروس",
        "سه ماه دسترسی کامل، با تخفیف نسبت به خرید ماهانه.",
        "ALL_COURSES",
        90,
        4_900_000,
        20,
    ),
    PlanSpec(
        "YEARLY_ALL",
        "اشتراک سالانه — همهٔ دروس",
        "یک سال دسترسی کامل به کل کتابخانه.",
        "ALL_COURSES",
        365,
        14_900_000,
        30,
    ),
    PlanSpec(
        "MONTHLY_COURSE",
        "اشتراک ماهانه — یک درس",
        "یک ماه دسترسی به کتابخانهٔ یک درس مشخص.",
        "SINGLE_COURSE",
        30,
        890_000,
        40,
    ),
)


@dataclass(frozen=True, slots=True)
class OfferingSpec:
    """ارائهٔ نمونه. `course_slug` باید با مانیفست پوشه یکی باشد."""

    course_slug: str
    enrollment_code: str
    capacity: int | None
    requires_approval: bool
    grading_policy: dict[str, int]


OFFERINGS: tuple[OfferingSpec, ...] = (
    OfferingSpec(
        "transportation-planning",
        "MTP1405",
        60,
        False,
        {"quiz": 30, "project": 50, "attendance": 10, "participation": 10},
    ),
    OfferingSpec(
        "transportation-engineering",
        "TRE1405",
        80,
        False,
        {"quiz": 40, "project": 40, "attendance": 10, "participation": 10},
    ),
    OfferingSpec(
        "traffic-engineering",
        "SUMO1405",
        40,
        True,
        {"quiz": 20, "project": 60, "attendance": 10, "participation": 10},
    ),
    OfferingSpec(
        "road-safety-modeling",
        "RSA1405",
        40,
        False,
        {"quiz": 30, "project": 50, "attendance": 10, "participation": 10},
    ),
    OfferingSpec(
        "data-mining-civil",
        "MLCE1405",
        50,
        False,
        {"quiz": 30, "project": 50, "attendance": 10, "participation": 10},
    ),
)


async def seed_terms(session: AsyncSession) -> tuple[int, int]:
    created = existing = 0
    for spec in TERMS:
        term = await session.scalar(select(Term).where(Term.code == spec.code))
        if term is None:
            session.add(
                Term(
                    code=spec.code,
                    title_fa=spec.title_fa,
                    starts_on=spec.starts_on,
                    ends_on=spec.ends_on,
                    is_current=spec.is_current,
                )
            )
            created += 1
        else:
            existing += 1
    await session.flush()
    return created, existing


async def seed_plans(session: AsyncSession) -> tuple[int, int]:
    created = existing = 0
    for spec in PLANS:
        plan = await session.scalar(
            select(SubscriptionPlan).where(SubscriptionPlan.code == spec.code)
        )
        if plan is None:
            session.add(
                SubscriptionPlan(
                    code=spec.code,
                    title_fa=spec.title_fa,
                    description=spec.description,
                    scope=spec.scope,
                    duration_days=spec.duration_days,
                    price_irr=spec.price_irr,
                    sort_order=spec.sort_order,
                )
            )
            created += 1
        else:
            existing += 1
    await session.flush()
    return created, existing


async def seed_offerings(
    session: AsyncSession, *, instructor_id: uuid.UUID, courses_root: Path
) -> tuple[int, int]:
    """ارائهٔ نیم‌سال جاری برای هر درسی که در پایگاه‌داده هست.

    درسی که هنوز همگام نشده، ارائه هم نمی‌گیرد — و این درست است: ارائهٔ
    بی‌درس معنا ندارد.
    """
    term = await session.scalar(select(Term).where(Term.is_current.is_(True)))
    if term is None:
        log.warning("no_current_term")
        return 0, 0

    manifests: dict[str, CourseManifest] = {}
    if courses_root.is_dir():
        for directory in discover_courses(courses_root):
            manifest = load_manifest(directory)
            manifests[manifest.slug] = manifest

    created = existing = 0
    for spec in OFFERINGS:
        course = await session.scalar(
            select(Course).where(Course.slug == spec.course_slug, Course.deleted_at.is_(None))
        )
        if course is None:
            log.info("offering_skipped_course_missing", slug=spec.course_slug)
            continue

        offering = await session.scalar(
            select(CourseOffering).where(
                CourseOffering.course_id == course.id,
                CourseOffering.term_id == term.id,
                CourseOffering.instructor_id == instructor_id,
            )
        )
        if offering is None:
            offering = CourseOffering(
                course_id=course.id,
                term_id=term.id,
                instructor_id=instructor_id,
                capacity=spec.capacity,
                enrollment_code=spec.enrollment_code,
                requires_approval=spec.requires_approval,
                status="OPEN",
                grading_policy=dict(spec.grading_policy),
            )
            session.add(offering)
            await session.flush()
            created += 1
            # نقش `INSTRUCTOR` این ارائه مشتق است (§6.1) و کش نقش ۶۰
            # ثانیه عمر دارد؛ بدون ابطال، استاد تا یک دقیقه روی ارائهٔ
            # تازه‌اش بی‌اختیار است.
            await authz.invalidate_roles(instructor_id)
        else:
            existing += 1

        syllabus = manifests.get(spec.course_slug)
        if syllabus is not None:
            await apply_syllabus(session, offering_id=offering.id, manifest=syllabus)
            await _publish_first_weeks(session, offering.id)

    await session.flush()
    return created, existing


async def _publish_first_weeks(session: AsyncSession, offering_id: uuid.UUID) -> None:
    """چند هفتهٔ اول را منتشر می‌کند تا کلاس در توسعه خالی نباشد."""
    from datetime import UTC, datetime

    weeks = await session.scalars(
        select(CourseWeek)
        .where(
            CourseWeek.offering_id == offering_id,
            CourseWeek.week_number <= PUBLISHED_WEEKS,
            CourseWeek.status == "DRAFT",
        )
        .order_by(CourseWeek.week_number)
    )
    now = datetime.now(UTC)
    for week in weeks:
        week.status = "PUBLISHED"
        week.published_at = now
        week.publish_at = None


__all__ = [
    "OFFERINGS",
    "PLANS",
    "PUBLISHED_WEEKS",
    "TERMS",
    "seed_offerings",
    "seed_plans",
    "seed_terms",
]
