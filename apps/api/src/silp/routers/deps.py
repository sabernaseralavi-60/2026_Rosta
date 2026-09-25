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
from sqlalchemy import text as sa_text
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
from silp.domain import audit
from silp.integrations.sms import SMSSender, get_sms_sender
from silp.integrations.storage import StorageBackend
from silp.integrations.storage import get_storage as storage_for
from silp.models.identity import User
from silp.services import authz
from silp.services.appeal_service import AppealService
from silp.services.application_service import ApplicationService
from silp.services.attempt_service import AttemptService
from silp.services.audit_service import AuditService
from silp.services.auth_service import AuthService
from silp.services.course_service import CourseService
from silp.services.delivery_service import DeliveryService
from silp.services.enrollment_service import EnrollmentService
from silp.services.entitlement_service import EntitlementService
from silp.services.file_service import FileService
from silp.services.grading_service import GradingService
from silp.services.otp_service import OTPService
from silp.services.peer_evaluation_service import PeerEvaluationService
from silp.services.profile_service import ProfileService
from silp.services.progress_service import ProgressService
from silp.services.project_service import ProjectService
from silp.services.quiz_service import QuizService
from silp.services.reflection_service import ReflectionService
from silp.services.subscription_service import SubscriptionService
from silp.services.teaching_service import TeachingService
from silp.services.token_service import TokenService
from silp.services.workspace_service import WorkspaceService

# auto_error=False تا نبود هدر، خطای انگلیسی FastAPI ندهد و از مسیر
# استاندارد خطای فارسی ما عبور کند.
bearer_scheme = HTTPBearer(auto_error=False, scheme_name="Bearer")

SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
CredentialsDep = Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)]

# resolver قلمرو: شناسهٔ قلمرو را از مسیر درخواست پیدا می‌کند.
#
# نشست درخواست را هم می‌گیرد، نه فقط `Request`: قلمرو یک تحویل‌دادنی
# با یک کوئری به دست می‌آید و آن کوئری باید روی **همان** نشست اجرا
# شود، وگرنه ردیف‌های نوشته‌شده و هنوز commit‌نشدهٔ همین درخواست را
# نمی‌بیند.
ScopeResolver = Callable[[Request, AsyncSession], Awaitable[uuid.UUID | None]]


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


def get_storage(settings: SettingsDep) -> StorageBackend:
    return storage_for(settings)


def get_file_service(
    session: SessionDep,
    settings: SettingsDep,
    storage: Annotated[StorageBackend, Depends(get_storage)],
) -> FileService:
    return FileService(session, settings, storage)


def get_project_service(session: SessionDep) -> ProjectService:
    return ProjectService(session)


def get_application_service(session: SessionDep) -> ApplicationService:
    return ApplicationService(session)


def get_delivery_service(session: SessionDep) -> DeliveryService:
    return DeliveryService(session)


def get_workspace_service(session: SessionDep) -> WorkspaceService:
    return WorkspaceService(session)


# ── آموزش (M3) ─────────────────────────────────────────────────────────
def get_entitlement_service(session: SessionDep) -> EntitlementService:
    return EntitlementService(session)


def get_course_service(
    session: SessionDep,
    entitlements: Annotated[EntitlementService, Depends(get_entitlement_service)],
) -> CourseService:
    return CourseService(session, entitlements)


def get_enrollment_service(session: SessionDep) -> EnrollmentService:
    return EnrollmentService(session)


def get_progress_service(session: SessionDep) -> ProgressService:
    return ProgressService(session)


def get_teaching_service(session: SessionDep) -> TeachingService:
    return TeachingService(session)


def get_quiz_service(session: SessionDep) -> QuizService:
    return QuizService(session)


def get_reflection_service(session: SessionDep) -> ReflectionService:
    return ReflectionService(session)


def get_peer_evaluation_service(session: SessionDep) -> PeerEvaluationService:
    return PeerEvaluationService(session)


def get_attempt_service(session: SessionDep) -> AttemptService:
    return AttemptService(session)


def get_grading_service(session: SessionDep) -> GradingService:
    return GradingService(session)


def get_appeal_service(session: SessionDep) -> AppealService:
    return AppealService(session)


