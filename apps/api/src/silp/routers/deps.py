"""وابستگی‌های FastAPI — احراز هویت، مجوز، و ساخت سرویس‌ها.

§6.4: `require(permission, scope)` تنها راه بررسی دسترسی در لایهٔ مسیر است.
هیچ مسیری نباید `if user.role == "ADMIN"` بنویسد.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from silp.core.config import Settings, get_settings
from silp.core.exceptions import (
    AccountSuspended,
    InvalidToken,
    PermissionDenied,
    Unauthenticated,
)
from silp.core.middleware import UNSAFE_METHODS, bind_user, client_ip
from silp.core.permissions import CurrentUser, Permission, Role, RoleGrant
from silp.core.security import decode_access_token
from silp.db.session import get_session
from silp.integrations.sms import SMSSender, get_sms_sender
from silp.models.identity import User
from silp.services import authz
from silp.services.auth_service import AuthService
from silp.services.otp_service import OTPService
from silp.services.profile_service import ProfileService
from silp.services.token_service import TokenService

# auto_error=False تا نبود هدر، خطای انگلیسی FastAPI ندهد و از مسیر
# استاندارد خطای فارسی ما عبور کند.
bearer_scheme = HTTPBearer(auto_error=False, scheme_name="Bearer")

SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
CredentialsDep = Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)]

# resolver قلمرو: از مسیر یا بدنهٔ درخواست، شناسهٔ قلمرو را استخراج می‌کند.
ScopeResolver = Callable[[Request], Awaitable[uuid.UUID | None]]


def get_sms(settings: SettingsDep) -> SMSSender:
    return get_sms_sender(settings)


def get_otp_service(
    session: SessionDep,
    settings: SettingsDep,
    sms: Annotated[SMSSender, Depends(get_sms)],
) -> OTPService:
    return OTPService(session, settings, sms)


def get_token_service(session: SessionDep, settings: SettingsDep) -> TokenService:
    return TokenService(session, settings)


def get_auth_service(
    session: SessionDep,
    settings: SettingsDep,
    otp: Annotated[OTPService, Depends(get_otp_service)],
    tokens: Annotated[TokenService, Depends(get_token_service)],
) -> AuthService:
    return AuthService(session, settings, otp, tokens)


def get_profile_service(session: SessionDep) -> ProfileService:
    return ProfileService(session)


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
ProfileServiceDep = Annotated[ProfileService, Depends(get_profile_service)]
TokenServiceDep = Annotated[TokenService, Depends(get_token_service)]
OTPServiceDep = Annotated[OTPService, Depends(get_otp_service)]


async def get_current_user(
    request: Request,
    credentials: CredentialsDep,
    session: SessionDep,
    settings: SettingsDep,
) -> CurrentUser:
    """کاربر احرازشده از روی access token.

    نقش‌ها از دیتابیس (با کش ۶۰ ثانیه‌ای) خوانده می‌شوند، نه از توکن: توکن
    تا ۱۵ دقیقه کهنه است و نقش گرفته‌شده نباید ۱۵ دقیقه زنده بماند.
    """
    if credentials is None or not credentials.credentials:
        raise Unauthenticated

    claims = decode_access_token(settings, credentials.credentials)

    try:
        user_id = uuid.UUID(str(claims["sub"]))
        session_id = uuid.UUID(str(claims["sid"]))
    except (KeyError, ValueError) as exc:
        raise InvalidToken from exc

    user = await session.get(User, user_id)
    if user is None or user.deleted_at is not None:
        raise InvalidToken
    if user.status != "ACTIVE":
        raise AccountSuspended

    impersonated_by: uuid.UUID | None = None
    if act_as := claims.get("act_as"):
        # §6.5 — جعل هویت فقط خواندنی است.
        if request.method in UNSAFE_METHODS:
            raise PermissionDenied(
                "در حالت مشاهده به‌عنوان کاربر دیگر، تغییر داده ممکن نیست.",
                code="IMPERSONATION_READ_ONLY",
            )
        impersonated_by = uuid.UUID(str(act_as))

    grants = await authz.get_grants(session, user_id)
    bind_user(user_id)
    request.state.user_id = user_id

    return CurrentUser(
        id=user_id,
        session_id=session_id,
        grants=grants,
        impersonated_by=impersonated_by,
    )


async def get_optional_user(
    request: Request,
    credentials: CredentialsDep,
    session: SessionDep,
    settings: SettingsDep,
) -> CurrentUser | None:
    """برای مسیرهای عمومی که اگر کاربر وارد باشد، بیشتر نشان می‌دهند."""
    if credentials is None:
        return None
    try:
        return await get_current_user(request, credentials, session, settings)
    except (Unauthenticated, AccountSuspended):
        return None


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]
OptionalUserDep = Annotated[CurrentUser | None, Depends(get_optional_user)]


def require(
    permission: Permission,
    scope: ScopeResolver | None = None,
) -> Callable[..., Awaitable[CurrentUser]]:
    """وابستگی FastAPI که مجوز را در قلمرو مشخص بررسی می‌کند — §6.4.

    نمونهٔ استفاده::

        @router.post("/offerings/{offering_id}/weeks/{n}/publish")
        async def publish_week(
            user: CurrentUser = Depends(
                require(Permission.COURSE_WEEK_PUBLISH, scope=offering_from_path)
            ),
        ): ...
    """

    async def dependency(
        request: Request,
        user: CurrentUserDep,
        session: SessionDep,
    ) -> CurrentUser:
        scope_id = await scope(request) if scope else None
        if not await authz.has_permission(session, user, permission, scope_id):
            raise PermissionDenied(permission=permission.value)
        return user

    return dependency


def require_role(role: Role) -> Callable[..., Awaitable[CurrentUser]]:
    """فقط برای مسیرهای مدیریتی که مجوز نام‌دار ندارند (مثل پنل ادمین).

    استفاده از این تابع در مسیرهای دامنه‌ای، نقض قاعدهٔ ۱ §6.4 است.
    """

    async def dependency(user: CurrentUserDep) -> CurrentUser:
        if not user.has_role(role):
            raise PermissionDenied
        return user

    return dependency


# ── resolverهای قلمرو ──────────────────────────────────────────────────
def path_uuid(param: str) -> ScopeResolver:
    """استخراج شناسهٔ قلمرو از پارامتر مسیر."""

    async def resolver(request: Request) -> uuid.UUID | None:
        raw = request.path_params.get(param)
        if raw is None:
            return None
        try:
            return uuid.UUID(str(raw))
        except ValueError:
            return None

    return resolver


# ── اطلاعات درخواست ────────────────────────────────────────────────────
def get_client_ip(request: Request) -> str:
    return client_ip(request)


def get_user_agent(request: Request) -> str | None:
    return request.headers.get("User-Agent")


ClientIPDep = Annotated[str, Depends(get_client_ip)]
UserAgentDep = Annotated[str | None, Depends(get_user_agent)]

__all__ = [
    "AuthServiceDep",
    "ClientIPDep",
    "CurrentUserDep",
    "OTPServiceDep",
    "OptionalUserDep",
    "ProfileServiceDep",
    "RoleGrant",
    "SessionDep",
    "SettingsDep",
    "TokenServiceDep",
    "UserAgentDep",
    "get_current_user",
    "path_uuid",
    "require",
    "require_role",
]
