"""اتصال رویدادهای دامنه به قواعد امتیاز — PRD §7.13، §9.2، M5-04.

هر شنونده اینجا یک رویداد (`silp.services.events`) را به ردیف‌های دفتر کل
ترجمه می‌کند. دو الگو هست:

* **رویداد یک‌باره** (پذیرش در پروژه، تأیید مرحله، تکمیل درس): `award`
  مستقیم. کلید بی‌اثری تکرار را بی‌اثر می‌کند.
* **امتیاز تابع وضعیت** (آزمون، حضور، تکمیل هفته): وضعیت مطلوب از
  دیتابیس حساب و با `reconcile` هم‌تراز می‌شود. همین تابع‌ها را کار
  پس‌زمینهٔ `release_quiz_points` هم صدا می‌زند.

ایده و کارآفرینی از M7 وصل‌اند؛ پژوهش و `TEAM_FORMED` از M7 بخش ب.
قواعدی که ماژول منبعشان هنوز ساخته نشده (پرسش‌وپاسخ، ارزیابی همتا، بازتاب)
در `point_rules` هستند ولی شنونده ندارند.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from silp.core.logging import get_logger
from silp.core.permissions import Role
from silp.domain import ideas as idea_rules
from silp.domain import research as research_rules
from silp.domain import ventures as venture_rules
from silp.domain.gamification import formulas
from silp.models.delivery import Deliverable, Milestone, OpeningApplication, TeamOpening
from silp.models.education import (
    AttendanceRecord,
    ClassSession,
    CourseWeek,
    Enrollment,
    Resource,
    ResourceProgress,
)
from silp.models.idea import Idea
from silp.models.profile import TOTAL_SURVEY_STEPS
from silp.models.project import Project, ProjectApplication, Team, TeamMember
from silp.models.quiz import Quiz, QuizAttempt
from silp.models.research import ResearchOutput, ResearchSubmission, ResearchTopic
from silp.models.venture import Venture, VentureMetric, VentureStageChange
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


# ── ایده — §9.2 `COMMUNITY` ────────────────────────────────────────────
@events.subscribe(events.IdeaSubmitted)
async def on_idea_submitted(session: AsyncSession, event: events.IdeaSubmitted) -> None:
    idea = await session.get(Idea, event.idea_id)
    if idea is None:
        return
    await PointsService(session).award(idea.author_id, Award("IDEA_SUBMITTED", "IDEA", idea.id))


@events.subscribe(events.IdeaWithdrawn)
async def on_idea_withdrawn(session: AsyncSession, event: events.IdeaWithdrawn) -> None:
    """ایدهٔ حذف یا بایگانی‌شده ارزشی نساخته؛ امتیاز ثبتش برمی‌گردد.

    بدون این، ثبت و حذف پیاپی زیر سقف روزانه، امتیاز بی‌کار بود (§09).
    امتیازهای آستانهٔ رأی می‌مانند: آن رأی‌ها را دیگران داده‌اند.
    """
    idea = await session.get(Idea, event.idea_id)
    if idea is None:
        return
    await PointsService(session).reconcile(
        idea.author_id,
        desired=[],
        universe=[("IDEA_SUBMITTED", "IDEA", idea.id)],
        reason="ایده حذف یا بایگانی شد",
    )


@events.subscribe(events.IdeaVoted)
async def on_idea_voted(session: AsyncSession, event: events.IdeaVoted) -> None:
    """آستانهٔ ۱۰ و ۵۰ رأی — «یک‌بار»؛ پس گرفتن رأی آن را برنمی‌گرداند."""
    idea = await session.get(Idea, event.idea_id)
    if idea is None:
        return
    points = PointsService(session)
    for rule in idea_rules.reached_milestones(idea.vote_count):
        await points.award(idea.author_id, Award(rule, "IDEA", idea.id))


@events.subscribe(events.IdeaPromoted)
async def on_idea_promoted(session: AsyncSession, event: events.IdeaPromoted) -> None:
    idea = await session.get(Idea, event.idea_id)
    if idea is None or idea.status != "PROMOTED":
        return
    await PointsService(session).award(idea.author_id, Award("IDEA_PROMOTED", "IDEA", idea.id))


# ── کارآفرینی — §9.2 `STARTUP` ─────────────────────────────────────────
@events.subscribe(events.VentureCreated)
async def on_venture_created(session: AsyncSession, event: events.VentureCreated) -> None:
    venture = await session.get(Venture, event.venture_id)
    if venture is None:
        return
    await PointsService(session).award(
        venture.founder_id, Award("VENTURE_CREATED", "VENTURE", venture.id)
    )


@events.subscribe(events.VentureDeleted)
async def on_venture_deleted(session: AsyncSession, event: events.VentureDeleted) -> None:
    venture = await session.get(Venture, event.venture_id)
    if venture is None:
        return
    await PointsService(session).reconcile(
        venture.founder_id,
        desired=[],
        universe=[("VENTURE_CREATED", "VENTURE", venture.id)],
        reason="کسب‌وکار حذف شد",
    )


async def venture_member_ids(session: AsyncSession, venture_id: uuid.UUID) -> list[uuid.UUID]:
    rows = await session.scalars(
        select(TeamMember.user_id)
        .join(Team, Team.id == TeamMember.team_id)
        .where(Team.venture_id == venture_id, TeamMember.status == "ACTIVE")
    )
    return list(dict.fromkeys(rows))


@events.subscribe(events.VentureStageChanged)
async def on_venture_stage_changed(
    session: AsyncSession, event: events.VentureStageChanged
) -> None:
    """`50 × مرحله` برای **همهٔ اعضای فعال** — ارتقا کار تیم است (ADR-0014).

    فقط گذار رو به جلو در مسیر رشد امتیاز دارد؛ بازگشت از توقف به همان
    مرحله، ارتقا نیست.
    """
    change = await session.get(VentureStageChange, event.change_id)
    if change is None:
        return
    target = change.to_stage
    if venture_rules.next_growth_stage(change.from_stage) != target:
        return
    award = Award(
        "VENTURE_STAGE_UP",
        "VENTURE_STAGE",
        change.id,
        multiplier=Decimal(venture_rules.stage_number(target)),
        note=venture_rules.stage_title(target),
    )
    points = PointsService(session)
    for member_id in await venture_member_ids(session, change.venture_id):
        await points.award(member_id, award)


@events.subscribe(events.MetricReviewed)
async def on_metric_reviewed(session: AsyncSession, event: events.MetricReviewed) -> None:
    """شاخص تأییدشده ⇒ امتیاز ثبت‌کننده. ضریب از `venture_rules.metric_multiplier`."""
    row = await session.get(VentureMetric, event.metric_id)
    if row is None or row.status != "VERIFIED":
        return
    rule_code = venture_rules.METRIC_RULES[row.metric]
    points = PointsService(session)
    rule = await points.rule(rule_code)
    offering_id = None
    if row.project_id is not None:
        project = await session.get(Project, row.project_id)
        offering_id = project.offering_id if project is not None else None
    await points.award(
        row.user_id,
        Award(
            rule_code,
            "METRIC",
            row.id,
            multiplier=venture_rules.metric_multiplier(
                row.metric, row.value, per_row_cap=rule.daily_cap if rule else None
            ),
            offering_id=offering_id,
        ),
    )


# ── پژوهش — §9.2 `RESEARCH`، ADR-0015 ──────────────────────────────────
@events.subscribe(events.ResearchReviewed)
async def on_research_reviewed(session: AsyncSession, event: events.ResearchReviewed) -> None:
    """`RESEARCH_Ln_APPROVED` — منبع، تحویلِ تأییدشده است؛ هر سطح یک‌بار تأیید می‌شود."""
    row = await session.get(ResearchSubmission, event.submission_id)
    if row is None or row.status != "APPROVED":
        return
    spec = research_rules.level_spec(row.level)
    await PointsService(session).award(
        row.user_id,
        Award(spec.rule_code, "RESEARCH_SUBMISSION", row.id, note=spec.title_fa),
    )


@events.subscribe(events.OutputReviewed)
async def on_output_reviewed(session: AsyncSession, event: events.OutputReviewed) -> None:
    """امتیاز خروجی = تابع آنچه راستی‌آزمایی شده. `reconcile` هم افزودن را
    می‌پوشاند (پذیرش پس از ارسال)، هم اصلاح را (چارک اشتباه، ادعای پس‌گرفته)."""
    output = await session.get(ResearchOutput, event.output_id)
    if output is None or output.review_status != "VERIFIED":
        return
    desired = [
        Award(rule, "RESEARCH_OUTPUT", output.id, multiplier=multiplier)
        for rule, multiplier in research_rules.output_awards(
            output.kind, output.verified_stage, output.verified_quartile
        )
    ]
    await PointsService(session).reconcile(
        output.owner_id,
        desired=desired,
        universe=[(rule, "RESEARCH_OUTPUT", output.id) for rule in research_rules.OUTPUT_RULES],
        reason="راستی‌آزمایی تازهٔ خروجی پژوهشی",
    )


@events.subscribe(events.TopicReviewed)
async def on_topic_reviewed(session: AsyncSession, event: events.TopicReviewed) -> None:
    """`TOPIC_PROPOSED` — «پیشنهاد موضوع پژوهشی **پذیرفته‌شده**» (§9.2)."""
    if not event.approved:
        return
    topic = await session.get(ResearchTopic, event.topic_id)
    if topic is None or topic.reviewed_by == topic.proposer_id:
        return
    await PointsService(session).award(
        topic.proposer_id, Award("TOPIC_PROPOSED", "RESEARCH_TOPIC", topic.id)
    )


# ── آگهی هم‌تیمی — `TEAM_FORMED`، §9.8 ─────────────────────────────────
async def award_team_formed(
    session: AsyncSession,
    *,
    happened_at: datetime,
    reviewer_id: uuid.UUID | None,
    project_id: uuid.UUID | None = None,
    venture_id: uuid.UUID | None = None,
    contributor_id: uuid.UUID | None = None,
) -> None:
    """«تشکیل تیم صوری ⇒ `TEAM_FORMED` فقط پس از اولین تحویل‌دادنی تأییدشدهٔ تیم».

    امتیاز به آگهی‌دهنده می‌رسد، یک‌بار برای هر آگهی، وقتی تیمی که از آگهی
    شکل گرفت **پس از پیوستن** کار تأییدشده‌ای داشته باشد و عضو تازه هنوز
    در تیم باشد. تأیید به دست خود آگهی‌دهنده حساب نیست — همان قاعدهٔ
    `MILESTONE_APPROVED` (ADR-0012): تأیید کار تیم خودت، امتیاز خودت نیست.
    """
    member_active = exists().where(
        TeamMember.user_id == OpeningApplication.applicant_id,
        TeamMember.status == "ACTIVE",
        TeamMember.team_id == Team.id,
    )
    stmt = (
        select(TeamOpening.id, TeamOpening.poster_id)
        .join(OpeningApplication, OpeningApplication.opening_id == TeamOpening.id)
        .join(
            Team,
            (Team.project_id == TeamOpening.project_id)
            | (Team.venture_id == TeamOpening.venture_id),
        )
        .where(
            TeamOpening.status == "FILLED",
            OpeningApplication.status == "ACCEPTED",
            OpeningApplication.decided_at < happened_at,
            member_active,
        )
    )
    if project_id is not None:
        stmt = stmt.where(TeamOpening.project_id == project_id)
    elif venture_id is not None:
        stmt = stmt.where(TeamOpening.venture_id == venture_id)
    else:
        return
    if contributor_id is not None:
        stmt = stmt.where(OpeningApplication.applicant_id == contributor_id)
    points = PointsService(session)
    for opening_id, poster_id in (await session.execute(stmt)).all():
        if poster_id == reviewer_id:
            continue
        await points.award(poster_id, Award("TEAM_FORMED", "OPENING", opening_id))


@events.subscribe(events.DeliverableReviewed)
async def on_deliverable_approved_team_formed(
    session: AsyncSession, event: events.DeliverableReviewed
) -> None:
    if event.decision != "APPROVED":
        return
    deliverable = await session.get(Deliverable, event.deliverable_id)
    if deliverable is None or deliverable.reviewed_at is None:
        return
    milestone = await session.get(Milestone, deliverable.milestone_id)
    if milestone is None:
        return
    await award_team_formed(
        session,
        happened_at=deliverable.reviewed_at,
        reviewer_id=event.reviewer_id,
        project_id=milestone.project_id,
    )


@events.subscribe(events.MetricReviewed)
async def on_metric_verified_team_formed(
    session: AsyncSession, event: events.MetricReviewed
) -> None:
    """کسب‌وکار تحویل‌دادنی ندارد؛ کار تأییدشدهٔ عضو تازه، شاخص تأییدشدهٔ اوست."""
    row = await session.get(VentureMetric, event.metric_id)
    if row is None or row.status != "VERIFIED":
        return
    assert row.reviewed_at is not None
    await award_team_formed(
        session,
        happened_at=row.reviewed_at,
        reviewer_id=row.reviewed_by,
        project_id=row.project_id,
        venture_id=row.venture_id,
        contributor_id=row.user_id,
    )


__all__ = [
    "LearningPoints",
    "active_member_ids",
    "award_team_formed",
    "venture_member_ids",
]
