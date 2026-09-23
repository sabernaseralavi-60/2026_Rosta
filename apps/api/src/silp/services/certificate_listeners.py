"""شنونده‌های صدور گواهی — §7.13، ADR-0017.

| رویداد | گواهی |
|--------|-------|
| `ProjectCompleted` | «تکمیل پروژه» برای هر عضو فعال تیم |
| `ResearchReviewed` (تأیید) | «سطح n مسیر پژوهش» (ADR-0015 آن را به M7-11 سپرد) |
| `EnrollmentCompleted` | «گذراندن درس» با نمرهٔ ≥ ۱۰؛ نمرهٔ اصلاح‌شده به زیر ۱۰ باطلش می‌کند |

همه بی‌اثرند (ایندکس یکتای موضوع)، پس `backfill_certificates` همین
شنونده‌ها را روی گذشته دوباره اجرا می‌کند.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from silp.domain import certificates as rules
from silp.domain import research as research_rules
from silp.models.delivery import Certificate
from silp.models.education import Course, CourseOffering, Enrollment, Term
from silp.models.project import KIND_TITLE_FA, Project, Team, TeamMember
from silp.models.research import ResearchSubmission, ResearchTopic
from silp.services import events
from silp.services.certificate_service import CertificateService


@events.subscribe(events.ProjectCompleted)
async def on_project_completed(session: AsyncSession, event: events.ProjectCompleted) -> None:
    project = await session.get(Project, event.project_id)
    if project is None or project.status != "COMPLETED":
        return
    members = list(
        await session.execute(
            select(TeamMember.user_id, TeamMember.is_lead)
            .join(Team, Team.id == TeamMember.team_id)
            .where(Team.project_id == project.id, TeamMember.status == "ACTIVE")
        )
    )
    if not members:
        return
    course_title = None
    if project.offering_id is not None:
        course_title = await session.scalar(
            select(Course.title_fa)
            .join(CourseOffering, CourseOffering.course_id == Course.id)
            .where(CourseOffering.id == project.offering_id)
        )
    # بازپخش `backfill_points` کنشگر را نمی‌داند؛ آنجا مدیر پروژه صادرکننده است.
    issuer = event.completed_by or project.lead_id
    service = CertificateService(session)
    for user_id, is_lead in dict.fromkeys(members):
        await service.issue(
            user_id=user_id,
            kind="PROJECT",
            subject_id=project.id,
            title_fa=rules.project_title(project.title_fa),
            issued_by=issuer,
            meta={
                "project_id": str(project.id),
                "project_title": project.title_fa,
                "project_kind": project.kind,
                "project_kind_fa": KIND_TITLE_FA.get(project.kind, project.kind),
                "role": "LEAD" if is_lead else "MEMBER",
                "team_size": len(members),
                "course_title": course_title,
            },
        )


@events.subscribe(events.ResearchReviewed)
async def on_research_reviewed(session: AsyncSession, event: events.ResearchReviewed) -> None:
    row = await session.get(ResearchSubmission, event.submission_id)
    if row is None or row.status != "APPROVED":
        return
    spec = research_rules.level_spec(row.level)
    topic_title = None
    if row.topic_id is not None:
        topic_title = await session.scalar(
            select(ResearchTopic.title).where(ResearchTopic.id == row.topic_id)
        )
    await CertificateService(session).issue(
        user_id=row.user_id,
        kind="RESEARCH_LEVEL",
        # موضوع گواهی «سطح n این کاربر» است، نه یک نسخهٔ تحویل: هر سطح فقط
        # یک‌بار تأیید می‌شود و تحویل تأییدشده شناسهٔ پایدارش است.
        subject_id=row.id,
        title_fa=rules.research_title(row.level, spec.title_fa),
        issued_by=row.reviewed_by,
        meta={"level": row.level, "level_title": spec.title_fa, "topic_title": topic_title},
    )


@events.subscribe(events.EnrollmentCompleted)
async def on_enrollment_completed(session: AsyncSession, event: events.EnrollmentCompleted) -> None:
    enrollment = await session.get(Enrollment, event.enrollment_id)
    if enrollment is None or enrollment.status != "COMPLETED":
        return
    service = CertificateService(session)
    if not rules.course_passed(enrollment.final_grade):
        await service.revoke_auto(
            user_id=enrollment.student_id,
            kind="COURSE",
            subject_id=enrollment.offering_id,
            reason="نمرهٔ نهایی درس اصلاح شد و به حد قبولی نمی‌رسد.",
        )
        return
    row = (
        await session.execute(
            select(Course.title_fa, Term.title_fa, CourseOffering.instructor_id)
            .join(CourseOffering, CourseOffering.course_id == Course.id)
            .join(Term, Term.id == CourseOffering.term_id)
            .where(CourseOffering.id == enrollment.offering_id)
        )
    ).first()
    if row is None:
        return
    course_title, term_title, instructor_id = row
    await service.issue(
        user_id=enrollment.student_id,
        kind="COURSE",
        # موضوع، ارائه است — گذراندن دوبارهٔ همان درس در نیم‌سال دیگر گواهی
        # دیگری است.
        subject_id=enrollment.offering_id,
        title_fa=rules.course_title(course_title),
        issued_by=enrollment.decided_by or instructor_id,
        meta={"course_title": course_title, "term_title": term_title},
    )


async def certificate_count(session: AsyncSession) -> int:
    """شمار گواهی‌های معتبر — برای اسکریپت پس‌پر کردن."""
    return int(
        await session.scalar(
            select(func.count()).select_from(Certificate).where(Certificate.revoked_at.is_(None))
        )
        or 0
    )


__all__ = ["certificate_count"]
