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

from silp.core.permissions import ROLE_TITLE_FA, Role
from silp.domain import city as city_rules
from silp.domain import research as research_rules
from silp.domain import ventures as venture_rules
from silp.domain.calendar import format_date_fa, format_datetime_fa
from silp.domain.gamification.formulas import LOCAL_TZ
from silp.domain.notifications.templating import excerpt
from silp.domain.text import format_number_fa, join_fa, to_persian_digits
from silp.models.access import Subscription, SubscriptionPlan
from silp.models.delivery import (
    Certificate,
    Deliverable,
    Milestone,
    OpeningApplication,
    TeamOpening,
)
from silp.models.education import (
    Announcement,
    Course,
    CourseOffering,
    CourseWeek,
    Enrollment,
    Term,
)
from silp.models.gamification import Badge, PointEntry
from silp.models.idea import Idea, IdeaComment
from silp.models.intake import IntakeEvent, IntakeRequest
from silp.models.project import Project, ProjectApplication, Team, TeamInvitation
from silp.models.qa import QaReply, QaThread
from silp.models.quiz import GradeAppeal, Quiz, QuizAttempt
from silp.models.research import (
    ResearchOutput,
    ResearchSubmission,
    ResearchTopic,
    ResearchTrack,
)
from silp.models.venture import METRIC_TITLE_FA, Venture, VentureMetric, VentureStageChange
from silp.services import events
from silp.services.directory import display_names, name_of
from silp.services.grading_service import results_visible
from silp.services.intake_service import IntakeService
from silp.services.notification_service import NotificationService
from silp.services.opening_service import OpeningService
from silp.services.point_listeners import active_member_ids, venture_member_ids
from silp.services.points_service import PointsService
from silp.services.reflection_service import RULE_CODE as REFLECTION_RULE

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


def announcement_dedup_key(announcement_id: uuid.UUID) -> str:
    return f"ANNOUNCEMENT:{announcement_id}"


async def _announcement_notice(
    session: AsyncSession, announcement: Announcement
) -> tuple[list[uuid.UUID], dict[str, str], str] | None:
    """گیرندگان، متغیرها و پیوند اعلان — مشترک انتشار و ویرایش."""
    if announcement.offering_id is not None:
        recipients = await _active_students(session, announcement.offering_id)
        where = await course_title(session, announcement.offering_id)
        url = f"/courses/{announcement.offering_id}"
    elif announcement.project_id is not None:
        project = await session.get(Project, announcement.project_id)
        if project is None:
            return None
        recipients = await active_member_ids(session, project.id)
        where = project.title_fa
        url = f"/projects/{project.id}/workspace"
    else:
        return None
    values = {
        "course": where,
        "title": announcement.title,
        "excerpt": excerpt(announcement.body, 280),
    }
    return [r for r in recipients if r != announcement.author_id], values, url


@events.subscribe(events.AnnouncementPublished)
async def on_announcement_published(
    session: AsyncSession, event: events.AnnouncementPublished
) -> None:
    announcement = await session.get(Announcement, event.announcement_id)
    if announcement is None:
        return
    notice = await _announcement_notice(session, announcement)
    if notice is None:
        return
    recipients, values, url = notice
    await NotificationService(session).notify(
        "ANNOUNCEMENT_POSTED",
        recipients,
        values,
        action_url=url,
        priority=announcement.priority,  # type: ignore[arg-type]
        dedup_key=announcement_dedup_key(announcement.id),
    )


@events.subscribe(events.AnnouncementRevised)
async def on_announcement_revised(session: AsyncSession, event: events.AnnouncementRevised) -> None:
    """ADR-0021 — «امتحان به شنبه افتاد» نباید در مرکز اعلان هنوز «جمعه» بگوید."""
    announcement = await session.get(Announcement, event.announcement_id)
    if announcement is None:
        return
    notice = await _announcement_notice(session, announcement)
    if notice is None:
        return
    await NotificationService(session).revise(
        "ANNOUNCEMENT_POSTED", announcement_dedup_key(announcement.id), notice[1]
    )