def get_subscription_service(session: SessionDep) -> SubscriptionService:
    return SubscriptionService(session)


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
ProfileServiceDep = Annotated[ProfileService, Depends(get_profile_service)]
TokenServiceDep = Annotated[TokenService, Depends(get_token_service)]
OTPServiceDep = Annotated[OTPService, Depends(get_otp_service)]
FileServiceDep = Annotated[FileService, Depends(get_file_service)]
ProjectServiceDep = Annotated[ProjectService, Depends(get_project_service)]
ApplicationServiceDep = Annotated[ApplicationService, Depends(get_application_service)]
DeliveryServiceDep = Annotated[DeliveryService, Depends(get_delivery_service)]
WorkspaceServiceDep = Annotated[WorkspaceService, Depends(get_workspace_service)]
CourseServiceDep = Annotated[CourseService, Depends(get_course_service)]
EnrollmentServiceDep = Annotated[EnrollmentService, Depends(get_enrollment_service)]
EntitlementServiceDep = Annotated[EntitlementService, Depends(get_entitlement_service)]
ProgressServiceDep = Annotated[ProgressService, Depends(get_progress_service)]
TeachingServiceDep = Annotated[TeachingService, Depends(get_teaching_service)]
SubscriptionServiceDep = Annotated[SubscriptionService, Depends(get_subscription_service)]
QuizServiceDep = Annotated[QuizService, Depends(get_quiz_service)]
ReflectionServiceDep = Annotated[ReflectionService, Depends(get_reflection_service)]
PeerEvaluationServiceDep = Annotated[PeerEvaluationService, Depends(get_peer_evaluation_service)]
AttemptServiceDep = Annotated[AttemptService, Depends(get_attempt_service)]
GradingServiceDep = Annotated[GradingService, Depends(get_grading_service)]
AppealServiceDep = Annotated[AppealService, Depends(get_appeal_service)]


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
        try:
            impersonated_by = uuid.UUID(str(act_as))
        except ValueError as exc:
            raise InvalidToken from exc
        await _audit_impersonated_request(request, session, user_id, impersonated_by)

    grants = await authz.get_grants(session, user_id)
    bind_user(user_id)
    request.state.user_id = user_id

    return CurrentUser(
        id=user_id,
        session_id=session_id,
        grants=grants,
        impersonated_by=impersonated_by,
    )


async def _audit_impersonated_request(
    request: Request, session: AsyncSession, user_id: uuid.UUID, agent_id: uuid.UUID
) -> None:
    """§6.5 — «**هر درخواست** در `audit_logs` با `impersonated_by`».

    پشتیبانی که از توکن جعل هویت استفاده می‌کند باید هنوز فعال باشد و
    مجوزش را داشته باشد: توکن ۳۰ دقیقه زنده است و نقشِ گرفته‌شده نباید تا
    پایانش کار کند.

    ردیف همین‌جا commit می‌شود: درخواست جعل هویت همیشه خواندنی است و
    مسیرهای `GET` هرگز commit نمی‌زنند، پس بدون این، لاگ با بسته شدن نشست
    بی‌صدا برمی‌گشت.
    """
    agent = await session.get(User, agent_id)
    if agent is None or not agent.is_active:
        raise InvalidToken
    agent_grants = await authz.get_grants(session, agent_id)
    if not CurrentUser(id=agent_id, session_id=agent_id, grants=agent_grants).has_permission(
        Permission.IMPERSONATE
    ):
        raise InvalidToken
    route = getattr(request.scope.get("route"), "path", None)
    AuditService(session).stage(
        audit.IMPERSONATED_REQUEST,
        actor=CurrentUser(id=user_id, session_id=agent_id, impersonated_by=agent_id),
        entity_type="REQUEST",
        after={"method": request.method, "path": request.url.path, "route": route},
    )
    await session.commit()


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
        scope_id = await scope(request, session) if scope else None
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

    async def resolver(request: Request, session: AsyncSession) -> uuid.UUID | None:
        return _path_uuid_value(request, param)

    return resolver


def _path_uuid_value(request: Request, param: str) -> uuid.UUID | None:
    raw = request.path_params.get(param)
    if raw is None:
        return None
    try:
        return uuid.UUID(str(raw))
    except ValueError:
        return None


