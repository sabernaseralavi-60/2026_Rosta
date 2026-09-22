"""مسیر /courses و /offerings — §5.5.

دو مخاطب دارد و مرزشان صریح است:

* **ویترین** (`/courses`, `/courses/{slug}`) برای همه، حتی مهمان. عنوان
  و فهرست محتوا آزاد است؛ آنچه پشت دروازه می‌ماند فقط **دانلود** است.
* **کلاس** (`/offerings/...`) برای ثبت‌نام‌شده و کادر آموزشی.

دروازهٔ دانلود از `EntitlementService` می‌آید و نه از نقش کاربر: قاعده
«دانشجوی این درس رایگان، بقیه با اشتراک» است، نه «نقش فلان» (ADR-0009).
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from silp.core.exceptions import NotFound, PermissionDenied
from silp.core.permissions import CurrentUser, Permission
from silp.models.access import MaterialAccessEvent
from silp.models.education import (
    ACCESS_TIER_TITLE_FA,
    DEGREE_LEVEL_TITLE_FA,
    MATERIAL_KIND_TITLE_FA,
    CourseOffering,
    Enrollment,
    Resource,
    ResourceProgress,
)
from silp.models.file import File
from silp.routers.deps import (
    CourseServiceDep,
    CurrentUserDep,
    EnrollmentServiceDep,
    EntitlementServiceDep,
    FileServiceDep,
    OptionalUserDep,
    ProgressServiceDep,
    SessionDep,
    SettingsDep,
)
from silp.schemas.common import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    ErrorResponse,
    Page,
    PageParams,
)
from silp.schemas.education import (
    AccessOut,
    AnnouncementOut,
    CourseDetailOut,
    CourseSummaryOut,
    DownloadOut,
    EnrollIn,
    EnrollmentOut,
    MaterialOut,
    OfferingDetailOut,
    OfferingRefOut,
    OfferingSummaryOut,
    ProgressIn,
    ResourceOut,
    ResourceProgressOut,
    SubscriptionPlanRefOut,
    WeekDetailOut,
    WeekSummaryOut,
)
from silp.services.course_service import CourseCard, MaterialView, OfferingOverview
from silp.services.directory import display_names, name_of
from silp.services.entitlement_service import AccessDecision, raise_for
from silp.services.subscription_service import SubscriptionService

router = APIRouter(prefix="/courses", tags=["education"])
offerings_router = APIRouter(prefix="/offerings", tags=["education"])
resources_router = APIRouter(prefix="/resources", tags=["education"])
materials_router = APIRouter(prefix="/materials", tags=["education"])


# ── تبدیل‌ها ───────────────────────────────────────────────────────────
def access_out(decision: AccessDecision) -> AccessOut:
    return AccessOut(
        allowed=decision.allowed,
        tier=decision.tier,
        reason=decision.reason.value if decision.reason else None,
        blocker=decision.blocker.value if decision.blocker else None,
        note_fa=decision.note_fa,
    )


def material_out(view: MaterialView) -> MaterialOut:
    material = view.material
    return MaterialOut(
        id=material.id,
        kind=material.kind,
        kind_fa=MATERIAL_KIND_TITLE_FA.get(material.kind, material.kind),
        title_fa=material.title_fa,
        description=material.description,
        authors=list(material.authors or []),
        edition=material.edition,
        language=material.language,
        size_bytes=material.size_bytes,
        page_count=material.page_count,
        duration_sec=material.duration_sec,
        is_downloadable=material.is_downloadable,
        # نشانی بیرونی فقط وقتی مجاز است — وگرنه همان دور زدن قفل است.
        external_url=material.external_url if view.access.allowed else None,
        section=view.section,
        is_required=view.is_required,
        access=access_out(view.access),
    )


def course_summary_out(card: CourseCard) -> CourseSummaryOut:
    course = card.course
    return CourseSummaryOut(
        id=course.id,
        slug=course.slug,
        code=course.code,
        title_fa=course.title_fa,
        title_en=course.title_en,
        description=course.description,
        degree_level=course.degree_level,
        degree_level_fa=DEGREE_LEVEL_TITLE_FA.get(course.degree_level or ""),
        credits=course.credits,
        topics=list(course.topics or []),
        material_count=card.material_count,
        free_material_count=card.free_material_count,
        open_offering_count=card.open_offering_count,
    )


def week_summary_out(card) -> WeekSummaryOut:  # type: ignore[no-untyped-def]
    week = card.week
    return WeekSummaryOut(
        id=week.id,
        week_number=week.week_number,
        title_fa=week.title_fa,
        description=week.description,
        status=week.status,
        published_at=week.published_at,
        publish_at=week.publish_at,
        resource_count=card.resource_count,
        material_count=card.material_count,
        completed_count=card.completed_count,
        progress_percent=card.progress_percent,
    )


def offering_summary_out(
    overview: OfferingOverview, *, instructor_name: str | None = None
) -> OfferingSummaryOut:
    current = overview.current_week
    return OfferingSummaryOut(
        id=overview.offering.id,
        course_id=overview.course.id,
        course_slug=overview.course.slug,
        course_title_fa=overview.course.title_fa,
        term_code=overview.term.code,
        term_title_fa=overview.term.title_fa,
        instructor_id=overview.offering.instructor_id,
        instructor_name=instructor_name,
        status=overview.offering.status,
        requires_approval=overview.offering.requires_approval,
        has_enrollment_code=bool(overview.offering.enrollment_code),
        capacity=overview.offering.capacity,
        active_students=overview.active_students,
        my_status=overview.enrollment.status if overview.enrollment else None,
        progress_percent=overview.progress_percent,
        current_week_number=current.week_number if current else None,
    )


# ── ویترین — عمومی ─────────────────────────────────────────────────────
@router.get("", response_model=Page[CourseSummaryOut], summary="ویترین دروس")
async def list_courses(
    courses: CourseServiceDep,
    response: Response,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    q: Annotated[str | None, Query(max_length=100)] = None,
    degree_level: Annotated[str | None, Query()] = None,
) -> Page[CourseSummaryOut]:
    """فهرست دروس فعال. بدون احراز هویت کار می‌کند."""
    params = PageParams(page=page, page_size=page_size)
    cards, total = await courses.list_courses(
        q=q, degree_level=degree_level, offset=params.offset, limit=params.page_size
    )
    # §5.4 — ویترین کم‌تغییر است و کش کوتاه فشار را برمی‌دارد.
    response.headers["Cache-Control"] = "public, max-age=300"
    return Page.of(
        [course_summary_out(c) for c in cards],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )


@router.get(
    "/{slug}",
    response_model=CourseDetailOut,
    summary="جزئیات درس و کتابخانهٔ آن",
    responses={404: {"model": ErrorResponse}},
)
async def course_detail(
    slug: str,
    courses: CourseServiceDep,
    session: SessionDep,
    current: OptionalUserDep,
) -> CourseDetailOut:
    """درس، کتابخانه‌اش، ارائه‌های باز، و طرح‌های اشتراک.

    مهمان هم می‌بیند؛ هر ماده سنجش دسترسی خودش را همراه دارد.
    """
    course = await courses.course_by_slug(slug)
    library = await courses.library_of(course, current)
    offerings = await courses.offerings_of(course.id)

    instructor_ids = [o.instructor_id for o, _ in offerings]
    names = await display_names(session, instructor_ids)
    counts = await courses.active_student_counts([o.id for o, _ in offerings])

    plans = await SubscriptionService(session).active_plans()

    my_offering_id: uuid.UUID | None = None
    if current is not None:
        my_offering_id = await session.scalar(
            select(Enrollment.offering_id)
            .join(CourseOffering, CourseOffering.id == Enrollment.offering_id)
            .where(
                Enrollment.student_id == current.id,
                Enrollment.status.in_(("ACTIVE", "COMPLETED", "PENDING")),
                CourseOffering.course_id == course.id,
            )
            .limit(1)
        )

    free_count = sum(1 for view in library if view.material.access_tier == "PUBLIC")
    return CourseDetailOut(
        id=course.id,
        slug=course.slug,
        code=course.code,
        title_fa=course.title_fa,
        title_en=course.title_en,
        description=course.description,
        degree_level=course.degree_level,
        degree_level_fa=DEGREE_LEVEL_TITLE_FA.get(course.degree_level or ""),
        credits=course.credits,
        topics=list(course.topics or []),
        material_count=len(library),
        free_material_count=free_count,
        open_offering_count=len(offerings),
        materials=[material_out(view) for view in library],
        offerings=[
            OfferingRefOut(
                id=offering.id,
                term_code=term.code,
                term_title_fa=term.title_fa,
                instructor_name=name_of(names, offering.instructor_id),
                status=offering.status,
                requires_approval=offering.requires_approval,
                has_enrollment_code=bool(offering.enrollment_code),
                capacity=offering.capacity,
                active_students=counts.get(offering.id, 0),
            )
            for offering, term in offerings
        ],
        plans=[
            SubscriptionPlanRefOut(
                id=plan.id,
                code=plan.code,
                title_fa=plan.title_fa,
                price_irr=plan.price_irr,
                duration_days=plan.duration_days,
                scope=plan.scope,
            )
            for plan in plans
        ],
        my_enrollment_offering_id=my_offering_id,
    )


# ── ارائه‌ها ───────────────────────────────────────────────────────────
@offerings_router.get("", response_model=list[OfferingSummaryOut], summary="ارائه‌های قابل ثبت‌نام")
async def open_offerings(
    courses: CourseServiceDep,
    session: SessionDep,
    current: CurrentUserDep,
    term_id: Annotated[uuid.UUID | None, Query()] = None,
) -> list[OfferingSummaryOut]:
    rows = await courses.open_offerings(term_id=term_id)
    names = await display_names(session, [o.instructor_id for o, _, _ in rows])
    counts = await courses.active_student_counts([o.id for o, _, _ in rows])
    mine: dict[uuid.UUID, str] = dict(
        (
            await session.execute(
                select(Enrollment.offering_id, Enrollment.status).where(
                    Enrollment.student_id == current.id,
                    Enrollment.offering_id.in_([o.id for o, _, _ in rows] or [uuid.UUID(int=0)]),
                )
            )
        ).tuples()
    )
    return [
        OfferingSummaryOut(
            id=offering.id,
            course_id=course.id,
            course_slug=course.slug,
            course_title_fa=course.title_fa,
            term_code=term.code,
            term_title_fa=term.title_fa,
            instructor_id=offering.instructor_id,
            instructor_name=name_of(names, offering.instructor_id),
            status=offering.status,
            requires_approval=offering.requires_approval,
            has_enrollment_code=bool(offering.enrollment_code),
            capacity=offering.capacity,
            active_students=counts.get(offering.id, 0),
            my_status=mine.get(offering.id),
        )
        for offering, course, term in rows
    ]


@offerings_router.get("/mine", response_model=list[OfferingSummaryOut], summary="دروس من")
async def my_offerings(
    courses: CourseServiceDep, session: SessionDep, current: CurrentUserDep
) -> list[OfferingSummaryOut]:
    """§3.4 `/courses` — دروس من با نوار پیشرفت."""
    overviews = await courses.my_offerings(current.id)
    names = await display_names(session, [o.offering.instructor_id for o in overviews])
    return [
        offering_summary_out(o, instructor_name=name_of(names, o.offering.instructor_id))
        for o in overviews
    ]


@offerings_router.get(
    "/{offering_id}",
    response_model=OfferingDetailOut,
    summary="نمای کلی ارائه",
    responses={403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
async def offering_detail(
    offering_id: uuid.UUID,
    courses: CourseServiceDep,
    session: SessionDep,
    current: CurrentUserDep,
) -> OfferingDetailOut:
    overview = await courses.offering_overview(offering_id, current)
    await _require_class_access(overview, current, session)

    names = await display_names(session, [overview.offering.instructor_id])
    summary = offering_summary_out(
        overview, instructor_name=name_of(names, overview.offering.instructor_id)
    )
    return OfferingDetailOut(
        **summary.model_dump(),
        description=overview.course.description,
        grading_policy=dict(overview.offering.grading_policy or {}),
        weeks=[week_summary_out(card) for card in overview.weeks],
        announcements=[AnnouncementOut.model_validate(a) for a in overview.announcements],
        final_grade=(
            float(overview.enrollment.final_grade)
            if overview.enrollment and overview.enrollment.final_grade is not None
            else None
        ),
    )


async def _require_class_access(
    overview: OfferingOverview, current: CurrentUser, session: AsyncSession
) -> None:
    """کلاس فقط برای ثبت‌نام‌شده و کادر آموزشی — §5.5.

    ثبت‌نام `PENDING` هم می‌بیند: دانشجویی که منتظر تأیید است باید
    بداند در چه چیزی منتظر مانده.
    """
    from silp.services import authz

    if overview.enrollment is not None and overview.enrollment.status in (
        "PENDING",
        "ACTIVE",
        "COMPLETED",
    ):
        return
    if overview.offering.instructor_id == current.id:
        return
    if await authz.has_permission(
        session, current, Permission.OFFERING_MANAGE, overview.offering.id
    ):
        return
    raise PermissionDenied("برای دیدن این کلاس باید در آن ثبت‌نام کنید.", code="NOT_ENROLLED")


@offerings_router.post(
    "/{offering_id}/enroll",
    response_model=EnrollmentOut,
    status_code=status.HTTP_201_CREATED,
    summary="ثبت‌نام در ارائه",
    responses={
        403: {"model": ErrorResponse, "description": "ENROLLMENT_CODE_INVALID"},
        409: {"model": ErrorResponse, "description": "ALREADY_ENROLLED | OFFERING_FULL"},
    },
)
async def enroll(
    offering_id: uuid.UUID,
    payload: EnrollIn,
    enrollments: EnrollmentServiceDep,
    current: CurrentUserDep,
) -> EnrollmentOut:
    enrollment = await enrollments.enroll(
        offering_id=offering_id,
        student_id=current.id,
        enrollment_code=payload.enrollment_code,
    )
    return EnrollmentOut.model_validate(enrollment)


@offerings_router.delete(
    "/{offering_id}/enroll",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="انصراف از ارائه",
    responses={404: {"model": ErrorResponse}},
)
async def drop(
    offering_id: uuid.UUID,
    enrollments: EnrollmentServiceDep,
    current: CurrentUserDep,
) -> None:
    await enrollments.drop(offering_id=offering_id, student_id=current.id)


@offerings_router.get(
    "/{offering_id}/weeks",
    response_model=list[WeekSummaryOut],
    summary="فهرست هفته‌ها",
    responses={403: {"model": ErrorResponse}},
)
async def list_weeks(
    offering_id: uuid.UUID,
    courses: CourseServiceDep,
    session: SessionDep,
    current: CurrentUserDep,
) -> list[WeekSummaryOut]:
    overview = await courses.offering_overview(offering_id, current)
    await _require_class_access(overview, current, session)
    return [week_summary_out(card) for card in overview.weeks]


@offerings_router.get(
    "/{offering_id}/weeks/{week_number}",
    response_model=WeekDetailOut,
    summary="محتوای یک هفته",
    responses={403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
async def week_detail(
    offering_id: uuid.UUID,
    week_number: int,
    courses: CourseServiceDep,
    session: SessionDep,
    current: CurrentUserDep,
) -> WeekDetailOut:
    overview = await courses.offering_overview(offering_id, current)
    await _require_class_access(overview, current, session)
    detail = await courses.week_detail(offering_id, week_number, current)

    return WeekDetailOut(
        week_number=detail.week.week_number,
        title_fa=detail.week.title_fa,
        description=detail.week.description,
        objectives=list(detail.week.objectives or []),
        status=detail.week.status,
        published_at=detail.week.published_at,
        resources=[
            ResourceOut(
                id=resource.id,
                kind=resource.kind,
                title_fa=resource.title_fa,
                description=resource.description,
                external_url=resource.external_url,
                duration_sec=resource.duration_sec,
                is_downloadable=resource.is_downloadable,
                is_required=resource.is_required,
                has_file=resource.file_id is not None,
                progress=_progress_out(progress),
            )
            for resource, progress in detail.resources
        ],
        materials=[material_out(view) for view in detail.materials],
    )


def _progress_out(progress: ResourceProgress | None) -> ResourceProgressOut | None:
    if progress is None:
        return None
    return ResourceProgressOut(
        status=progress.status,
        percent=float(progress.percent or 0),
        position_sec=progress.position_sec,
        completed_at=progress.completed_at,
    )


@offerings_router.get(
    "/{offering_id}/announcements",
    response_model=list[AnnouncementOut],
    summary="اعلانات درس",
)
async def offering_announcements(
    offering_id: uuid.UUID,
    courses: CourseServiceDep,
    session: SessionDep,
    current: CurrentUserDep,
) -> list[AnnouncementOut]:
    overview = await courses.offering_overview(offering_id, current)
    await _require_class_access(overview, current, session)
    return [AnnouncementOut.model_validate(a) for a in overview.announcements]


# ── منابع هفته ─────────────────────────────────────────────────────────
@resources_router.post(
    "/{resource_id}/progress",
    response_model=ResourceProgressOut,
    summary="ثبت پیشرفت مطالعه",
    responses={404: {"model": ErrorResponse}},
)
async def record_progress(
    resource_id: uuid.UUID,
    payload: ProgressIn,
    progress_service: ProgressServiceDep,
    session: SessionDep,
    current: CurrentUserDep,
) -> ResourceProgressOut:
    """FR-EDU-04 — ویدئو خودش تمام می‌شود، PDF با دکمهٔ صریح."""
    await _require_resource_access(session, resource_id, current)
    progress = await progress_service.record(
        user_id=current.id,
        resource_id=resource_id,
        percent=payload.percent,
        position_sec=payload.position_sec,
        completed=payload.completed,
    )
    out = _progress_out(progress)
    if out is None:  # pragma: no cover — سرویس همیشه ردیف برمی‌گرداند
        raise NotFound("ثبت پیشرفت انجام نشد.")
    return out


@resources_router.get(
    "/{resource_id}/download",
    response_model=DownloadOut,
    summary="URL دانلود موقت منبع",
    responses={403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
async def download_resource(
    resource_id: uuid.UUID,
    files: FileServiceDep,
    session: SessionDep,
    settings: SettingsDep,
    current: CurrentUserDep,
) -> DownloadOut:
    resource = await _require_resource_access(session, resource_id, current)
    if not resource.is_downloadable:
        raise PermissionDenied("این منبع قابل دانلود نیست.")
    if resource.file_id is None:
        raise NotFound("این منبع فایلی ندارد.")
    file = await session.get(File, resource.file_id)
    if file is None or file.deleted_at is not None:
        raise NotFound("فایل این منبع پیدا نشد.")
    url = await files.download_url(file=file)
    return DownloadOut(
        download_url=url,
        expires_in=settings.download_url_ttl_seconds,
        original_name=file.original_name,
    )


async def _require_resource_access(
    session: AsyncSession, resource_id: uuid.UUID, current: CurrentUser
) -> Resource:
    """منبع هفته فقط برای ثبت‌نام‌شدهٔ همان ارائه — §6.4 قاعدهٔ ۴.

    ۴۰۴ می‌دهد، نه ۴۰۳: منبع درسی که کاربر در آن نیست، برای او وجود
    ندارد. منابع هفته **فروختنی نیستند**؛ اشتراک فقط کتابخانهٔ درس را
    باز می‌کند (ADR-0009).
    """
    from silp.models.education import CourseWeek
    from silp.services import authz

    row = (
        await session.execute(
            select(Resource, CourseWeek, CourseOffering)
            .join(CourseWeek, CourseWeek.id == Resource.week_id)
            .join(CourseOffering, CourseOffering.id == CourseWeek.offering_id)
            .where(Resource.id == resource_id)
        )
    ).first()
    if row is None:
        raise NotFound("این منبع پیدا نشد.")
    resource, week, offering = row._tuple()

    if offering.instructor_id == current.id:
        return resource
    if await authz.has_permission(session, current, Permission.OFFERING_MANAGE, offering.id):
        return resource

    enrolled = await session.scalar(
        select(Enrollment.id).where(
            Enrollment.offering_id == offering.id,
            Enrollment.student_id == current.id,
            Enrollment.status.in_(("ACTIVE", "COMPLETED")),
        )
    )
    if enrolled is None or week.status != "PUBLISHED":
        raise NotFound("این منبع پیدا نشد.")
    return resource


# ── کتابخانهٔ درس ──────────────────────────────────────────────────────
@materials_router.get(
    "/{material_id}/download",
    response_model=DownloadOut,
    summary="URL دانلود محتوای کتابخانه",
    responses={
        402: {"model": ErrorResponse, "description": "SUBSCRIPTION_REQUIRED"},
        403: {"model": ErrorResponse, "description": "ENROLLMENT_REQUIRED"},
        404: {"model": ErrorResponse},
    },
)
async def download_material(
    material_id: uuid.UUID,
    courses: CourseServiceDep,
    entitlements: EntitlementServiceDep,
    files: FileServiceDep,
    session: SessionDep,
    settings: SettingsDep,
    current: CurrentUserDep,
) -> DownloadOut:
    """دروازهٔ اصلی اشتراک — ADR-0009.

    مهمان اینجا ۴۰۱ می‌گیرد (نیازمند ورود)، کاربر بدون حق ۴۰۲، و
    کاربری که دنبال مادهٔ `ENROLLED` است ۴۰۳. هر سه پیام فارسی
    آماده‌ٔ نمایش دارند.
    """
    material, course = await courses.material_with_course(material_id)
    decision = await entitlements.decide_for_material(material, current)
    raise_for(decision, course_slug=course.slug)

    if not material.is_downloadable:
        raise PermissionDenied("این محتوا قابل دانلود نیست.")
    if material.file_id is None:
        raise NotFound("این محتوا فایلی ندارد.")
    file = await session.get(File, material.file_id)
    if file is None or file.deleted_at is not None:
        raise NotFound("فایل این محتوا پیدا نشد.")

    url = await files.download_url(file=file)
    # FR-EDU-03 — «ثبت رویداد resource_accessed».
    session.add(
        MaterialAccessEvent(
            material_id=material.id,
            user_id=current.id,
            granted_by_reason=decision.reason.value if decision.reason else "UNKNOWN",
        )
    )
    await session.commit()

    return DownloadOut(
        download_url=url,
        expires_in=settings.download_url_ttl_seconds,
        original_name=file.original_name,
    )


@materials_router.get("/tiers", response_model=dict[str, str], summary="معنی سطوح دسترسی")
async def access_tiers(response: Response) -> dict[str, str]:
    """متن فارسی هر سطح — تا رابط کاربری آن را ننویسد."""
    response.headers["Cache-Control"] = "public, max-age=3600"
    return dict(ACCESS_TIER_TITLE_FA)


__all__ = [
    "access_out",
    "material_out",
    "materials_router",
    "offerings_router",
    "resources_router",
    "router",
]
