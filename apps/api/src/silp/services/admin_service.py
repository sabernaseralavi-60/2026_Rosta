"""پنل مدیریت: کاربران، نقش‌ها، وضعیت حساب و جعل هویت — FR-ADM-01، §6.5، ADR-0017.

هر تغییر این‌جا در **همان تراکنش** در `audit_logs` می‌نشیند. سه نگهبان
که در سند صریح نیستند ولی نبودشان سامانه را قفل می‌کند:

* **هیچ‌کس نقش مدیر یا حساب خودش را برنمی‌دارد.** مدیری که با یک کلیک
  خودش را بیرون کند، اگر آخرین مدیر باشد، کسی نمی‌ماند که برگرداندش.
* **آخرین مدیر فعال** نه سلب نقش می‌شود و نه تعلیق.
* **نقش مشتق اعطا نمی‌شود.** `PROJECT_MEMBER` و `PROJECT_LEAD` از عضویت
  تیم می‌آیند (§6.1)؛ ردیف دستی‌شان چیزی را باز نمی‌کرد جز سردرگمی.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Select, and_, delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from silp.core.config import Settings
from silp.core.exceptions import Conflict, NotFound, PermissionDenied, ValidationFailed
from silp.core.logging import get_logger
from silp.core.permissions import (
    OFFERING_SCOPED_ROLES,
    ROLE_TITLE_FA,
    CurrentUser,
    Permission,
    Role,
    ScopeType,
)
from silp.core.security import create_access_token
from silp.domain import audit
from silp.models.admin import AuditLog
from silp.models.delivery import Certificate, Deliverable
from silp.models.education import Course, CourseOffering, Enrollment, Term
from silp.models.identity import NULL_SCOPE, RefreshToken, User, UserRole
from silp.models.messaging import OutboxMessage
from silp.models.profile import Profile
from silp.models.project import Project, Team, TeamMember
from silp.models.research import ResearchOutput, ResearchSubmission
from silp.models.venture import VentureMetric
from silp.services import authz, events
from silp.services.audit_service import AuditService

log = get_logger("silp.admin")

#: نقش‌هایی که از پنل اعطا نمی‌شوند. `INSTRUCTOR` با آنکه مشتق هم هست
#: (از `course_offerings.instructor_id`)، اعطا می‌شود: اعطای سراسری‌اش
#: مجوزهای بی‌قلمرو را می‌دهد و اعطای ارائه‌ای، دستیار دوم یک درس را می‌سازد.
NON_GRANTABLE: frozenset[Role] = frozenset({Role.GUEST, Role.PROJECT_MEMBER, Role.PROJECT_LEAD})
#: وضعیت‌هایی که ورود را می‌بندند — نشست‌های باز هم بسته می‌شوند.
LOCKED_STATUSES = frozenset({"SUSPENDED", "DEACTIVATED"})
IMPERSONATION_MINUTES = 30
REVOKED_ACCOUNT_LOCKED = "ACCOUNT_LOCKED"


def grantable_roles() -> list[Role]:
    return [role for role in Role if role not in NON_GRANTABLE]


def scopes_for(role: Role) -> list[str]:
    """`TA` و `INSTRUCTOR` می‌توانند به یک ارائه محدود شوند (§6.1)."""
    return ["GLOBAL", "OFFERING"] if role in OFFERING_SCOPED_ROLES else ["GLOBAL"]


@dataclass(frozen=True, slots=True)
class UserFilters:
    q: str | None = None
    role: str | None = None
    status: str | None = None


@dataclass(frozen=True, slots=True)
class StoredGrant:
    role_code: str
    scope_type: str
    scope_id: uuid.UUID | None
    granted_by: uuid.UUID | None
    granted_at: datetime
    expires_at: datetime | None


@dataclass(frozen=True, slots=True)
class Impersonation:
    token: str
    expires_at: datetime
    target: User
    roles: list[str]


class AdminService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.audit = AuditService(session)

    # ── کاربران — FR-ADM-01 ───────────────────────────────────────────
    def user_query(self, filters: UserFilters) -> Select[tuple[User, Profile]]:
        stmt = (
            select(User, Profile)
            .outerjoin(Profile, Profile.user_id == User.id)
            .where(User.deleted_at.is_(None))
        )
        if filters.status:
            stmt = stmt.where(User.status == filters.status)
        if filters.role:
            stmt = stmt.where(
                User.id.in_(select(UserRole.user_id).where(UserRole.role_code == filters.role))
            )
        if filters.q and filters.q.strip():
            raw = filters.q.strip()
            needle = func.concat("%", func.fa_normalize(raw), "%")
            conditions = [
                func.fa_normalize(
                    func.concat_ws(" ", Profile.first_name, Profile.last_name, Profile.display_name)
                ).like(needle),
                User.username.ilike(f"%{raw}%"),
                User.email.ilike(f"%{raw}%"),
            ]
            digits = "".join(ch for ch in raw.translate(_DIGITS) if ch.isdigit())
            if len(digits) >= 4:
                conditions.append(User.mobile.like(f"%{digits}%"))
            stmt = stmt.where(or_(*conditions))
        return stmt.order_by(User.created_at.desc(), User.id.desc())

    async def users(
        self, filters: UserFilters, *, offset: int, limit: int
    ) -> tuple[list[tuple[User, Profile | None]], int]:
        stmt = self.user_query(filters)
        total = await self.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = [tuple(row) for row in await self.session.execute(stmt.offset(offset).limit(limit))]
        return rows, int(total)

    async def stored_role_codes(self, user_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[str]]:
        if not user_ids:
            return {}
        rows = await self.session.execute(
            select(UserRole.user_id, UserRole.role_code).where(UserRole.user_id.in_(user_ids))
        )
        result: dict[uuid.UUID, set[str]] = {}
        for user_id, code in rows:
            result.setdefault(user_id, set()).add(code)
        return {uid: sorted(codes) for uid, codes in result.items()}

    async def get_user(self, user_id: uuid.UUID) -> tuple[User, Profile | None]:
        row = (
            await self.session.execute(
                select(User, Profile)
                .outerjoin(Profile, Profile.user_id == User.id)
                .where(User.id == user_id, User.deleted_at.is_(None))
            )
        ).first()
        if row is None:
            raise NotFound("این کاربر پیدا نشد.")
        return row[0], row[1]

    async def grants(self, user_id: uuid.UUID) -> list[StoredGrant]:
        """ستون‌ها، نه موجودیت: کلید اصلی ORM مدل `scope_id` را ندارد و دو
        اعطای یک نقش در دو ارائه در نقشهٔ هویت یکی می‌شدند."""
        rows = await self.session.execute(
            select(
                UserRole.role_code,
                UserRole.scope_type,
                UserRole.scope_id,
                UserRole.granted_by,
                UserRole.granted_at,
                UserRole.expires_at,
            )
            .where(UserRole.user_id == user_id)
            .order_by(UserRole.granted_at.desc())
        )
        return [StoredGrant(*row) for row in rows]

    async def offering_labels(self, offering_ids: list[uuid.UUID]) -> dict[uuid.UUID, str]:
        if not offering_ids:
            return {}
        rows = await self.session.execute(
            select(CourseOffering.id, Course.title_fa, Term.title_fa)
            .join(Course, Course.id == CourseOffering.course_id)
            .join(Term, Term.id == CourseOffering.term_id)
            .where(CourseOffering.id.in_(offering_ids))
        )
        return {oid: f"{course} · {term}" for oid, course, term in rows}

    async def user_counts(self, user_id: uuid.UUID) -> dict[str, int]:
        async def count(stmt: Any) -> int:
            return int(await self.session.scalar(stmt) or 0)

        membership = (
            select(func.count(func.distinct(Project.id)))
            .join(Team, Team.project_id == Project.id)
            .join(TeamMember, TeamMember.team_id == Team.id)
            .where(TeamMember.user_id == user_id, Project.deleted_at.is_(None))
        )
        return {
            "projects_active": await count(
                membership.where(
                    TeamMember.status == "ACTIVE",
                    Project.status.in_(("OPEN", "IN_PROGRESS", "PAUSED")),
                )
            ),
            "projects_completed": await count(
                membership.where(TeamMember.status == "ACTIVE", Project.status == "COMPLETED")
            ),
            "enrollments": await count(
                select(func.count()).select_from(Enrollment).where(Enrollment.student_id == user_id)
            ),
            "certificates": await count(
                select(func.count())
                .select_from(Certificate)
                .where(Certificate.user_id == user_id, Certificate.revoked_at.is_(None))
            ),
        }

    # ── وضعیت حساب ─────────────────────────────────────────────────────
    async def set_status(
        self, *, user_id: uuid.UUID, status: str, reason: str, actor: CurrentUser
    ) -> User:
        """«غیرفعال‌سازی حساب (نه حذف)» — FR-ADM-01.

        تعلیق همهٔ نشست‌ها را می‌بندد؛ توکن دسترسی باقی‌مانده هم در
        درخواست بعدی رد می‌شود چون `get_current_user` وضعیت را هر بار می‌خواند.
        """
        if user_id == actor.id:
            raise Conflict("وضعیت حساب خودتان را نمی‌توانید تغییر دهید.")
        user, _ = await self.get_user(user_id)
        if user.status == status:
            return user
        if status in LOCKED_STATUSES and await self._is_last_admin(user_id):
            raise Conflict("این آخرین مدیر فعال سامانه است؛ اول مدیر دیگری تعیین کنید.")
        before = user.status
        user.status = status
        if status in LOCKED_STATUSES:
            await self.session.execute(
                update(RefreshToken)
                .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
                .values(revoked_at=datetime.now(UTC), revoked_reason=REVOKED_ACCOUNT_LOCKED)
            )
        self.audit.stage(
            audit.USER_STATUS_CHANGED,
            actor=actor,
            entity_type="USER",
            entity_id=user_id,
            before={"status": before},
            after={"status": status, "reason": reason.strip()},
        )
        await self.session.commit()
        await authz.invalidate_roles(user_id)
        log.info("user_status_changed", user_id=str(user_id), status=status)
        return user

    # ── نقش — اعطا و سلب ───────────────────────────────────────────────
    async def grant(
        self,
        *,
        user_id: uuid.UUID,
        role_code: str,
        scope_type: str,
        scope_id: uuid.UUID | None,
        expires_at: datetime | None,
        actor: CurrentUser,
    ) -> None:
        role = _role(role_code)
        if role in NON_GRANTABLE:
            raise ValidationFailed(
                f"نقش «{ROLE_TITLE_FA[role]}» از عضویت تیم می‌آید و دستی اعطا نمی‌شود."
            )
        if scope_type not in scopes_for(role):
            raise ValidationFailed(f"نقش «{ROLE_TITLE_FA[role]}» فقط سراسری اعطا می‌شود.")
        if scope_type == "GLOBAL":
            scope_id = None
        else:
            if scope_id is None:
                raise ValidationFailed("برای نقش محدود به ارائه، ارائه را انتخاب کنید.")
            if await self.session.get(CourseOffering, scope_id) is None:
                raise NotFound("این ارائهٔ درس پیدا نشد.")
        if expires_at is not None and expires_at <= datetime.now(UTC):
            raise ValidationFailed("تاریخ انقضای نقش باید در آینده باشد.")
        await self.get_user(user_id)

        created = await authz.grant_role(
            self.session,
            user_id=user_id,
            role=role,
            scope_type=ScopeType(scope_type),
            scope_id=scope_id,
            granted_by=actor.id,
            expires_at=expires_at,
        )
        if created is None:
            raise Conflict("این نقش در همین قلمرو از قبل اعطا شده است.")
        self.audit.stage(
            audit.ROLE_GRANTED,
            actor=actor,
            entity_type="USER",
            entity_id=user_id,
            after={
                "role": role.value,
                "scope_type": scope_type,
                "scope_id": scope_id,
                "expires_at": expires_at,
            },
        )
        await events.publish(self.session, events.RoleGranted(user_id=user_id, role=role.value))
        await self.session.commit()
        await authz.invalidate_roles(user_id)

    async def revoke(
        self,
        *,
        user_id: uuid.UUID,
        role_code: str,
        scope_type: str,
        scope_id: uuid.UUID | None,
        actor: CurrentUser,
    ) -> None:
        role = _role(role_code)
        if role is Role.ADMIN and user_id == actor.id:
            raise Conflict("نقش مدیر خودتان را نمی‌توانید بردارید.")
        if role is Role.ADMIN and await self._is_last_admin(user_id):
            raise Conflict("این آخرین مدیر فعال سامانه است؛ اول مدیر دیگری تعیین کنید.")
        scope_value = scope_id if scope_type != "GLOBAL" else None
        removed = await self.session.scalar(
            delete(UserRole)
            .where(
                UserRole.user_id == user_id,
                UserRole.role_code == role.value,
                UserRole.scope_type == scope_type,
                func.coalesce(UserRole.scope_id, NULL_SCOPE) == (scope_value or NULL_SCOPE),
            )
            .returning(UserRole.granted_at)
        )
        if removed is None:
            raise NotFound("این نقش در این قلمرو اعطا نشده است.")
        self.audit.stage(
            audit.ROLE_REVOKED,
            actor=actor,
            entity_type="USER",
            entity_id=user_id,
            before={"role": role.value, "scope_type": scope_type, "scope_id": scope_value},
        )
        await self.session.commit()
        await authz.invalidate_roles(user_id)

    async def _is_last_admin(self, user_id: uuid.UUID) -> bool:
        """آیا این کاربر تنها مدیر سراسری فعالِ منقضی‌نشده است؟"""
        now = datetime.now(UTC)
        admins = set(
            await self.session.scalars(
                select(UserRole.user_id)
                .join(User, User.id == UserRole.user_id)
                .where(
                    UserRole.role_code == Role.ADMIN.value,
                    UserRole.scope_type == "GLOBAL",
                    or_(UserRole.expires_at.is_(None), UserRole.expires_at > now),
                    User.status == "ACTIVE",
                    User.deleted_at.is_(None),
                )
            )
        )
        return admins == {user_id}

    # ── جعل هویت — §6.5 ────────────────────────────────────────────────
    async def impersonation_block(self, target: User, actor: CurrentUser) -> str | None:
        """دلیل ممنوع بودن، یا `None` اگر مجاز است."""
        if actor.is_impersonating:
            return "در حالت مشاهده به‌عنوان کاربر دیگر، جعل هویت دوباره ممکن نیست."
        if target.id == actor.id:
            return "خودتان را نمی‌توانید «مشاهده به‌عنوان» کنید."
        if not target.is_active:
            return "حساب این کاربر فعال نیست."
        target_grants = await authz.get_grants(self.session, target.id)
        if any(g.role is Role.ADMIN for g in target_grants):
            return "مشاهده به‌عنوان مدیر سامانه ممنوع است (§6.5)."
        return None

    async def impersonate(
        self, *, target_id: uuid.UUID, actor: CurrentUser, settings: Settings
    ) -> Impersonation:
        target, _ = await self.get_user(target_id)
        blocked = await self.impersonation_block(target, actor)
        if blocked:
            raise PermissionDenied(blocked, code="IMPERSONATION_FORBIDDEN")
        roles = await authz.role_codes(self.session, target.id)
        token, expires_at = create_access_token(
            settings,
            user_id=target.id,
            roles=roles,
            session_id=actor.session_id,
            act_as=actor.id,
            expires_in=timedelta(minutes=IMPERSONATION_MINUTES),
        )
        self.audit.stage(
            audit.IMPERSONATION_STARTED,
            actor=actor,
            entity_type="USER",
            entity_id=target.id,
            after={"expires_at": expires_at},
        )
        await events.publish(
            self.session, events.ImpersonationStarted(target_id=target.id, agent_id=actor.id)
        )
        await self.session.commit()
        log.warning("impersonation_started", target_id=str(target.id), agent_id=str(actor.id))
        return Impersonation(token=token, expires_at=expires_at, target=target, roles=roles)

    async def end_impersonation(self, *, target_id: uuid.UUID, actor: CurrentUser) -> None:
        self.audit.stage(
            audit.IMPERSONATION_ENDED,
            actor=actor,
            entity_type="USER",
            entity_id=target_id,
        )
        await self.session.commit()

    # ── شاخص‌های کلان — `GET /admin/metrics` ───────────────────────────
    async def metrics(self) -> dict[str, object]:
        now = datetime.now(UTC)
        week_ago = now - timedelta(days=7)

        async def count(stmt: Any) -> int:
            return int(await self.session.scalar(stmt) or 0)

        live_user = User.deleted_at.is_(None)
        by_role = {
            code: int(n)
            for code, n in await self.session.execute(
                select(UserRole.role_code, func.count(func.distinct(UserRole.user_id)))
                .join(User, User.id == UserRole.user_id)
                .where(live_user)
                .group_by(UserRole.role_code)
            )
        }
        by_status = {
            status: int(n)
            for status, n in await self.session.execute(
                select(Project.status, func.count())
                .where(Project.deleted_at.is_(None))
                .group_by(Project.status)
            )
        }
        outbox = {
            status: int(n)
            for status, n in await self.session.execute(
                select(OutboxMessage.status, func.count()).group_by(OutboxMessage.status)
            )
        }
        return {
            "users_total": await count(select(func.count()).select_from(User).where(live_user)),
            "users_active_7d": await count(
                select(func.count())
                .select_from(User)
                .where(live_user, User.last_login_at >= week_ago)
            ),
            "users_new_7d": await count(
                select(func.count()).select_from(User).where(live_user, User.created_at >= week_ago)
            ),
            "users_suspended": await count(
                select(func.count())
                .select_from(User)
                .where(live_user, User.status.in_(tuple(LOCKED_STATUSES)))
            ),
            "public_profiles": await count(
                select(func.count()).select_from(Profile).where(Profile.is_public.is_(True))
            ),
            "roles": by_role,
            "projects": by_status,
            "pending_deliverables": await count(
                select(func.count())
                .select_from(Deliverable)
                .where(Deliverable.status.in_(("SUBMITTED", "UNDER_REVIEW")))
            ),
            "pending_research": await count(
                select(func.count())
                .select_from(ResearchSubmission)
                .where(ResearchSubmission.status == "SUBMITTED")
            ),
            "pending_metrics": await count(
                select(func.count())
                .select_from(VentureMetric)
                .where(VentureMetric.status == "PENDING")
            ),
            "pending_outputs": await count(
                select(func.count())
                .select_from(ResearchOutput)
                .where(ResearchOutput.review_status == "PENDING")
            ),
            "outbox": outbox,
            "certificates": await count(
                select(func.count())
                .select_from(Certificate)
                .where(Certificate.revoked_at.is_(None))
            ),
            "audit_24h": await count(
                select(func.count())
                .select_from(AuditLog)
                .where(AuditLog.created_at >= now - timedelta(days=1))
            ),
            "impersonations_7d": await count(
                select(func.count())
                .select_from(AuditLog)
                .where(
                    and_(
                        AuditLog.action == audit.IMPERSONATION_STARTED,
                        AuditLog.created_at >= week_ago,
                    )
                )
            ),
        }


_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def _role(code: str) -> Role:
    try:
        return Role(code)
    except ValueError:
        raise ValidationFailed(f"نقش ناشناخته: {code}") from None


def can_view_contact(user: CurrentUser) -> bool:
    return user.has_permission(Permission.PROFILE_VIEW_CONTACT)


__all__ = [
    "IMPERSONATION_MINUTES",
    "NON_GRANTABLE",
    "AdminService",
    "Impersonation",
    "StoredGrant",
    "UserFilters",
    "can_view_contact",
    "grantable_roles",
    "scopes_for",
]
