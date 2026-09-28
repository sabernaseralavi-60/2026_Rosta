"""مسیرهای عمومی «طرح مسئله / نیاز» و «همکاری با ما» — ADR-0030.

| مسیر | توضیح |
|------|-------|
| `POST /public/intake` | مسئله یا نیاز؛ بی‌ورود |
| `POST /public/collaboration` | درخواست همکاری؛ بی‌ورود |

هر دو `201` با کد پیگیری برمی‌گردانند. سهمیهٔ IP و راه تماس در سرویس است.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Response, status

from silp.routers.deps import ClientIPDep, SessionDep
from silp.schemas.common import ErrorResponse
from silp.schemas.intake import CollaborationIn, IntakeIn, SubmissionOut
from silp.services.intake_service import DECOY_CODE, IntakeService, Submission

router = APIRouter(prefix="/public", tags=["public"])

_RESPONSES: dict[int | str, dict[str, Any]] = {429: {"model": ErrorResponse}}


def _out(submission: Submission | None, *, collaboration: bool) -> SubmissionOut:
    what = "درخواست همکاری شما" if collaboration else "مسئلهٔ شما"
    code = (
        submission.request.tracking_code
        if submission
        else ("C-0000" if collaboration else DECOY_CODE)
    )
    return SubmissionOut(
        tracking_code=code,
        person_code=submission.person_code if submission else None,
        account_linked=submission.account_linked if submission else False,
        message=f"{what} ثبت شد. کد پیگیری: {code}. به‌زودی با شما تماس می‌گیریم.",
    )


@router.post(
    "/intake",
    status_code=status.HTTP_201_CREATED,
    response_model=SubmissionOut,
    summary="ثبت مسئله یا نیاز",
    responses=_RESPONSES,
)
async def submit_intake(
    payload: IntakeIn, session: SessionDep, ip: ClientIPDep, response: Response
) -> SubmissionOut:
    submission = await IntakeService(session).submit_intake(payload, ip=ip)
    response.headers["Cache-Control"] = "no-store"
    return _out(submission, collaboration=False)


@router.post(
    "/collaboration",
    status_code=status.HTTP_201_CREATED,
    response_model=SubmissionOut,
    summary="درخواست همکاری",
    responses=_RESPONSES,
)
async def submit_collaboration(
    payload: CollaborationIn, session: SessionDep, ip: ClientIPDep, response: Response
) -> SubmissionOut:
    submission = await IntakeService(session).submit_collaboration(payload, ip=ip)
    response.headers["Cache-Control"] = "no-store"
    return _out(submission, collaboration=True)


__all__ = ["router"]
