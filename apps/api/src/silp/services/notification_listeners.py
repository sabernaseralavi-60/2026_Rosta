"""اتصال رویدادهای دامنه به اعلان — PRD §7.13، M6-02.

هر شنونده یک رویداد را به «چه کسی، کدام نوع، با چه متغیرهایی» ترجمه
می‌کند و بقیه را به `NotificationService.notify` می‌سپارد. شنونده‌ها روی
همان نشست و داخل savepoint خودشان اجرا می‌شوند (`silp.services.events`):
اشکال در ساختن یک اعلان، تأیید تحویل‌دادنی را نمی‌شکند.

## چه کسی خبردار نمی‌شود

کسی که خودش کار را کرده. استادی که هفته را منتشر کرد اعلان «هفتهٔ تازه»
نمی‌گیرد، بازبین اعلان تأیید تحویلی که خودش تأیید کرد نمی‌گیرد، و مدیر
پروژه‌ای که خودش تحویل فرستاده، «تحویل تازه» نمی‌گیرد.

## نتیجهٔ آزمون

تصحیح خودکار اعلان ندارد: دانشجو نتیجه را همان لحظه روی صفحه می‌بیند.
اعلان فقط وقتی است که نتیجه **بعداً** معلوم می‌شود — تصحیح تشریحی به دست
استاد، یا انتشار دستی نتیجه.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from silp.domain.calendar import format_datetime_fa
from silp.domain.notifications.templating import excerpt
from silp.domain.text import to_persian_digits
from silp.models.delivery import Deliverable, Milestone
from silp.models.education import Announcement, Course, CourseOffering, CourseWeek, Enrollment
from silp.models.gamification import Badge, PointEntry
from silp.models.project import Project, ProjectApplication
from silp.models.quiz import GradeAppeal, Quiz, QuizAttempt
from silp.services import events
from silp.services.directory import display_names, name_of
from silp.services.grading_service import results_visible
from silp.services.notification_service import NotificationService
from silp.services.point_listeners import active_member_ids

#: وقتی نام کاربر هنوز ثبت نشده (پیش از ورود اولیه).
UNKNOWN_NAME = "یک کاربر"
DEFAULT_REJECTION_HINT = "پروژه‌های پیشنهادی دیگر را در صفحهٔ پروژه‌ها ببین."


def _now() -> datetime:
    return datetime.now(UTC)


def fa_number(value: Decimal | int | float) -> str:
    """۱۲ یا ۱۲٫۵ — صفرهای اعشاری بی‌معنا حذف می‌شوند."""
    number = Decimal(str(value))
    text = format(number.normalize(), "f") if number != number.to_integral() else str(int(number))
    return to_persian_digits(text)


async def course_title(session: AsyncSession, offering_id: uuid.UUID) -> str:
    title = await session.scalar(
        select(Course.title_fa)
        .join(CourseOffering, CourseOffering.course_id == Course.id)
        .where(CourseOffering.id == offering_id)
    )
    return title or "درس"


async def _active_students(session: AsyncSession, offering_id: uuid.UUID) -> list[uuid.UUID]:
    return list(
        await session.scalars(
            select(Enrollment.student_id).where(
                Enrollment.offering_id == offering_id, Enrollment.status == "ACTIVE"
            )
        )
    )


async def _name(session: AsyncSession, user_id: uuid.UUID) -> str:
    return name_of(await display_names(session, [user_id]), user_id) or UNKNOWN_NAME


# ── حساب ───────────────────────────────────────────────────────────────
@events.subscribe(events.UserRegistered)
async def on_user_registered(session: AsyncSession, event: events.UserRegistered) -> None:
    await NotificationService(session).notify(
        "WELCOME", [event.user_id], action_url="/dashboard", dedup_key="WELCOME"
    )


@events.subscribe(events.SessionsRevoked)
async def on_sessions_revoked(session: AsyncSession, event: events.SessionsRevoked) -> None:
    await NotificationService(session).notify("SESSIONS_REVOKED", [event.user_id])


# ── دروس ───────────────────────────────────────────────────────────────
@events.subscribe(events.EnrollmentRequested)
async def on_enrollment_requested(session: AsyncSession, event: events.EnrollmentRequested) -> None:
    enrollment = await session.get(Enrollment, event.enrollment_id)
    if enrollment is None:
        return
    offering = await session.get(CourseOffering, enrollment.offering_id)
    if offering is None:
        return
    await NotificationService(session).notify(
        "ENROLLMENT_REQUESTED",
        [offering.instructor_id],
        {
            "student": await _name(session, enrollment.student_id),
            "course": await course_title(session, offering.id),
        },
        action_url=f"/teach/offerings/{offering.id}",
        dedup_key=f"ENROLLMENT_REQUESTED:{enrollment.id}:{enrollment.enrolled_at.isoformat()}",
    )


@events.subscribe(events.EnrollmentDecided)
async def on_enrollment_decided(session: AsyncSession, event: events.EnrollmentDecided) -> None:
    enrollment = await session.get(Enrollment, event.enrollment_id)
    if enrollment is None:
        return
    await NotificationService(session).notify(
        "ENROLLMENT_APPROVED" if event.approved else "ENROLLMENT_REJECTED",
        [enrollment.student_id],
        {"course": await course_title(session, enrollment.offering_id)},
        action_url=f"/courses/{enrollment.offering_id}" if event.approved else "/courses",
    )


@events.subscribe(events.WeekPublished)
async def on_week_published(session: AsyncSession, event: events.WeekPublished) -> None:
    week = await session.get(CourseWeek, event.week_id)
    if week is None:
        return
    await NotificationService(session).notify(
        "WEEK_PUBLISHED",
        await _active_students(session, week.offering_id),
        {
            "course": await course_title(session, week.offering_id),
            "week": to_persian_digits(week.week_number),
            "title": week.title_fa,
        },
        action_url=f"/courses/{week.offering_id}/weeks/{week.week_number}",
        dedup_key=f"WEEK_PUBLISHED:{week.id}",
    )


@events.subscribe(events.QuizPublished)
async def on_quiz_published(session: AsyncSession, event: events.QuizPublished) -> None:
    quiz = await session.get(Quiz, event.quiz_id)
    if quiz is None or quiz.closes_at <= _now():
        return
    await NotificationService(session).notify(
        "QUIZ_OPENED",
        await _active_students(session, quiz.offering_id),
        {
            "course": await course_title(session, quiz.offering_id),
            "quiz": quiz.title_fa,
            "closes_at": format_datetime_fa(quiz.closes_at),
        },
        action_url=f"/courses/{quiz.offering_id}/quizzes",
        dedup_key=f"QUIZ_OPENED:{quiz.id}",
    )


async def _notify_result(session: AsyncSession, quiz: Quiz, attempt: QuizAttempt) -> None:
    if attempt.status != "GRADED" or attempt.is_provisional or attempt.total_score is None:
        return
    if not results_visible(quiz, attempt, now=_now()):
        return
    await NotificationService(session).notify(
        "QUIZ_RESULT",
        [attempt.student_id],
        {
            "quiz": quiz.title_fa,
            "score": fa_number(attempt.total_score),
            "total": fa_number(quiz.total_points),
        },
        action_url=f"/quiz/{attempt.id}/result",
        dedup_key=f"QUIZ_RESULT:{attempt.id}",
    )


@events.subscribe(events.QuizGraded)
async def on_quiz_graded(session: AsyncSession, event: events.QuizGraded) -> None:
    if not event.manual:
        return
    attempt = await session.get(QuizAttempt, event.attempt_id)
    if attempt is None:
        return
    quiz = await session.get(Quiz, attempt.quiz_id)
    if quiz is not None:
        await _notify_result(session, quiz, attempt)


@events.subscribe(events.QuizResultsPublished)
async def on_quiz_results_published(
    session: AsyncSession, event: events.QuizResultsPublished
) -> None:
    quiz = await session.get(Quiz, event.quiz_id)
    if quiz is None:
        return
    attempts = await session.scalars(
        select(QuizAttempt)
        .where(QuizAttempt.quiz_id == quiz.id, QuizAttempt.status == "GRADED")
        .order_by(QuizAttempt.student_id, QuizAttempt.attempt_no.desc())
    )
    # یک اعلان برای هر دانشجو — آخرین تلاشش، نه یکی به‌ازای هر تلاش.
    latest: dict[uuid.UUID, QuizAttempt] = {}
    for attempt in attempts:
        latest.setdefault(attempt.student_id, attempt)
    for attempt in latest.values():
        await _notify_result(session, quiz, attempt)


@events.subscribe(events.AppealResolved)
async def on_appeal_resolved(session: AsyncSession, event: events.AppealResolved) -> None:
    appeal = await session.get(GradeAppeal, event.appeal_id)
    if appeal is None:
        return
    attempt = await session.get(QuizAttempt, appeal.attempt_id)
    quiz = await session.get(Quiz, attempt.quiz_id) if attempt else None
    if attempt is None or quiz is None:
        return
    outcome = "پذیرفته شد" if appeal.status == "ACCEPTED" else "پذیرفته نشد"
    if appeal.response:
        outcome = f"{outcome} — {excerpt(appeal.response, 100)}"
    await NotificationService(session).notify(
        "APPEAL_RESOLVED",
        [appeal.student_id],
        {"quiz": quiz.title_fa, "outcome": outcome},
        action_url=f"/quiz/{attempt.id}/result",
    )


@events.subscribe(events.AnnouncementPublished)
async def on_announcement_published(
    session: AsyncSession, event: events.AnnouncementPublished
) -> None:
    announcement = await session.get(Announcement, event.announcement_id)
    if announcement is None:
        return
    if announcement.offering_id is not None:
        recipients = await _active_students(session, announcement.offering_id)
        where = await course_title(session, announcement.offering_id)
        url = f"/courses/{announcement.offering_id}"
    elif announcement.project_id is not None:
        project = await session.get(Project, announcement.project_id)
        if project is None:
            return
        recipients = await active_member_ids(session, project.id)
        where = project.title_fa
        url = f"/projects/{project.id}/workspace"
    else:
        return
    await NotificationService(session).notify(
        "ANNOUNCEMENT_POSTED",
        [r for r in recipients if r != announcement.author_id],
        {
            "course": where,
            "title": announcement.title,
            "excerpt": excerpt(announcement.body, 280),
        },
        action_url=url,
        priority=announcement.priority,  # type: ignore[arg-type]
        dedup_key=f"ANNOUNCEMENT:{announcement.id}",
    )


# ── پروژه‌ها ────────────────────────────────────────────────────────────
@events.subscribe(events.ApplicationSubmitted)
async def on_application_submitted(
    session: AsyncSession, event: events.ApplicationSubmitted
) -> None:
    application = await session.get(ProjectApplication, event.application_id)
    if application is None:
        return
    project = await session.get(Project, application.project_id)
    if project is None:
        return
    await NotificationService(session).notify(
        "APPLICATION_SUBMITTED",
        [project.lead_id],
        {"project": project.title_fa, "applicant": await _name(session, application.applicant_id)},
        action_url=f"/projects/{project.id}/applications",
    )


@events.subscribe(events.ApplicationDecided)
async def on_application_decided(session: AsyncSession, event: events.ApplicationDecided) -> None:
    application = await session.get(ProjectApplication, event.application_id)
    if application is None:
        return
    project = await session.get(Project, application.project_id)
    if project is None:
        return
    service = NotificationService(session)
    values: dict[str, object] = {"project": project.title_fa}
    match event.decision:
        case "ACCEPTED":
            await service.notify(
                "APPLICATION_ACCEPTED",
                [application.applicant_id],
                values,
                action_url=f"/projects/{project.id}/workspace",
            )
        case "REJECTED":
            values["reason"] = application.decision_note or DEFAULT_REJECTION_HINT
            await service.notify(
                "APPLICATION_REJECTED", [application.applicant_id], values, action_url="/projects"
            )
        case "WAITLISTED":
            await service.notify(
                "APPLICATION_WAITLISTED",
                [application.applicant_id],
                values,
                action_url=f"/projects/{project.id}",
            )


async def _deliverable_scene(
    session: AsyncSession, deliverable_id: uuid.UUID
) -> tuple[Deliverable, Milestone, Project] | None:
    deliverable = await session.get(Deliverable, deliverable_id)
    if deliverable is None:
        return None
    milestone = await session.get(Milestone, deliverable.milestone_id)
    if milestone is None:
        return None
    project = await session.get(Project, milestone.project_id)
    if project is None:
        return None
    return deliverable, milestone, project


@events.subscribe(events.DeliverableSubmitted)
async def on_deliverable_submitted(
    session: AsyncSession, event: events.DeliverableSubmitted
) -> None:
    scene = await _deliverable_scene(session, event.deliverable_id)
    if scene is None:
        return
    deliverable, milestone, project = scene
    if project.lead_id == deliverable.submitter_id:
        return
    await NotificationService(session).notify(
        "DELIVERABLE_SUBMITTED",
        [project.lead_id],
        {
            "project": project.title_fa,
            "milestone": milestone.title_fa,
            "submitter": await _name(session, deliverable.submitter_id),
        },
        action_url=f"/projects/{project.id}/workspace",
    )


@events.subscribe(events.DeliverableReviewed)
async def on_deliverable_reviewed(session: AsyncSession, event: events.DeliverableReviewed) -> None:
    """تأیید به کل تیم خبر داده می‌شود (امتیازش هم به کل تیم رسید)؛ اصلاح و رد
    فقط به فرستنده — او باید نسخهٔ بعدی را بفرستد."""
    scene = await _deliverable_scene(session, event.deliverable_id)
    if scene is None:
        return
    deliverable, milestone, project = scene
    service = NotificationService(session)
    url = f"/projects/{project.id}/workspace"
    values: dict[str, object] = {"project": project.title_fa, "milestone": milestone.title_fa}

    if event.decision == "APPROVED":
        team = await active_member_ids(session, project.id)
        members = [m for m in team if m != event.reviewer_id]
        # امتیاز هر عضو همان است که شنوندهٔ امتیاز همین لحظه ثبت کرد
        # (LISTENER_MODULES: امتیاز پیش از اعلان).
        earned: dict[uuid.UUID, Decimal] = {
            row[0]: row[1]
            for row in (
                await session.execute(
                    select(PointEntry.user_id, func.sum(PointEntry.amount))
                    .where(
                        PointEntry.user_id.in_(members),
                        PointEntry.rule_code == "MILESTONE_APPROVED",
                        PointEntry.source_type == "MILESTONE",
                        PointEntry.source_id == milestone.id,
                    )
                    .group_by(PointEntry.user_id)
                )
            ).all()
        }
        for member_id in members:
            await service.notify(
                "DELIVERABLE_APPROVED",
                [member_id],
                {**values, "points": fa_number(earned.get(member_id) or 0)},
                action_url=url,
                dedup_key=f"DELIVERABLE_APPROVED:{deliverable.id}",
            )
        return

    changes = event.decision == "CHANGES_REQUESTED"
    kind = "DELIVERABLE_CHANGES" if changes else "DELIVERABLE_REJECTED"
    await service.notify(
        kind,
        [deliverable.submitter_id],
        {**values, "feedback": excerpt(deliverable.feedback or "", 200)},
        action_url=url,
    )


@events.subscribe(events.ProjectStalled)
async def on_project_stalled(session: AsyncSession, event: events.ProjectStalled) -> None:
    project = await session.get(Project, event.project_id)
    if project is None:
        return
    recipients = [project.lead_id]
    if project.offering_id is not None:
        offering = await session.get(CourseOffering, project.offering_id)
        if offering is not None:
            recipients.append(offering.instructor_id)
    await NotificationService(session).notify(
        "PROJECT_STALLED",
        recipients,
        {"project": project.title_fa, "days": to_persian_digits(event.days_inactive)},
        action_url=f"/projects/{project.id}/workspace",
    )


# ── نشان ───────────────────────────────────────────────────────────────
@events.subscribe(events.BadgeAwarded)
async def on_badge_awarded(session: AsyncSession, event: events.BadgeAwarded) -> None:
    badge = await session.get(Badge, event.badge_code)
    if badge is None:
        return
    await NotificationService(session).notify(
        "BADGE_AWARDED",
        [event.user_id],
        {"badge": badge.title_fa},
        action_url="/me/badges",
        dedup_key=f"BADGE:{badge.code}",
    )


__all__ = ["course_title", "fa_number"]
