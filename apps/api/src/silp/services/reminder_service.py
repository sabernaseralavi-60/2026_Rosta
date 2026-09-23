"""یادآوری مهلت و خلاصهٔ هفتگی — §7.11، M6-11.

* `send_deadline_reminders` — هر روز ۹ صبح تهران. اعضای تیم، ۳ و ۱ روز
  پیش از مهلت مرحله؛ و دانشجویانی که هنوز در آزمون شرکت نکرده‌اند، ۳ و ۱
  روز پیش از بسته شدنش.
* `weekly_digest` — شنبه ۹ صبح. دانشجو: امتیاز هفته، مهلت‌های پیش رو و
  خوانده‌نشده‌ها. استاد: صف بررسی، ثبت‌نام در انتظار و پروژهٔ در خطر.

هر دو **بی‌اثر در تکرار**اند (§7.11): کلید `dedup_key` هر اعلان از
موضوع و روز ساخته می‌شود و ایندکس یکتای `idx_notifications_dedup` دومی
را نمی‌پذیرد. کارگری که دو بار اجرا شود، پیامک دوم نمی‌فرستد.

خلاصهٔ خالی فرستاده نمی‌شود: «این هفته ۰ امتیاز، ۰ مهلت، ۰ اعلان» فقط
یاد می‌دهد که خلاصه را نخوانند.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from silp.core.logging import get_logger
from silp.domain.calendar import format_date_fa, format_datetime_fa
from silp.domain.gamification.formulas import LOCAL_TZ
from silp.domain.text import to_persian_digits
from silp.models.delivery import Milestone
from silp.models.education import CourseOffering, Enrollment
from silp.models.gamification import PointEntry
from silp.models.messaging import Notification
from silp.models.project import Project, Team, TeamMember
from silp.models.quiz import GradeAppeal, Quiz, QuizAttempt
from silp.services.notification_listeners import course_title, fa_number
from silp.services.notification_service import NotificationService
from silp.services.point_listeners import active_member_ids

log = get_logger("silp.reminders")

REMINDER_DAYS = (3, 1)
OPEN_MILESTONE_STATUSES = ("PENDING", "IN_PROGRESS", "OVERDUE")
TEACHING_OFFERING_STATUSES = ("OPEN", "IN_PROGRESS")
DIGEST_HORIZON_DAYS = 7


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class ReminderStats:
    milestones: int
    quizzes: int


@dataclass(frozen=True, slots=True)
class DigestStats:
    students: int
    teachers: int


class ReminderService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.notifications = NotificationService(session)

    # ── یادآوری مهلت ───────────────────────────────────────────────────
    async def send_deadline_reminders(self, *, now: datetime | None = None) -> ReminderStats:
        moment = now or _now()
        today = moment.astimezone(LOCAL_TZ).date()
        milestones = await self._milestone_reminders(today)
        quizzes = await self._quiz_reminders(moment, today)
        await self.session.commit()
        if milestones or quizzes:
            log.info("deadline_reminders_sent", milestones=milestones, quizzes=quizzes)
        return ReminderStats(milestones=milestones, quizzes=quizzes)

    async def _milestone_reminders(self, today: date) -> int:
        targets = {today + timedelta(days=d): d for d in REMINDER_DAYS}
        rows = await self.session.execute(
            select(Milestone, Project)
            .join(Project, Project.id == Milestone.project_id)
            .where(
                Milestone.due_on.in_(list(targets)),
                Milestone.status.in_(OPEN_MILESTONE_STATUSES),
                Project.status == "IN_PROGRESS",
                Project.deleted_at.is_(None),
            )
        )
        sent = 0
        for milestone, project in rows.all():
            assert milestone.due_on is not None
            days = targets[milestone.due_on]
            members = await active_member_ids(self.session, project.id)
            created = await self.notifications.notify(
                "DEADLINE_REMINDER",
                members,
                {
                    "project": project.title_fa,
                    "milestone": milestone.title_fa,
                    "days": to_persian_digits(days),
                    "due_on": format_date_fa(milestone.due_on),
                },
                action_url=f"/projects/{project.id}/workspace",
                dedup_key=f"DEADLINE:{milestone.id}:{days}",
            )
            sent += len(created)
        return sent

    async def _quiz_reminders(self, moment: datetime, today: date) -> int:
        horizon = moment + timedelta(days=max(REMINDER_DAYS) + 1)
        quizzes = await self.session.scalars(
            select(Quiz).where(
                Quiz.status == "PUBLISHED",
                Quiz.deleted_at.is_(None),
                Quiz.opens_at <= moment,
                Quiz.closes_at > moment,
                Quiz.closes_at <= horizon,
            )
        )
        sent = 0
        for quiz in quizzes:
            days = (quiz.closes_at.astimezone(LOCAL_TZ).date() - today).days
            if days not in REMINDER_DAYS:
                continue
            attempted = select(QuizAttempt.student_id).where(QuizAttempt.quiz_id == quiz.id)
            students = list(
                await self.session.scalars(
                    select(Enrollment.student_id).where(
                        Enrollment.offering_id == quiz.offering_id,
                        Enrollment.status == "ACTIVE",
                        Enrollment.student_id.not_in(attempted),
                    )
                )
            )
            created = await self.notifications.notify(
                "QUIZ_CLOSING",
                students,
                {
                    "course": await course_title(self.session, quiz.offering_id),
                    "quiz": quiz.title_fa,
                    "days": to_persian_digits(days),
                    "closes_at": format_datetime_fa(quiz.closes_at),
                },
                action_url=f"/courses/{quiz.offering_id}/quizzes",
                dedup_key=f"QUIZ_CLOSING:{quiz.id}:{days}",
            )
            sent += len(created)
        return sent

    # ── خلاصهٔ هفتگی ───────────────────────────────────────────────────
    async def weekly_digest(self, *, now: datetime | None = None) -> DigestStats:
        moment = now or _now()
        today = moment.astimezone(LOCAL_TZ).date()
        key = f"DIGEST:{today.isocalendar().year}-W{today.isocalendar().week:02d}"
        students = await self._student_digests(moment, today, key)
        teachers = await self._teacher_digests(key)
        await self.session.commit()
        log.info("weekly_digest_sent", students=students, teachers=teachers)
        return DigestStats(students=students, teachers=teachers)

    async def _student_digests(self, moment: datetime, today: date, key: str) -> int:
        enrolled = select(Enrollment.student_id).where(Enrollment.status == "ACTIVE")
        on_team = (
            select(TeamMember.user_id)
            .join(Team, Team.id == TeamMember.team_id)
            .join(Project, Project.id == Team.project_id)
            .where(TeamMember.status == "ACTIVE", Project.status == "IN_PROGRESS")
        )
        users = sorted(set(await self.session.scalars(enrolled.union(on_team))))
        if not users:
            return 0

        week_ago = moment - timedelta(days=7)
        points: dict[uuid.UUID, Decimal] = {
            row[0]: row[1]
            for row in (
                await self.session.execute(
                    select(PointEntry.user_id, func.sum(PointEntry.amount))
                    .where(PointEntry.user_id.in_(users), PointEntry.created_at >= week_ago)
                    .group_by(PointEntry.user_id)
                )
            ).all()
        }
        unread: dict[uuid.UUID, int] = {
            row[0]: row[1]
            for row in (
                await self.session.execute(
                    select(Notification.user_id, func.count())
                    .where(
                        Notification.user_id.in_(users),
                        Notification.read_at.is_(None),
                        Notification.archived_at.is_(None),
                    )
                    .group_by(Notification.user_id)
                )
            ).all()
        }
        deadlines = await self._upcoming_deadlines(users, moment, today)

        sent = 0
        for user_id in users:
            earned = points.get(user_id) or 0
            due = deadlines.get(user_id, 0)
            waiting = unread.get(user_id, 0)
            if not earned and not due and not waiting:
                continue
            created = await self.notifications.notify(
                "WEEKLY_DIGEST",
                [user_id],
                {
                    "points": fa_number(earned),
                    "deadlines": to_persian_digits(due),
                    "unread": to_persian_digits(waiting),
                },
                action_url="/dashboard",
                dedup_key=key,
            )
            sent += len(created)
        return sent

    async def _upcoming_deadlines(
        self, users: list[uuid.UUID], moment: datetime, today: date
    ) -> dict[uuid.UUID, int]:
        counts: dict[uuid.UUID, int] = defaultdict(int)
        horizon_day = today + timedelta(days=DIGEST_HORIZON_DAYS)
        milestone_rows = await self.session.execute(
            select(TeamMember.user_id, func.count(Milestone.id))
            .join(Team, Team.id == TeamMember.team_id)
            .join(Milestone, Milestone.project_id == Team.project_id)
            .where(
                TeamMember.user_id.in_(users),
                TeamMember.status == "ACTIVE",
                Milestone.status.in_(OPEN_MILESTONE_STATUSES),
                Milestone.due_on >= today,
                Milestone.due_on <= horizon_day,
            )
            .group_by(TeamMember.user_id)
        )
        for user_id, n in milestone_rows.all():
            counts[user_id] += int(n)
        quiz_rows = await self.session.execute(
            select(Enrollment.student_id, func.count(Quiz.id))
            .join(Quiz, Quiz.offering_id == Enrollment.offering_id)
            .where(
                Enrollment.student_id.in_(users),
                Enrollment.status == "ACTIVE",
                Quiz.status == "PUBLISHED",
                Quiz.deleted_at.is_(None),
                Quiz.closes_at > moment,
                Quiz.closes_at <= moment + timedelta(days=DIGEST_HORIZON_DAYS),
            )
            .group_by(Enrollment.student_id)
        )
        for user_id, n in quiz_rows.all():
            counts[user_id] += int(n)
        return counts

    async def _teacher_digests(self, key: str) -> int:
        offerings = list(
            (
                await self.session.execute(
                    select(CourseOffering.id, CourseOffering.instructor_id).where(
                        CourseOffering.status.in_(TEACHING_OFFERING_STATUSES),
                        CourseOffering.deleted_at.is_(None),
                    )
                )
            ).all()
        )
        by_teacher: dict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)
        for offering_id, instructor_id in offerings:
            by_teacher[instructor_id].append(offering_id)

        sent = 0
        for teacher_id, offering_ids in by_teacher.items():
            provisional = await self._count(
                select(func.count())
                .select_from(QuizAttempt)
                .join(Quiz, Quiz.id == QuizAttempt.quiz_id)
                .where(Quiz.offering_id.in_(offering_ids), QuizAttempt.is_provisional.is_(True))
            )
            appeals = await self._count(
                select(func.count())
                .select_from(GradeAppeal)
                .join(QuizAttempt, QuizAttempt.id == GradeAppeal.attempt_id)
                .join(Quiz, Quiz.id == QuizAttempt.quiz_id)
                .where(Quiz.offering_id.in_(offering_ids), GradeAppeal.status == "OPEN")
            )
            pending = await self._count(
                select(func.count())
                .select_from(Enrollment)
                .where(Enrollment.offering_id.in_(offering_ids), Enrollment.status == "PENDING")
            )
            at_risk = await self._count(
                select(func.count())
                .select_from(Project)
                .where(
                    Project.offering_id.in_(offering_ids),
                    Project.status == "IN_PROGRESS",
                    Project.health != "HEALTHY",
                )
            )
            if not (provisional or appeals or pending or at_risk):
                continue
            created = await self.notifications.notify(
                "WEEKLY_DIGEST_TEACHER",
                [teacher_id],
                {
                    "reviews": to_persian_digits(provisional + appeals),
                    "enrollments": to_persian_digits(pending),
                    "at_risk": to_persian_digits(at_risk),
                },
                action_url="/teach",
                dedup_key=key,
            )
            sent += len(created)
        return sent

    async def _count(self, statement: object) -> int:
        return int(await self.session.scalar(statement) or 0)  # type: ignore[call-overload]


__all__ = ["REMINDER_DAYS", "DigestStats", "ReminderService", "ReminderStats"]
