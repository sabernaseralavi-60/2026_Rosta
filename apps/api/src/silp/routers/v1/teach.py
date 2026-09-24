"""مسیر /teach — ناحیهٔ استاد، §5.11.

هر endpoint اینجا `require(permission, scope=…)` دارد و قلمرو همیشه
**ارائه** است. استاد ارائهٔ الف هیچ‌جا نمی‌تواند روی ارائهٔ ب بنویسد،
حتی اگر شناسهٔ درست را حدس بزند: بررسی هم در مسیر است و هم دوباره در
سرویس (§6.4 قاعدهٔ ۲).
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from silp.core.exceptions import NotFound, PermissionDenied
from silp.core.permissions import (
    OFFERING_SCOPED_ROLES,
    CurrentUser,
    Permission,
    Role,
    RoleGrant,
    ScopeType,
)
from silp.models.education import (
    ATTENDANCE_STATUSES,
    Course,
    CourseOffering,
    CourseWeek,
    Enrollment,
    Resource,
    Term,
)
from silp.models.quiz import Quiz
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
from silp.routers.v1.gamification import learning_out
from silp.schemas.common import ErrorResponse
from silp.schemas.education import (
    AnnouncementIn,
    AnnouncementOut,
    AnnouncementPatchIn,
    AttendanceIn,
    CopyContentIn,
    CopyResultOut,
    EnrollmentDecisionIn,
    EnrollmentOut,
    FinalGradeIn,
    GradingPolicyIn,
    LinkMaterialIn,
    PublishWeekIn,
    ResourceIn,
    ResourceOut,
    RosterEntryOut,
    WeekIn,
    WeekSummaryOut,
)
from silp.schemas.teaching import (
    AttendanceMarkOut,
    AttendanceSessionOut,
    AttendanceSheetOut,
    AttendanceTallyOut,
    GradebookCellOut,
    GradebookOut,
    GradebookQuizOut,
    GradebookRowOut,
    OfferingPermissionsOut,
    OfferingSettingsIn,
    StaffRole,
    TeachAnnouncementOut,
    TeachOfferingDetailOut,
    TeachOfferingOut,
)
from silp.services import authz
from silp.services.course_service import CourseService
from silp.services.directory import display_names, name_of
from silp.services.gradebook_service import GradebookService
from silp.services.teaching_service import (
    OFFERING_TRANSITIONS,
    AttendanceEntry,
    ResourceDraft,
    TeachingService,
    WeekDraft,
)

router = APIRouter(prefix="/teach", tags=["teaching"])


@router.get("/offerings", response_model=list[TeachOfferingOut], summary="ارائه‌های من")
async def my_offerings(
    session: SessionDep,
    teaching: TeachingServiceDep,
    courses: CourseServiceDep,
    current: CurrentUserDep,
) -> list[TeachOfferingOut]:
    """استاد اصلی، و هر ارائه‌ای که کاربر در آن اعطای قلمرودار دارد (ADR-0019)."""
    grants = await authz.get_grants(session, current.id)
    scoped = [
        g.scope_id
        for g in grants
        if g.role in OFFERING_SCOPED_ROLES
        and g.scope_type is ScopeType.OFFERING
        and g.scope_id is not None
    ]
    offerings = await teaching.my_offerings(current.id, scoped_offering_ids=scoped)
    if not offerings:
        return []
    return await _summaries(session, teaching, courses, offerings, current.id, grants)


async def _summaries(
    session: AsyncSession,
    teaching: TeachingService,
    courses: CourseService,
    offerings: list[CourseOffering],
    viewer_id: uuid.UUID,
    grants: tuple[RoleGrant, ...],
) -> list[TeachOfferingOut]:
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
    pending = await teaching.pending_enrollment_counts(ids)
    names = await display_names(session, [o.instructor_id for o in offerings])
    result: list[TeachOfferingOut] = []
    for offering in offerings:
        course, term = rows[offering.id]
        result.append(
            TeachOfferingOut(
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
                staff_role=_staff_role(offering, viewer_id, grants),
                pending_enrollments=pending.get(offering.id, 0),
            )
        )
    return result


def _staff_role(
    offering: CourseOffering, viewer_id: uuid.UUID, grants: tuple[RoleGrant, ...]
) -> StaffRole | None:
    """بالاترین نقش بیننده در همین ارائه — برای رابط، نه برای مجوز."""
    roles = {g.role for g in grants if g.covers(offering.id)}
    if Role.ADMIN in roles:
        return "ADMIN"
    if Role.COORDINATOR in roles:
        return "COORDINATOR"
    scoped = {
        g.role for g in grants if g.scope_type is ScopeType.OFFERING and g.scope_id == offering.id
    }
    if offering.instructor_id == viewer_id or Role.INSTRUCTOR in scoped:
        return "INSTRUCTOR"
    if Role.TA in scoped:
        return "TA"
    return None


async def _detail(
    session: AsyncSession,
    teaching: TeachingService,
    courses: CourseService,
    offering: CourseOffering,
    viewer: CurrentUser,
) -> TeachOfferingDetailOut:
    grants = await authz.get_grants(session, viewer.id)
    fresh = CurrentUser(id=viewer.id, session_id=viewer.session_id, grants=grants)
    (summary,) = await _summaries(session, teaching, courses, [offering], viewer.id, grants)
    cards = await courses.week_cards(offering.id, viewer.id, include_drafts=True)
    quiz_count = int(
        await session.scalar(
            select(func.count()).where(Quiz.offering_id == offering.id, Quiz.deleted_at.is_(None))
        )
        or 0
    )

    def can(permission: Permission) -> bool:
        return fresh.has_permission(permission, offering.id)

    return TeachOfferingDetailOut(
        **summary.model_dump(),
        enrollment_code=offering.enrollment_code if can(Permission.OFFERING_MANAGE) else None,
        grading_policy=dict(offering.grading_policy or {}),
        weeks=[week_summary_out(card) for card in cards],
        announcements=[
            TeachAnnouncementOut(
                **AnnouncementOut.model_validate(a).model_dump(),
                can_edit=a.author_id == viewer.id or can(Permission.OFFERING_MANAGE),
            )
            for a in await courses.announcements_of(offering.id)
        ],
        quiz_count=quiz_count,
        allowed_statuses=list(OFFERING_TRANSITIONS.get(offering.status, ())),
        permissions=OfferingPermissionsOut(
            manage=can(Permission.OFFERING_MANAGE),
            edit_weeks=can(Permission.COURSE_WEEK_EDIT),
            publish_weeks=can(Permission.COURSE_WEEK_PUBLISH),
            upload_resources=can(Permission.RESOURCE_UPLOAD),
            record_attendance=can(Permission.ATTENDANCE_RECORD),
            approve_enrollments=can(Permission.ENROLLMENT_APPROVE),
            submit_final_grades=can(Permission.GRADE_FINAL_SUBMIT),
            publish_announcements=can(Permission.ANNOUNCEMENT_PUBLISH),
            create_quizzes=can(Permission.QUIZ_CREATE),
            grade_quizzes=can(Permission.QUIZ_GRADE),
        ),
    )


@router.get(
    "/offerings/{offering_id}",
    response_model=TeachOfferingDetailOut,
    summary="ارائه از دید کادر آموزشی",
    responses={403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
async def offering_detail(
    offering_id: uuid.UUID,
    session: SessionDep,
    teaching: TeachingServiceDep,
    courses: CourseServiceDep,
    viewer: Annotated[
        CurrentUser,
        Depends(require(Permission.COURSE_WEEK_VIEW_DRAFT, scope=offering_from_path)),
    ],
) -> TeachOfferingDetailOut:
    """هفته‌ها با پیش‌نویس، کد ثبت‌نام (فقط برای مدیر ارائه)، و آنچه بیننده
    می‌تواند — دستیار همان صفحه را می‌بیند با دکمه‌های کمتر."""
    offering = await teaching.offering(offering_id)
    return await _detail(session, teaching, courses, offering, viewer)


@router.patch(
    "/offerings/{offering_id}",
    response_model=TeachOfferingDetailOut,
    summary="تنظیمات ثبت‌نام و وضعیت ارائه",
    responses={
        403: {"model": ErrorResponse},
        409: {"model": ErrorResponse, "description": "OFFERING_TRANSITION_INVALID | …"},
        422: {"model": ErrorResponse},
    },
)
async def update_offering(
    offering_id: uuid.UUID,
    payload: OfferingSettingsIn,
    session: SessionDep,
    teaching: TeachingServiceDep,
    courses: CourseServiceDep,
    actor: Annotated[
        CurrentUser, Depends(require(Permission.OFFERING_MANAGE, scope=offering_from_path))
    ],
) -> TeachOfferingDetailOut:
    offering = await teaching.update_settings(
        offering_id=offering_id,
        status=payload.status,
        requires_approval=payload.requires_approval,
        capacity=payload.capacity,
        clear_capacity=payload.clear_capacity,
        enrollment_code=payload.enrollment_code,
        clear_enrollment_code=payload.clear_enrollment_code,
    )
    return await _detail(session, teaching, courses, offering, actor)


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
    session: SessionDep,
    actor: Annotated[
        CurrentUser, Depends(require(Permission.OFFERING_MANAGE, scope=offering_from_path))
    ],
) -> CopyResultOut:
    """هفته‌ها **پیش‌نویس** کپی می‌شوند؛ انتشار تصمیم تازه‌ای است.

    مبدأ هم قلمرو می‌خواهد (ADR-0019): وگرنه استاد یک ارائه، پیش‌نویس‌های
    ارائهٔ استاد دیگرِ همان درس را با یک شناسه کپی می‌کرد و می‌خواند.
    """
    if not await authz.has_permission(
        session, actor, Permission.COURSE_WEEK_VIEW_DRAFT, payload.source_offering_id
    ):
        raise PermissionDenied("فقط از ارائه‌ای که خودت در آن استاد یا دستیاری می‌توانی کپی کنی.")
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
    viewer: Annotated[
        CurrentUser,
        Depends(require(Permission.COURSE_WEEK_VIEW_DRAFT, scope=offering_from_path)),
    ],
    status_filter: Annotated[str | None, Query(alias="status")] = None,
) -> list[RosterEntryOut]:
    """همهٔ کادر ارائه فهرست را می‌بینند — دستیار برای حضور و غیاب لازمش دارد.

    نمرهٔ نهایی فقط برای کسی که ارائه را مدیریت می‌کند (ADR-0019)؛ پیش از
    آن این مسیر `OFFERING_MANAGE` می‌خواست و دستیاری که حضور ثبت می‌کرد،
    فهرست کلاس را نداشت.
    """
    rows = await enrollments.roster(offering_id, status=status_filter)
    names = await display_names(session, [r.student_id for r in rows])
    grades_visible = await authz.has_permission(
        session, viewer, Permission.OFFERING_MANAGE, offering_id
    )
    return [
        RosterEntryOut(
            enrollment_id=row.id,
            student_id=row.student_id,
            student_name=name_of(names, row.student_id),
            status=row.status,
            final_grade=(
                float(row.final_grade) if grades_visible and row.final_grade is not None else None
            ),
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


@router.patch(
    "/offerings/{offering_id}/announcements/{announcement_id}",
    response_model=AnnouncementOut,
    summary="ویرایش اعلان درس",
    responses={403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
async def revise_announcement(
    offering_id: uuid.UUID,
    announcement_id: uuid.UUID,
    payload: AnnouncementPatchIn,
    teaching: TeachingServiceDep,
    session: SessionDep,
    actor: Annotated[
        CurrentUser,
        Depends(require(Permission.ANNOUNCEMENT_PUBLISH, scope=offering_from_path)),
    ],
) -> AnnouncementOut:
    """ADR-0021 — دوباره فرستاده نمی‌شود؛ متن اعلان‌های رفته بازنویسی می‌شود."""
    announcement = await teaching.update_announcement(
        offering_id=offering_id,
        announcement_id=announcement_id,
        actor_id=actor.id,
        can_manage=await authz.has_permission(
            session, actor, Permission.OFFERING_MANAGE, offering_id
        ),
        changes=payload.model_dump(exclude_unset=True),
    )
    return AnnouncementOut.model_validate(announcement)


@router.delete(
    "/offerings/{offering_id}/announcements/{announcement_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="حذف اعلان درس",
    responses={403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
async def withdraw_announcement(
    offering_id: uuid.UUID,
    announcement_id: uuid.UUID,
    teaching: TeachingServiceDep,
    session: SessionDep,
    actor: Annotated[
        CurrentUser,
        Depends(require(Permission.ANNOUNCEMENT_PUBLISH, scope=offering_from_path)),
    ],
) -> None:
    """ADR-0021 — اعلان‌های رفته و پیام‌های صف‌مانده هم پس گرفته می‌شوند."""
    await teaching.delete_announcement(
        offering_id=offering_id,
        announcement_id=announcement_id,
        actor_id=actor.id,
        can_manage=await authz.has_permission(
            session, actor, Permission.OFFERING_MANAGE, offering_id
        ),
    )


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
    "/offerings/{offering_id}/attendance",
    response_model=list[AttendanceSessionOut],
    summary="جلسه‌های ثبت‌شده با شمار حضور",
    responses={403: {"model": ErrorResponse}},
)
async def attendance_sessions(
    offering_id: uuid.UUID,
    teaching: TeachingServiceDep,
    _: Annotated[
        CurrentUser, Depends(require(Permission.ATTENDANCE_RECORD, scope=offering_from_path))
    ],
) -> list[AttendanceSessionOut]:
    """تا امروز حضور فقط نوشته می‌شد؛ هیچ راهی برای دیدن یا اصلاحش نبود."""
    return [
        AttendanceSessionOut(
            held_on=t.session.held_on,
            week_number=t.session.week_number,
            topic=t.session.topic,
            present=t.counts.get("PRESENT", 0),
            late=t.counts.get("LATE", 0),
            absent=t.counts.get("ABSENT", 0),
            excused=t.counts.get("EXCUSED", 0),
        )
        for t in await teaching.attendance_sessions(offering_id)
    ]


@router.get(
    "/offerings/{offering_id}/attendance/{held_on}",
    response_model=AttendanceSheetOut,
    summary="حضور یک روز، برای اصلاح",
    responses={403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
async def attendance_sheet(
    offering_id: uuid.UUID,
    held_on: date,
    teaching: TeachingServiceDep,
    _: Annotated[
        CurrentUser, Depends(require(Permission.ATTENDANCE_RECORD, scope=offering_from_path))
    ],
) -> AttendanceSheetOut:
    found = await teaching.attendance_sheet(offering_id, held_on)
    if found is None:
        raise NotFound("برای این روز حضوری ثبت نشده است.", code="ATTENDANCE_NOT_RECORDED")
    class_session, records = found
    counts = {s: sum(1 for r in records if r.status == s) for s in ATTENDANCE_STATUSES}
    return AttendanceSheetOut(
        held_on=class_session.held_on,
        week_number=class_session.week_number,
        topic=class_session.topic,
        present=counts["PRESENT"],
        late=counts["LATE"],
        absent=counts["ABSENT"],
        excused=counts["EXCUSED"],
        marks=[
            AttendanceMarkOut(student_id=r.student_id, status=r.status, note=r.note)
            for r in records
        ],
    )


@router.get(
    "/offerings/{offering_id}/gradebook",
    response_model=GradebookOut,
    summary="دفتر نمره",
    responses={403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
async def gradebook(
    offering_id: uuid.UUID,
    session: SessionDep,
    _: Annotated[
        CurrentUser, Depends(require(Permission.OFFERING_MANAGE, scope=offering_from_path))
    ],
) -> GradebookOut:
    """§3.5 — آزمون‌ها، حضور، نمرهٔ یادگیری و نمرهٔ نهایی در یک پاسخ.

    هیچ چیزی نمی‌نویسد؛ نمرهٔ نهایی با `PATCH /teach/enrollments/{id}/grade`.
    """
    book = await GradebookService(session).for_offering(offering_id)
    names = await display_names(session, [r.enrollment.student_id for r in book.rows])
    rows = []
    for row in book.rows:
        learning = learning_out(offering_id, row.learning) if row.learning is not None else None
        enrollment = row.enrollment
        rows.append(
            GradebookRowOut(
                enrollment_id=enrollment.id,
                student_id=enrollment.student_id,
                student_name=name_of(names, enrollment.student_id),
                status=enrollment.status,
                quizzes=[
                    GradebookCellOut(
                        quiz_id=c.quiz_id,
                        score=c.score,
                        is_provisional=c.is_provisional,
                        attempts=c.attempts,
                    )
                    for c in row.cells
                ],
                attendance=AttendanceTallyOut(
                    present=row.attendance.get("PRESENT", 0),
                    late=row.attendance.get("LATE", 0),
                    absent=row.attendance.get("ABSENT", 0),
                    excused=row.attendance.get("EXCUSED", 0),
                ),
                learning_score=learning.score if learning else None,
                suggested_grade=learning.suggested_grade if learning else None,
                components=learning.components if learning else [],
                final_grade=(
                    float(enrollment.final_grade) if enrollment.final_grade is not None else None
                ),
            )
        )
    rows.sort(key=lambda r: (r.student_name or "", str(r.student_id)))
    return GradebookOut(
        offering_id=offering_id,
        sessions_held=book.sessions_held,
        quizzes=[
            GradebookQuizOut(
                id=q.id,
                title_fa=q.title_fa,
                status=q.status,
                total_points=q.total_points,
                closes_at=q.closes_at,
            )
            for q in book.quizzes
        ],
        rows=rows,
    )


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
