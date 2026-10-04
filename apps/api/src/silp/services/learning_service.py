"""حلقهٔ یادگیری روزانه — ADR-0036.

* درس‌نامه و ماژول (کادر می‌نویسد؛ دانشجوی ثبت‌نام‌شده فقط منتشرشده را می‌بیند).
* زنجیرهٔ دانش: شایستگی ← مفهوم؛ سؤال به مفهوم وصل می‌شود.
* «امروز»: درس‌نامهٔ تازه + چالش باز + استمرار + بازخورد آخرین چالش + پیشنهاد بعدی.
* پردازش یک تلاشِ چالش: شایستگی، استمرار و امتیاز — **یک‌بار** به‌ازای هر تلاش
  (`checkpoint_results` قفل بی‌اثری است، چون `QuizGraded` با تصحیح دستی دوباره می‌آید).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from silp.core.exceptions import Conflict, NotFound, PermissionDenied, ValidationFailed
from silp.core.logging import get_logger
from silp.domain import learning as rules
from silp.models.education import Course, CourseOffering, Enrollment
from silp.models.learning import (
    CheckpointResult,
    Competency,
    CompetencyMastery,
    Concept,
    Lesson,
    Module,
    Streak,
)
from silp.models.quiz import Quiz, QuizAnswer, QuizAttempt, QuizQuestion

log = get_logger("silp.learning")

ACTIVE = ("ACTIVE", "COMPLETED")
HIGH_SCORE = Decimal("0.8")
IMPROVEMENT_STEP = 0.10


def _now() -> datetime:
    return datetime.now(UTC)


# ── خروجی‌ها ───────────────────────────────────────────────────────────
@dataclass(frozen=True)
class MasteryRow:
    competency_id: uuid.UUID
    code: str
    title: str
    score: float
    evidence_n: int
    level: str


@dataclass(frozen=True)
class CheckpointCard:
    quiz_id: uuid.UUID
    title: str
    state: str  # AVAILABLE | IN_PROGRESS | DONE | UPCOMING
    opens_at: datetime
    closes_at: datetime
    duration_min: int
    question_count: int
    attempt_id: uuid.UUID | None = None


@dataclass(frozen=True)
class LessonCard:
    id: uuid.UUID
    title: str
    est_minutes: int
    published_at: datetime


@dataclass(frozen=True)
class SkillOutcome:
    title: str
    correct: int
    total: int


@dataclass(frozen=True)
class LastResult:
    quiz_title: str
    day: date
    correct: int
    total: int
    skills: list[SkillOutcome] = field(default_factory=list)


@dataclass(frozen=True)
class StreakCard:
    current: int
    longest: int
    alive: bool


@dataclass(frozen=True)
class TodayOffering:
    offering_id: uuid.UUID
    course_title: str
    lesson: LessonCard | None
    checkpoint: CheckpointCard | None
    streak: StreakCard
    last_result: LastResult | None


@dataclass(frozen=True)
class Suggestion:
    kind: str  # REVIEW | KEEP_GOING
    competency_id: uuid.UUID | None
    title: str | None


@dataclass(frozen=True)
class Today:
    offerings: list[TodayOffering]
    mastery: list[MasteryRow]
    suggestion: Suggestion | None


@dataclass(frozen=True)
class Processed:
    correct: int
    total: int
    improved: list[uuid.UUID]
    streak: rules.StreakStep


class LearningService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ── ماژول و درس‌نامه (کادر) ────────────────────────────────────────
    async def create_module(self, offering_id: uuid.UUID, title_fa: str) -> Module:
        await self._offering(offering_id)
        title = title_fa.strip()
        if not title:
            raise ValidationFailed("عنوان ماژول نمی‌تواند خالی باشد.")
        count = await self.session.scalar(
            select(func.count()).select_from(Module).where(Module.offering_id == offering_id)
        )
        module = Module(offering_id=offering_id, title_fa=title, sort_order=int(count or 0))
        self.session.add(module)
        await self.session.commit()
        return module

    async def modules(self, offering_id: uuid.UUID) -> list[Module]:
        return list(
            await self.session.scalars(
                select(Module).where(Module.offering_id == offering_id).order_by(Module.sort_order)
            )
        )

    async def create_lesson(
        self,
        offering_id: uuid.UUID,
        author_id: uuid.UUID,
        *,
        title_fa: str,
        body_md: str,
        est_minutes: int = 5,
        module_id: uuid.UUID | None = None,
        week_id: uuid.UUID | None = None,
        publish_at: datetime | None = None,
        publish: bool = False,
    ) -> Lesson:
        await self._offering(offering_id)
        await self._check_lesson_fields(offering_id, title_fa, body_md, est_minutes, module_id)
        count = await self.session.scalar(
            select(func.count()).select_from(Lesson).where(Lesson.offering_id == offering_id)
        )
        lesson = Lesson(
            offering_id=offering_id,
            module_id=module_id,
            week_id=week_id,
            title_fa=title_fa.strip(),
            body_md=body_md,
            est_minutes=est_minutes,
            publish_at=publish_at,
            status="PUBLISHED" if publish else "DRAFT",
            sort_order=int(count or 0),
            created_by=author_id,
        )
        self.session.add(lesson)
        await self.session.commit()
        return lesson

    async def update_lesson(
        self,
        lesson_id: uuid.UUID,
        offering_id: uuid.UUID,
        *,
        title_fa: str,
        body_md: str,
        est_minutes: int,
        module_id: uuid.UUID | None,
        publish_at: datetime | None,
    ) -> Lesson:
        lesson = await self._lesson_of(lesson_id, offering_id)
        await self._check_lesson_fields(offering_id, title_fa, body_md, est_minutes, module_id)
        lesson.title_fa = title_fa.strip()
        lesson.body_md = body_md
        lesson.est_minutes = est_minutes
        lesson.module_id = module_id
        lesson.publish_at = publish_at
        lesson.updated_at = _now()
        await self.session.commit()
        return lesson

    async def set_lesson_published(
        self, lesson_id: uuid.UUID, offering_id: uuid.UUID, published: bool
    ) -> Lesson:
        lesson = await self._lesson_of(lesson_id, offering_id)
        lesson.status = "PUBLISHED" if published else "DRAFT"
        lesson.updated_at = _now()
        await self.session.commit()
        return lesson

    async def delete_lesson(self, lesson_id: uuid.UUID, offering_id: uuid.UUID) -> None:
        lesson = await self._lesson_of(lesson_id, offering_id)
        await self.session.delete(lesson)
        await self.session.commit()

    async def lessons_for_staff(self, offering_id: uuid.UUID) -> list[Lesson]:
        await self._offering(offering_id)
        return list(
            await self.session.scalars(
                select(Lesson)
                .where(Lesson.offering_id == offering_id)
                .order_by(Lesson.sort_order, Lesson.created_at)
            )
        )

    async def lessons_for_student(
        self, offering_id: uuid.UUID, student_id: uuid.UUID
    ) -> list[Lesson]:
        await self._require_student(offering_id, student_id)
        return list(
            await self.session.scalars(
                select(Lesson)
                .where(Lesson.offering_id == offering_id, *self._visible())
                .order_by(func.coalesce(Lesson.publish_at, Lesson.updated_at).desc())
            )
        )

    async def lesson_for_student(self, lesson_id: uuid.UUID, student_id: uuid.UUID) -> Lesson:
        lesson = await self.session.scalar(
            select(Lesson).where(Lesson.id == lesson_id, *self._visible())
        )
        if lesson is None:
            raise NotFound("درس‌نامه پیدا نشد.")
        await self._require_student(lesson.offering_id, student_id)
        return lesson

    async def checkpoints_of_lesson(self, lesson_id: uuid.UUID) -> list[Quiz]:
        return list(
            await self.session.scalars(
                select(Quiz)
                .where(
                    Quiz.lesson_id == lesson_id,
                    Quiz.kind == "CHECKPOINT",
                    Quiz.status.in_(("PUBLISHED", "CLOSED")),
                    Quiz.deleted_at.is_(None),
                )
                .order_by(Quiz.opens_at)
            )
        )

    # ── زنجیرهٔ دانش ───────────────────────────────────────────────────
    async def competencies(self) -> list[tuple[Competency, list[Concept]]]:
        comps = list(
            await self.session.scalars(
                select(Competency).order_by(Competency.sort_order, Competency.title_fa)
            )
        )
        concepts = list(await self.session.scalars(select(Concept).order_by(Concept.title_fa)))
        by_comp: dict[uuid.UUID, list[Concept]] = {}
        for concept in concepts:
            by_comp.setdefault(concept.competency_id, []).append(concept)
        return [(comp, by_comp.get(comp.id, [])) for comp in comps]

    async def create_competency(
        self, code: str, title_fa: str, domain: str | None = None
    ) -> Competency:
        code = code.strip().lower()
        if not code or not title_fa.strip():
            raise ValidationFailed("کد و عنوان شایستگی لازم است.")
        if await self.session.scalar(select(Competency.id).where(Competency.code == code)):
            raise Conflict("شایستگی با این کد از قبل هست.", code="COMPETENCY_EXISTS")
        comp = Competency(code=code, title_fa=title_fa.strip(), domain=domain)
        self.session.add(comp)
        await self.session.commit()
        return comp

    async def create_concept(self, competency_id: uuid.UUID, code: str, title_fa: str) -> Concept:
        if await self.session.get(Competency, competency_id) is None:
            raise NotFound("شایستگی پیدا نشد.")
        code = code.strip().lower()
        if not code or not title_fa.strip():
            raise ValidationFailed("کد و عنوان مفهوم لازم است.")
        if await self.session.scalar(select(Concept.id).where(Concept.code == code)):
            raise Conflict("مفهوم با این کد از قبل هست.", code="CONCEPT_EXISTS")
        concept = Concept(competency_id=competency_id, code=code, title_fa=title_fa.strip())
        self.session.add(concept)
        await self.session.commit()
        return concept

    # ── نمای دانشجو ────────────────────────────────────────────────────
    async def mastery(self, user_id: uuid.UUID) -> list[MasteryRow]:
        rows = (
            await self.session.execute(
                select(CompetencyMastery, Competency)
                .join(Competency, Competency.id == CompetencyMastery.competency_id)
                .where(CompetencyMastery.user_id == user_id)
            )
        ).all()
        out = [
            MasteryRow(
                competency_id=comp.id,
                code=comp.code,
                title=comp.title_fa,
                score=float(m.score),
                evidence_n=m.evidence_n,
                level=rules.mastery_level(m.score, m.evidence_n),
            )
            for m, comp in rows
        ]
        # ضعیف‌ترین اول؛ «کم‌داده» آخر چون هنوز چیزی ثابت نشده.
        order = {"WEAK": 0, "MEDIUM": 1, "STRONG": 2, "LOW_DATA": 3}
        return sorted(out, key=lambda r: (order[r.level], r.score))

    async def today(self, user_id: uuid.UUID) -> Today:
        now = _now()
        offerings = (
            await self.session.execute(
                select(CourseOffering.id, Course.title_fa)
                .join(Enrollment, Enrollment.offering_id == CourseOffering.id)
                .join(Course, Course.id == CourseOffering.course_id)
                .where(
                    Enrollment.student_id == user_id,
                    Enrollment.status.in_(ACTIVE),
                    CourseOffering.deleted_at.is_(None),
                )
            )
        ).all()
        cards = [
            await self._today_offering(user_id, offering_id, title, now)
            for offering_id, title in offerings
        ]
        mastery = await self.mastery(user_id)
        weakest = next((m for m in mastery if m.level == "WEAK"), None)
        suggestion: Suggestion | None = None
        if weakest is not None:
            suggestion = Suggestion("REVIEW", weakest.competency_id, weakest.title)
        elif mastery:
            suggestion = Suggestion("KEEP_GOING", None, None)
        return Today(offerings=cards, mastery=mastery, suggestion=suggestion)

    async def _today_offering(
        self, user_id: uuid.UUID, offering_id: uuid.UUID, title: str, now: datetime
    ) -> TodayOffering:
        lesson = await self.session.scalar(
            select(Lesson)
            .where(Lesson.offering_id == offering_id, *self._visible())
            .order_by(func.coalesce(Lesson.publish_at, Lesson.updated_at).desc())
            .limit(1)
        )
        lesson_card = (
            LessonCard(
                id=lesson.id,
                title=lesson.title_fa,
                est_minutes=lesson.est_minutes,
                published_at=lesson.publish_at or lesson.updated_at,
            )
            if lesson
            else None
        )
        streak_row = await self.session.get(Streak, (user_id, offering_id))
        state = _state_of(streak_row)
        streak = StreakCard(
            current=state.current if rules.streak_is_alive(state, rules.tehran_day(now)) else 0,
            longest=state.longest,
            alive=rules.streak_is_alive(state, rules.tehran_day(now)),
        )
        return TodayOffering(
            offering_id=offering_id,
            course_title=title,
            lesson=lesson_card,
            checkpoint=await self._checkpoint_card(user_id, offering_id, now),
            streak=streak,
            last_result=await self._last_result(user_id, offering_id),
        )

    async def _checkpoint_card(
        self, user_id: uuid.UUID, offering_id: uuid.UUID, now: datetime
    ) -> CheckpointCard | None:
        quizzes = list(
            await self.session.scalars(
                select(Quiz)
                .where(
                    Quiz.offering_id == offering_id,
                    Quiz.kind == "CHECKPOINT",
                    Quiz.status == "PUBLISHED",
                    Quiz.deleted_at.is_(None),
                    Quiz.closes_at >= now,
                )
                .order_by(Quiz.closes_at)
            )
        )
        if not quizzes:
            return None
        attempts = {
            (a.quiz_id): a
            for a in await self.session.scalars(
                select(QuizAttempt)
                .where(
                    QuizAttempt.student_id == user_id,
                    QuizAttempt.quiz_id.in_([q.id for q in quizzes]),
                )
                .order_by(QuizAttempt.attempt_no)
            )
        }
        counts: dict[uuid.UUID, int] = dict(
            (
                await self.session.execute(
                    select(QuizQuestion.quiz_id, func.count())
                    .where(QuizQuestion.quiz_id.in_([q.id for q in quizzes]))
                    .group_by(QuizQuestion.quiz_id)
                )
            )
            .tuples()
            .all()
        )

        def card(quiz: Quiz, state: str) -> CheckpointCard:
            attempt = attempts.get(quiz.id)
            pool = int(counts.get(quiz.id, 0))
            return CheckpointCard(
                quiz_id=quiz.id,
                title=quiz.title_fa,
                state=state,
                opens_at=quiz.opens_at,
                closes_at=quiz.closes_at,
                duration_min=quiz.duration_min,
                question_count=min(pool, quiz.draw_count) if quiz.draw_count else pool,
                attempt_id=attempt.id if attempt else None,
            )

        open_now = [q for q in quizzes if q.opens_at <= now]
        for quiz in open_now:
            attempt = attempts.get(quiz.id)
            if attempt is None:
                return card(quiz, "AVAILABLE")
            if attempt.status == "IN_PROGRESS" and attempt.expires_at > now:
                return card(quiz, "IN_PROGRESS")
        if open_now:
            return card(open_now[0], "DONE")
        return card(quizzes[0], "UPCOMING")

    async def _last_result(self, user_id: uuid.UUID, offering_id: uuid.UUID) -> LastResult | None:
        row = (
            await self.session.execute(
                select(CheckpointResult, Quiz.title_fa)
                .join(Quiz, Quiz.id == CheckpointResult.quiz_id)
                .where(
                    CheckpointResult.user_id == user_id,
                    CheckpointResult.offering_id == offering_id,
                )
                .order_by(CheckpointResult.created_at.desc())
                .limit(1)
            )
        ).first()
        if row is None:
            return None
        result, quiz_title = row
        outcomes = await self._outcomes(result.attempt_id)
        titles: dict[uuid.UUID, str] = dict(
            (
                await self.session.execute(
                    select(Competency.id, Competency.title_fa).where(
                        Competency.id.in_(list(outcomes))
                    )
                )
            )
            .tuples()
            .all()
        )
        skills = [
            SkillOutcome(title=titles[cid], correct=sum(flags), total=len(flags))
            for cid, flags in outcomes.items()
            if cid in titles
        ]
        skills.sort(key=lambda s: (s.correct / s.total, s.title))
        return LastResult(
            quiz_title=quiz_title,
            day=result.day,
            correct=result.correct,
            total=result.total,
            skills=skills,
        )

    # ── پردازش یک تلاش ─────────────────────────────────────────────────
    async def process_checkpoint_attempt(
        self, attempt: QuizAttempt, quiz: Quiz
    ) -> Processed | None:
        """شایستگی + استمرار؛ `None` اگر این تلاش قبلاً پردازش شده یا چالش نیست."""
        if quiz.kind != "CHECKPOINT" or attempt.status != "GRADED":
            return None
        answers = await self._answers_with_outcome(attempt.id)
        if not answers:
            return None
        day = rules.tehran_day(attempt.submitted_at or attempt.started_at)
        correct = sum(1 for _, ok in answers if ok)
        inserted = await self.session.execute(
            pg_insert(CheckpointResult)
            .values(
                attempt_id=attempt.id,
                user_id=attempt.student_id,
                quiz_id=quiz.id,
                offering_id=quiz.offering_id,
                day=day,
                correct=correct,
                total=len(answers),
            )
            .on_conflict_do_nothing()
            .returning(CheckpointResult.attempt_id)
        )
        if inserted.first() is None:
            return None  # قبلاً پردازش شده

        improved = await self._apply_mastery(attempt.student_id, attempt.id)
        step = await self._apply_streak(attempt.student_id, quiz.offering_id, day)
        return Processed(correct=correct, total=len(answers), improved=improved, streak=step)

    async def _answers_with_outcome(
        self, attempt_id: uuid.UUID
    ) -> list[tuple[uuid.UUID | None, bool]]:
        """(مفهومِ سؤال، درست؟) به‌ازای سؤال‌هایی که در این تلاش آمده‌اند."""
        attempt = await self.session.get(QuizAttempt, attempt_id)
        if attempt is None or not attempt.question_order:
            return []
        questions = {
            q.id: q
            for q in await self.session.scalars(
                select(QuizQuestion).where(QuizQuestion.id.in_(attempt.question_order))
            )
        }
        # `_write_answer_scores` با upsert هسته می‌نویسد و ردیف‌های نگاشت‌شده را تازه نمی‌کند؛
        # بدون `populate_existing` نمرهٔ کهنهٔ (بدون امتیاز) خوانده می‌شد.
        saved = {
            a.question_id: a
            for a in await self.session.scalars(
                select(QuizAnswer)
                .where(QuizAnswer.attempt_id == attempt_id)
                .execution_options(populate_existing=True)
            )
        }
        out: list[tuple[uuid.UUID | None, bool]] = []
        for qid in attempt.question_order:
            question = questions.get(qid)
            if question is None:
                continue
            answer = saved.get(qid)
            score = answer.effective_score if answer else None
            out.append((question.concept_id, score is not None and score >= question.points))
        return out

    async def _outcomes(self, attempt_id: uuid.UUID) -> dict[uuid.UUID, list[bool]]:
        """درستی پاسخ‌ها به تفکیک **شایستگی** (سؤال بی‌مفهوم کنار گذاشته می‌شود)."""
        answers = await self._answers_with_outcome(attempt_id)
        concept_ids = {cid for cid, _ in answers if cid is not None}
        if not concept_ids:
            return {}
        comp_of: dict[uuid.UUID, uuid.UUID] = dict(
            (
                await self.session.execute(
                    select(Concept.id, Concept.competency_id).where(Concept.id.in_(concept_ids))
                )
            )
            .tuples()
            .all()
        )
        grouped: dict[uuid.UUID, list[bool]] = {}
        for cid, ok in answers:
            comp = comp_of.get(cid) if cid is not None else None
            if comp is not None:
                grouped.setdefault(comp, []).append(ok)
        return grouped

    async def _apply_mastery(self, user_id: uuid.UUID, attempt_id: uuid.UUID) -> list[uuid.UUID]:
        improved: list[uuid.UUID] = []
        for comp_id, flags in (await self._outcomes(attempt_id)).items():
            row = await self.session.get(CompetencyMastery, (user_id, comp_id))
            before = float(row.score) if row else rules.PRIOR_SCORE
            n_before = row.evidence_n if row else 0
            score, n = rules.update_mastery(before, n_before, flags)
            if row is None:
                self.session.add(
                    CompetencyMastery(
                        user_id=user_id,
                        competency_id=comp_id,
                        score=Decimal(str(score)),
                        evidence_n=n,
                    )
                )
            else:
                row.score = Decimal(str(score))
                row.evidence_n = n
                row.updated_at = _now()
            # بهبود فقط وقتی معنا دارد که پیش‌تر شاهدی بوده باشد.
            if n_before >= rules.MIN_EVIDENCE and score - before >= IMPROVEMENT_STEP:
                improved.append(comp_id)
        await self.session.flush()
        return improved

    async def _apply_streak(
        self, user_id: uuid.UUID, offering_id: uuid.UUID, day: date
    ) -> rules.StreakStep:
        row = await self.session.get(Streak, (user_id, offering_id))
        step = rules.advance_streak(_state_of(row), day)
        state = step.state
        if row is None:
            row = Streak(user_id=user_id, offering_id=offering_id)
            self.session.add(row)
        row.current = state.current
        row.longest = state.longest
        row.started_on = state.started_on
        row.last_day = state.last_day
        row.freeze_week = state.freeze_week
        row.updated_at = _now()
        await self.session.flush()
        return step

    # ── کمکی ───────────────────────────────────────────────────────────
    @staticmethod
    def _visible() -> tuple[ColumnElement[bool], ColumnElement[bool]]:
        """درس‌نامهٔ قابل‌دیدن برای دانشجو: منتشرشده و زمانش رسیده."""
        return (
            Lesson.status == "PUBLISHED",
            or_(Lesson.publish_at.is_(None), Lesson.publish_at <= func.now()),
        )

    async def _offering(self, offering_id: uuid.UUID) -> CourseOffering:
        offering = await self.session.get(CourseOffering, offering_id)
        if offering is None or offering.deleted_at is not None:
            raise NotFound("ارائهٔ درس پیدا نشد.")
        return offering

    async def _require_student(self, offering_id: uuid.UUID, user_id: uuid.UUID) -> None:
        found = await self.session.scalar(
            select(Enrollment.id).where(
                Enrollment.offering_id == offering_id,
                Enrollment.student_id == user_id,
                Enrollment.status.in_(ACTIVE),
            )
        )
        if found is None:
            raise PermissionDenied("این درس‌نامه برای دانشجوی همان درس است.")

    async def _lesson_of(self, lesson_id: uuid.UUID, offering_id: uuid.UUID) -> Lesson:
        lesson = await self.session.scalar(
            select(Lesson).where(Lesson.id == lesson_id, Lesson.offering_id == offering_id)
        )
        if lesson is None:
            raise NotFound("درس‌نامه پیدا نشد.")
        return lesson

    async def _check_lesson_fields(
        self,
        offering_id: uuid.UUID,
        title_fa: str,
        body_md: str,
        est_minutes: int,
        module_id: uuid.UUID | None,
    ) -> None:
        if not title_fa.strip():
            raise ValidationFailed("عنوان درس‌نامه نمی‌تواند خالی باشد.")
        if not body_md.strip():
            raise ValidationFailed("متن درس‌نامه نمی‌تواند خالی باشد.")
        if len(body_md) > 60000:
            raise ValidationFailed("متن درس‌نامه بیش از حد بلند است.")
        if not 1 <= est_minutes <= 120:
            raise ValidationFailed("زمان مطالعه باید بین ۱ تا ۱۲۰ دقیقه باشد.")
        if module_id is not None:
            owner = await self.session.scalar(
                select(Module.offering_id).where(Module.id == module_id)
            )
            if owner != offering_id:
                raise NotFound("ماژول در این ارائه نیست.")


def _state_of(row: Streak | None) -> rules.StreakState:
    if row is None:
        return rules.StreakState()
    return rules.StreakState(
        current=row.current,
        longest=row.longest,
        started_on=row.started_on,
        last_day=row.last_day,
        freeze_week=row.freeze_week,
    )