@events.subscribe(events.AnnouncementWithdrawn)
async def on_announcement_withdrawn(
    session: AsyncSession, event: events.AnnouncementWithdrawn
) -> None:
    await NotificationService(session).retract(announcement_dedup_key(event.announcement_id))


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
        action_url=_milestone_url(project),
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
    url = _milestone_url(project)
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


@events.subscribe(events.ProjectCompleted)
async def on_project_completed(session: AsyncSession, event: events.ProjectCompleted) -> None:
    """ADR-0024 — «درخواست بازتاب از اعضا» (§7.13). بدون این، فرم را کسی پیدا نمی‌کند.

    همهٔ اعضای فعال، مدیری که پروژه را بست هم: بازتاب او هم لازم است. متن
    امتیاز را از خودِ قاعده می‌خواند (مدیر عوضش می‌کند) و اگر قاعده غیرفعال
    است چیزی نمی‌گوید.
    """
    project = await session.get(Project, event.project_id)
    if project is None or project.status != "COMPLETED":
        return
    rule = await PointsService(session).rule(REFLECTION_RULE)
    reward = (
        f"{fa_number(rule.base_points)} امتیاز یادگیری هم دارد."
        if rule is not None and rule.is_active
        else ""
    )
    await NotificationService(session).notify(
        "REFLECTION_REQUESTED",
        await active_member_ids(session, project.id),
        {"project": project.title_fa, "reward": reward},
        action_url=f"/projects/{project.id}/workspace",
        dedup_key=f"REFLECTION_REQUESTED:{project.id}",
    )


# ── پرسش‌وپاسخ درس — ADR-0024 برش ج ─────────────────────────────────────
def _qa_url(thread: QaThread) -> str:
    return f"/courses/{thread.offering_id}/qa?thread={thread.id}"


@events.subscribe(events.QaReplyPosted)
async def on_qa_reply_posted(session: AsyncSession, event: events.QaReplyPosted) -> None:
    """«پاسخ تازه به پرسشت» — به پرسنده، نه به خودِ پاسخ‌دهنده."""
    reply = await session.get(QaReply, event.reply_id)
    thread = await session.get(QaThread, reply.thread_id) if reply is not None else None
    if reply is None or thread is None or thread.author_id == reply.author_id:
        return
    await NotificationService(session).notify(
        "QA_REPLY_POSTED",
        [thread.author_id],
        {
            "course": await course_title(session, thread.offering_id),
            "thread": excerpt(thread.title, 80),
            "replier": await _name(session, reply.author_id),
            "excerpt": excerpt(reply.body, 120),
        },
        action_url=_qa_url(thread),
        dedup_key=f"QA_REPLY_POSTED:{reply.id}",
    )


