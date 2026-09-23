"""پنل مدیریت — §5.12، FR-ADM-01/02، §6.5، M7-12، ADR-0017.

| مسیر | مجوز |
|------|------|
| `GET /admin/metrics` | `admin.metrics.view` |
| `GET /admin/users`، `GET /admin/users/{id}` | `user.view_all` |
| `PATCH /admin/users/{id}` | `user.deactivate` — تعلیق و فعال‌سازی، با دلیل |
| `GET /admin/roles` | `user.role.assign` — نقش‌های قابل اعطا |
| `POST /admin/users/{id}/roles` | `user.role.assign` |
| `DELETE /admin/users/{id}/roles/{code}` | `user.role.assign` |
| `POST /admin/users/{id}/impersonate` | `user.impersonate` — توکن فقط‌خواندنی ۳۰ دقیقه‌ای |
| `POST /admin/impersonation/end` | `user.impersonate` |
| `GET /admin/audit`، `GET /admin/audit/export` | `audit.log.view` |

قواعد امتیاز (`/admin/point-rules…`) در `gamification.py` و صف ارسال و
الگوها (`/admin/outbox…`، `/admin/message-templates…`) در
`notifications.py` مانده‌اند؛ پنل وب هر سه را کنار هم نشان می‌دهد.
"""

from __future__ import annotations

import csv
import io
import json
import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from silp.core.exceptions import ValidationFailed
from silp.core.permissions import ROLE_TITLE_FA, CurrentUser, Permission, Role
from silp.core.security import mask_email, mask_mobile
from silp.domain import audit as audit_codes
from silp.models.admin import AuditLog
from silp.models.identity import USER_STATUSES
from silp.routers.deps import SessionDep, SettingsDep, require
from silp.schemas.admin import (
    AdminUserDetailOut,
    AdminUserOut,
    AdminUserPage,
    AuditEntryOut,
    AuditPageOut,
    ImpersonationEndIn,
    ImpersonationOut,
    MetricsOut,
    RoleGrantAdminOut,
    RoleGrantIn,
    RoleOptionOut,
    UserStatusIn,
)
from silp.schemas.common import ErrorResponse, PageParams
from silp.services import authz
from silp.services.admin_service import (
    AdminService,
    UserFilters,
    grantable_roles,
    scopes_for,
)
from silp.services.audit_service import AuditFilters, AuditService
from silp.services.directory import display_names, name_of
from silp.services.points_service import PointsService

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    responses={
        401: {"model": ErrorResponse, "description": "احراز هویت نشده"},
        403: {"model": ErrorResponse, "description": "بدون مجوز"},
    },
)


# ── تبدیل‌ها ───────────────────────────────────────────────────────────
async def _can_view_contact(session: AsyncSession, actor: CurrentUser) -> bool:
    return await authz.has_permission(session, actor, Permission.PROFILE_VIEW_CONTACT)


def _full_name(profile: object | None) -> str | None:
    if profile is None:
        return None
    name = getattr(profile, "public_name", None)
    return str(name) if name else None


async def audit_out(session: AsyncSession, rows: list[AuditLog]) -> list[AuditEntryOut]:
    names = await display_names(
        session, [r.actor_id for r in rows] + [r.impersonated_by for r in rows]
    )
    return [
        AuditEntryOut(
            id=r.id,
            action=r.action,
            action_fa=audit_codes.title_of(r.action),
            entity_type=r.entity_type,
            entity_type_fa=audit_codes.ENTITY_TITLE_FA.get(r.entity_type, r.entity_type),
            entity_id=r.entity_id,
            actor_id=r.actor_id,
            actor_name=name_of(names, r.actor_id),
            impersonated_by=r.impersonated_by,
            impersonator_name=name_of(names, r.impersonated_by),
            before=r.before,
            after=r.after,
            ip_address=str(r.ip_address) if r.ip_address else None,
            user_agent=r.user_agent,
            created_at=r.created_at,
        )
        for r in rows
    ]


