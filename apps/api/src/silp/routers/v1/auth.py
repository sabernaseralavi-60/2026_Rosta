"""مسیرهای احراز هویت — §5.2."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Response, status

from silp.core.exceptions import NotFound
from silp.domain.identity.normalize import detect_channel
from silp.routers.deps import (
    AuthServiceDep,
    ClientIPDep,
    CurrentUserDep,
    TokenServiceDep,
    UserAgentDep,
)
from silp.schemas.auth import (
    AuthUserOut,
    LoginOut,
    LogoutIn,
    OTPRequestIn,
    OTPRequestOut,
    OTPVerifyIn,
    PasswordLoginIn,
    RefreshIn,
    SessionOut,
    TokenPairOut,
)
from silp.schemas.common import ErrorResponse
from silp.services.auth_service import AuthenticatedUser
from silp.services.token_service import REVOKED_LOGOUT

router = APIRouter(
    prefix="/auth",
    tags=["auth"],
    responses={
        401: {"model": ErrorResponse, "description": "احراز هویت نشده"},
        429: {"model": ErrorResponse, "description": "محدودیت نرخ"},
    },
)


def _login_response(result: AuthenticatedUser) -> LoginOut:
    user = result.user
    return LoginOut(
        access_token=result.tokens.access_token,
        refresh_token=result.tokens.refresh_token,
        token_type=result.tokens.token_type,
        expires_in=result.tokens.expires_in,
        user=AuthUserOut(
            id=user.id,
            display_name=None,  # نیمرخ در M1 اضافه می‌شود
            username=user.username,
            roles=result.roles,
            onboarding_state=result.onboarding.state.value,
        ),
    )


@router.post(
    "/otp/request",
    response_model=OTPRequestOut,
    summary="درخواست کد یک‌بارمصرف",
)
async def request_otp(
    payload: OTPRequestIn,
    auth: AuthServiceDep,
    ip: ClientIPDep,
) -> OTPRequestOut:
    """FR-AUTH-01 — کد شش‌رقمی با اعتبار ۱۲۰ ثانیه.

    کانال اگر تصریح نشده باشد از شکل ورودی حدس زده می‌شود، تا کاربر
    مجبور به انتخاب نباشد.
    """
    channel = payload.channel or detect_channel(payload.destination)
    issued = await auth.request_otp(
        destination=payload.destination,
        channel=channel,
        purpose=payload.purpose,
        ip_address=ip,
    )
    return OTPRequestOut.model_validate(issued, from_attributes=True)


@router.post(
    "/otp/verify",
    response_model=LoginOut,
    summary="تأیید کد و دریافت توکن",
)
async def verify_otp(
    payload: OTPVerifyIn,
    auth: AuthServiceDep,
    ip: ClientIPDep,
    user_agent: UserAgentDep,
) -> LoginOut:
    """FR-AUTH-01 — در صورت نبود حساب، ساخته می‌شود و نقش STUDENT می‌گیرد."""
    result = await auth.verify_otp_and_login(
        challenge_id=str(payload.challenge_id),
        code=payload.code,
        user_agent=user_agent,
        ip_address=ip,
    )
    return _login_response(result)


@router.post("/login", response_model=LoginOut, summary="ورود با رمز عبور")
async def login(
    payload: PasswordLoginIn,
    auth: AuthServiceDep,
    ip: ClientIPDep,
    user_agent: UserAgentDep,
) -> LoginOut:
    """FR-AUTH-02 — پیام خطا هرگز افشا نمی‌کند که کاربر وجود دارد یا نه."""
    result = await auth.login_with_password(
        identifier=payload.identifier,
        password=payload.password,
        user_agent=user_agent,
        ip_address=ip,
    )
    return _login_response(result)


@router.post("/refresh", response_model=TokenPairOut, summary="تمدید توکن")
async def refresh(
    payload: RefreshIn,
    auth: AuthServiceDep,
    ip: ClientIPDep,
    user_agent: UserAgentDep,
) -> TokenPairOut:
    """FR-AUTH-03 — چرخش اجباری. توکن قدیمی بلافاصله باطل می‌شود.

    استفادهٔ دوباره از یک توکن باطل‌شده ⇒ `401 TOKEN_REUSE_DETECTED` و
    ابطال کل خانواده.
    """
    pair = await auth.refresh(
        raw_refresh=payload.refresh_token,
        user_agent=user_agent,
        ip_address=ip,
    )
    return TokenPairOut(
        access_token=pair.access_token,
        refresh_token=pair.refresh_token,
        token_type=pair.token_type,
        expires_in=pair.expires_in,
    )


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="خروج از نشست جاری",
)
async def logout(payload: LogoutIn, tokens: TokenServiceDep) -> Response:
    """خروج بی‌اثر در تکرار است: خروج از نشستی که وجود ندارد هم ۲۰۴ می‌دهد."""
    await tokens.revoke(raw_refresh=payload.refresh_token, reason=REVOKED_LOGOUT)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/sessions",
    response_model=list[SessionOut],
    summary="فهرست نشست‌های فعال",
)
async def list_sessions(user: CurrentUserDep, tokens: TokenServiceDep) -> list[SessionOut]:
    """FR-AUTH-03 — کاربر باید بتواند دستگاه‌های واردشده را ببیند."""
    records = await tokens.active_sessions(user.id)
    return [
        SessionOut(
            id=record.id,
            user_agent=record.user_agent,
            ip_address=str(record.ip_address) if record.ip_address else None,
            created_at=record.created_at,
            expires_at=record.expires_at,
            is_current=record.id == user.session_id,
        )
        for record in records
    ]


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="قطع یک نشست",
)
async def revoke_session(
    session_id: uuid.UUID,
    user: CurrentUserDep,
    tokens: TokenServiceDep,
) -> Response:
    """۴۰۴ برای نشست کاربر دیگر — وجود آن نباید افشا شود (§6.4 قاعدهٔ ۴)."""
    revoked = await tokens.revoke_session(user_id=user.id, session_id=session_id)
    if not revoked:
        raise NotFound("این نشست پیدا نشد.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["router"]
