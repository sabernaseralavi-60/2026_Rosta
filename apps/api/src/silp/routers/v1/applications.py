"""مسیر /applications — تصمیم و انصراف. §5.7، §7.5.

مسیر **ارسال** درخواست زیر `/projects/{id}/applications` است؛ اینجا فقط
کارهایی است که روی یک درخواست موجود انجام می‌شود.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status

from silp.core.permissions import CurrentUser, Permission
from silp.routers.deps import (
    ApplicationServiceDep,
    CurrentUserDep,
    SessionDep,
    project_of_application,
    require,
)
from silp.routers.v1.projects import applications_out, project_summary_of
from silp.schemas.common import ErrorResponse
from silp.schemas.project import (
    AlternativeOut,
    ApplicationOut,
    DecisionIn,
    DecisionOut,
    reasons_of,
)

router = APIRouter(prefix="/applications", tags=["projects"])


@router.get(
    "/mine",
    response_model=list[ApplicationOut],
    summary="درخواست‌های من",
)
async def my_applications(
    current: CurrentUserDep,
    applications: ApplicationServiceDep,
    session: SessionDep,
) -> list[ApplicationOut]:
    rows = await applications.mine(current.id)
    return await applications_out(session, rows)


@router.post(
    "/{application_id}/decide",
    response_model=DecisionOut,
    summary="تصمیم دربارهٔ درخواست",
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse, "description": "PROJECT_CAPACITY_FULL"},
    },
)
async def decide_application(
    application_id: uuid.UUID,
    payload: DecisionIn,
    applications: ApplicationServiceDep,
    session: SessionDep,
    current: Annotated[
        CurrentUser,
        Depends(require(Permission.PROJECT_APPLICATION_DECIDE, scope=project_of_application)),
    ],
) -> DecisionOut:
    """§7.5 — پاسخ رد **همیشه** با سه پروژهٔ جایگزین برمی‌گردد.

    جایگزین‌ها از موتور توصیه‌گر می‌آیند و همان‌جا در پاسخ می‌نشینند تا
    کلاینت مجبور نشود یک درخواست دیگر بزند؛ «رد شدم» و «مسیر بهتری پیدا
    کردم» نباید به تأخیر شبکه گره بخورد.
    """
    decision = await applications.decide(
        application_id=application_id,
        actor=current,
        decision=payload.decision,
        note=payload.note,
    )
    presented = await applications_out(session, [decision.application])
    return DecisionOut(
        application=presented[0],
        alternatives=[
            AlternativeOut(
                project=project_summary_of(match.project),
                match_score=round(match.score, 1),
                reasons=reasons_of(match),
            )
            for match in decision.alternatives
        ],
    )


@router.delete(
    "/{application_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="انصراف از درخواست",
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
async def withdraw_application(
    application_id: uuid.UUID,
    current: CurrentUserDep,
    applications: ApplicationServiceDep,
) -> None:
    await applications.withdraw(application_id=application_id, actor=current)


__all__ = ["router"]
