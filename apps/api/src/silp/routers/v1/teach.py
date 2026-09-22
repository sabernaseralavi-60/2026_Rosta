"""مسیر /teach — ناحیهٔ استاد، §5.11.

هر endpoint اینجا `require(permission, scope=…)` دارد و قلمرو همیشه
**ارائه** است. استاد ارائهٔ الف هیچ‌جا نمی‌تواند روی ارائهٔ ب بنویسد،
حتی اگر شناسهٔ درست را حدس بزند: بررسی هم در مسیر است و هم دوباره در
سرویس (§6.4 قاعدهٔ ۲).
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select

from silp.core.exceptions import NotFound
from silp.core.permissions import CurrentUser, Permission
from silp.models.education import (
    Course,
    CourseOffering,
    CourseWeek,
    Enrollment,
    Resource,
    Term,
)
from silp.routers.deps import (
    CourseServiceDep,
    CurrentUserDep,
    EnrollmentServiceDep,
    SessionDep,
    TeachingServiceDep,
    offering_from_path,
    offering_of_enrollment,
    offering_of_resource,
    offering_of_week,
    require,
)
from silp.routers.v1.courses import week_summary_out
from silp.schemas.common import ErrorResponse
from silp.schemas.education import (
    AnnouncementIn,
    AnnouncementOut,
    AttendanceIn,
    CopyContentIn,
    CopyResultOut,
    EnrollmentDecisionIn,
    EnrollmentOut,
    FinalGradeIn,
    GradingPolicyIn,
    LinkMaterialIn,
    OfferingSummaryOut,
    PublishWeekIn,
    ResourceIn,
    ResourceOut,
    RosterEntryOut,
    WeekIn,
    WeekSummaryOut,
)
from silp.services.directory import display_names, name_of
from silp.services.teaching_service import AttendanceEntry, ResourceDraft, WeekDraft

router = APIRouter(prefix="/teach", tags=["teaching"])


@router.get("/offerings", response_model=list[OfferingSummaryOut], summary="ارائه‌های من")
async def my_offerings(
    session: SessionDep,
    teaching: TeachingServiceDep,
    courses: CourseServiceDep,
    current: CurrentUserDep,
) -> list[OfferingSummaryOut]:
    offerings = await teaching.my_offerings(current.id)
    if not offerings:
        return []
    ids = [o.id for o in offerings]
    rows = {
        offering_id: (course, term)
        for offering_id, course, term in await session.execute(
            select(CourseOffering.id, Course, Term)
            .join(Course, Course.id == CourseOffering.course_id)
            .join(Term, Term.id == CourseOffering.term_id)
            .where(CourseOffering.id.in_(ids))
        )
    }
    counts = await courses.active_student_counts(ids)
    names = await display_names(session, [current.id])
    result: list[OfferingSummaryOut] = []
    for offering in offerings:
        course, term = rows[offering.id]
        result.append(
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
            )
        )
    return result


# ── هفته — FR-EDU-02 ───────────────────────────────────────────────────
@router.put(
    "/offerings/{offering_id}/weeks",
    response_model=WeekSummaryOut,
    summary="ساخت یا ویرایش هفته",
    responses={403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
async def upsert_week(
    offering_id: uuid.UUID,
    payload: WeekIn,
    teaching: TeachingServiceDep,
    courses: CourseServiceDep,
    _: Annotated[
        CurrentUser, Depends(require(Permission.COURSE_WEEK_EDIT, scope=offering_from_path))
    ],
) -> WeekSummaryOut:
    """شمارهٔ هفته کلید است — همان ۱ تا ۱۷ که استاد در ذهن دارد."""
    week = await teaching.upsert_week(
        offering_id=offering_id,
        draft=WeekDraft(
            week_number=payload.week_number,
            title_fa=payload.title_fa,
            description=payload.description,
            objectives=payload.objectives,
            publish_at=payload.publish_at,
        ),
    )
    cards = await courses.week_cards(offering_id, _.id, include_drafts=True)
    card = next((c for c in cards if c.week.id == week.id), None)
    if card is None:  # pragma: no cover — هفته همین الان ساخته شد
        raise NotFound("هفته پیدا نشد.")
    return week_summary_out(card)


@router.post(
    "/weeks/{week_id}/publish",
    response_model=WeekSummaryOut,
    summary="انتشار هفته (فوری یا زمان‌بندی‌شده)",
    responses={403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
async def publish_week(
    week_id: uuid.UUID,
    payload: PublishWeekIn,
    teaching: TeachingServiceDep,
    courses: CourseServiceDep,
    actor: Annotated[
        CurrentUser, Depends(require(Permission.COURSE_WEEK_PUBLISH, scope=offering_of_week))
    ],
) -> WeekSummaryOut:
    week = await teaching.publish_week(week_id=week_id, at=payload.publish_at)
    cards = await courses.week_cards(week.offering_id, actor.id, include_drafts=True)
    card = next((c for c in cards if c.week.id == week.id), None)
    if card is None:  # pragma: no cover
        raise NotFound("هفته پیدا نشد.")
    return week_summary_out(card)


# ── منبع — FR-EDU-03 ───────────────────────────────────────────────────
@router.post(
    "/offerings/{offering_id}/weeks/{week_id}/resources",
    response_model=ResourceOut,
    status_code=status.HTTP_201_CREATED,
    summary="افزودن منبع به هفته",
    responses={403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
async def add_resource(
    offering_id: uuid.UUID,
    week_id: uuid.UUID,
    payload: ResourceIn,
    teaching: TeachingServiceDep,
    _: Annotated[
        CurrentUser, Depends(require(Permission.RESOURCE_UPLOAD, scope=offering_from_path))
    ],
) -> ResourceOut:
    resource = await teaching.add_resource(
        offering_id=offering_id,
        week_id=week_id,
        draft=ResourceDraft(
            kind=payload.kind,
            title_fa=payload.title_fa,
            description=payload.description,
            file_id=payload.file_id,
            external_url=payload.external_url,
            duration_sec=payload.duration_sec,
            is_downloadable=payload.is_downloadable,
            is_required=payload.is_required,
            sort_order=payload.sort_order,
        ),
    )
    return ResourceOut(
        id=resource.id,
        kind=resource.kind,
        title_fa=resource.title_fa,
        description=resource.description,
        external_url=resource.external_url,
        duration_sec=resource.duration_sec,
        is_downloadable=resource.is_downloadable,
        is_required=resource.is_required,
        has_file=resource.file_id is not None,
    )


@router.delete(
    "/resources/{resource_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="حذف منبع",
    responses={403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
async def remove_resource(
    resource_id: uuid.UUID,
    teaching: TeachingServiceDep,
    session: SessionDep,
    _: Annotated[
        CurrentUser, Depends(require(Permission.RESOURCE_UPLOAD, scope=offering_of_resource))
    ],
) -> None:
    offering_id = await session.scalar(
        select(CourseWeek.offering_id)
        .join(Resource, Resource.week_id == CourseWeek.id)
        .where(Resource.id == resource_id)
    )
    if offering_id is None:
        raise NotFound("این منبع پیدا نشد.")
    await teaching.remove_resource(offering_id=offering_id, resource_id=resource_id)


# ── کتابخانهٔ درس ← هفته (ADR-0008) ────────────────────────────────────
@router.post(
    "/offerings/{offering_id}/weeks/{week_id}/materials",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="بستن محتوای کتابخانه به هفته",
    responses={403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
async def link_material(
    offering_id: uuid.UUID,
    week_id: uuid.UUID,
    payload: LinkMaterialIn,
    teaching: TeachingServiceDep,
    _: Annotated[
        CurrentUser, Depends(require(Permission.COURSE_WEEK_EDIT, scope=offering_from_path))
    ],
) -> None:
    await teaching.link_material(
        offering_id=offering_id,
        week_id=week_id,
        material_id=payload.material_id,
        section=payload.section,
        is_required=payload.is_required,
        sort_order=payload.sort_order,
    )


@router.delete(
    "/offerings/{offering_id}/weeks/{week_id}/materials/{material_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="برداشتن پیوند محتوا از هفته",
    responses={403: {"model": ErrorResponse}},
)
async def unlink_material(
    offering_id: uuid.UUID,
    week_id: uuid.UUID,
    material_id: uuid.UUID,
    teaching: TeachingServiceDep,
    _: Annotated[
        CurrentUser, Depends(require(Permission.COURSE_WEEK_EDIT, scope=offering_from_path))
    ],
) -> None:
    await teaching.unlink_material(
        offering_id=offering_id, week_id=week_id, material_id=material_id
    )


# ── کپی از ارائهٔ قبلی — FR-EDU-01 ─────────────────────────────────────
@router.post(
    "/offerings/{offering_id}/copy-content",
    response_model=CopyResultOut,
    summary="کپی محتوا از ارائهٔ قبلی",
    responses={403: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
async def copy_content(
    offering_id: uuid.UUID,
    payload: CopyContentIn,
    teaching: TeachingServiceDep,
    _: Annotated[
        CurrentUser, Depends(require(Permission.OFFERING_MANAGE, scope=offering_from_path))
    ],
) -> CopyResultOut:
    """هفته‌ها **پیش‌نویس** کپی می‌شوند؛ انتشار تصمیم تازه‌ای است."""
    count = await teaching.copy_weeks_from(
        target_offering_id=offering_id, source_offering_id=payload.source_offering_id
    )
    return CopyResultOut(weeks_copied=count)


# ── دانشجویان و نمره ───────────────────────────────────────────────────
@router.get(
    "/offerings/{offering_id}/students",
    response_model=list[RosterEntryOut],
    summary="دانشجویان ارائه",
    responses={403: {"model": ErrorResponse}},
)
async def roster(
    offering_id: uuid.UUID,
    enrollments: EnrollmentServiceDep,
    session: SessionDep,
    _: Annotated[
        CurrentUser, Depends(require(Permission.OFFERING_MANAGE, scope=offering_from_path))
    ],
    status_filter: Annotated[str | None, Query(alias="status")] = None,
) -> list[RosterEntryOut]:
    rows = await enrollments.roster(offering_id, status=status_filter)
    names = await display_names(session, [r.student_id for r in rows])
    return [
        RosterEntryOut(
            enrollment_id=row.id,
            student_id=row.student_id,
            student_name=name_of(names, row.student_id),
            status=row.status,
            final_grade=float(row.final_grade) if row.final_grade is not None else None,
            enrolled_at=row.enrolled_at,
        )
        for row in rows
    ]


@router.post(
    "/enrollments/{enrollment_id}/decide",
    response_model=EnrollmentOut,
    summary="تأیید یا رد ثبت‌نام",
    responses={403: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
async def decide_enrollment(
    enrollment_id: uuid.UUID,
    payload: EnrollmentDecisionIn,
    enrollments: EnrollmentServiceDep,
    actor: Annotated[
        CurrentUser,
        Depends(require(Permission.ENROLLMENT_APPROVE, scope=offering_of_enrollment)),
    ],
) -> EnrollmentOut:
    enrollment = await enrollments.decide(
        enrollment_id=enrollment_id, approve=payload.approve, decided_by=actor.id
    )
    return EnrollmentOut.model_validate(enrollment)


@router.patch(
    "/enrollments/{enrollment_id}/grade",
    response_model=EnrollmentOut,
    summary="ثبت نمرهٔ نهایی",
    responses={403: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
async def set_grade(
    enrollment_id: uuid.UUID,
    payload: FinalGradeIn,
    enrollments: EnrollmentServiceDep,
    actor: Annotated[
        CurrentUser,
        Depends(require(Permission.GRADE_FINAL_SUBMIT, scope=offering_of_enrollment)),
    ],
) -> EnrollmentOut:
    enrollment = await enrollments.set_final_grade(
        enrollment_id=enrollment_id, grade=payload.grade, decided_by=actor.id
    )
    return EnrollmentOut.model_validate(enrollment)


@router.put(
    "/offerings/{offering_id}/grading-policy",
    response_model=dict[str, int],
    summary="تعیین وزن‌های نمره",
    responses={403: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
async def set_grading_policy(
    offering_id: uuid.UUID,
    payload: GradingPolicyIn,
    teaching: TeachingServiceDep,
    _: Annotated[
        CurrentUser, Depends(require(Permission.OFFERING_MANAGE, scope=offering_from_path))
    ],
) -> dict[str, int]:
    offering = await teaching.set_grading_policy(
        offering_id=offering_id, policy=payload.model_dump()
    )
    return dict(offering.grading_policy)


# ── اعلان و حضور ───────────────────────────────────────────────────────
@router.post(
    "/offerings/{offering_id}/announcements",
    response_model=AnnouncementOut,
    status_code=status.HTTP_201_CREATED,
    summary="انتشار اعلان درس",
    responses={403: {"model": ErrorResponse}},
)
async def publish_announcement(
    offering_id: uuid.UUID,
    payload: AnnouncementIn,
    teaching: TeachingServiceDep,
    actor: Annotated[
        CurrentUser,
        Depends(require(Permission.ANNOUNCEMENT_PUBLISH, scope=offering_from_path)),
    ],
) -> AnnouncementOut:
    announcement = await teaching.publish_announcement(
        offering_id=offering_id,
        author_id=actor.id,
        title=payload.title,
        body=payload.body,
        priority=payload.priority,
        expires_at=payload.expires_at,
    )
    return AnnouncementOut.model_validate(announcement)


@router.post(
    "/offerings/{offering_id}/attendance",
    response_model=dict[str, int],
    summary="ثبت گروهی حضور و غیاب",
    responses={403: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
async def record_attendance(
    offering_id: uuid.UUID,
    payload: AttendanceIn,
    teaching: TeachingServiceDep,
    actor: Annotated[
        CurrentUser, Depends(require(Permission.ATTENDANCE_RECORD, scope=offering_from_path))
    ],
) -> dict[str, int]:
    """FR-EDU-05 — یک درخواست برای کل کلاس، نه یکی به‌ازای هر دانشجو."""
    count = await teaching.record_attendance(
        offering_id=offering_id,
        held_on=payload.held_on,
        week_number=payload.week_number,
        topic=payload.topic,
        entries=[
            AttendanceEntry(student_id=e.student_id, status=e.status, note=e.note)
            for e in payload.entries
        ],
        recorded_by=actor.id,
    )
    return {"recorded": count}


@router.get(
    "/offerings/{offering_id}/enrollment-requests",
    response_model=list[RosterEntryOut],
    summary="درخواست‌های ثبت‌نام در انتظار",
    responses={403: {"model": ErrorResponse}},
)
async def pending_enrollments(
    offering_id: uuid.UUID,
    session: SessionDep,
    _: Annotated[
        CurrentUser,
        Depends(require(Permission.ENROLLMENT_APPROVE, scope=offering_from_path)),
    ],
) -> list[RosterEntryOut]:
    rows = list(
        await session.scalars(
            select(Enrollment)
            .where(Enrollment.offering_id == offering_id, Enrollment.status == "PENDING")
            .order_by(Enrollment.enrolled_at)
        )
    )
    names = await display_names(session, [r.student_id for r in rows])
    return [
        RosterEntryOut(
            enrollment_id=row.id,
            student_id=row.student_id,
            student_name=name_of(names, row.student_id),
            status=row.status,
            final_grade=None,
            enrolled_at=row.enrolled_at,
        )
        for row in rows
    ]


__all__ = ["router"]