def _lookup_scope(sql: str, param: str) -> ScopeResolver:
    """قلمرو را از یک شناسهٔ وابسته در مسیر پیدا می‌کند.

    کوئری خام است تا وابستگی حلقوی `deps → service → deps` نسازد؛ فقط
    یک شناسه لازم است، نه یک موجودیت کامل.
    """
    statement = sa_text(sql)

    async def resolver(request: Request, session: AsyncSession) -> uuid.UUID | None:
        entity_id = _path_uuid_value(request, param)
        if entity_id is None:
            return None
        scope_id: uuid.UUID | None = await session.scalar(statement, {"id": entity_id})
        return scope_id

    return resolver


# نام قدیمی، برای خوانایی مسیرهای پروژه.
_lookup_project_scope = _lookup_scope


# قلمرو مجوزهای پروژه‌ای — §6.4. هر endpoint پروژه یکی از این‌ها را
# به `require(...)` می‌دهد تا «مدیر پروژهٔ الف» نتواند در پروژهٔ ب
# تصمیم بگیرد.
project_from_path = path_uuid("project_id")

project_of_application = _lookup_project_scope(
    "SELECT project_id FROM project_applications WHERE id = :id", "application_id"
)
project_of_milestone = _lookup_project_scope(
    "SELECT project_id FROM milestones WHERE id = :id", "milestone_id"
)
project_of_deliverable = _lookup_project_scope(
    "SELECT m.project_id FROM deliverables d"
    " JOIN milestones m ON m.id = d.milestone_id WHERE d.id = :id",
    "deliverable_id",
)


# قلمرو مجوزهای آموزشی — §6.4. «استاد ارائهٔ الف» نباید بتواند در
# ارائهٔ ب هفته منتشر کند یا حضور ثبت نماید.
offering_from_path = path_uuid("offering_id")

offering_of_week = _lookup_scope("SELECT offering_id FROM course_weeks WHERE id = :id", "week_id")
offering_of_resource = _lookup_scope(
    "SELECT w.offering_id FROM resources r"
    " JOIN course_weeks w ON w.id = r.week_id WHERE r.id = :id",
    "resource_id",
)
offering_of_enrollment = _lookup_scope(
    "SELECT offering_id FROM enrollments WHERE id = :id", "enrollment_id"
)

# قلمرو مجوزهای آزمون — §6.4. آزمون به ارائه تعلق دارد، پس قلمرو
# مجوزِ تصحیح و ابطال هم همان ارائه است (ADR-0010).
offering_of_quiz = _lookup_scope("SELECT offering_id FROM quizzes WHERE id = :id", "quiz_id")
offering_of_attempt = _lookup_scope(
    "SELECT q.offering_id FROM quiz_attempts a JOIN quizzes q ON q.id = a.quiz_id WHERE a.id = :id",
    "attempt_id",
)
offering_of_appeal = _lookup_scope(
    "SELECT q.offering_id FROM grade_appeals g"
    " JOIN quiz_attempts a ON a.id = g.attempt_id"
    " JOIN quizzes q ON q.id = a.quiz_id WHERE g.id = :id",
    "appeal_id",
)


# ── اطلاعات درخواست ────────────────────────────────────────────────────
def get_client_ip(request: Request) -> str:
    return client_ip(request)


def get_user_agent(request: Request) -> str | None:
    return request.headers.get("User-Agent")


ClientIPDep = Annotated[str, Depends(get_client_ip)]
UserAgentDep = Annotated[str | None, Depends(get_user_agent)]

__all__ = [
    "ApplicationServiceDep",
    "AuthServiceDep",
    "ClientIPDep",
    "CourseServiceDep",
    "CurrentUserDep",
    "DeliveryServiceDep",
    "EnrollmentServiceDep",
    "EntitlementServiceDep",
    "FileServiceDep",
    "OTPServiceDep",
    "OptionalUserDep",
    "PeerEvaluationServiceDep",
    "ProfileServiceDep",
    "ProgressServiceDep",
    "ProjectServiceDep",
    "ReflectionServiceDep",
    "RoleGrant",
    "SessionDep",
    "SettingsDep",
    "SubscriptionServiceDep",
    "TeachingServiceDep",
    "TokenServiceDep",
    "UserAgentDep",
    "WorkspaceServiceDep",
    "get_current_user",
    "offering_from_path",
    "offering_of_enrollment",
    "offering_of_resource",
    "offering_of_week",
    "path_uuid",
    "project_from_path",
    "project_of_application",
    "project_of_deliverable",
    "project_of_milestone",
    "require",
    "require_role",
]
