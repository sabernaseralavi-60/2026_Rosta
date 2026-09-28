"""ورود دانشجوی درس با موبایل + شمارهٔ دانشجویی — ADR-0035.

| مسیر | توضیح |
|------|-------|
| `POST /public/roster/lookup` | موبایل + شمارهٔ دانشجویی ⇒ «شما فلانی هستید؟» |
| `POST /public/roster/confirm` | تأیید هویت ⇒ کد به ایمیل ثبت‌شدهٔ فهرست |
| `POST /public/roster/complete` | کد + رمز تازه ⇒ حساب و توکن |

هر سه بی‌ورودند. شمارهٔ دانشجویی رمز نیست و دنبال‌کردنِ فقط آن، حسابی نمی‌دهد.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Response

from silp.routers.deps import AuthServiceDep, ClientIPDep, RosterServiceDep, UserAgentDep
from silp.routers.v1.auth import _login_response
from silp.schemas.common import ErrorResponse
from silp.schemas.roster import (
    RosterCompleteIn,
    RosterCompleteOut,
    RosterConfirmIn,
    RosterConfirmOut,
    RosterLookupIn,
    RosterLookupOut,
)

router = APIRouter(prefix="/public/roster", tags=["public"])

_RESPONSES: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
    429: {"model": ErrorResponse},
}


@router.post(
    "/lookup",
    response_model=RosterLookupOut,
    summary="پیدا کردن ردیف دانشجو با موبایل و شمارهٔ دانشجویی",
    responses=_RESPONSES,
)
async def lookup(
    payload: RosterLookupIn, roster: RosterServiceDep, ip: ClientIPDep, response: Response
) -> RosterLookupOut:
    response.headers["Cache-Control"] = "no-store"
    found = await roster.lookup(mobile=payload.mobile, student_no=payload.student_no, ip=ip)
    return RosterLookupOut(
        claim_id=found.claim_id, display_name=found.display_name, has_email=found.has_email
    )


@router.post(
    "/confirm",
    response_model=RosterConfirmOut,
    summary="تأیید «من همین‌ام» و ارسال کد به ایمیل ثبت‌شده",
    responses=_RESPONSES,
)
async def confirm(
    payload: RosterConfirmIn, roster: RosterServiceDep, response: Response
) -> RosterConfirmOut:
    response.headers["Cache-Control"] = "no-store"
    result = await roster.confirm(claim_id=payload.claim_id, accept=payload.accept)
    return RosterConfirmOut(
        cancelled=result.cancelled,
        masked_email=result.masked_email,
        expires_in=result.expires_in,
        resend_after=result.resend_after,
    )


@router.post(
    "/complete",
    response_model=RosterCompleteOut,
    summary="کد ایمیل + رمز تازه ⇒ حساب، ثبت‌نام در درس‌ها و توکن",
    responses=_RESPONSES,
)
async def complete(
    payload: RosterCompleteIn,
    roster: RosterServiceDep,
    auth: AuthServiceDep,
    ip: ClientIPDep,
    user_agent: UserAgentDep,
    response: Response,
) -> RosterCompleteOut:
    response.headers["Cache-Control"] = "no-store"
    done = await roster.complete(
        claim_id=payload.claim_id, code=payload.code, password=payload.password
    )
    login = await auth.issue_login(
        done.user, is_new_user=done.is_new_user, user_agent=user_agent, ip_address=ip
    )
    return RosterCompleteOut(
        **_login_response(login).model_dump(),
        is_new_user=done.is_new_user,
        courses=done.courses,
    )


__all__ = ["router"]
