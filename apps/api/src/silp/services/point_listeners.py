"""اتصال رویدادهای دامنه به قواعد امتیاز — PRD §7.13، §9.2، M5-04.

هر شنونده اینجا یک رویداد (`silp.services.events`) را به ردیف‌های دفتر کل
ترجمه می‌کند. دو الگو هست:

* **رویداد یک‌باره** (پذیرش در پروژه، تأیید مرحله، تکمیل درس): `award`
  مستقیم. کلید بی‌اثری تکرار را بی‌اثر می‌کند.
* **امتیاز تابع وضعیت** (آزمون، حضور، تکمیل هفته): وضعیت مطلوب از
  دیتابیس حساب و با `reconcile` هم‌تراز می‌شود. همین تابع‌ها را کار
  پس‌زمینهٔ `release_quiz_points` هم صدا می‌زند.

قواعدی که ماژول منبعشان هنوز ساخته نشده (پژوهش، کارآفرینی، ایده،
پرسش‌وپاسخ، ارزیابی همتا، بازتاب) در `point_rules` هستند ولی شنونده ندارند؛
با همان ماژول‌ها در M7 وصل می‌شوند (§13.6).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from silp.core.logging import get_logger
from silp.core.permissions import Role
from silp.domain.gamification import formulas
from silp.models.delivery import Deliverable, Milestone
from silp.models.education import (
    AttendanceRecord,
    ClassSession,
    CourseWeek,
    Enrollment,
    Resource,
    ResourceProgress,
)
from silp.models.profile import TOTAL_SURVEY_STEPS
from silp.models.project import Project, ProjectApplication, Team, TeamMember
from silp.models.quiz import Quiz, QuizAttempt
from silp.services import authz, events
from silp.services.grading_service import results_visible
from silp.services.points_service import Award, PointsService, SourceKey

log = get_logger("silp.points.listeners")

ENROLLED_STATUSES = ("ACTIVE", "COMPLETED")
QUIZ_RULES = ("QUIZ_ATTEMPTED", "QUIZ_SCORE", "QUIZ_PERFECT", "QUIZ_FIRST_TRY")
#: پنجرهٔ نگاه‌به‌عقب کار `release_quiz_points` — چند برابر فاصلهٔ ۱۰ دقیقه‌ای.
RELEASE_LOOKBACK = timedelta(hours=2)


def _now() -> datetime:
    return datetime.now(UTC)


class LearningPoints:
    """امتیازهای تابع وضعیتِ یادگیری — آزمون، هفته، حضور."""

    def __init__(self, session: AsyncSession, points: PointsService | None = None) -> None:
        self.session = session
        self.points = points or PointsService(session)

    # ── آزمون — §9.2، §7.12 ────────────────────────────────────────────
    async def reconcile_quiz(self, *, student_id: uuid.UUID, quiz: Quiz) -> None:
        """چهار قاعدهٔ آزمون برای یک (دانشجو، آزمون).

        * `QUIZ_ATTEMPTED` — هر تلاش ارسال‌شده و باطل‌نشده.
        * `QUIZ_SCORE` — فقط **بهترین** تلاش (§9.8)؛ منبع خودِ تلاش است، پس
          تلاش بهتر بعدی، قبلی را معکوس و خودش را ثبت می‌کند (§7.12).
        * `QUIZ_PERFECT`، `QUIZ_FIRST_TRY` — یک‌بار برای هر آزمون.

        سه قاعدهٔ نمره‌ای فقط وقتی ثبت می‌شوند که (۱) نمره قطعی است —
        تشریحیِ تصحیح‌نشده ندارد — و (۲) دانشجو نتیجه را می‌بیند (ADR-0012).
        """
        attempts = list(
            await self.session.scalars(
                select(QuizAttempt)
                .where(
                    QuizAttempt.quiz_id == quiz.id,
                    QuizAttempt.student_id == student_id,
                    QuizAttempt.status == "GRADED",
                )
                .order_by(QuizAttempt.attempt_no)
            )
        )
        universe: list[SourceKey] = [
            (rule, "QUIZ", quiz.id) for rule in QUIZ_RULES if rule != "QUIZ_SCORE"
        ]
        all_attempt_ids = await self.session.scalars(
            select(QuizAttempt.id).where(
                QuizAttempt.quiz_id == quiz.id, QuizAttempt.student_id == student_id
            )
        )
        universe += [("QUIZ_SCORE", "QUIZ_ATTEMPT", aid) for aid in all_attempt_ids]

        desired: list[Award] = []
        if attempts:
            desired.append(Award("QUIZ_ATTEMPTED", "QUIZ", quiz.id, offering_id=quiz.offering_id))

        now = _now()
        final = [a for a in attempts if not a.is_provisional and a.total_score is not None]
        visible = [a for a in final if results_visible(quiz, a, now=now)]
        total = quiz.total_points
        if visible and total > 0:
            # بهترین نمره؛ در تساوی، تلاش زودتر — تلاش بعدیِ هم‌نمره چیزی نمی‌افزاید.
            best = max(visible, key=lambda a: (a.total_score, -a.attempt_no))
            score = best.total_score or Decimal(0)
            desired.append(
                Award(
                    "QUIZ_SCORE",
                    "QUIZ_ATTEMPT",
                    best.id,
                    multiplier=formulas.score_ratio(score, total),
                    offering_id=quiz.offering_id,
                )
            )
            if score >= total:
                desired.append(Award("QUIZ_PERFECT", "QUIZ", quiz.id, offering_id=quiz.offering_id))
            # «تلاش اول» یعنی اولین تلاش معتبر: تلاش باطل‌شده به خاطر خرابی
            # فنی، فرصت دانشجو را نمی‌سوزاند (همان منطق شمارش دفعات، M4).
            first = attempts[0]
            if first in visible and formulas.passed(
                first.total_score or Decimal(0), total, quiz.passing_score
            ):
                desired.append(
                    Award("QUIZ_FIRST_TRY", "QUIZ", quiz.id, offering_id=quiz.offering_id)
                )

        await self.points.reconcile(
            student_id, desired=desired, universe=universe, reason="بازنگری نمرهٔ آزمون"
        )
        if quiz.week_id is not None:
            await self.reconcile_week(student_id=student_id, week_id=quiz.week_id)

    async def release_closed_quizzes(self, *, lookback: timedelta = RELEASE_LOOKBACK) -> int:
        """کار `release_quiz_points` — امتیاز آزمون‌های «نتیجه پس از پایان».

        برای `IMMEDIATE` امتیاز همان لحظهٔ تصحیح ثبت می‌شود و برای `MANUAL`
        لحظهٔ انتشار دستی (رویداد `QuizResultsPublished`). ولی «پس از پایان
        مهلت» رویدادی ندارد — فقط گذر زمان است — پس یک کار زمان‌بندی‌شده
        آزمون‌هایی را که تازه بسته شده‌اند هم‌تراز می‌کند. پنجره چند برابر
        فاصلهٔ اجراست و `reconcile` بی‌اثر در تکرار است.

        خروجی: تعداد (دانشجو، آزمون)های بررسی‌شده.
        """
        now = _now()
        quizzes = list(
            await self.session.scalars(
                select(Quiz).where(
                    Quiz.result_visibility == "AFTER_CLOSE",
                    Quiz.status.in_(("PUBLISHED", "CLOSED")),
                    Quiz.deleted_at.is_(None),
                    Quiz.closes_at <= now,
                    Quiz.closes_at >= now - lookback,
                )
            )
        )
        checked = 0
        for quiz in quizzes:
            students = await self.session.scalars(
                select(QuizAttempt.student_id).where(QuizAttempt.quiz_id == quiz.id).distinct()
            )
            for student_id in list(students):
                await self.reconcile_quiz(student_id=student_id, quiz=quiz)
                checked += 1
        await self.session.commit()
        return checked

    # ── تکمیل هفته — §9.2 `WEEK_COMPLETED` ─────────────────────────────
    async def reconcile_week(self, *, student_id: uuid.UUID, week_id: uuid.UUID) -> None:
        """همهٔ منابع الزامی + یک تلاش تصحیح‌شده در هر آزمون هفته.

        هفته‌ای که نه منبع الزامی دارد نه آزمون، «تکمیل» ندارد — امتیازی
        که بدون هیچ کاری کسب شود، طبق §09 یک باگ است.
        """
        week = await self.session.get(CourseWeek, week_id)
        if week is None or week.status != "PUBLISHED":
            return
        if not await self.is_enrolled(student_id, week.offering_id):
            return

        required = list(
            await self.session.scalars(
                select(Resource.id).where(Resource.week_id == week_id, Resource.is_required)
            )
        )
        quizzes = list(
            await self.session.scalars(
                select(Quiz.id).where(
                    Quiz.week_id == week_id,
                    Quiz.status.in_(("PUBLISHED", "CLOSED")),
                    Quiz.deleted_at.is_(None),
                )
            )
        )
        complete = False
        if required or quizzes:
            done_resources = 0
            if required:
                done_resources = (
                    await self.session.scalar(
                        select(func.count())
                        .select_from(ResourceProgress)
                        .where(
                            ResourceProgress.user_id == student_id,
                            ResourceProgress.resource_id.in_(required),
                            ResourceProgress.status == "COMPLETED",
                        )
                    )
                    or 0
                )
            done_quizzes = 0
            if quizzes:
                done_quizzes = (
                    await self.session.scalar(
                        select(func.count(func.distinct(QuizAttempt.quiz_id))).where(
                            QuizAttempt.student_id == student_id,
                            QuizAttempt.quiz_id.in_(quizzes),
                            QuizAttempt.status == "GRADED",
                        )
                    )
                    or 0
                )
            complete = done_resources >= len(required) and done_quizzes >= len(quizzes)

        key: SourceKey = ("WEEK_COMPLETED", "COURSE_WEEK", week_id)
        desired = (
            [Award(*key, offering_id=week.offering_id, note=f"هفتهٔ {week.week_number}")]
            if complete
            else []
        )
        await self.points.reconcile(
            student_id, desired=desired, universe=[key], reason="هفته دیگر کامل نیست"
        )

    # ── حضور — §9.2 ────────────────────────────────────────────────────
    async def reconcile_attendance(self, *, student_id: uuid.UUID, offering_id: uuid.UUID) -> None:
        """`ATTENDANCE_PRESENT` برای هر حضور و `ATTENDANCE_STREAK` برای هر ۴ پیاپی.

        تابع وضعیت است چون حضور اصلاح می‌شود: استادی که «حاضر» را به
        «غایب» تغییر داد، هم امتیاز آن جلسه و هم زنجیره‌ای که شکست باید
        برگردد.
        """
        rows = list(
            await self.session.execute(
                select(ClassSession.id, AttendanceRecord.status)
                .outerjoin(
                    AttendanceRecord,
                    (AttendanceRecord.session_id == ClassSession.id)
                    & (AttendanceRecord.student_id == student_id),
                )
                .where(ClassSession.offering_id == offering_id)
                .order_by(ClassSession.held_on, ClassSession.id)
            )
        )
        session_ids = [sid for sid, _ in rows]
        statuses = [status for _, status in rows]

        universe: list[SourceKey] = []
        for sid in session_ids:
            universe.append(("ATTENDANCE_PRESENT", "CLASS_SESSION", sid))
            universe.append(("ATTENDANCE_STREAK", "CLASS_SESSION", sid))

        desired = [
            Award("ATTENDANCE_PRESENT", "CLASS_SESSION", sid, offering_id=offering_id)
            for sid, status in rows
            if status == "PRESENT"
        ]
        desired += [
            Award(
                "ATTENDANCE_STREAK",
                "CLASS_SESSION",
                session_ids[index],
                offering_id=offering_id,
            )
            for index in formulas.streak_completions(statuses)
        ]
        await self.points.reconcile(
            student_id, desired=desired, universe=universe, reason="اصلاح حضور و غیاب"
        )

    async def is_enrolled(self, student_id: uuid.UUID, offering_id: uuid.UUID) -> bool:
        found = await self.session.scalar(
            select(Enrollment.id).where(
                Enrollment.offering_id == offering_id,
                Enrollment.student_id == student_id,
                Enrollment.status.in_(ENROLLED_STATUSES),
            )
        )
        return found is not None


async def active_member_ids(session: AsyncSession, project_id: uuid.UUID) -> list[uuid.UUID]:
    rows = await session.scalars(
        select(TeamMember.user_id)
        .join(Team, Team.id == TeamMember.team_id)
        .where(Team.project_id == project_id, TeamMember.status == "ACTIVE")
    )
    return list(dict.fromkeys(rows))


# ── شنونده‌ها ──────────────────────────────────────────────────────────
@events.subscribe(events.ResourceCompleted)
async def on_resource_completed(session: AsyncSession, event: events.ResourceCompleted) -> None:
    resource = await session.get(Resource, event.resource_id)
    if resource is None:
        return
    week = await session.get(CourseWeek, resource.week_id)
    if week is None or week.status != "PUBLISHED":
        return
    learning = LearningPoints(session)
    # منبع فقط برای دانشجوی همان درس امتیاز دارد — استادی که جزوهٔ خودش
    # را باز می‌کند، امتیاز یادگیری نمی‌گیرد.
    if not await learning.is_enrolled(event.user_id, week.offering_id):
        return
    await learning.points.award(
        event.user_id,
        Award(
            "RESOURCE_COMPLETED",
            "RESOURCE",
            resource.id,
            offering_id=week.offering_id,
        ),
    )
    await learning.reconcile_week(student_id=event.user_id, week_id=week.id)


@events.subscribe(events.QuizGraded)
async def on_quiz_graded(session: AsyncSession, event: events.QuizGraded) -> None:
    attempt = await session.get(QuizAttempt, event.attempt_id)
    if attempt is None:
        return
    quiz = await session.get(Quiz, attempt.quiz_id)
    if quiz is None:
        return
    await LearningPoints(session).reconcile_quiz(student_id=attempt.student_id, quiz=quiz)


@events.subscribe(events.QuizResultsPublished)
async def on_quiz_results_published(
    session: AsyncSession, event: events.QuizResultsPublished
) -> None:
    quiz = await session.get(Quiz, event.quiz_id)
    if quiz is None:
        return
    learning = LearningPoints(session)
    students = await session.scalars(
        select(QuizAttempt.student_id).where(QuizAttempt.quiz_id == quiz.id).distinct()
    )
    for student_id in list(students):
        await learning.reconcile_quiz(student_id=student_id, quiz=quiz)


@events.subscribe(events.AttendanceRecorded)
async def on_attendance_recorded(session: AsyncSession, event: events.AttendanceRecorded) -> None:
    learning = LearningPoints(session)
    for student_id in event.student_ids:
        await learning.reconcile_attendance(student_id=student_id, offering_id=event.offering_id)


@events.subscribe(events.EnrollmentCompleted)
async def on_enrollment_completed(session: AsyncSession, event: events.EnrollmentCompleted) -> None:
    enrollment = await session.get(Enrollment, event.enrollment_id)
    if enrollment is None or enrollment.status != "COMPLETED":
        return
    await PointsService(session).award(
        enrollment.student_id,
        Award(
            "COURSE_COMPLETED",
            "ENROLLMENT",
            enrollment.id,
            offering_id=enrollment.offering_id,
        ),
    )


@events.subscribe(events.ApplicationDecided)
async def on_application_accepted(session: AsyncSession, event: events.ApplicationDecided) -> None:
    if event.decision != "ACCEPTED":
        return
    application = await session.get(ProjectApplication, event.application_id)
    if application is None or application.status != "ACCEPTED":
        return
    await PointsService(session).award(
        application.applicant_id,
        Award("APPLICATION_ACCEPTED", "APPLICATION", application.id),
    )


@events.subscribe(events.DeliverableReviewed)
async def on_deliverable_reviewed(session: AsyncSession, event: events.DeliverableReviewed) -> None:
    """`MILESTONE_APPROVED` برای تیم، و `MENTORED_DELIVERABLE` برای منتور.

    امتیاز مرحله به **همهٔ اعضای فعال تیم** می‌رسد، نه فقط فرستنده: مرحله
    کار تیم است و تحویل‌دهنده فقط کسی است که دکمه را زد. بازبین از این
    فهرست بیرون است — تأیید کار تیمی که خودت عضوش هستی، امتیاز خودت
    نیست (§9.8، ADR-0012).
    """
    deliverable = await session.get(Deliverable, event.deliverable_id)
    if deliverable is None:
        return
    points = PointsService(session)

    grants = await authz.get_grants(session, event.reviewer_id)
    if any(g.role is Role.MENTOR for g in grants) and event.reviewer_id != deliverable.submitter_id:
        await points.award(
            event.reviewer_id,
            Award("MENTORED_DELIVERABLE", "DELIVERABLE", deliverable.id),
        )

    if event.decision != "APPROVED":
        return
    milestone = await session.get(Milestone, deliverable.milestone_id)
    if milestone is None or milestone.points <= 0:
        return
    project = await session.get(Project, milestone.project_id)
    if project is None:
        return

    had_changes = (
        await session.scalar(
            select(func.count())
            .select_from(Deliverable)
            .where(
                Deliverable.milestone_id == milestone.id,
                Deliverable.status == "CHANGES_REQUESTED",
            )
        )
        or 0
    ) > 0
    factors = formulas.adjustment_factors(
        is_late=deliverable.is_late,
        submitted_on=deliverable.submitted_at.astimezone(formulas.LOCAL_TZ).date(),
        due_on=milestone.due_on,
        had_changes_requested=had_changes,
        rubric_scores=deliverable.rubric_scores,
    )
    award = Award(
        "MILESTONE_APPROVED",
        "MILESTONE",
        milestone.id,
        multiplier=formulas.milestone_multiplier(milestone.points, factors),
        category=formulas.category_for_project(project.kind),
        offering_id=project.offering_id,
        note=formulas.factors_note(factors),
    )
    for member_id in await active_member_ids(session, project.id):
        if member_id == event.reviewer_id:
            continue
        await points.award(member_id, award)


@events.subscribe(events.ProjectCompleted)
async def on_project_completed(session: AsyncSession, event: events.ProjectCompleted) -> None:
    project = await session.get(Project, event.project_id)
    if project is None or project.status != "COMPLETED":
        return
    points = PointsService(session)
    award = Award(
        "PROJECT_COMPLETED",
        "PROJECT",
        project.id,
        multiplier=formulas.project_completion_multiplier(
            kind=project.kind, difficulty=project.difficulty
        ),
        category=formulas.category_for_project(project.kind),
        offering_id=project.offering_id,
    )
    for member_id in await active_member_ids(session, project.id):
        await points.award(member_id, award)


@events.subscribe(events.SurveyStepCompleted)
async def on_survey_step_completed(
    session: AsyncSession, event: events.SurveyStepCompleted
) -> None:
    if event.completed_steps < TOTAL_SURVEY_STEPS:
        return
    await PointsService(session).award(
        event.user_id, Award("PROFILE_COMPLETED", "PROFILE", event.user_id)
    )


__all__ = ["LearningPoints", "active_member_ids"]
