"""مسیر /quizzes و /attempts — ناحیهٔ دانشجو، §5.6.

مالکیتِ تلاش، اینجا **مجوز نیست، هویت است**: هیچ نقشی «تلاشِ دیگری» را
باز نمی‌کند، پس `require(...)` روی این مسیرها نمی‌نشیند و سرویس خودش
`student_id` را تطبیق می‌دهد. تلاشِ کس دیگر `404` می‌گیرد نه `403` —
§6.4 قاعدهٔ ۴.

استاد نتیجهٔ دانشجو را از مسیر `/teach` می‌بیند، با مجوز
`QUIZ_VIEW_OTHERS_RESULT` و در قلمرو ارائهٔ خودش.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, status
from sqlalchemy import func, select

from silp.core.exceptions import NotFound
from silp.core.logging import get_logger
from silp.domain.quiz import (
    QUESTION_KIND_TITLE_FA,
    QUIZ_AVAILABILITY_TITLE_FA,
    QuestionKind,
    availability,
    compute_expires_at,
)
from silp.models.education import CourseWeek, Enrollment
from silp.models.quiz import (
    APPEAL_STATUS_TITLE_FA,
    GradeAppeal,
    Quiz,
    QuizAttempt,
    QuizQuestion,
)
from silp.routers.deps import (
    AppealServiceDep,
    AttemptServiceDep,
    CurrentUserDep,
    GradingServiceDep,
    SessionDep,
)
from silp.schemas.common import ErrorResponse
from silp.schemas.quiz import (
    AppealIn,
    AppealOut,
    AttemptResultOut,
    AttemptStartOut,
    AttemptViewOut,
    IntegrityEventIn,
    IntegrityEventOut,
    QuestionReviewOut,
    QuizSummaryOut,
    ResultQuestionOut,
    SaveAnswerIn,
    SaveAnswerOut,
    SubmitIn,
    SubmitOut,
    SyncIn,
    SyncOut,
    VisibleQuestionOut,
)

log = get_logger("silp.routers.quizzes")

router = APIRouter(prefix="/quizzes", tags=["quiz"])
attempts_router = APIRouter(prefix="/attempts", tags=["quiz"])

NOT_FOUND: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": "پیدا نشد"}
}
CONFLICT: dict[int | str, dict[str, Any]] = {
    409: {"model": ErrorResponse, "description": "وضعیت اجازه نمی‌دهد"}
}


# ── فهرست و فراداده ────────────────────────────────────────────────────
@router.get(
    "/offering/{offering_id}",
    response_model=list[QuizSummaryOut],
    summary="آزمون‌های یک ارائه",
)
async def quizzes_of_offering(
    offering_id: uuid.UUID,
    session: SessionDep,
    current: CurrentUserDep,
) -> list[QuizSummaryOut]:
    enrolled = await session.scalar(
        select(Enrollment).where(
            Enrollment.offering_id == offering_id, Enrollment.student_id == current.id
        )
    )
    if enrolled is None or not enrolled.is_active:
        raise NotFound("این ارائه پیدا نشد.")

    quizzes = list(
        await session.scalars(
            select(Quiz)
            .where(
                Quiz.offering_id == offering_id,
                Quiz.deleted_at.is_(None),
                Quiz.status != "DRAFT",
            )
            .order_by(Quiz.opens_at.desc())
        )
    )
    if not quizzes:
        return []
    return await _summaries(session, quizzes, student_id=current.id)


@router.get(
    "/{quiz_id}",
    response_model=QuizSummaryOut,
    responses=NOT_FOUND,
    summary="فراداده — بدون سؤالات",
)
async def quiz_detail(
    quiz_id: uuid.UUID,
    session: SessionDep,
    current: CurrentUserDep,
) -> QuizSummaryOut:
    quiz = await session.get(Quiz, quiz_id)
    if quiz is None or not quiz.is_live:
        raise NotFound("این آزمون پیدا نشد.")
    enrolled = await session.scalar(
        select(Enrollment).where(
            Enrollment.offering_id == quiz.offering_id, Enrollment.student_id == current.id
        )
    )
    if enrolled is None or not enrolled.is_active:
        raise NotFound("این آزمون پیدا نشد.")
    summaries = await _summaries(session, [quiz], student_id=current.id)
    return summaries[0]


@router.post(
    "/{quiz_id}/attempts",
    response_model=AttemptStartOut,
    status_code=status.HTTP_201_CREATED,
    responses={**NOT_FOUND, **CONFLICT},
    summary="شروع تلاش",
)
async def start_attempt(
    quiz_id: uuid.UUID,
    attempts: AttemptServiceDep,
    current: CurrentUserDep,
) -> AttemptStartOut:
    started = await attempts.start(quiz_id=quiz_id, student_id=current.id)
    return AttemptStartOut(
        attempt_id=started.attempt_id,
        server_time=started.server_time,
        expires_at=started.expires_at,
        seconds_remaining=started.seconds_remaining,
        question_count=started.question_count,
        total_points=started.total_points,
    )


# ── تلاش ───────────────────────────────────────────────────────────────
@attempts_router.get(
    "/{attempt_id}",
    response_model=AttemptViewOut,
    responses=NOT_FOUND,
    summary="سؤالات + پاسخ‌های ذخیره‌شده + زمان باقی",
)
async def view_attempt(
    attempt_id: uuid.UUID,
    attempts: AttemptServiceDep,
    current: CurrentUserDep,
) -> AttemptViewOut:
    view = await attempts.view(attempt_id=attempt_id, student_id=current.id)
    return AttemptViewOut(
        attempt_id=view.attempt.id,
        quiz_id=view.quiz.id,
        quiz_title_fa=view.quiz.title_fa,
        status=view.attempt.status,
        server_time=view.server_time,
        expires_at=view.attempt.expires_at,
        seconds_remaining=view.seconds_remaining,
        total_points=view.quiz.total_points,
        questions=[
            VisibleQuestionOut(
                id=q.id,
                kind=q.kind,
                kind_fa=QUESTION_KIND_TITLE_FA[QuestionKind(q.kind)],
                body=q.body,
                points=q.points,
                payload=q.payload,
                my_answer=q.my_answer,
                is_flagged=q.is_flagged,
            )
            for q in view.questions
        ],
    )


@attempts_router.put(
    "/{attempt_id}/answers/{question_id}",
    response_model=SaveAnswerOut,
    responses={**NOT_FOUND, **CONFLICT},
    summary="ذخیرهٔ پاسخ — بی‌اثر در تکرار",
)
async def save_answer(
    attempt_id: uuid.UUID,
    question_id: uuid.UUID,
    body: SaveAnswerIn,
    attempts: AttemptServiceDep,
    current: CurrentUserDep,
) -> SaveAnswerOut:
    saved = await attempts.save_answer(
        attempt_id=attempt_id,
        student_id=current.id,
        question_id=question_id,
        response=body.response,
        is_flagged=body.is_flagged,
        client_ts=body.client_ts,
    )
    return SaveAnswerOut(saved_at=saved.saved_at, seconds_remaining=saved.seconds_remaining)


@attempts_router.post(
    "/{attempt_id}/sync",
    response_model=SyncOut,
    responses={**NOT_FOUND, **CONFLICT},
    summary="همگام‌سازی دسته‌ای پس از آفلاین",
)
async def sync_answers(
    attempt_id: uuid.UUID,
    body: SyncIn,
    attempts: AttemptServiceDep,
    current: CurrentUserDep,
) -> SyncOut:
    outcome = await attempts.sync(
        attempt_id=attempt_id,
        student_id=current.id,
        answers=[item.model_dump() for item in body.answers],
    )
    return SyncOut(
        accepted=outcome.accepted,
        rejected=outcome.rejected,
        seconds_remaining=outcome.seconds_remaining,
    )


@attempts_router.post(
    "/{attempt_id}/submit",
    response_model=SubmitOut,
    responses={**NOT_FOUND, **CONFLICT},
    summary="ارسال نهایی",
)
async def submit_attempt(
    attempt_id: uuid.UUID,
    body: SubmitIn,
    attempts: AttemptServiceDep,
    session: SessionDep,
    current: CurrentUserDep,
) -> SubmitOut:
    outcome = await attempts.submit(attempt_id=attempt_id, student_id=current.id)
    quiz = await session.get(Quiz, outcome.attempt.quiz_id)
    log.info(
        "attempt_submitted",
        attempt_id=str(attempt_id),
        client_unanswered=body.confirm_unanswered,
    )
    return SubmitOut(
        status=outcome.attempt.status,
        auto_score=outcome.auto_score,
        is_provisional=outcome.is_provisional,
        total_points=quiz.total_points if quiz else Decimal("0"),
        result_available=bool(quiz and quiz.result_visibility == "IMMEDIATE"),
    )


@attempts_router.post(
    "/{attempt_id}/integrity",
    response_model=IntegrityEventOut,
    responses=NOT_FOUND,
    summary="ثبت رویداد تمامیت — گزارش، نه اتهام",
)
async def record_integrity(
    attempt_id: uuid.UUID,
    body: IntegrityEventIn,
    attempts: AttemptServiceDep,
    current: CurrentUserDep,
) -> IntegrityEventOut:
    count = await attempts.record_integrity_event(
        attempt_id=attempt_id, student_id=current.id, kind=body.kind, detail=body.detail
    )
    return IntegrityEventOut(recorded=count)


@attempts_router.get(
    "/{attempt_id}/result",
    response_model=AttemptResultOut,
    responses={**NOT_FOUND, **CONFLICT},
    summary="نتیجه",
)
async def attempt_result(
    attempt_id: uuid.UUID,
    grading: GradingServiceDep,
    current: CurrentUserDep,
) -> AttemptResultOut:
    result = await grading.result(attempt_id=attempt_id, viewer_id=current.id)
    return result_out(result)


@attempts_router.post(
    "/{attempt_id}/appeal",
    response_model=AppealOut,
    status_code=status.HTTP_201_CREATED,
    responses={**NOT_FOUND, **CONFLICT},
    summary="اعتراض به نمره",
)
async def open_appeal(
    attempt_id: uuid.UUID,
    body: AppealIn,
    appeals: AppealServiceDep,
    current: CurrentUserDep,
) -> AppealOut:
    appeal = await appeals.open(
        attempt_id=attempt_id,
        student_id=current.id,
        reason=body.reason,
        question_id=body.question_id,
    )
    return appeal_out(appeal)


# ── مبدل‌های مشترک ─────────────────────────────────────────────────────
def appeal_out(appeal: GradeAppeal) -> AppealOut:
    return AppealOut(
        id=appeal.id,
        attempt_id=appeal.attempt_id,
        question_id=appeal.question_id,
        status=appeal.status,
        status_fa=APPEAL_STATUS_TITLE_FA.get(appeal.status, appeal.status),
        reason=appeal.reason,
        response=appeal.response,
        created_at=appeal.created_at,
        resolved_at=appeal.resolved_at,
    )


def result_out(result: object) -> AttemptResultOut:
    """`AttemptResult` سرویس ← اسکیمای خروجی.

    تایپ ورودی عمداً باز است تا این ماژول به `grading_service` وابستگی
    تایپی نسازد؛ مسیر استاد هم از همین استفاده می‌کند.
    """
    attempt = result.attempt  # type: ignore[attr-defined]
    quiz = result.quiz  # type: ignore[attr-defined]
    questions = []
    for item in result.questions:  # type: ignore[attr-defined]
        review = None
        if item.review is not None:
            review = QuestionReviewOut(
                correct=item.review.get("correct"),
                accepted=item.review.get("accepted"),
                tolerance=item.review.get("tolerance"),
                explanation=item.review.get("explanation"),
            )
        questions.append(
            ResultQuestionOut(
                id=item.question.id,
                kind=item.question.kind,
                kind_fa=QUESTION_KIND_TITLE_FA[QuestionKind(item.question.kind)],
                body=item.question.body,
                points=item.question.points,
                score=item.score,
                is_correct=item.is_correct,
                my_answer=item.response,
                feedback=item.feedback,
                review=review,
            )
        )
    return AttemptResultOut(
        attempt_id=attempt.id,
        quiz_id=quiz.id,
        quiz_title_fa=quiz.title_fa,
        attempt_no=attempt.attempt_no,
        status=attempt.status,
        submitted_at=attempt.submitted_at,
        total_score=attempt.total_score,
        total_points=quiz.total_points,
        is_provisional=attempt.is_provisional,
        auto_closed=attempt.auto_closed,
        passed=result.passed,  # type: ignore[attr-defined]
        class_average=result.class_average,  # type: ignore[attr-defined]
        cohort_size=result.cohort_size,  # type: ignore[attr-defined]
        questions=questions,
    )


async def _summaries(
    session: SessionDep, quizzes: list[Quiz], *, student_id: uuid.UUID
) -> list[QuizSummaryOut]:
    """فهرست آزمون‌ها با وضعیتِ همین دانشجو — بدون N+1 (§5.14)."""
    quiz_ids = [q.id for q in quizzes]

    counts: dict[uuid.UUID, int] = {}
    for quiz_id, count in (
        await session.execute(
            select(QuizQuestion.quiz_id, func.count())
            .where(QuizQuestion.quiz_id.in_(quiz_ids))
            .group_by(QuizQuestion.quiz_id)
        )
    ).all():
        counts[quiz_id] = count
    week_numbers: dict[uuid.UUID, int] = {}
    for week_id, number in (
        await session.execute(
            select(CourseWeek.id, CourseWeek.week_number).where(
                CourseWeek.id.in_([q.week_id for q in quizzes if q.week_id])
            )
        )
    ).all():
        week_numbers[week_id] = number

    mine = list(
        await session.scalars(
            select(QuizAttempt).where(
                QuizAttempt.quiz_id.in_(quiz_ids), QuizAttempt.student_id == student_id
            )
        )
    )
    by_quiz: dict[uuid.UUID, list[QuizAttempt]] = {}
    for attempt in mine:
        if attempt.status != "VOIDED":
            by_quiz.setdefault(attempt.quiz_id, []).append(attempt)

    now = datetime.now(UTC)
    out: list[QuizSummaryOut] = []
    for quiz in quizzes:
        attempts = by_quiz.get(quiz.id, [])
        active = next((a for a in attempts if a.is_active), None)
        state = availability(
            now=now,
            opens_at=quiz.opens_at,
            closes_at=quiz.closes_at,
            has_active_attempt=active is not None,
            used_attempts=len(attempts),
            max_attempts=quiz.max_attempts,
        )
        # چقدر وقت واقعی می‌ماند اگر همین حالا شروع کند — ADR-0011 §۳.
        effective = None
        if state.value == "AVAILABLE":
            expires = compute_expires_at(
                started_at=now, duration_min=quiz.duration_min, closes_at=quiz.closes_at
            )
            effective = max(0, int((expires - now).total_seconds()))

        out.append(
            QuizSummaryOut(
                id=quiz.id,
                title_fa=quiz.title_fa,
                description=quiz.description,
                week_number=week_numbers.get(quiz.week_id) if quiz.week_id else None,
                duration_min=quiz.duration_min,
                opens_at=quiz.opens_at,
                closes_at=quiz.closes_at,
                max_attempts=quiz.max_attempts,
                total_points=quiz.total_points,
                question_count=counts.get(quiz.id, 0),
                passing_score=quiz.passing_score,
                state=state.value,
                state_fa=QUIZ_AVAILABILITY_TITLE_FA[state],
                server_time=now,
                used_attempts=len(attempts),
                active_attempt_id=active.id if active else None,
                effective_duration_sec=effective,
            )
        )
    return out


__all__ = ["attempts_router", "router"]