@events.subscribe(events.QaReplyEndorsed)
async def on_qa_reply_endorsed(session: AsyncSession, event: events.QaReplyEndorsed) -> None:
    """«استاد پاسخت را تأیید کرد» — فقط هنگام گذاشتن تأیید، و یک‌بار برای هر پاسخ.

    برداشتن تأیید اعلان ندارد؛ تأیید دوباره هم تکرار نمی‌شود (`dedup_key`).
    امتیاز را شنوندهٔ امتیاز همین لحظه ثبت کرد (پیش از اعلان اجرا می‌شود)، پس
    جمع خالص دفتر همان است که پرسنده در حسابش می‌بیند.
    """
    reply = await session.get(QaReply, event.reply_id)
    thread = await session.get(QaThread, reply.thread_id) if reply is not None else None
    if reply is None or thread is None or reply.endorsed_at is None:
        return
    earned = await session.scalar(
        select(func.coalesce(func.sum(PointEntry.amount), 0)).where(
            PointEntry.user_id == reply.author_id,
            PointEntry.source_type == "QA_REPLY",
            PointEntry.source_id == reply.id,
        )
    )
    await NotificationService(session).notify(
        "QA_REPLY_ENDORSED",
        [reply.author_id],
        {
            "course": await course_title(session, thread.offering_id),
            "thread": excerpt(thread.title, 80),
            "reward": f"{fa_number(earned)} امتیاز جامعه گرفتی." if earned and earned > 0 else "",
        },
        action_url=_qa_url(thread),
        dedup_key=f"QA_REPLY_ENDORSED:{reply.id}",
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


# ── ایده — M7 ──────────────────────────────────────────────────────────
@events.subscribe(events.IdeaCommented)
async def on_idea_commented(session: AsyncSession, event: events.IdeaCommented) -> None:
    """نویسندهٔ ایده، و نویسندهٔ نظری که به آن پاسخ داده شد — نه خودِ نظردهنده."""
    comment = await session.get(IdeaComment, event.comment_id)
    if comment is None:
        return
    idea = await session.get(Idea, comment.idea_id)
    if idea is None:
        return
    recipients = [idea.author_id]
    if comment.parent_id is not None:
        parent = await session.get(IdeaComment, comment.parent_id)
        if parent is not None:
            recipients.append(parent.author_id)
    recipients = [uid for uid in recipients if uid != comment.author_id]
    await NotificationService(session).notify(
        "IDEA_COMMENTED",
        recipients,
        {
            "idea": idea.title,
            "commenter": await _name(session, comment.author_id),
            "excerpt": excerpt(comment.body, 120),
        },
        action_url=f"/ideas/{idea.id}",
        dedup_key=f"IDEA_COMMENTED:{comment.id}",
    )


@events.subscribe(events.IdeaPromoted)
async def on_idea_promoted(session: AsyncSession, event: events.IdeaPromoted) -> None:
    idea = await session.get(Idea, event.idea_id)
    if idea is None or idea.promoted_to_id is None or idea.promoted_by == idea.author_id:
        return
    if idea.promoted_to_type == "VENTURE":
        venture = await session.get(Venture, idea.promoted_to_id)
        values = {
            "target": "کسب‌وکار",
            "title": venture.name if venture else idea.title,
            "next_step": "تو بنیان‌گذار آنی؛ مشخصاتش را کامل کن.",
        }
        url = f"/ventures/{idea.promoted_to_id}"
    else:
        project = await session.get(Project, idea.promoted_to_id)
        values = {
            "target": "پروژه",
            "title": project.title_fa if project else idea.title,
            "next_step": "دعوت پیوستن به تیمش برایت فرستاده شد.",
        }
        url = "/me/invitations"
    await NotificationService(session).notify(
        "IDEA_PROMOTED",
        [idea.author_id],
        {"idea": idea.title, **values},
        action_url=url,
        dedup_key=f"IDEA_PROMOTED:{idea.id}",
    )


# ── تیم و کارآفرینی — M7 ───────────────────────────────────────────────
async def _team_title(session: AsyncSession, invitation: TeamInvitation) -> str:
    team = await session.get(Team, invitation.team_id)
    return team.name if team is not None else "تیم"


@events.subscribe(events.InvitationSent)
async def on_invitation_sent(session: AsyncSession, event: events.InvitationSent) -> None:
    invitation = await session.get(TeamInvitation, event.invitation_id)
    if invitation is None:
        return
    await NotificationService(session).notify(
        "TEAM_INVITATION",
        [invitation.invitee_id],
        {
            "inviter": await _name(session, invitation.inviter_id),
            "team": await _team_title(session, invitation),
            "message": excerpt(invitation.message or "", 200),
        },
        action_url="/me/invitations",
        dedup_key=f"TEAM_INVITATION:{invitation.id}",
    )


@events.subscribe(events.InvitationAccepted)
async def on_invitation_accepted(session: AsyncSession, event: events.InvitationAccepted) -> None:
    invitation = await session.get(TeamInvitation, event.invitation_id)
    if invitation is None:
        return
    await NotificationService(session).notify(
        "INVITATION_ACCEPTED",
        [invitation.inviter_id],
        {
            "invitee": await _name(session, invitation.invitee_id),
            "team": await _team_title(session, invitation),
        },
        dedup_key=f"INVITATION_ACCEPTED:{invitation.id}",
    )


@events.subscribe(events.MetricReviewed)
async def on_metric_reviewed(session: AsyncSession, event: events.MetricReviewed) -> None:
    row = await session.get(VentureMetric, event.metric_id)
    if row is None or row.status == "PENDING":
        return
    if row.venture_id is not None:
        venture = await session.get(Venture, row.venture_id)
        owner = venture.name if venture else "کسب‌وکار"
        url = f"/ventures/{row.venture_id}"
    else:
        project = await session.get(Project, row.project_id)
        owner = project.title_fa if project else "پروژه"
        url = f"/projects/{row.project_id}/workspace"

    if row.status == "VERIFIED":
        # امتیاز پیش از اعلان ثبت شده (ترتیب `LISTENER_MODULES`).
        earned = await session.scalar(
            select(func.sum(PointEntry.amount)).where(
                PointEntry.user_id == row.user_id,
                PointEntry.source_type == "METRIC",
                PointEntry.source_id == row.id,
            )
        )
        detail = f"{fa_number(earned)} امتیاز کارآفرینی گرفتی." if earned else ""
        if row.share_rial:
            share = f"سهمت از این فروش {format_number_fa(row.share_rial)} ریال است."
            detail = f"{detail} {share}".strip()
        decision = "تأیید شد"
    else:
        detail = excerpt(row.review_note or "", 200)
        decision = "رد شد"
    value = format_number_fa(row.value)
    if row.metric == "SALES_AMOUNT":
        value = f"{value} ریال"
    await NotificationService(session).notify(
        "METRIC_REVIEWED",
        [row.user_id],
        {
            "metric": METRIC_TITLE_FA.get(row.metric, row.metric),
            "value": value,
            "owner": owner,
            "decision": decision,
            "detail": detail,
        },
        action_url=url,
        dedup_key=f"METRIC_REVIEWED:{row.id}",
    )


@events.subscribe(events.VentureStageChanged)
async def on_venture_stage_changed(
    session: AsyncSession, event: events.VentureStageChanged
) -> None:
    change = await session.get(VentureStageChange, event.change_id)
    if change is None:
        return
    venture = await session.get(Venture, change.venture_id)
    if venture is None:
        return
    recipients = [
        uid for uid in await venture_member_ids(session, venture.id) if uid != change.changed_by
    ]
    await NotificationService(session).notify(
        "VENTURE_STAGE_CHANGED",
        recipients,
        {
            "venture": venture.name,
            "stage": venture_rules.stage_title(change.to_stage),
            "from_stage": venture_rules.stage_title(change.from_stage),
        },
        action_url=f"/ventures/{venture.id}",
        dedup_key=f"VENTURE_STAGE_CHANGED:{change.id}",
    )


# ── پژوهش و آگهی هم‌تیمی — M7 بخش ب ───────────────────────────────────
def level_label(level: int) -> str:
    """«۲ (تحلیل داده)» — شمارهٔ سطح با عنوانش."""
    return f"{to_persian_digits(level)} ({research_rules.level_spec(level).title_fa})"


async def _earned(
    session: AsyncSession, user_id: uuid.UUID, source_type: str, source_id: uuid.UUID
) -> Decimal | None:
    """امتیاز فعال این منبع — امتیاز پیش از اعلان ثبت شده (ترتیب `LISTENER_MODULES`)."""
    total: Decimal | None = await session.scalar(
        select(func.sum(PointEntry.amount)).where(
            PointEntry.user_id == user_id,
            PointEntry.source_type == source_type,
            PointEntry.source_id == source_id,
        )
    )
    return total


@events.subscribe(events.ResearchSubmitted)
async def on_research_submitted(session: AsyncSession, event: events.ResearchSubmitted) -> None:
    """به منتور سطح — کسی که پیش‌تر همین سطح را بررسی کرده. تحویل اول منتور ندارد و در صف می‌نشیند."""
    row = await session.get(ResearchSubmission, event.submission_id)
    if row is None:
        return
    track = await session.get(ResearchTrack, (row.user_id, row.level))
    if track is None or track.mentor_id is None or track.mentor_id == row.user_id:
        return
    await NotificationService(session).notify(
        "RESEARCH_SUBMITTED",
        [track.mentor_id],
        {"student": await _name(session, row.user_id), "level": level_label(row.level)},
        action_url="/research/review",
        dedup_key=f"RESEARCH_SUBMITTED:{row.id}",
    )


@events.subscribe(events.ResearchReviewed)
async def on_research_reviewed(session: AsyncSession, event: events.ResearchReviewed) -> None:
    row = await session.get(ResearchSubmission, event.submission_id)
    if row is None or row.status == "SUBMITTED":
        return
    if row.status == "APPROVED":
        earned = await _earned(session, row.user_id, "RESEARCH_SUBMISSION", row.id)
        decision = "تأیید شد"
        detail = f"{fa_number(earned)} امتیاز پژوهش گرفتی." if earned else ""
        if row.level < research_rules.MAX_LEVEL:
            detail = (detail + " سطح بعدی برایت باز شد.").strip()
    else:
        decision = "نیاز به اصلاح دارد"
        detail = excerpt(row.feedback or "", 200)
    await NotificationService(session).notify(
        "RESEARCH_REVIEWED",
        [row.user_id],
        {"level": level_label(row.level), "decision": decision, "detail": detail},
        action_url=f"/research/level/{row.level}",
        dedup_key=f"RESEARCH_REVIEWED:{row.id}",
    )


@events.subscribe(events.TopicReviewed)
async def on_topic_reviewed(session: AsyncSession, event: events.TopicReviewed) -> None:
    topic = await session.get(ResearchTopic, event.topic_id)
    if topic is None or topic.reviewed_by == topic.proposer_id:
        return
    if event.approved:
        earned = await _earned(session, topic.proposer_id, "RESEARCH_TOPIC", topic.id)
        decision = "پذیرفته شد"
        detail = "حالا در بانک موضوع است و دیگران می‌توانند رزروش کنند."
        if earned:
            detail += f" {fa_number(earned)} امتیاز پژوهش گرفتی."
    else:
        decision = "پذیرفته نشد"
        detail = excerpt(topic.review_note or "", 200)
    await NotificationService(session).notify(
        "TOPIC_REVIEWED",
        [topic.proposer_id],
        {"topic": topic.title, "decision": decision, "detail": detail},
        action_url=f"/research/topics/{topic.id}",
        dedup_key=f"TOPIC_REVIEWED:{topic.id}",
    )


@events.subscribe(events.OutputReviewed)
async def on_output_reviewed(session: AsyncSession, event: events.OutputReviewed) -> None:
    output = await session.get(ResearchOutput, event.output_id)
    if output is None or output.review_status not in ("VERIFIED", "REJECTED"):
        return
    if output.review_status == "VERIFIED":
        earned = await _earned(session, output.owner_id, "RESEARCH_OUTPUT", output.id)
        decision = "راستی‌آزمایی شد"
        detail = f"امتیاز پژوهش این خروجی اکنون {fa_number(earned)} است." if earned else ""
    else:
        decision = "راستی‌آزمایی نشد"
        detail = excerpt(output.review_note or "", 200)
    assert output.reviewed_at is not None
    await NotificationService(session).notify(
        "OUTPUT_REVIEWED",
        [output.owner_id],
        {"title": output.title, "decision": decision, "detail": detail},
        action_url="/research/outputs",
        # هر بررسی یک اعلان — خروجی می‌تواند چند بار (ارسال، پذیرش، انتشار) بررسی شود.
        dedup_key=f"OUTPUT_REVIEWED:{output.id}:{output.reviewed_at.isoformat()}",
    )


@events.subscribe(events.OpeningCreated)
async def on_opening_created(session: AsyncSession, event: events.OpeningCreated) -> None:
    """FR-TEAM-02 «دانشجویان واجد شرایط، اعلان هدفمند دریافت می‌کنند»."""
    opening = await session.get(TeamOpening, event.opening_id)
    if opening is None:
        return
    service = OpeningService(session)
    target = await service.target_of(opening)
    notifications = NotificationService(session)
    for user_id, skills in await service.matching_users(opening):
        await notifications.notify(
            "OPENING_MATCH",
            [user_id],
            {"opening": opening.title, "team": target.title, "skills": join_fa(skills[:3])},
            action_url=f"/teams/openings/{opening.id}",
            dedup_key=f"OPENING_MATCH:{opening.id}",
        )


@events.subscribe(events.OpeningApplied)
async def on_opening_applied(session: AsyncSession, event: events.OpeningApplied) -> None:
    application = await session.get(OpeningApplication, event.application_id)
    if application is None:
        return
    opening = await session.get(TeamOpening, application.opening_id)
    if opening is None:
        return
    await NotificationService(session).notify(
        "OPENING_APPLIED",
        [opening.poster_id],
        {"applicant": await _name(session, application.applicant_id), "opening": opening.title},
        action_url=f"/teams/openings/{opening.id}",
        dedup_key=f"OPENING_APPLIED:{application.id}",
    )


@events.subscribe(events.OpeningDecided)
async def on_opening_decided(session: AsyncSession, event: events.OpeningDecided) -> None:
    application = await session.get(OpeningApplication, event.application_id)
    if application is None or application.status not in ("ACCEPTED", "DECLINED"):
        return
    opening = await session.get(TeamOpening, application.opening_id)
    if opening is None:
        return
    target = await OpeningService(session).target_of(opening)
    if application.status == "ACCEPTED":
        decision = "پذیرفته شد"
        detail = "حالا عضو تیمی؛ از صفحهٔ تیم شروع کن."
        url = (
            f"/projects/{target.project.id}/workspace"
            if target.project is not None
            else target.href
        )
    else:
        decision = "پذیرفته نشد"
        detail = excerpt(application.decision_note or "", 200)
        url = "/teams/openings"
    await NotificationService(session).notify(
        "OPENING_DECIDED",
        [application.applicant_id],
        {"opening": opening.title, "team": target.title, "decision": decision, "detail": detail},
        action_url=url,
        dedup_key=f"OPENING_DECIDED:{application.id}",
    )


# ── آزمایشگاه شهر هوشمند — M7 بخش ج ───────────────────────────────────
@events.subscribe(events.MilestoneOwnerAssigned)
async def on_milestone_owner_assigned(
    session: AsyncSession, event: events.MilestoneOwnerAssigned
) -> None:
    """کسی که خودش را مسئول کرد، از خودش خبر نمی‌گیرد."""
    milestone = await session.get(Milestone, event.milestone_id)
    if milestone is None or milestone.owner_id is None or milestone.owner_id == event.assigned_by:
        return
    project = await session.get(Project, milestone.project_id)
    if project is None:
        return
    await NotificationService(session).notify(
        "MILESTONE_OWNER_ASSIGNED",
        [milestone.owner_id],
        {
            "project": project.title_fa,
            "milestone": milestone.title_fa,
            "assigner": await _name(session, event.assigned_by),
        },
        action_url=_milestone_url(project),
    )


@events.subscribe(events.DeliverableReviewed)
async def on_city_stage_approved(session: AsyncSession, event: events.DeliverableReviewed) -> None:
    """تأیید مرحلهٔ n، مرحلهٔ n+۱ را باز می‌کند — به مسئولش خبر بده."""
    if event.decision != "APPROVED":
        return
    scene = await _deliverable_scene(session, event.deliverable_id)
    if scene is None:
        return
    _, milestone, project = scene
    stage = milestone.workflow_stage
    if stage is None or stage >= city_rules.STAGE_COUNT:
        return
    following = await session.scalar(
        select(Milestone).where(
            Milestone.project_id == project.id, Milestone.workflow_stage == stage + 1
        )
    )
    if following is None or following.owner_id is None or following.status == "APPROVED":
        return
    if following.owner_id == event.reviewer_id:
        return
    await NotificationService(session).notify(
        "CITY_STAGE_UNLOCKED",
        [following.owner_id],
        {
            "project": project.title_fa,
            "milestone": following.title_fa,
            "number": to_persian_digits(stage + 1),
        },
        action_url=_milestone_url(project),
        dedup_key=f"CITY_STAGE_UNLOCKED:{following.id}",
    )


@events.subscribe(events.CityWorkflowCompleted)
async def on_city_workflow_completed(
    session: AsyncSession, event: events.CityWorkflowCompleted
) -> None:
    project = await session.get(Project, event.project_id)
    if project is None:
        return
    recipients = [*await active_member_ids(session, project.id), project.lead_id]
    await NotificationService(session).notify(
        "CITY_WORKFLOW_COMPLETED",
        recipients,
        {"project": project.title_fa},
        action_url=f"/projects/{project.id}/city",
        dedup_key=f"CITY_WORKFLOW_COMPLETED:{project.id}",
    )


# ── گواهی و مدیریت — M7 بخش د ─────────────────────────────────────────
@events.subscribe(events.CertificateIssued)
async def on_certificate_issued(session: AsyncSession, event: events.CertificateIssued) -> None:
    certificate = await session.get(Certificate, event.certificate_id)
    if certificate is None or certificate.revoked_at is not None:
        return
    await NotificationService(session).notify(
        "CERTIFICATE_ISSUED",
        [certificate.user_id],
        {"title": certificate.title_fa},
        action_url="/me/certificates",
        dedup_key=f"CERTIFICATE_ISSUED:{certificate.id}",
        data={"public_code": certificate.public_code},
    )


@events.subscribe(events.CertificateRevoked)
async def on_certificate_revoked(session: AsyncSession, event: events.CertificateRevoked) -> None:
    certificate = await session.get(Certificate, event.certificate_id)
    if certificate is None or certificate.revoked_at is None:
        return
    await NotificationService(session).notify(
        "CERTIFICATE_REVOKED",
        [certificate.user_id],
        {"title": certificate.title_fa, "reason": certificate.revoke_reason or ""},
        action_url="/me/certificates",
        dedup_key=f"CERTIFICATE_REVOKED:{certificate.id}",
    )


@events.subscribe(events.SubscriptionActivated)
async def on_subscription_activated(
    session: AsyncSession, event: events.SubscriptionActivated
) -> None:
    """ADR-0019 — کسی که پول داده باید بداند دسترسی‌اش باز شد، نه حدس بزند."""
    subscription = await session.get(Subscription, event.subscription_id)
    if subscription is None or subscription.status != "ACTIVE":
        return
    plan = await session.get(SubscriptionPlan, subscription.plan_id)
    ends_on = subscription.ends_at.astimezone(LOCAL_TZ).date()
    await NotificationService(session).notify(
        "SUBSCRIPTION_ACTIVATED",
        [subscription.user_id],
        {
            "plan": plan.title_fa if plan else "",
            "ends_on": format_date_fa(ends_on, with_year=True),
        },
        action_url="/pricing",
        dedup_key=f"SUBSCRIPTION_ACTIVATED:{subscription.id}",
    )


@events.subscribe(events.SubscriptionRejected)
async def on_subscription_rejected(
    session: AsyncSession, event: events.SubscriptionRejected
) -> None:
    subscription = await session.get(Subscription, event.subscription_id)
    if subscription is None:
        return
    plan = await session.get(SubscriptionPlan, subscription.plan_id)
    await NotificationService(session).notify(
        "SUBSCRIPTION_REJECTED",
        [subscription.user_id],
        {"plan": plan.title_fa if plan else "", "reason": event.reason},
        action_url="/pricing",
        dedup_key=f"SUBSCRIPTION_REJECTED:{subscription.id}",
    )


#: وضعیت‌هایی که مشتری برایشان اعلان می‌گیرد. برگشتن به «ثبت‌شده» و بایگانی کار
#: داخلی مالک است؛ اعلانش «درخواست شما بایگانی شد» می‌شد بی‌آنکه چیزی از او بخواهد.
INTAKE_NOTIFIED_STATUS_FA = {
    "IN_REVIEW": "در حال بررسی",
    "ACCEPTED": "پذیرفته‌شده",
    "DECLINED": "پذیرفته‌نشده",
}


@events.subscribe(events.IntakeHandled)
async def on_intake_handled(session: AsyncSession, event: events.IntakeHandled) -> None:
    """ADR-0033 — مشتریِ دارای حساب از تغییر وضعیت و پیام مالک خبر می‌گیرد.

    گیرنده همان کسی است که `/me/requests` درخواست را به او نشان می‌دهد: `user_id`
    ذخیره‌شده، وگرنه کاربری با موبایل/ایمیل **تأییدشدهٔ** برابر. مشتری بی‌حساب گیرنده
    ندارد؛ برای او فقط `/track` می‌ماند (ADR-0032).

    متن فقط از وضعیت و `public_note` ساخته می‌شود؛ `owner_note` و راه تماس هرگز به
    این تابع نمی‌رسند.
    """
    request = await session.get(IntakeRequest, event.request_id)
    intake_event = await session.get(IntakeEvent, event.event_id)
    if request is None or intake_event is None:
        return
    recipient = request.user_id
    if recipient is None:
        user = await IntakeService(session).match_user(
            request.contact_mobile, request.contact_email
        )
        recipient = user.id if user else None
    if recipient is None or recipient == event.actor_id:
        return

    note = intake_event.public_note or ""
    status = INTAKE_NOTIFIED_STATUS_FA.get(intake_event.to_status)
    changed = intake_event.to_status != intake_event.from_status
    if changed and status:
        kind = "INTAKE_STATUS_CHANGED"
        values = {
            "code": request.tracking_code,
            "status": status,
            "note": f" توضیح: «{note}»" if note else "",
        }
    elif note:
        kind = "INTAKE_MESSAGE"
        values = {"code": request.tracking_code, "note": note}
    else:
        return
    await NotificationService(session).notify(
        kind,
        [recipient],
        values,
        action_url="/me/requests",
        dedup_key=f"INTAKE:{intake_event.id}",
    )


@events.subscribe(events.OfferingAssigned)
async def on_offering_assigned(session: AsyncSession, event: events.OfferingAssigned) -> None:
    """ADR-0021 — استاد از پنل ارائه می‌گیرد، نه از کسی که به او زنگ بزند.

    استاد قبلی هم خبر می‌گیرد: دسترسی‌اش همان لحظه بسته می‌شود و بی این
    اعلان فقط یک ۴۰۳ می‌بیند. کسی که ارائه را به خودش سپرده، اعلان نمی‌گیرد.
    """
    offering = await session.get(CourseOffering, event.offering_id)
    if offering is None or offering.instructor_id != event.instructor_id:
        return
    course = await session.get(Course, offering.course_id)
    term = await session.get(Term, offering.term_id)
    values = {
        "course": course.title_fa if course else "",
        "term": term.title_fa if term else "",
    }
    service = NotificationService(session)
    if event.instructor_id != event.actor_id:
        await service.notify(
            "OFFERING_ASSIGNED",
            [event.instructor_id],
            values,
            action_url=f"/teach/offerings/{offering.id}",
            data={"offering_id": str(offering.id)},
        )
    previous = event.previous_instructor_id
    if previous is not None and previous not in (event.actor_id, event.instructor_id):
        names = await display_names(session, [event.instructor_id])
        await service.notify(
            "OFFERING_REASSIGNED",
            [previous],
            {**values, "instructor": name_of(names, event.instructor_id) or "استاد دیگری"},
            action_url="/dashboard",
            data={"offering_id": str(offering.id)},
        )


@events.subscribe(events.RoleGranted)
async def on_role_granted(session: AsyncSession, event: events.RoleGranted) -> None:
    await NotificationService(session).notify(
        "ROLE_GRANTED",
        [event.user_id],
        {"role": ROLE_TITLE_FA.get(Role(event.role), event.role)},
        action_url="/dashboard",
    )


@events.subscribe(events.ImpersonationStarted)
async def on_impersonation_started(
    session: AsyncSession, event: events.ImpersonationStarted
) -> None:
    """§6.5 — «کاربر هدف اعلان دریافت می‌کند». نام پشتیبان را می‌بیند."""
    names = await display_names(session, [event.agent_id])
    agent = name_of(names, event.agent_id) or "پشتیبانی"
    await NotificationService(session).notify(
        "ACCOUNT_VIEWED_BY_SUPPORT",
        [event.target_id],
        {"agent": f"پشتیبانی رُستا ({agent})"},
    )


def _milestone_url(project: Project) -> str:
    """پروژهٔ شهری صفحهٔ گردش‌کار خودش را دارد؛ بقیه فضای کاری."""
    if project.workflow == city_rules.WORKFLOW_CITY:
        return f"/projects/{project.id}/city"
    return f"/projects/{project.id}/workspace"


__all__ = ["course_title", "fa_number", "level_label"]
