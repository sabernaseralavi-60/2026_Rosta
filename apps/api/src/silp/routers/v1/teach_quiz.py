"""مسیر /teach — بخش آزمون، §5.11 و §3.5.

جدا از `teach.py` نگه داشته شده چون آزمون به‌تنهایی به اندازهٔ بقیهٔ
ناحیهٔ استاد endpoint دارد؛ یک فایل هزارخطی کسی را خوشحال نمی‌کند.

قلمرو همهٔ مجوزها **ارائه** است (ADR-0010). آزمون به ارائه وصل است، پس
`offering_of_quiz` قلمرو را از خود آزمون درمی‌آورد و استاد ارائهٔ الف
نمی‌تواند آزمون ارائهٔ ب را باز کند، حتی با شناسهٔ درست.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select

from silp.core.exceptions import NotFound
from silp.core.permissions import CurrentUser, Permission
from silp.domain.quiz import QUESTION_KIND_TITLE_FA, QuestionKind
from silp.models.quiz import (
    ATTEMPT_STATUS_TITLE_FA,
    QUIZ_STATUS_TITLE_FA,
    RESULT_VISIBILITY_TITLE_FA,
    GradeAppeal,
    Quiz,
    QuizAttempt,
    QuizQuestion,
)
from silp.routers.deps import (
    AppealServiceDep,
    CurrentUserDep,
    GradingServiceDep,
    QuizServiceDep,
    SessionDep,
    offering_from_path,
    offering_of_appeal,
    offering_of_quiz,
    require,
)
from silp.routers.v1.quizzes import appeal_out, result_out
from silp.schemas.common import ErrorResponse
from silp.schemas.quiz import (
    AppealDecisionIn,
    AppealOut,
    AttemptResultOut,
    AttemptSummaryOut,
    BankItemIn,
    BankItemOut,
    CopyFromBankIn,
    GradeAnswerIn,
    GradedAnswerOut,
    GradingQueueOut,
    PendingAnswerOut,
    PickRandomIn,
    QuestionIn,
    QuestionOut,
    QuestionStatsOut,
    QuizDetailOut,
    QuizIn,
    ReorderIn,
)
from silp.services.directory import display_names
from silp.services.quiz_service import QuestionDraft, QuizDraft

router = APIRouter(prefix="/teach", tags=["teaching"])

NOT_FOUND: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": "پیدا نشد"}
}
CONFLICT: dict[int | str, dict[str, Any]] = {
    409: {"model": ErrorResponse, "description": "وضعیت اجازه نمی‌دهد"}
}

#: آستانه‌هایی که تحلیل سؤال را به جملهٔ فارسی تبدیل می‌کنند — M4-13.
EASY_THRESHOLD = 0.85
HARD_THRESHOLD = 0.30
WEAK_DISCRIMINATION = 0.15


# ── آزمون ──────────────────────────────────────────────────────────────
@router.get(
    "/offerings/{offering_id}/quizzes",
    response_model=list[QuizDetailOut],
    summary="آزمون‌های ارائه",
)
async def list_quizzes(
    offering_id: uuid.UUID,
    quizzes: QuizServiceDep,
    session: SessionDep,
    _: Annotated[CurrentUser, Depends(require(Permission.QUIZ_CREATE, scope=offering_from_path))],
) -> list[QuizDetailOut]:
    rows = await quizzes.list_for_offering(offering_id, include_drafts=True)
    if not rows:
        return []
    counts = await _attempt_counts(session, [q.id for q in rows])
    return [_quiz_out(q, attempts=counts.get(q.id, 0)) for q in rows]


@router.post(
    "/offerings/{offering_id}/quizzes",
    response_model=QuizDetailOut,
    status_code=status.HTTP_201_CREATED,
    responses={**NOT_FOUND, 422: {"model": ErrorResponse}},
    summary="ساخت آزمون",
)
async def create_quiz(
    offering_id: uuid.UUID,
    body: QuizIn,
    quizzes: QuizServiceDep,
    user: Annotated[
        CurrentUser, Depends(require(Permission.QUIZ_CREATE, scope=offering_from_path))
    ],
) -> QuizDetailOut:
    quiz = await quizzes.create(offering_id=offering_id, draft=_draft(body), created_by=user.id)
    return _quiz_out(quiz)


@router.get(
    "/quizzes/{quiz_id}",
    response_model=QuizDetailOut,
    responses=NOT_FOUND,
    summary="آزمون با سؤال‌ها و کلید پاسخ",
)
async def quiz_detail(
    quiz_id: uuid.UUID,
    quizzes: QuizServiceDep,
    session: SessionDep,
    _: Annotated[CurrentUser, Depends(require(Permission.QUIZ_CREATE, scope=offering_of_quiz))],
) -> QuizDetailOut:
    quiz = await quizzes.get(quiz_id)
    questions = await quizzes.questions(quiz_id)
    counts = await _attempt_counts(session, [quiz_id])
    return _quiz_out(quiz, questions=questions, attempts=counts.get(quiz_id, 0))


@router.put(
    "/quizzes/{quiz_id}",
    response_model=QuizDetailOut,
    responses={**NOT_FOUND, **CONFLICT},
    summary="ویرایش آزمون",
)
async def update_quiz(
    quiz_id: uuid.UUID,
    body: QuizIn,
    quizzes: QuizServiceDep,
    _: Annotated[CurrentUser, Depends(require(Permission.QUIZ_CREATE, scope=offering_of_quiz))],
) -> QuizDetailOut:
    quiz = await quizzes.get(quiz_id)
    updated = await quizzes.update(
        quiz_id=quiz_id, offering_id=quiz.offering_id, draft=_draft(body)
    )
    return _quiz_out(updated, questions=await quizzes.questions(quiz_id))


@router.post(
    "/quizzes/{quiz_id}/publish",
    response_model=QuizDetailOut,
    responses={**NOT_FOUND, **CONFLICT},
    summary="انتشار آزمون",
)
async def publish_quiz(
    quiz_id: uuid.UUID,
    quizzes: QuizServiceDep,
    _: Annotated[CurrentUser, Depends(require(Permission.QUIZ_CREATE, scope=offering_of_quiz))],
) -> QuizDetailOut:
    quiz = await quizzes.get(quiz_id)
    published = await quizzes.publish(quiz_id=quiz_id, offering_id=quiz.offering_id)
    return _quiz_out(published, questions=await quizzes.questions(quiz_id))


@router.post(
    "/quizzes/{quiz_id}/close",
    response_model=QuizDetailOut,
    responses=NOT_FOUND,
    summary="بستن آزمون",
)
async def close_quiz(
    quiz_id: uuid.UUID,
    quizzes: QuizServiceDep,
    _: Annotated[CurrentUser, Depends(require(Permission.QUIZ_CREATE, scope=offering_of_quiz))],
) -> QuizDetailOut:
    quiz = await quizzes.get(quiz_id)
    closed = await quizzes.close(quiz_id=quiz_id, offering_id=quiz.offering_id)
    return _quiz_out(closed)


@router.post(
    "/quizzes/{quiz_id}/publish-results",
    response_model=QuizDetailOut,
    responses=NOT_FOUND,
    summary="انتشار نتیجه — حالت MANUAL",
)
async def publish_results(
    quiz_id: uuid.UUID,
    quizzes: QuizServiceDep,
    _: Annotated[CurrentUser, Depends(require(Permission.QUIZ_GRADE, scope=offering_of_quiz))],
) -> QuizDetailOut:
    quiz = await quizzes.get(quiz_id)
    published = await quizzes.publish_results(quiz_id=quiz_id, offering_id=quiz.offering_id)
    return _quiz_out(published)


@router.delete(
    "/quizzes/{quiz_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    responses={**NOT_FOUND, **CONFLICT},
    summary="حذف آزمون بدون تلاش",
)
async def delete_quiz(
    quiz_id: uuid.UUID,
    quizzes: QuizServiceDep,
    _: Annotated[CurrentUser, Depends(require(Permission.QUIZ_CREATE, scope=offering_of_quiz))],
) -> None:
    quiz = await quizzes.get(quiz_id)
    await quizzes.soft_delete(quiz_id=quiz_id, offering_id=quiz.offering_id)


# ── سؤال ───────────────────────────────────────────────────────────────
@router.post(
    "/quizzes/{quiz_id}/questions",
    response_model=QuestionOut,
    status_code=status.HTTP_201_CREATED,
    responses={**NOT_FOUND, **CONFLICT, 422: {"model": ErrorResponse}},
    summary="افزودن سؤال",
)
async def add_question(
    quiz_id: uuid.UUID,
    body: QuestionIn,
    quizzes: QuizServiceDep,
    _: Annotated[CurrentUser, Depends(require(Permission.QUIZ_CREATE, scope=offering_of_quiz))],
) -> QuestionOut:
    quiz = await quizzes.get(quiz_id)
    question = await quizzes.add_question(
        quiz_id=quiz_id, offering_id=quiz.offering_id, draft=_question_draft(body)
    )
    return _question_out(question)


@router.put(
    "/quizzes/{quiz_id}/questions/{question_id}",
    response_model=QuestionOut,
    responses={**NOT_FOUND, **CONFLICT, 422: {"model": ErrorResponse}},
    summary="ویرایش سؤال",
)
async def update_question(
    quiz_id: uuid.UUID,
    question_id: uuid.UUID,
    body: QuestionIn,
    quizzes: QuizServiceDep,
    _: Annotated[CurrentUser, Depends(require(Permission.QUIZ_CREATE, scope=offering_of_quiz))],
) -> QuestionOut:
    quiz = await quizzes.get(quiz_id)
    question = await quizzes.update_question(
        quiz_id=quiz_id,
        offering_id=quiz.offering_id,
        question_id=question_id,
        draft=_question_draft(body),
    )
    return _question_out(question)


@router.delete(
    "/quizzes/{quiz_id}/questions/{question_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    responses={**NOT_FOUND, **CONFLICT},
    summary="حذف سؤال",
)
async def delete_question(
    quiz_id: uuid.UUID,
    question_id: uuid.UUID,
    quizzes: QuizServiceDep,
    _: Annotated[CurrentUser, Depends(require(Permission.QUIZ_CREATE, scope=offering_of_quiz))],
) -> None:
    quiz = await quizzes.get(quiz_id)
    await quizzes.delete_question(
        quiz_id=quiz_id, offering_id=quiz.offering_id, question_id=question_id
    )


@router.post(
    "/quizzes/{quiz_id}/questions/reorder",
    response_model=list[QuestionOut],
    responses={**NOT_FOUND, **CONFLICT, 422: {"model": ErrorResponse}},
    summary="ترتیب سؤال‌ها",
)
async def reorder_questions(
    quiz_id: uuid.UUID,
    body: ReorderIn,
    quizzes: QuizServiceDep,
    _: Annotated[CurrentUser, Depends(require(Permission.QUIZ_CREATE, scope=offering_of_quiz))],
) -> list[QuestionOut]:
    quiz = await quizzes.get(quiz_id)
    rows = await quizzes.reorder(
        quiz_id=quiz_id, offering_id=quiz.offering_id, ordered_ids=body.question_ids
    )
    return [_question_out(q) for q in rows]


# ── بانک سؤال — M4-03 ──────────────────────────────────────────────────
@router.get("/question-bank", response_model=list[BankItemOut], summary="بانک سؤال من")
async def search_bank(
    quizzes: QuizServiceDep,
    current: CurrentUserDep,
    course_id: uuid.UUID | None = None,
    category: str | None = None,
    difficulty: Annotated[int | None, Query(ge=1, le=5)] = None,
    kind: str | None = None,
) -> list[BankItemOut]:
    rows = await quizzes.search_bank(
        owner_id=current.id,
        course_id=course_id,
        category=category,
        difficulty=difficulty,
        kind=kind,
    )
    return [_bank_out(item) for item in rows]


@router.post(
    "/question-bank",
    response_model=BankItemOut,
    status_code=status.HTTP_201_CREATED,
    responses={422: {"model": ErrorResponse}},
    summary="افزودن سؤال به بانک",
)
async def add_bank_item(
    body: BankItemIn,
    quizzes: QuizServiceDep,
    current: CurrentUserDep,
) -> BankItemOut:
    item = await quizzes.add_to_bank(
        owner_id=current.id,
        draft=QuestionDraft(
            kind=body.kind, body=body.body, payload=body.payload, explanation=body.explanation
        ),
        course_id=body.course_id,
        category=body.category,
        difficulty=body.difficulty,
    )
    return _bank_out(item)


@router.post(
    "/quizzes/{quiz_id}/questions/from-bank",
    response_model=list[QuestionOut],
    status_code=status.HTTP_201_CREATED,
    responses={**NOT_FOUND, **CONFLICT},
    summary="کپی سؤال از بانک",
)
async def copy_from_bank(
    quiz_id: uuid.UUID,
    body: CopyFromBankIn,
    quizzes: QuizServiceDep,
    _: Annotated[CurrentUser, Depends(require(Permission.QUIZ_CREATE, scope=offering_of_quiz))],
) -> list[QuestionOut]:
    quiz = await quizzes.get(quiz_id)
    rows = await quizzes.copy_from_bank(
        quiz_id=quiz_id,
        offering_id=quiz.offering_id,
        bank_ids=body.bank_ids,
        points=body.points,
    )
    return [_question_out(q) for q in rows]


@router.post(
    "/quizzes/{quiz_id}/questions/random",
    response_model=list[QuestionOut],
    status_code=status.HTTP_201_CREATED,
    responses={**NOT_FOUND, **CONFLICT},
    summary="انتخاب تصادفی N سؤال از بانک",
)
async def pick_random(
    quiz_id: uuid.UUID,
    body: PickRandomIn,
    quizzes: QuizServiceDep,
    _: Annotated[CurrentUser, Depends(require(Permission.QUIZ_CREATE, scope=offering_of_quiz))],
) -> list[QuestionOut]:
    quiz = await quizzes.get(quiz_id)
    rows = await quizzes.pick_random_from_bank(
        quiz_id=quiz_id,
        offering_id=quiz.offering_id,
        count=body.count,
        course_id=body.course_id,
        category=body.category,
        difficulty=body.difficulty,
        points=body.points,
    )
    return [_question_out(q) for q in rows]


# ── تلاش‌ها و تصحیح — M4-10 ────────────────────────────────────────────
@router.get(
    "/quizzes/{quiz_id}/attempts",
    response_model=list[AttemptSummaryOut],
    responses=NOT_FOUND,
    summary="تلاش‌های این آزمون",
)
async def quiz_attempts(
    quiz_id: uuid.UUID,
    session: SessionDep,
    _: Annotated[
        CurrentUser, Depends(require(Permission.QUIZ_VIEW_OTHERS_RESULT, scope=offering_of_quiz))
    ],
) -> list[AttemptSummaryOut]:
    rows = list(
        await session.scalars(
            select(QuizAttempt)
            .where(QuizAttempt.quiz_id == quiz_id)
            .order_by(QuizAttempt.submitted_at.desc().nulls_last())
        )
    )
    if not rows:
        return []
    names = await display_names(session, [a.student_id for a in rows])
    return [
        AttemptSummaryOut(
            id=a.id,
            student_id=a.student_id,
            student_name=_name_of(names, a.student_id),
            attempt_no=a.attempt_no,
            status=a.status,
            status_fa=ATTEMPT_STATUS_TITLE_FA.get(a.status, a.status),
            submitted_at=a.submitted_at,
            total_score=a.total_score,
            is_provisional=a.is_provisional,
            auto_closed=a.auto_closed,
            integrity_event_count=len(a.integrity_events or []),
        )
        for a in rows
    ]


@router.get(
    "/quizzes/{quiz_id}/grading-queue",
    response_model=list[GradingQueueOut],
    responses=NOT_FOUND,
    summary="صف تصحیح تشریحی — بر اساس سؤال",
)
async def grading_queue(
    quiz_id: uuid.UUID,
    grading: GradingServiceDep,
    session: SessionDep,
    _: Annotated[CurrentUser, Depends(require(Permission.QUIZ_GRADE, scope=offering_of_quiz))],
) -> list[GradingQueueOut]:
    questions = await grading.pending_questions(quiz_id)
    out: list[GradingQueueOut] = []
    for question in questions:
        queue = await grading.queue_for_question(quiz_id=quiz_id, question_id=question.id)
        names = await display_names(session, [p.student_id for p in queue.pending])
        out.append(
            GradingQueueOut(
                question_id=question.id,
                body=question.body,
                points=question.points,
                rubric=(question.payload or {}).get("rubric"),
                graded_count=queue.graded_count,
                pending=[
                    PendingAnswerOut(
                        attempt_id=p.attempt_id,
                        question_id=p.question_id,
                        student_name=_name_of(names, p.student_id),
                        attempt_no=p.attempt_no,
                        response=p.response,
                        points=p.points,
                    )
                    for p in queue.pending
                ],
            )
        )
    return out


@router.put(
    "/quizzes/{quiz_id}/attempts/{attempt_id}/answers/{question_id}",
    response_model=GradedAnswerOut,
    responses={**NOT_FOUND, 422: {"model": ErrorResponse}},
    summary="ثبت یا بازنویسی نمرهٔ یک سؤال",
)
async def grade_answer(
    quiz_id: uuid.UUID,
    attempt_id: uuid.UUID,
    question_id: uuid.UUID,
    body: GradeAnswerIn,
    grading: GradingServiceDep,
    session: SessionDep,
    user: Annotated[CurrentUser, Depends(require(Permission.QUIZ_GRADE, scope=offering_of_quiz))],
) -> GradedAnswerOut:
    answer = await grading.grade_answer(
        quiz_id=quiz_id,
        attempt_id=attempt_id,
        question_id=question_id,
        score=body.score,
        grader_id=user.id,
        feedback=body.feedback,
    )
    attempt = await session.get(QuizAttempt, attempt_id)
    return GradedAnswerOut(
        attempt_id=attempt_id,
        question_id=question_id,
        score=answer.manual_score or body.score,
        feedback=answer.feedback,
        attempt_total=attempt.total_score if attempt else None,
        attempt_is_provisional=bool(attempt and attempt.is_provisional),
    )


@router.post(
    "/quizzes/{quiz_id}/attempts/{attempt_id}/finalize",
    response_model=AttemptSummaryOut,
    responses=NOT_FOUND,
    summary="پایان تصحیح دستی یک تلاش",
)
async def finalize_attempt(
    quiz_id: uuid.UUID,
    attempt_id: uuid.UUID,
    grading: GradingServiceDep,
    session: SessionDep,
    user: Annotated[CurrentUser, Depends(require(Permission.QUIZ_GRADE, scope=offering_of_quiz))],
) -> AttemptSummaryOut:
    attempt = await grading.finalize_attempt(
        quiz_id=quiz_id, attempt_id=attempt_id, grader_id=user.id
    )
    names = await display_names(session, [attempt.student_id])
    return _attempt_summary(attempt, _name_of(names, attempt.student_id))


@router.post(
    "/quizzes/{quiz_id}/attempts/{attempt_id}/void",
    response_model=AttemptSummaryOut,
    responses=NOT_FOUND,
    summary="ابطال تلاش",
)
async def void_attempt(
    quiz_id: uuid.UUID,
    attempt_id: uuid.UUID,
    grading: GradingServiceDep,
    session: SessionDep,
    user: Annotated[
        CurrentUser,
        Depends(require(Permission.QUIZ_ATTEMPT_INVALIDATE, scope=offering_of_quiz)),
    ],
) -> AttemptSummaryOut:
    attempt = await grading.void_attempt(quiz_id=quiz_id, attempt_id=attempt_id, grader_id=user.id)
    names = await display_names(session, [attempt.student_id])
    return _attempt_summary(attempt, _name_of(names, attempt.student_id))


@router.get(
    "/quizzes/{quiz_id}/attempts/{attempt_id}/result",
    response_model=AttemptResultOut,
    responses=NOT_FOUND,
    summary="نتیجهٔ یک دانشجو از دید استاد",
)
async def attempt_result(
    quiz_id: uuid.UUID,
    attempt_id: uuid.UUID,
    grading: GradingServiceDep,
    user: Annotated[
        CurrentUser, Depends(require(Permission.QUIZ_VIEW_OTHERS_RESULT, scope=offering_of_quiz))
    ],
) -> AttemptResultOut:
    result = await grading.result(attempt_id=attempt_id, viewer_id=user.id, is_staff=True)
    return result_out(result)


# ── تحلیل سؤال — M4-13 ─────────────────────────────────────────────────
@router.get(
    "/quizzes/{quiz_id}/question-stats",
    response_model=list[QuestionStatsOut],
    responses=NOT_FOUND,
    summary="ضریب دشواری و تمیز هر سؤال",
)
async def question_stats(
    quiz_id: uuid.UUID,
    grading: GradingServiceDep,
    _: Annotated[
        CurrentUser, Depends(require(Permission.QUIZ_VIEW_OTHERS_RESULT, scope=offering_of_quiz))
    ],
) -> list[QuestionStatsOut]:
    rows = await grading.question_stats(quiz_id)
    return [
        QuestionStatsOut(
            question_id=s.question_id,
            body=s.body,
            kind=s.kind,
            points=s.points,
            answered=s.answered,
            difficulty=s.difficulty,
            discrimination=s.discrimination,
            note_fa=_stats_note(s.difficulty, s.discrimination),
        )
        for s in rows
    ]


# ── اعتراض — M4-12 ─────────────────────────────────────────────────────
@router.get(
    "/quizzes/{quiz_id}/appeals",
    response_model=list[AppealOut],
    responses=NOT_FOUND,
    summary="اعتراض‌های این آزمون",
)
async def quiz_appeals(
    quiz_id: uuid.UUID,
    appeals: AppealServiceDep,
    _: Annotated[CurrentUser, Depends(require(Permission.APPEAL_RESOLVE, scope=offering_of_quiz))],
    only_open: bool = True,
) -> list[AppealOut]:
    rows = await appeals.list_for_quiz(quiz_id, only_open=only_open)
    return [appeal_out(a) for a in rows]


@router.post(
    "/appeals/{appeal_id}/resolve",
    response_model=AppealOut,
    responses={**NOT_FOUND, **CONFLICT, 422: {"model": ErrorResponse}},
    summary="رسیدگی به اعتراض",
)
async def resolve_appeal(
    appeal_id: uuid.UUID,
    body: AppealDecisionIn,
    appeals: AppealServiceDep,
    session: SessionDep,
    user: Annotated[
        CurrentUser, Depends(require(Permission.APPEAL_RESOLVE, scope=offering_of_appeal))
    ],
) -> AppealOut:
    # قلمرو را `offering_of_appeal` بررسی کرده؛ اینجا فقط شناسهٔ آزمون
    # لازم است تا سرویس بتواند تعلق اعتراض را دوباره تأیید کند.
    quiz_id = await session.scalar(
        select(QuizAttempt.quiz_id)
        .join(GradeAppeal, GradeAppeal.attempt_id == QuizAttempt.id)
        .where(GradeAppeal.id == appeal_id)
    )
    if quiz_id is None:
        raise NotFound("این اعتراض پیدا نشد.")
    appeal = await appeals.resolve(
        appeal_id=appeal_id,
        quiz_id=quiz_id,
        resolver_id=user.id,
        accept=body.accept,
        response=body.response,
        new_score=body.new_score,
    )
    return appeal_out(appeal)


# بستن خودکار تلاش‌های منقضی (M4-07) endpoint ندارد و عمداً:
# قلمرو `QUIZ_GRADE` **ارائه** است (ADR-0010)، پس یک مسیر سراسری با آن
# مجوز را هیچ استادی نمی‌تواند صدا بزند — نه استاد، چون قلمرو ندارد؛ نه
# مدیر، چون کار او نیست. مسیری که هیچ‌کس نمی‌تواند صدا بزند، بدتر از
# نبودنش است.
#
# مکانیزم واقعی، کار زمان‌بندی‌شدهٔ §7.11 است:
# `silp.workers.settings.close_expired_attempts`، هر ۶۰ ثانیه.


# ── مبدل‌ها ────────────────────────────────────────────────────────────
async def _attempt_counts(session: SessionDep, quiz_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    """تعداد تلاش هر آزمون — یک کوئری برای کل فهرست (§5.14)."""
    if not quiz_ids:
        return {}
    rows = await session.execute(
        select(QuizAttempt.quiz_id, func.count())
        .where(QuizAttempt.quiz_id.in_(quiz_ids))
        .group_by(QuizAttempt.quiz_id)
    )
    counts: dict[uuid.UUID, int] = {}
    for quiz_id, count in rows.all():
        counts[quiz_id] = count
    return counts


def _draft(body: QuizIn) -> QuizDraft:
    return QuizDraft(
        title_fa=body.title_fa,
        duration_min=body.duration_min,
        opens_at=body.opens_at,
        closes_at=body.closes_at,
        week_id=body.week_id,
        description=body.description,
        max_attempts=body.max_attempts,
        passing_score=body.passing_score,
        shuffle_questions=body.shuffle_questions,
        shuffle_options=body.shuffle_options,
        result_visibility=body.result_visibility,
        show_correct_answers=body.show_correct_answers,
    )


def _question_draft(body: QuestionIn) -> QuestionDraft:
    return QuestionDraft(
        kind=body.kind,
        body=body.body,
        payload=body.payload,
        points=body.points,
        explanation=body.explanation,
        sort_order=body.sort_order,
    )


def _quiz_out(
    quiz: Quiz, *, questions: list[QuizQuestion] | None = None, attempts: int = 0
) -> QuizDetailOut:
    return QuizDetailOut(
        id=quiz.id,
        offering_id=quiz.offering_id,
        week_id=quiz.week_id,
        title_fa=quiz.title_fa,
        description=quiz.description,
        duration_min=quiz.duration_min,
        opens_at=quiz.opens_at,
        closes_at=quiz.closes_at,
        max_attempts=quiz.max_attempts,
        passing_score=quiz.passing_score,
        shuffle_questions=quiz.shuffle_questions,
        shuffle_options=quiz.shuffle_options,
        result_visibility=quiz.result_visibility,
        result_visibility_fa=RESULT_VISIBILITY_TITLE_FA.get(
            quiz.result_visibility, quiz.result_visibility
        ),
        show_correct_answers=quiz.show_correct_answers,
        status=quiz.status,
        status_fa=QUIZ_STATUS_TITLE_FA.get(quiz.status, quiz.status),
        total_points=quiz.total_points,
        results_published_at=quiz.results_published_at,
        attempt_count=attempts,
        questions=[_question_out(q) for q in (questions or [])],
    )


def _question_out(question: QuizQuestion) -> QuestionOut:
    return QuestionOut(
        id=question.id,
        kind=question.kind,
        kind_fa=QUESTION_KIND_TITLE_FA[QuestionKind(question.kind)],
        body=question.body,
        payload=question.payload,
        explanation=question.explanation,
        points=question.points,
        sort_order=question.sort_order,
        bank_id=question.bank_id,
    )


def _bank_out(item: object) -> BankItemOut:
    return BankItemOut(
        id=item.id,  # type: ignore[attr-defined]
        kind=item.kind,  # type: ignore[attr-defined]
        kind_fa=QUESTION_KIND_TITLE_FA[QuestionKind(item.kind)],  # type: ignore[attr-defined]
        body=item.body,  # type: ignore[attr-defined]
        category=item.category,  # type: ignore[attr-defined]
        difficulty=item.difficulty,  # type: ignore[attr-defined]
        usage_count=item.usage_count,  # type: ignore[attr-defined]
    )


def _attempt_summary(attempt: QuizAttempt, name: str) -> AttemptSummaryOut:
    return AttemptSummaryOut(
        id=attempt.id,
        student_id=attempt.student_id,
        student_name=name,
        attempt_no=attempt.attempt_no,
        status=attempt.status,
        status_fa=ATTEMPT_STATUS_TITLE_FA.get(attempt.status, attempt.status),
        submitted_at=attempt.submitted_at,
        total_score=attempt.total_score,
        is_provisional=attempt.is_provisional,
        auto_closed=attempt.auto_closed,
        integrity_event_count=len(attempt.integrity_events or []),
    )


def _name_of(names: dict[uuid.UUID, Any], user_id: uuid.UUID) -> str:
    entry = names.get(user_id)
    if entry is None:
        return "—"
    return entry.full_name or entry.username or "—"


def _stats_note(difficulty: object, discrimination: object) -> str | None:
    """تحلیل عددی را به یک جملهٔ قابل اقدام تبدیل می‌کند — M4-13.

    عدد خالی برای استادی که آمار نخوانده، یعنی هیچ. جمله می‌گوید با
    سؤال چه کند.
    """
    if difficulty is None:
        return None
    value = float(difficulty)  # type: ignore[arg-type]
    if discrimination is not None and float(discrimination) < WEAK_DISCRIMINATION:  # type: ignore[arg-type]
        return "این سؤال بین دانشجوی قوی و ضعیف فرقی نگذاشته؛ متن یا گزینه‌هایش را بازبینی کنید."
    if value >= EASY_THRESHOLD:
        return "تقریباً همه درست زده‌اند — سؤال آسان بود."
    if value <= HARD_THRESHOLD:
        return "بیشتر دانشجویان اشتباه زده‌اند — یا سؤال سخت بود یا مطلب خوب منتقل نشده."
    return None


__all__ = ["router"]