# ── شاخص‌های کلان ──────────────────────────────────────────────────────
@router.get("/metrics", response_model=MetricsOut, summary="شاخص‌های کلان سامانه")
async def metrics(
    session: SessionDep,
    _: Annotated[CurrentUser, Depends(require(Permission.ADMIN_METRICS_VIEW))],
) -> MetricsOut:
    return MetricsOut.model_validate(await AdminService(session).metrics())


# ── کاربران ────────────────────────────────────────────────────────────
@router.get("/users", response_model=AdminUserPage, summary="جستجوی کاربران")
async def list_users(
    session: SessionDep,
    actor: Annotated[CurrentUser, Depends(require(Permission.USER_VIEW_ALL))],
    q: Annotated[
        str | None, Query(max_length=100, description="نام، نام کاربری، موبایل یا ایمیل")
    ] = None,
    role: Annotated[str | None, Query(max_length=30)] = None,
    status: Annotated[str | None, Query(max_length=20)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> AdminUserPage:
    if status and status not in USER_STATUSES:
        raise ValidationFailed("وضعیت ناشناخته است.")
    params = PageParams(page=page, page_size=page_size)
    service = AdminService(session)
    rows, total = await service.users(
        UserFilters(q=q, role=role, status=status), offset=params.offset, limit=params.page_size
    )
    roles = await service.stored_role_codes([u.id for u, _ in rows])
    full_contact = await _can_view_contact(session, actor)
    items = [
        AdminUserOut(
            id=user.id,
            name=_full_name(profile),
            username=user.username,
            mobile=user.mobile if full_contact else mask_mobile(user.mobile),
            email=user.email if full_contact else mask_email(user.email),
            status=user.status,
            roles=roles.get(user.id, []),
            is_public=bool(profile and profile.is_public),
            created_at=user.created_at,
            last_login_at=user.last_login_at,
        )
        for user, profile in rows
    ]
    return AdminUserPage(
        items=items,
        total=total,
        page=params.page,
        page_size=params.page_size,
        has_next=params.page * params.page_size < total,
    )


async def _user_detail(
    session: AsyncSession, user_id: uuid.UUID, actor: CurrentUser
) -> AdminUserDetailOut:
    service = AdminService(session)
    user, profile = await service.get_user(user_id)
    grants = await service.grants(user_id)
    labels = await service.offering_labels(
        [g.scope_id for g in grants if g.scope_type == "OFFERING" and g.scope_id]
    )
    granters = await display_names(session, [g.granted_by for g in grants])
    effective = await authz.load_grants(session, user_id)
    stored_codes = {g.role_code for g in grants}
    derived = sorted({g.role.value for g in effective} - stored_codes)
    counts = await service.user_counts(user_id)
    level = (await PointsService(session).summary(user_id)).level
    recent, _ = await AuditService(session).page(
        AuditFilters(subject_user_id=user_id), before=None, limit=10
    )
    blocked = await service.impersonation_block(user, actor)
    can_impersonate = blocked is None and await authz.has_permission(
        session, actor, Permission.IMPERSONATE
    )
    full_contact = await _can_view_contact(session, actor)
    return AdminUserDetailOut(
        id=user.id,
        name=_full_name(profile),
        username=user.username,
        mobile=user.mobile if full_contact else mask_mobile(user.mobile),
        email=user.email if full_contact else mask_email(user.email),
        status=user.status,
        roles=sorted(stored_codes),
        is_public=bool(profile and profile.is_public),
        created_at=user.created_at,
        last_login_at=user.last_login_at,
        grants=[
            RoleGrantAdminOut(
                code=g.role_code,
                title_fa=ROLE_TITLE_FA.get(Role(g.role_code), g.role_code)
                if g.role_code in Role.__members__
                else g.role_code,
                scope_type=g.scope_type,
                scope_id=g.scope_id,
                scope_label=labels.get(g.scope_id) if g.scope_id else None,
                granted_by_name=name_of(granters, g.granted_by),
                granted_at=g.granted_at,
                expires_at=g.expires_at,
            )
            for g in grants
        ],
        derived_roles=derived,
        points_total=int(level.total),
        level=level.level,
        recent_audit=await audit_out(session, recent),
        can_impersonate=can_impersonate,
        impersonation_blocked_reason=blocked,
        **counts,
    )


@router.get(
    "/users/{user_id}",
    response_model=AdminUserDetailOut,
    summary="جزئیات یک کاربر",
    responses={404: {"model": ErrorResponse}},
)
async def get_user(
    user_id: uuid.UUID,
    session: SessionDep,
    actor: Annotated[CurrentUser, Depends(require(Permission.USER_VIEW_ALL))],
) -> AdminUserDetailOut:
    return await _user_detail(session, user_id, actor)


@router.patch(
    "/users/{user_id}",
    response_model=AdminUserDetailOut,
    summary="تعلیق یا فعال‌سازی حساب",
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
async def set_user_status(
    user_id: uuid.UUID,
    payload: UserStatusIn,
    session: SessionDep,
    actor: Annotated[CurrentUser, Depends(require(Permission.USER_DEACTIVATE))],
) -> AdminUserDetailOut:
    """«غیرفعال‌سازی حساب (نه حذف)» — حذف فیزیکی از هیچ مسیری ممکن نیست (§6.3)."""
    await AdminService(session).set_status(
        user_id=user_id, status=payload.status, reason=payload.reason, actor=actor
    )
    return await _user_detail(session, user_id, actor)


# ── نقش‌ها ─────────────────────────────────────────────────────────────
@router.get("/roles", response_model=list[RoleOptionOut], summary="نقش‌های قابل اعطا")
async def role_options(
    _: Annotated[CurrentUser, Depends(require(Permission.USER_ROLE_ASSIGN))],
) -> list[RoleOptionOut]:
    return [
        RoleOptionOut(code=role.value, title_fa=ROLE_TITLE_FA[role], scopes=scopes_for(role))
        for role in grantable_roles()
    ]


@router.post(
    "/users/{user_id}/roles",
    response_model=AdminUserDetailOut,
    status_code=201,
    summary="اعطای نقش",
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
async def grant_role(
    user_id: uuid.UUID,
    payload: RoleGrantIn,
    session: SessionDep,
    actor: Annotated[CurrentUser, Depends(require(Permission.USER_ROLE_ASSIGN))],
) -> AdminUserDetailOut:
    await AdminService(session).grant(
        user_id=user_id,
        role_code=payload.role,
        scope_type=payload.scope_type,
        scope_id=payload.scope_id,
        expires_at=payload.expires_at,
        actor=actor,
    )
    return await _user_detail(session, user_id, actor)


@router.delete(
    "/users/{user_id}/roles/{code}",
    response_model=AdminUserDetailOut,
    summary="سلب نقش",
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
async def revoke_role(
    user_id: uuid.UUID,
    code: str,
    session: SessionDep,
    actor: Annotated[CurrentUser, Depends(require(Permission.USER_ROLE_ASSIGN))],
    scope_type: Annotated[str, Query(pattern="^(GLOBAL|OFFERING)$")] = "GLOBAL",
    scope_id: uuid.UUID | None = None,
) -> AdminUserDetailOut:
    await AdminService(session).revoke(
        user_id=user_id, role_code=code, scope_type=scope_type, scope_id=scope_id, actor=actor
    )
    return await _user_detail(session, user_id, actor)


# ── جعل هویت — §6.5 ────────────────────────────────────────────────────
@router.post(
    "/users/{user_id}/impersonate",
    response_model=ImpersonationOut,
    summary="مشاهده به‌عنوان کاربر (فقط خواندنی)",
    responses={404: {"model": ErrorResponse}},
)
async def impersonate(
    user_id: uuid.UUID,
    session: SessionDep,
    settings: SettingsDep,
    actor: Annotated[CurrentUser, Depends(require(Permission.IMPERSONATE))],
) -> ImpersonationOut:
    """توکن ۳۰ دقیقه‌ای، بی refresh؛ هر درخواست با آن در لاگ حسابرسی می‌نشیند
    و هر `POST`/`PATCH`/`DELETE` با `IMPERSONATION_READ_ONLY` رد می‌شود."""
    result = await AdminService(session).impersonate(
        target_id=user_id, actor=actor, settings=settings
    )
    names = await display_names(session, [result.target.id])
    return ImpersonationOut(
        access_token=result.token,
        expires_at=result.expires_at,
        user_id=result.target.id,
        user_name=name_of(names, result.target.id),
        username=result.target.username,
        roles=result.roles,
    )


@router.post("/impersonation/end", status_code=204, summary="پایان مشاهده به‌عنوان کاربر")
async def end_impersonation(
    payload: ImpersonationEndIn,
    session: SessionDep,
    actor: Annotated[CurrentUser, Depends(require(Permission.IMPERSONATE))],
) -> Response:
    await AdminService(session).end_impersonation(target_id=payload.user_id, actor=actor)
    return Response(status_code=204)


# ── لاگ حسابرسی — FR-ADM-02 ────────────────────────────────────────────
def _audit_filters(
    actor_id: uuid.UUID | None,
    user_id: uuid.UUID | None,
    entity_type: str | None,
    entity_id: uuid.UUID | None,
    action: str | None,
    since: datetime | None,
    until: datetime | None,
) -> AuditFilters:
    return AuditFilters(
        actor_id=actor_id,
        subject_user_id=user_id,
        entity_type=entity_type or None,
        entity_id=entity_id,
        action=action or None,
        since=since,
        until=until,
    )


@router.get("/audit", response_model=AuditPageOut, summary="لاگ حسابرسی")
async def audit_log(
    session: SessionDep,
    _: Annotated[CurrentUser, Depends(require(Permission.AUDIT_LOG_VIEW))],
    actor_id: uuid.UUID | None = None,
    user_id: Annotated[
        uuid.UUID | None, Query(description="هرچه این کاربر کرد یا بر او شد")
    ] = None,
    entity_type: Annotated[str | None, Query(max_length=40)] = None,
    entity_id: uuid.UUID | None = None,
    action: Annotated[str | None, Query(max_length=40)] = None,
    since: datetime | None = None,
    until: datetime | None = None,
    cursor: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> AuditPageOut:
    filters = _audit_filters(actor_id, user_id, entity_type, entity_id, action, since, until)
    rows, next_cursor = await AuditService(session).page(filters, before=cursor, limit=limit)
    return AuditPageOut(items=await audit_out(session, rows), next_cursor=next_cursor)


@router.get(
    "/audit/export",
    summary="خروجی CSV لاگ حسابرسی",
    response_class=Response,
    responses={200: {"content": {"text/csv": {}}}},
)
async def export_audit(
    session: SessionDep,
    _: Annotated[CurrentUser, Depends(require(Permission.AUDIT_LOG_VIEW))],
    actor_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    entity_type: Annotated[str | None, Query(max_length=40)] = None,
    entity_id: uuid.UUID | None = None,
    action: Annotated[str | None, Query(max_length=40)] = None,
    since: datetime | None = None,
    until: datetime | None = None,
) -> Response:
    """«قابل جستجو و خروجی‌گیری» — BOM دارد تا Excel فارسی را درست باز کند."""
    filters = _audit_filters(actor_id, user_id, entity_type, entity_id, action, since, until)
    rows = await audit_out(session, await AuditService(session).export(filters))
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        ["زمان", "عمل", "کد عمل", "کنشگر", "به جای", "موجودیت", "شناسه", "قبل", "بعد", "IP"]
    )
    for row in rows:
        writer.writerow(
            [
                row.created_at.isoformat(),
                row.action_fa,
                row.action,
                row.actor_name or (str(row.actor_id) if row.actor_id else ""),
                row.impersonator_name or "",
                row.entity_type_fa,
                str(row.entity_id or ""),
                json.dumps(row.before, ensure_ascii=False) if row.before else "",
                json.dumps(row.after, ensure_ascii=False) if row.after else "",
                row.ip_address or "",
            ]
        )
    body = chr(0xFEFF) + buffer.getvalue()
    return Response(
        content=body.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="silp-audit.csv"'},
    )


__all__ = ["router"]
