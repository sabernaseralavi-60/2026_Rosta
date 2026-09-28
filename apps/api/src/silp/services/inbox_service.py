"""صندوق درخواست‌های ورودی و داشبورد مالک — ADR-0032.

* هر تغییر وضعیت یک `IntakeEvent` می‌نویسد و یک ردیف حسابرسی (`INTAKE_UPDATED`) در
  **همان تراکنش**؛ commit را فراخوان می‌زند.
* `owner_note` خصوصی است و فقط از این سرویس بیرون می‌آید؛ مشتری هیچ‌جا آن را نمی‌بیند.
* «نیاز به پیگیری» = `NEW` یا `IN_REVIEW` که بیش از سه روز دست‌نخورده مانده.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Text, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from silp.core.exceptions import NotFound
from silp.core.permissions import CurrentUser
from silp.domain import audit
from silp.models.content import ContentItem
from silp.models.education import Course, Enrollment
from silp.models.identity import User, UserRole
from silp.models.intake import INTAKE_STATUSES, IntakeEvent, IntakeRequest
from silp.schemas.inbox import InboxUpdateIn
from silp.services import events
from silp.services.audit_service import AuditService

STALE_AFTER = timedelta(days=3)
OPEN_STATUSES = ("NEW", "IN_REVIEW")
FOLLOW_UP_LIMIT = 5

Row = tuple[IntakeRequest, str | None]


def _like(term: str) -> str:
    escaped = term.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def is_stale(request: IntakeRequest, *, now: datetime | None = None) -> bool:
    now = now or datetime.now(UTC)
    return request.status in OPEN_STATUSES and now - request.updated_at > STALE_AFTER


class InboxService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ── فهرست ──────────────────────────────────────────────────────────
    def _search(self, kind: str | None, q: str | None) -> list[Any]:
        conditions: list[Any] = []
        if kind:
            conditions.append(IntakeRequest.kind == kind)
        if q and q.strip():
            pattern = _like(q)
            conditions.append(
                or_(
                    IntakeRequest.tracking_code.ilike(pattern),
                    IntakeRequest.contact_mobile.ilike(pattern),
                    IntakeRequest.contact_email.ilike(pattern),
                    func.fa_normalize(IntakeRequest.contact_name).ilike(func.fa_normalize(pattern)),
                    func.fa_normalize(func.coalesce(IntakeRequest.organization, "")).ilike(
                        func.fa_normalize(pattern)
                    ),
                    func.fa_normalize(IntakeRequest.summary).ilike(func.fa_normalize(pattern)),
                )
            )
        return conditions

    async def page(
        self,
        *,
        kind: str | None,
        status: str | None,
        q: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[Row], int, dict[str, int]]:
        base = self._search(kind, q)
        counts = {s: 0 for s in INTAKE_STATUSES}
        counts.update(
            {
                s: int(n)
                for s, n in await self.session.execute(
                    select(IntakeRequest.status, func.count())
                    .where(*base)
                    .group_by(IntakeRequest.status)
                )
            }
        )
        conditions = [*base, IntakeRequest.status == status] if status else base
        total = int(
            await self.session.scalar(
                select(func.count()).select_from(IntakeRequest).where(*conditions)
            )
            or 0
        )
        rows = await self.session.execute(
            select(IntakeRequest, User.person_code)
            .outerjoin(User, User.id == IntakeRequest.user_id)
            .where(*conditions)
            .order_by(IntakeRequest.created_at.desc(), IntakeRequest.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(rows.tuples().all()), total, counts

    # ── جزئیات ─────────────────────────────────────────────────────────
    async def get(self, request_id: uuid.UUID) -> tuple[Row, list[IntakeEvent]]:
        row = (
            await self.session.execute(
                select(IntakeRequest, User.person_code)
                .outerjoin(User, User.id == IntakeRequest.user_id)
                .where(IntakeRequest.id == request_id)
            )
        ).first()
        if row is None:
            raise NotFound("درخواست پیدا نشد.")
        events = list(
            await self.session.scalars(
                select(IntakeEvent)
                .where(IntakeEvent.request_id == request_id)
                .order_by(IntakeEvent.id)
            )
        )
        return (row[0], row[1]), events

    # ── رسیدگی ─────────────────────────────────────────────────────────
    async def update(
        self, request_id: uuid.UUID, data: InboxUpdateIn, *, actor: CurrentUser
    ) -> tuple[Row, list[IntakeEvent]]:
        result = await self.session.scalars(
            select(IntakeRequest).where(IntakeRequest.id == request_id).with_for_update()
        )
        request = result.first()
        if request is None:
            raise NotFound("درخواست پیدا نشد.")

        before = {"status": request.status, "owner_note": bool(request.owner_note)}
        previous = request.status
        changed_status = data.status is not None and data.status != previous
        if changed_status:
            request.status = str(data.status)
        if data.owner_note is not None:
            request.owner_note = data.owner_note or None
        note = (data.public_note or "").strip() or None
        handled: IntakeEvent | None = None
        if changed_status or note:
            handled = IntakeEvent(
                request_id=request.id,
                actor_id=actor.id,
                from_status=previous,
                to_status=request.status,
                public_note=note,
            )
            self.session.add(handled)
        # یادداشتِ عمومی که وضعیت را عوض نکرده هم «رسیدگی» است: بی‌این خط هیچ ستونی عوض
        # نمی‌شد، UPDATE نمی‌رفت و تریگر ساعت پیگیری را از نو نمی‌شمرد.
        request.updated_at = datetime.now(UTC)
        AuditService(self.session).stage(
            audit.INTAKE_UPDATED,
            actor=actor,
            entity_type="INTAKE_REQUEST",
            entity_id=request.id,
            before=before,
            after={
                "status": request.status,
                "owner_note": bool(request.owner_note),
                "public_note": bool(note),
                "tracking_code": request.tracking_code,
            },
        )
        await self.session.flush()
        if handled is not None:
            await events.publish(
                self.session,
                events.IntakeHandled(request_id=request.id, event_id=handled.id, actor_id=actor.id),
            )
        return await self.get(request.id)

    # ── داشبورد مالک ───────────────────────────────────────────────────
    async def overview(self) -> dict[str, Any]:
        now = datetime.now(UTC)

        async def count(stmt: Any) -> int:
            return int(await self.session.scalar(stmt) or 0)

        intake: dict[str, dict[str, int]] = {
            "INTAKE": {s: 0 for s in INTAKE_STATUSES},
            "COLLABORATION": {s: 0 for s in INTAKE_STATUSES},
        }
        for kind, status, n in (
            await self.session.execute(
                select(IntakeRequest.kind, IntakeRequest.status, func.count()).group_by(
                    IntakeRequest.kind, IntakeRequest.status
                )
            )
        ).tuples():
            intake[kind][status] = int(n)

        stale_where = (
            IntakeRequest.status.in_(OPEN_STATUSES),
            IntakeRequest.updated_at < now - STALE_AFTER,
        )
        oldest = await self.session.scalar(
            select(func.min(IntakeRequest.created_at)).where(IntakeRequest.status == "NEW")
        )
        follow_up_rows = (
            (
                await self.session.execute(
                    select(IntakeRequest, User.person_code)
                    .outerjoin(User, User.id == IntakeRequest.user_id)
                    .where(*stale_where)
                    .order_by(IntakeRequest.updated_at, IntakeRequest.id)
                    .limit(FOLLOW_UP_LIMIT)
                )
            )
            .tuples()
            .all()
        )

        student = (
            select(func.count(func.distinct(UserRole.user_id)))
            .join(User, User.id == UserRole.user_id)
            .where(UserRole.role_code == "STUDENT", User.deleted_at.is_(None))
        )
        content = {
            status: int(n)
            for status, n in await self.session.execute(
                select(ContentItem.status, func.count()).group_by(ContentItem.status)
            )
        }

        def people(kind: str) -> Any:
            # هر فرد یک بار: کاربر وصل‌شده، وگرنه شمارهٔ تماس، وگرنه ایمیل.
            identity = func.coalesce(
                cast(IntakeRequest.user_id, Text),
                IntakeRequest.contact_mobile,
                IntakeRequest.contact_email,
            )
            return select(func.count(func.distinct(identity))).where(
                IntakeRequest.kind == kind, IntakeRequest.status == "ACCEPTED"
            )

        return {
            "intake": intake,
            "new_7d": await count(
                select(func.count())
                .select_from(IntakeRequest)
                .where(IntakeRequest.created_at >= now - timedelta(days=7))
            ),
            "stale": await count(
                select(func.count()).select_from(IntakeRequest).where(*stale_where)
            ),
            "oldest_new_days": (now - oldest).days if oldest else None,
            "students_total": await count(student),
            "students_active_7d": await count(
                student.where(User.last_login_at >= now - timedelta(days=7))
            ),
            "enrollments_active": await count(
                select(func.count()).select_from(Enrollment).where(Enrollment.status == "ACTIVE")
            ),
            "courses_total": await count(
                select(func.count()).select_from(Course).where(Course.deleted_at.is_(None))
            ),
            "content": content,
            "clients_accepted": await count(people("INTAKE")),
            "collaborators_accepted": await count(people("COLLABORATION")),
            "follow_up": follow_up_rows,
        }


__all__ = ["STALE_AFTER", "InboxService", "is_stale"]
