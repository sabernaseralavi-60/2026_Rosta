"""حلقهٔ یادگیری روزانه — ADR-0036.

| مسیر | توضیح |
|------|-------|
| `GET /learning/today` | «امروز»: درس‌نامه، چالش باز، استمرار، بازخورد، پیشنهاد (دانشجو) |
| `GET /learning/mastery` | نقشهٔ شایستگی من |
| `GET /learning/offerings/{id}/lessons` | درس‌نامه‌های منتشرشدهٔ ارائه (دانشجوی همان ارائه) |
| `GET /learning/lessons/{id}` | یک درس‌نامه + چالش‌های وصل‌شده |
| `…/teach/offerings/{id}/lessons…` | کادر: ساخت، ویرایش، انتشار، حذف |
| `…/teach/offerings/{id}/modules` | کادر: ماژول |
| `…/teach/offerings/{id}/checkpoints` | کادر: ساخت چالش روزانه از بانک سؤال |
| `GET/POST /learning/competencies…` | شایستگی و مفهوم (کادر) |

درس‌نامهٔ پیش‌نویس هرگز به دانشجو نمی‌رسد؛ سرور هم زمان انتشار را می‌سنجد.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import func, select

from silp.core.exceptions import PermissionDenied
from silp.core.permissions import CurrentUser, Permission, Role
from silp.models.quiz import QuizQuestion
from silp.routers.deps import (
    CurrentUserDep,
    LearningServiceDep,
    QuizServiceDep,
    SessionDep,
    offering_from_path,
    require,
)
from silp.schemas.common import ErrorResponse
from silp.schemas.learning import (
    CheckpointIn,
    CheckpointOut,
    CompetencyIn,
    CompetencyOut,
    ConceptIn,
    ConceptOut,
    LessonCheckpointOut,
    LessonDetailOut,
    LessonIn,
    LessonOut,
    LessonPatchIn,
    LessonSummaryOut,
    MasteryOut,
    ModuleIn,
    ModuleOut,
    PublishIn,
    TodayOut,
)

router = APIRouter(prefix="/learning", tags=["learning"])

_R: dict[int | str, dict[str, object]] = {
    404: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
}
_STAFF_ROLES = {Role.TA, Role.INSTRUCTOR, Role.COORDINATOR, Role.ADMIN}

EditDep = Annotated[
    CurrentUser, Depends(require(Permission.COURSE_WEEK_EDIT, scope=offering_from_path))
]
PublishDep = Annotated[
    CurrentUser, Depends(require(Permission.COURSE_WEEK_PUBLISH, scope=offering_from_path))
]
QuizStaffDep = Annotated[
    CurrentUser, Depends(require(Permission.QUIZ_CREATE, scope=offering_from_path))
]


def _require_staff(user: CurrentUser) -> None:
    """شایستگی و مفهوم به یک ارائه بسته نیست؛ هر عضو کادر (در هر ارائه) می‌تواند بسازد."""
    if not any(grant.role in _STAFF_ROLES for grant in user.grants):
        raise PermissionDenied()


# ── دانشجو ─────────────────────────────────────────────────────────────
@router.get("/today", response_model=TodayOut, summary="امروز: چه بخوانم، چه چالشی، چه بازخوردی")
async def today(svc: LearningServiceDep, user: CurrentUserDep) -> TodayOut:
    result = await svc.today(user.id)
    return TodayOut.model_validate(result, from_attributes=True)


@router.get("/mastery", response_model=list[MasteryOut], summary="نقشهٔ شایستگی من")
async def mastery(svc: LearningServiceDep, user: CurrentUserDep) -> list[MasteryOut]:
    return [MasteryOut.model_validate(m, from_attributes=True) for m in await svc.mastery(user.id)]


@router.get(
    "/offerings/{offering_id}/lessons",
    response_model=list[LessonSummaryOut],
    summary="درس‌نامه‌های منتشرشدهٔ ارائه",
    responses=_R,
)
async def student_lessons(
    offering_id: uuid.UUID, svc: LearningServiceDep, user: CurrentUserDep
) -> list[LessonSummaryOut]:
    rows = await svc.lessons_for_student(offering_id, user.id)
    return [LessonSummaryOut.model_validate(r) for r in rows]


@router.get(
    "/lessons/{lesson_id}",
    response_model=LessonDetailOut,
    summary="یک درس‌نامه با چالش‌های وصل‌شده",
    responses=_R,
)
async def student_lesson(
    lesson_id: uuid.UUID, svc: LearningServiceDep, user: CurrentUserDep
) -> LessonDetailOut:
    lesson = await svc.lesson_for_student(lesson_id, user.id)
    quizzes = await svc.checkpoints_of_lesson(lesson.id)
    return LessonDetailOut(
        **LessonSummaryOut.model_validate(lesson).model_dump(),
        body_md=lesson.body_md,
        checkpoints=[
            LessonCheckpointOut(
                quiz_id=q.id,
                title_fa=q.title_fa,
                opens_at=q.opens_at,
                closes_at=q.closes_at,
                duration_min=q.duration_min,
                status=q.status,
            )
            for q in quizzes
        ],
    )


# ── کادر: درس‌نامه و ماژول ─────────────────────────────────────────────
@router.get(
    "/teach/offerings/{offering_id}/lessons",
    response_model=list[LessonOut],
    summary="کادر: همهٔ درس‌نامه‌ها (با پیش‌نویس)",
    responses=_R,
)
async def staff_lessons(
    offering_id: uuid.UUID, svc: LearningServiceDep, _: EditDep
) -> list[LessonOut]:
    return [LessonOut.model_validate(r) for r in await svc.lessons_for_staff(offering_id)]


@router.post(
    "/teach/offerings/{offering_id}/lessons",
    response_model=LessonOut,
    status_code=status.HTTP_201_CREATED,
    summary="کادر: ساخت درس‌نامه",
    responses=_R,
)
async def create_lesson(
    offering_id: uuid.UUID, body: LessonIn, svc: LearningServiceDep, user: EditDep
) -> LessonOut:
    if body.publish and not user.has_permission(Permission.COURSE_WEEK_PUBLISH, offering_id):
        raise PermissionDenied(permission=Permission.COURSE_WEEK_PUBLISH.value)
    lesson = await svc.create_lesson(
        offering_id,
        user.id,
        title_fa=body.title_fa,
        body_md=body.body_md,
        est_minutes=body.est_minutes,
        module_id=body.module_id,
        week_id=body.week_id,
        publish_at=body.publish_at,
        publish=body.publish,
    )
    return LessonOut.model_validate(lesson)


@router.put(
    "/teach/offerings/{offering_id}/lessons/{lesson_id}",
    response_model=LessonOut,
    summary="کادر: ویرایش درس‌نامه",
    responses=_R,
)
async def update_lesson(
    offering_id: uuid.UUID,
    lesson_id: uuid.UUID,
    body: LessonPatchIn,
    svc: LearningServiceDep,
    _: EditDep,
) -> LessonOut:
    lesson = await svc.update_lesson(
        lesson_id,
        offering_id,
        title_fa=body.title_fa,
        body_md=body.body_md,
        est_minutes=body.est_minutes,
        module_id=body.module_id,
        publish_at=body.publish_at,
    )
    return LessonOut.model_validate(lesson)


@router.post(
    "/teach/offerings/{offering_id}/lessons/{lesson_id}/publish",
    response_model=LessonOut,
    summary="کادر: انتشار یا برگرداندن به پیش‌نویس",
    responses=_R,
)
async def publish_lesson(
    offering_id: uuid.UUID,
    lesson_id: uuid.UUID,
    body: PublishIn,
    svc: LearningServiceDep,
    _: PublishDep,
) -> LessonOut:
    lesson = await svc.set_lesson_published(lesson_id, offering_id, body.published)
    return LessonOut.model_validate(lesson)


@router.delete(
    "/teach/offerings/{offering_id}/lessons/{lesson_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="کادر: حذف درس‌نامه",
    responses=_R,
)
async def delete_lesson(
    offering_id: uuid.UUID, lesson_id: uuid.UUID, svc: LearningServiceDep, _: EditDep
) -> Response:
    await svc.delete_lesson(lesson_id, offering_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/teach/offerings/{offering_id}/modules",
    response_model=list[ModuleOut],
    summary="کادر: ماژول‌های ارائه",
    responses=_R,
)
async def modules(offering_id: uuid.UUID, svc: LearningServiceDep, _: EditDep) -> list[ModuleOut]:
    return [ModuleOut.model_validate(m) for m in await svc.modules(offering_id)]


@router.post(
    "/teach/offerings/{offering_id}/modules",
    response_model=ModuleOut,
    status_code=status.HTTP_201_CREATED,
    summary="کادر: ساخت ماژول",
    responses=_R,
)
async def create_module(
    offering_id: uuid.UUID, body: ModuleIn, svc: LearningServiceDep, _: EditDep
) -> ModuleOut:
    return ModuleOut.model_validate(await svc.create_module(offering_id, body.title_fa))


# ── کادر: چالش روزانه ──────────────────────────────────────────────────
@router.post(
    "/teach/offerings/{offering_id}/checkpoints",
    response_model=CheckpointOut,
    status_code=status.HTTP_201_CREATED,
    summary="کادر: ساخت چالش روزانه از سؤال‌های بانک (مفاهیم انتخابی)",
    responses={**_R, 409: {"model": ErrorResponse}},
)
async def create_checkpoint(
    offering_id: uuid.UUID,
    body: CheckpointIn,
    quizzes: QuizServiceDep,
    session: SessionDep,
    user: QuizStaffDep,
) -> CheckpointOut:
    quiz = await quizzes.create_checkpoint(
        offering_id=offering_id,
        created_by=user.id,
        title_fa=body.title_fa,
        lesson_id=body.lesson_id,
        concept_ids=body.concept_ids,
        draw_count=body.draw_count,
        opens_at=body.opens_at,
        closes_at=body.closes_at,
        duration_min=body.duration_min,
        publish=body.publish,
    )
    pool = await session.scalar(
        select(func.count()).select_from(QuizQuestion).where(QuizQuestion.quiz_id == quiz.id)
    )
    return CheckpointOut(
        id=quiz.id,
        title_fa=quiz.title_fa,
        status=quiz.status,
        draw_count=quiz.draw_count,
        pool_size=int(pool or 0),
    )


# ── شایستگی و مفهوم ────────────────────────────────────────────────────
@router.get(
    "/competencies",
    response_model=list[CompetencyOut],
    summary="شایستگی‌ها با مفاهیم (کادر)",
    responses=_R,
)
async def competencies(svc: LearningServiceDep, user: CurrentUserDep) -> list[CompetencyOut]:
    _require_staff(user)
    return [
        CompetencyOut(
            id=comp.id,
            code=comp.code,
            title_fa=comp.title_fa,
            domain=comp.domain,
            concepts=[ConceptOut.model_validate(c) for c in concepts],
        )
        for comp, concepts in await svc.competencies()
    ]


@router.post(
    "/competencies",
    response_model=CompetencyOut,
    status_code=status.HTTP_201_CREATED,
    summary="ساخت شایستگی (کادر)",
    responses={**_R, 409: {"model": ErrorResponse}},
)
async def create_competency(
    body: CompetencyIn, svc: LearningServiceDep, user: CurrentUserDep
) -> CompetencyOut:
    _require_staff(user)
    comp = await svc.create_competency(body.code, body.title_fa, body.domain)
    return CompetencyOut(
        id=comp.id, code=comp.code, title_fa=comp.title_fa, domain=comp.domain, concepts=[]
    )


@router.post(
    "/competencies/{competency_id}/concepts",
    response_model=ConceptOut,
    status_code=status.HTTP_201_CREATED,
    summary="ساخت مفهوم زیر یک شایستگی (کادر)",
    responses={**_R, 409: {"model": ErrorResponse}},
)
async def create_concept(
    competency_id: uuid.UUID, body: ConceptIn, svc: LearningServiceDep, user: CurrentUserDep
) -> ConceptOut:
    _require_staff(user)
    concept = await svc.create_concept(competency_id, body.code, body.title_fa)
    return ConceptOut.model_validate(concept)
