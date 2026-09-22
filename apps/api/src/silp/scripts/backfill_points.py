"""بازسازی امتیاز از وضعیت موجود — M5.

اجرا::

    make points-backfill
    python -m silp.scripts.backfill_points

امتیاز از M5 با رویدادهای دامنه ثبت می‌شود (§7.13). هر کاری که **پیش از**
استقرار M5 انجام شده — نیمرخی که کامل شده، آزمونی که داده شده، مرحله‌ای
که تأیید شده — رویدادی نساخته و امتیازی ندارد. این اسکریپت وضعیت فعلی
هر منبع را از همان شنونده‌های `silp.services.point_listeners` رد می‌کند.

**بی‌اثر در تکرار است:** کلید بی‌اثری دفتر کل و `reconcile` تضمین می‌کنند
اجرای دوباره هیچ ردیف تکراری نسازد. پس می‌شود بی‌نگرانی دوباره اجرایش کرد.

دو محدودیت که باید دانست:

* زمان ردیف‌ها لحظهٔ اجرای اسکریپت است، نه لحظهٔ رویداد اصلی — دفتر کل
  تغییرناپذیر است و زمانِ ساختگیِ گذشته در آن نمی‌نویسیم. پس روند هفتگی
  داشبورد این امتیازها را در هفتهٔ اجرا نشان می‌دهد.
* سقف روزانه (مثلاً ۲۰ منبع در روز) از روز اجرا شمرده می‌شود.
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy import select

from silp.core.config import get_settings
from silp.core.logging import configure_logging, get_logger
from silp.db.session import dispose_engine, session_scope
from silp.models.delivery import Deliverable
from silp.models.education import AttendanceRecord, ClassSession, Enrollment, ResourceProgress
from silp.models.profile import TOTAL_SURVEY_STEPS, Profile
from silp.models.project import Project, ProjectApplication
from silp.models.quiz import Quiz, QuizAttempt
from silp.services import events, point_listeners
from silp.services.badge_service import BadgeService
from silp.services.point_listeners import LearningPoints
from silp.services.points_service import PointsService

log = get_logger("silp.backfill")


async def _replay(
    label: str,
    rows: list[Any],
    handle: Callable[[Any], Awaitable[None]],
) -> int:
    for row in rows:
        await handle(row)
    print(f"  {label}: {len(rows)}")
    return len(rows)


async def backfill() -> int:
    async with session_scope() as session:
        learning = LearningPoints(session)
        total = 0

        profiles = list(
            await session.scalars(
                select(Profile.user_id).where(Profile.survey_completed_steps >= TOTAL_SURVEY_STEPS)
            )
        )
        total += await _replay(
            "نیمرخ کامل",
            profiles,
            lambda uid: point_listeners.on_survey_step_completed(
                session, events.SurveyStepCompleted(uid, TOTAL_SURVEY_STEPS)
            ),
        )

        progress = list(
            await session.execute(
                select(ResourceProgress.user_id, ResourceProgress.resource_id)
                .where(ResourceProgress.status == "COMPLETED")
                .order_by(ResourceProgress.completed_at)
            )
        )
        total += await _replay(
            "منبع خوانده‌شده",
            progress,
            lambda row: point_listeners.on_resource_completed(
                session, events.ResourceCompleted(user_id=row[0], resource_id=row[1])
            ),
        )

        pairs = list(
            await session.execute(select(QuizAttempt.student_id, QuizAttempt.quiz_id).distinct())
        )

        async def quiz(row: Any) -> None:
            found = await session.get(Quiz, row[1])
            if found is not None:
                await learning.reconcile_quiz(student_id=row[0], quiz=found)

        total += await _replay("(دانشجو، آزمون)", pairs, quiz)

        attendance = list(
            await session.execute(
                select(ClassSession.offering_id, AttendanceRecord.student_id)
                .join(ClassSession, ClassSession.id == AttendanceRecord.session_id)
                .distinct()
            )
        )
        total += await _replay(
            "(ارائه، دانشجو) با حضور",
            attendance,
            lambda row: learning.reconcile_attendance(student_id=row[1], offering_id=row[0]),
        )

        completed = list(
            await session.scalars(select(Enrollment.id).where(Enrollment.status == "COMPLETED"))
        )
        total += await _replay(
            "درس تمام‌شده",
            completed,
            lambda eid: point_listeners.on_enrollment_completed(
                session, events.EnrollmentCompleted(enrollment_id=eid)
            ),
        )

        accepted = list(
            await session.scalars(
                select(ProjectApplication.id).where(ProjectApplication.status == "ACCEPTED")
            )
        )
        total += await _replay(
            "درخواست پذیرفته",
            accepted,
            lambda aid: point_listeners.on_application_accepted(
                session, events.ApplicationAccepted(application_id=aid)
            ),
        )

        approved = list(
            await session.execute(
                select(Deliverable.id, Deliverable.reviewed_by).where(
                    Deliverable.status == "APPROVED", Deliverable.reviewed_by.is_not(None)
                )
            )
        )
        total += await _replay(
            "تحویل‌دادنی تأییدشده",
            approved,
            lambda row: point_listeners.on_deliverable_reviewed(
                session,
                events.DeliverableReviewed(
                    deliverable_id=row[0], reviewer_id=row[1], decision="APPROVED"
                ),
            ),
        )

        projects = list(
            await session.scalars(select(Project.id).where(Project.status == "COMPLETED"))
        )
        total += await _replay(
            "پروژهٔ تکمیل‌شده",
            projects,
            lambda pid: point_listeners.on_project_completed(
                session, events.ProjectCompleted(project_id=pid)
            ),
        )

        await session.commit()
        await PointsService(session).refresh_totals()
        await session.commit()
        badges = await BadgeService(session).evaluate_recent(all_users=True)
        print(f"  نشان اعطاشده: {badges}")
        return total


async def main() -> int:
    settings = get_settings()
    configure_logging(settings.log_level, renderer="console")
    print("بازسازی امتیاز از وضعیت موجود…")
    try:
        replayed = await backfill()
    finally:
        await dispose_engine()
    print(f"انجام شد — {replayed} منبع بررسی شد.")
    log.info("points_backfilled", sources=replayed)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
