"""لاگ حسابرسی — FR-ADM-02، §6.5، ADR-0017.

دو قاعده:

۱. **ثبت در همان تراکنش عمل.** `stage` ردیف را فقط به نشست می‌افزاید و
   commit نمی‌زند؛ commit سرویسی که عمل را انجام می‌دهد هر دو را با هم
   تثبیت می‌کند. تغییر نمره‌ای که لاگش نوشته نشده، یا لاگی که عملش
   برگشته، وجود ندارد.
۲. **فقط افزودنی.** اینجا هیچ متد ویرایش یا حذفی نیست، و اگر باشد هم
   تریگر `audit_logs_append_only` در دیتابیس ردش می‌کند.

IP و User-Agent از `contextvars` درخواست جاری خوانده می‌شوند
(`TraceMiddleware`)، پس سرویس دامنه لازم نیست `Request` را بشناسد. در
کار پس‌زمینه یا اسکریپت، هر دو خالی‌اند.
"""

from __future__ import annotations

import ipaddress
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from silp.core.logging import client_ip_var, user_agent_var
from silp.core.permissions import CurrentUser
from silp.models.admin import AuditLog

#: سقف یک صفحهٔ خروجی CSV — خروجی بزرگ‌تر با بازهٔ زمانی تنگ‌تر گرفته می‌شود.
EXPORT_LIMIT = 10_000


@dataclass(frozen=True, slots=True)
class AuditFilters:
    actor_id: uuid.UUID | None = None
    entity_type: str | None = None
    entity_id: uuid.UUID | None = None
    action: str | None = None
    since: datetime | None = None
    until: datetime | None = None
    #: هم کنشگر و هم موجودیت — «هرچه به این کاربر مربوط است».
    subject_user_id: uuid.UUID | None = None


def jsonable(value: Any) -> Any:
    """مقدار قبل و بعد به JSON امن — شناسه، زمان و عدد اعشاری به رشته."""
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, uuid.UUID | Decimal):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, list | tuple | set | frozenset):
        return [jsonable(v) for v in value]
    return str(value)


def _valid_ip(raw: str | None) -> str | None:
    """ستون `INET` مقدار «unknown» یا «testclient» را نمی‌پذیرد."""
    if not raw:
        return None
    try:
        return str(ipaddress.ip_address(raw))
    except ValueError:
        return None


class AuditService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def stage(
        self,
        action: str,
        *,
        actor: CurrentUser | uuid.UUID | None,
        entity_type: str,
        entity_id: uuid.UUID | None = None,
        before: Mapping[str, Any] | None = None,
        after: Mapping[str, Any] | None = None,
    ) -> AuditLog:
        """ردیف را به نشست می‌افزاید؛ commit با فراخوان است."""
        if isinstance(actor, CurrentUser):
            actor_id: uuid.UUID | None = actor.id
            impersonated_by = actor.impersonated_by
        else:
            actor_id, impersonated_by = actor, None
        row = AuditLog(
            actor_id=actor_id,
            impersonated_by=impersonated_by,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            before=jsonable(before) if before is not None else None,
            after=jsonable(after) if after is not None else None,
            ip_address=_valid_ip(client_ip_var.get()),
            user_agent=user_agent_var.get(),
        )
        self.session.add(row)
        return row

    # ── جستجو — `GET /admin/audit` ─────────────────────────────────────
    def query(self, filters: AuditFilters) -> Select[tuple[AuditLog]]:
        stmt = select(AuditLog)
        if filters.actor_id is not None:
            stmt = stmt.where(AuditLog.actor_id == filters.actor_id)
        if filters.subject_user_id is not None:
            uid = filters.subject_user_id
            stmt = stmt.where(
                (AuditLog.actor_id == uid)
                | (AuditLog.impersonated_by == uid)
                | ((AuditLog.entity_type == "USER") & (AuditLog.entity_id == uid))
            )
        if filters.entity_type:
            stmt = stmt.where(AuditLog.entity_type == filters.entity_type)
        if filters.entity_id is not None:
            stmt = stmt.where(AuditLog.entity_id == filters.entity_id)
        if filters.action:
            stmt = stmt.where(AuditLog.action == filters.action)
        if filters.since is not None:
            stmt = stmt.where(AuditLog.created_at >= filters.since)
        if filters.until is not None:
            stmt = stmt.where(AuditLog.created_at < filters.until)
        # UUIDv7 به ترتیب زمان است؛ مرتب‌سازی با شناسه، مکان‌نمای پایدار می‌دهد.
        return stmt.order_by(AuditLog.id.desc())

    async def page(
        self, filters: AuditFilters, *, before: uuid.UUID | None, limit: int
    ) -> tuple[list[AuditLog], uuid.UUID | None]:
        stmt = self.query(filters)
        if before is not None:
            stmt = stmt.where(AuditLog.id < before)
        rows = list(await self.session.scalars(stmt.limit(limit + 1)))
        next_cursor = rows[limit - 1].id if len(rows) > limit else None
        return rows[:limit], next_cursor

    async def export(self, filters: AuditFilters) -> list[AuditLog]:
        return list(await self.session.scalars(self.query(filters).limit(EXPORT_LIMIT)))


__all__ = ["EXPORT_LIMIT", "AuditFilters", "AuditService", "jsonable"]
