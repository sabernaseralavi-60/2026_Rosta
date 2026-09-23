"""مدل‌های پنل مدیریت — §5.12، FR-ADM-01/02، §6.5، ADR-0017."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

UserStatus = Literal["ACTIVE", "SUSPENDED", "DEACTIVATED"]
GrantScope = Literal["GLOBAL", "OFFERING"]


class RoleGrantAdminOut(BaseModel):
    code: str
    title_fa: str
    scope_type: str
    scope_id: uuid.UUID | None
    #: عنوان قلمرو — «برنامه‌ریزی حمل‌ونقل · پاییز ۱۴۰۵».
    scope_label: str | None = None
    granted_by_name: str | None = None
    granted_at: datetime
    expires_at: datetime | None = None


class AdminUserOut(BaseModel):
    """یک ردیف فهرست کاربران.

    موبایل و ایمیل پوشانده‌اند مگر کنشگر `profile.view.contact` داشته باشد
    (NFR-01): پشتیبانی کاربر را پیدا می‌کند بی‌آنکه شمارهٔ کامل ببیند.
    """

    id: uuid.UUID
    name: str | None
    username: str | None
    mobile: str | None
    email: str | None
    status: UserStatus
    roles: list[str]
    is_public: bool
    created_at: datetime
    last_login_at: datetime | None


class AdminUserPage(BaseModel):
    items: list[AdminUserOut]
    total: int
    page: int
    page_size: int
    has_next: bool


class AuditEntryOut(BaseModel):
    id: uuid.UUID
    action: str
    action_fa: str
    entity_type: str
    entity_type_fa: str
    entity_id: uuid.UUID | None
    actor_id: uuid.UUID | None
    actor_name: str | None
    impersonated_by: uuid.UUID | None
    impersonator_name: str | None
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    ip_address: str | None
    user_agent: str | None
    created_at: datetime


class AuditPageOut(BaseModel):
    items: list[AuditEntryOut]
    next_cursor: uuid.UUID | None = None


class AdminUserDetailOut(AdminUserOut):
    grants: list[RoleGrantAdminOut]
    derived_roles: list[str]
    points_total: int
    level: int
    projects_active: int
    projects_completed: int
    enrollments: int
    certificates: int
    recent_audit: list[AuditEntryOut]
    can_impersonate: bool
    impersonation_blocked_reason: str | None = None


class UserStatusIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: UserStatus
    reason: Annotated[str, Field(min_length=5, max_length=500)]


class RoleGrantIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: str
    scope_type: GrantScope = "GLOBAL"
    scope_id: uuid.UUID | None = None
    expires_at: datetime | None = None


class ImpersonationOut(BaseModel):
    """توکن فقط‌خواندنی ۳۰ دقیقه‌ای، بی refresh — §6.5."""

    access_token: str
    expires_at: datetime
    user_id: uuid.UUID
    user_name: str | None
    username: str | None
    roles: list[str]


class ImpersonationEndIn(BaseModel):
    user_id: uuid.UUID


class RoleOptionOut(BaseModel):
    code: str
    title_fa: str
    scopes: list[GrantScope]


class MetricsOut(BaseModel):
    """`GET /admin/metrics` — شاخص‌های کلان (§3.6 `/admin`)."""

    users_total: int
    users_active_7d: int
    users_new_7d: int
    users_suspended: int
    public_profiles: int
    roles: dict[str, int]
    projects: dict[str, int]
    pending_deliverables: int
    pending_research: int
    pending_metrics: int
    pending_outputs: int
    outbox: dict[str, int]
    certificates: int
    audit_24h: int
    impersonations_7d: int
