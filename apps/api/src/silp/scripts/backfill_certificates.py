"""صدور گواهی برای کارهای پیش از M7 بخش د — ADR-0017.

اجرا::

    python -m silp.scripts.backfill_certificates

گواهی از M7-11 با رویدادها صادر می‌شود. پروژه‌ای که پیش از آن بسته شد،
سطح پژوهشی که پیش از آن تأیید شد و درسی که پیش از آن نمره گرفت، رویدادی
برای صدور نساخته‌اند. این اسکریپت وضعیت فعلی هرکدام را از همان
شنونده‌های `silp.services.certificate_listeners` رد می‌کند.

**بی‌اثر در تکرار است:** ایندکس یکتای «یک گواهی معتبر برای هر موضوع»
گواهی دوم نمی‌سازد. اعلان «گواهی تازه» هم با کلید تکرار یک‌بار می‌رود.
تاریخ صدور، لحظهٔ اجراست — تاریخ ساختگیِ گذشته روی سند نمی‌نویسیم.
"""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import select

from silp.core.config import get_settings
from silp.core.logging import configure_logging, get_logger
from silp.db.session import dispose_engine, session_scope
from silp.models.education import Enrollment
from silp.models.project import Project
from silp.models.research import ResearchSubmission
from silp.services import certificate_listeners, events

log = get_logger("silp.backfill")


async def backfill() -> tuple[int, int]:
    async with session_scope() as session:
        before = await certificate_listeners.certificate_count(session)
        projects = list(
            await session.scalars(
                select(Project.id).where(
                    Project.status == "COMPLETED", Project.deleted_at.is_(None)
                )
            )
        )
        for project_id in projects:
            await certificate_listeners.on_project_completed(
                session, events.ProjectCompleted(project_id=project_id)
            )
        submissions = list(
            await session.scalars(
                select(ResearchSubmission.id).where(ResearchSubmission.status == "APPROVED")
            )
        )
        for submission_id in submissions:
            await certificate_listeners.on_research_reviewed(
                session, events.ResearchReviewed(submission_id=submission_id)
            )
        enrollments = list(
            await session.scalars(select(Enrollment.id).where(Enrollment.status == "COMPLETED"))
        )
        for enrollment_id in enrollments:
            await certificate_listeners.on_enrollment_completed(
                session, events.EnrollmentCompleted(enrollment_id=enrollment_id)
            )
        await session.commit()
        after = await certificate_listeners.certificate_count(session)
        print(f"  پروژهٔ تکمیل‌شده: {len(projects)}")
        print(f"  سطح پژوهش تأییدشده: {len(submissions)}")
        print(f"  درس با نمرهٔ نهایی: {len(enrollments)}")
        return len(projects) + len(submissions) + len(enrollments), after - before


async def main() -> int:
    settings = get_settings()
    configure_logging(settings.log_level, renderer="console")
    print("صدور گواهی برای کارهای پیشین…")
    try:
        sources, issued = await backfill()
    finally:
        await dispose_engine()
    print(f"انجام شد — {sources} منبع بررسی و {issued} گواهی تازه صادر شد.")
    log.info("certificates_backfilled", sources=sources, issued=issued)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
