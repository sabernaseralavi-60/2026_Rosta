"""تعریف درس، نیم‌سال و ارائه — §3.6 `/admin/courses`، §5.12، FR-EDU-01، ADR-0020.

| مسیر | مجوز |
|------|------|
| `GET/POST /admin/terms`، `PATCH/DELETE /admin/terms/{id}` | `term.manage` |
| `GET/POST /admin/courses`، `PATCH /admin/courses/{id}` | `course.create` |
| `GET/POST /admin/offerings`، `PATCH/DELETE /admin/offerings/{id}` | `offering.create` |
| `GET /admin/instructor-candidates?q=` | `offering.create` |

هر سه مجوز فقط با مدیر آموزشی و مدیر سامانه است. استاد ارائه را نمی‌سازد؛
پس از سپرده شدن، وضعیت و ثبت‌نام و هفته‌هایش را در `/teach` تنظیم می‌کند.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from silp.core.permissions import CurrentUser, Permission
from silp.core.security import mask_mobile
from silp.models.education import Term
from silp.routers.deps import SessionDep, require
from silp.schemas.common import ErrorResponse
from silp.schemas.course_admin import (
    AdminCourseOut,
    AdminOfferingOut,
    AdminTermOut,
    CourseCreateIn,
    CourseUpdateIn,
    InstructorCandidateOut,
    OfferingCreatedOut,
    OfferingCreateIn,
    OfferingReassignIn,
    TermCreateIn,
    TermUpdateIn,
)
from silp.schemas.education import OfferingStatus
from silp.services import authz
from silp.services.admin_service import AdminService, UserFilters
from silp.services.course_admin_service import (
    CourseAdminService,
    CourseDraft,
    CourseRow,
    OfferingDraft,
    OfferingRow,
    TermDraft,
)
from silp.services.directory import display_names, name_of

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    responses={
        401: {"model": ErrorResponse, "description": "احراز هویت نشده"},
        403: {"model": ErrorResponse, "description": "بدون مجوز"},
    },
)

TermManager = Annotated[CurrentUser, Depends(require(Permission.TERM_MANAGE))]
CourseManager = Annotated[CurrentUser, Depends(require(Permission.COURSE_CREATE))]
OfferingManager = Annotated[CurrentUser, Depends(require(Permission.OFFERING_CREATE))]

#: بیشترین نامزد استاد در یک جستجو — فهرست گزینش است، نه فهرست کاربران.
CANDIDATE_LIMIT = 10


def _service(session: SessionDep) -> CourseAdminService:
    # پوشهٔ دروس همان است که `sync_courses` می‌خواند؛ در تولید فقط‌خواندنی
    # سوار می‌شود (compose.prod.yml).
    from silp.scripts.sync_courses import resolve_root

    return CourseAdminService(session, courses_root=resolve_root(None))


ServiceDep = Annotated[CourseAdminService, Depends(_service)]


# ── تبدیل‌ها ───────────────────────────────────────────────────────────
def _term_out(term: Term, offering_count: int = 0) -> AdminTermOut:
    return AdminTermOut(
        id=term.id,
        code=term.code,
        title_fa=term.title_fa,
        starts_on=term.starts_on,
        ends_on=term.ends_on,
        is_current=term.is_current,
        offering_count=offering_count,
    )


def _course_out(row: CourseRow) -> AdminCourseOut:
    course = row.course
    return AdminCourseOut(
        id=course.id,
        code=course.code,
        slug=course.slug,
        title_fa=course.title_fa,
        title_en=course.title_en,
        description=course.description,
        degree_level=course.degree_level,
        credits=course.credits,
        is_public=course.is_public,
        is_active=course.is_active,
        default_access_tier=course.default_access_tier,
        topics=list(course.topics or []),
        source_dir=course.source_dir,
        offering_count=row.offering_count,
        material_count=row.material_count,
        syllabus_weeks=row.syllabus_weeks,
        created_at=course.created_at,
    )


async def _offerings_out(session: SessionDep, rows: list[OfferingRow]) -> list[AdminOfferingOut]:
    names = await display_names(session, [r.offering.instructor_id for r in rows])
    return [
        AdminOfferingOut(
            id=r.offering.id,
            course_id=r.course.id,
            course_code=r.course.code,
            course_title_fa=r.course.title_fa,
            term_id=r.term.id,
            term_code=r.term.code,
            term_title_fa=r.term.title_fa,
            instructor_id=r.offering.instructor_id,
            instructor_name=name_of(names, r.offering.instructor_id),
            status=r.offering.status,
            capacity=r.offering.capacity,
            requires_approval=r.offering.requires_approval,
            has_enrollment_code=bool(r.offering.enrollment_code),
            active_students=r.active_students,
            pending_students=r.pending_students,
            week_count=r.week_count,
            published_weeks=r.published_weeks,
            created_at=r.offering.created_at,
        )
        for r in rows
    ]


async def _one_offering(
    service: CourseAdminService, session: SessionDep, offering_id: uuid.UUID
) -> AdminOfferingOut:
    rows = await service.offerings(offering_id=offering_id)
    return (await _offerings_out(session, rows))[0]


# ── نیم‌سال ────────────────────────────────────────────────────────────
@router.get("/terms", response_model=list[AdminTermOut], summary="نیم‌سال‌ها")
async def list_terms(service: ServiceDep, _: TermManager) -> list[AdminTermOut]:
    return [_term_out(r.term, r.offering_count) for r in await service.terms()]


@router.post(
    "/terms",
    response_model=AdminTermOut,
    status_code=status.HTTP_201_CREATED,
    summary="تعریف نیم‌سال",
    responses={409: {"model": ErrorResponse, "description": "TERM_CODE_TAKEN"}},
)
async def create_term(
    payload: TermCreateIn, service: ServiceDep, actor: TermManager
) -> AdminTermOut:
    term = await service.create_term(TermDraft(**payload.model_dump()), actor=actor)
    return _term_out(term)


@router.patch(
    "/terms/{term_id}",
    response_model=AdminTermOut,
    summary="ویرایش نیم‌سال یا جاری کردنش",
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
async def update_term(
    term_id: uuid.UUID, payload: TermUpdateIn, service: ServiceDep, actor: TermManager
) -> AdminTermOut:
    term = await service.update_term(term_id, payload.model_dump(exclude_unset=True), actor=actor)
    counts = {r.term.id: r.offering_count for r in await service.terms()}
    return _term_out(term, counts.get(term.id, 0))


@router.delete(
    "/terms/{term_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="حذف نیم‌سال بی‌استفاده",
    responses={
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse, "description": "TERM_IN_USE"},
    },
)
async def delete_term(term_id: uuid.UUID, service: ServiceDep, actor: TermManager) -> None:
    await service.delete_term(term_id, actor=actor)


# ── درس ────────────────────────────────────────────────────────────────
@router.get("/courses", response_model=list[AdminCourseOut], summary="همهٔ دروس، با غیرفعال‌ها")
async def list_courses(
    service: ServiceDep,
    _: CourseManager,
    q: Annotated[str | None, Query(max_length=100)] = None,
) -> list[AdminCourseOut]:
    return [_course_out(row) for row in await service.courses(q=q)]


@router.post(
    "/courses",
    response_model=AdminCourseOut,
    status_code=status.HTTP_201_CREATED,
    summary="تعریف درس",
    responses={
        409: {"model": ErrorResponse, "description": "COURSE_CODE_TAKEN | COURSE_SLUG_TAKEN"}
    },
)
async def create_course(
    payload: CourseCreateIn, service: ServiceDep, actor: CourseManager
) -> AdminCourseOut:
    course = await service.create_course(CourseDraft(**payload.model_dump()), actor=actor)
    return _course_out(
        CourseRow(course=course, offering_count=0, material_count=0, syllabus_weeks=None)
    )


@router.patch(
    "/courses/{course_id}",
    response_model=AdminCourseOut,
    summary="ویرایش درسی که در پنل ساخته شده",
    responses={
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse, "description": "COURSE_MANAGED_BY_FOLDER | …_TAKEN"},
    },
)
async def update_course(
    course_id: uuid.UUID, payload: CourseUpdateIn, service: ServiceDep, actor: CourseManager
) -> AdminCourseOut:
    course = await service.update_course(
        course_id, payload.model_dump(exclude_unset=True), actor=actor
    )
    return _course_out((await service.courses(course_id=course.id))[0])


# ── ارائه ──────────────────────────────────────────────────────────────
@router.get("/offerings", response_model=list[AdminOfferingOut], summary="همهٔ ارائه‌ها")
async def list_offerings(
    service: ServiceDep,
    session: SessionDep,
    _: OfferingManager,
    term_id: Annotated[uuid.UUID | None, Query()] = None,
    course_id: Annotated[uuid.UUID | None, Query()] = None,
    offering_status: Annotated[OfferingStatus | None, Query(alias="status")] = None,
) -> list[AdminOfferingOut]:
    rows = await service.offerings(term_id=term_id, course_id=course_id, status=offering_status)
    return await _offerings_out(session, rows)


@router.post(
    "/offerings",
    response_model=OfferingCreatedOut,
    status_code=status.HTTP_201_CREATED,
    summary="تعریف ارائه و سپردن به استاد",
    responses={
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse, "description": "OFFERING_EXISTS"},
        422: {
            "model": ErrorResponse,
            "description": (
                "TERM_ENDED | COURSE_INACTIVE | INSTRUCTOR_INACTIVE | SYLLABUS_UNAVAILABLE"
            ),
        },
    },
)
async def create_offering(
    payload: OfferingCreateIn, service: ServiceDep, session: SessionDep, actor: OfferingManager
) -> OfferingCreatedOut:
    created = await service.create_offering(OfferingDraft(**payload.model_dump()), actor=actor)
    out = await _one_offering(service, session, created.offering.id)
    return OfferingCreatedOut(**out.model_dump(), weeks_created=created.weeks_created)


@router.patch(
    "/offerings/{offering_id}",
    response_model=AdminOfferingOut,
    summary="سپردن ارائه به استاد دیگر یا نیم‌سال دیگر",
    responses={
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse, "description": "OFFERING_EXISTS | OFFERING_HAS_ENROLLMENTS"},
    },
)
async def reassign_offering(
    offering_id: uuid.UUID,
    payload: OfferingReassignIn,
    service: ServiceDep,
    session: SessionDep,
    actor: OfferingManager,
) -> AdminOfferingOut:
    await service.update_offering(
        offering_id, instructor_id=payload.instructor_id, term_id=payload.term_id, actor=actor
    )
    return await _one_offering(service, session, offering_id)


@router.delete(
    "/offerings/{offering_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="حذف ارائه‌ای که به اشتباه ساخته شده",
    responses={
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse, "description": "OFFERING_IN_USE"},
    },
)
async def delete_offering(
    offering_id: uuid.UUID, service: ServiceDep, actor: OfferingManager
) -> None:
    await service.delete_offering(offering_id, actor=actor)


# ── گزینش استاد ────────────────────────────────────────────────────────
@router.get(
    "/instructor-candidates",
    response_model=list[InstructorCandidateOut],
    summary="جستجوی کاربر برای سپردن ارائه",
)
async def instructor_candidates(
    service: ServiceDep,
    session: SessionDep,
    actor: OfferingManager,
    q: Annotated[str, Query(min_length=2, max_length=100)],
) -> list[InstructorCandidateOut]:
    """فقط حساب فعال؛ حداکثر ده نفر. مدیر آموزشی `user.view_all` ندارد و
    فهرست کاربران را نمی‌بیند — فقط کسی را که دنبالش است (ADR-0020)."""
    admin = AdminService(session)
    rows = list(
        await session.execute(
            admin.user_query(UserFilters(q=q, status="ACTIVE")).limit(CANDIDATE_LIMIT)
        )
    )
    counts = await service.offering_counts_by_instructor([user.id for user, _ in rows])
    full_contact = await authz.has_permission(session, actor, Permission.PROFILE_VIEW_CONTACT)
    return [
        InstructorCandidateOut(
            id=user.id,
            name=getattr(profile, "public_name", None) if profile is not None else None,
            username=user.username,
            mobile=(user.mobile if full_contact else mask_mobile(user.mobile))
            if user.mobile
            else None,
            active_offerings=counts.get(user.id, 0),
        )
        for user, profile in rows
    ]


__all__ = ["router"]
