"""کسب‌وکار و مرحلهٔ بلوغ — FR-VEN-01، §7.7، M7-03.

## چه کسی چه می‌کند

| عمل | بنیان‌گذار | عضو تیم | `venture.manage` |
|-----|-----------|---------|------------------|
| ویرایش مشخصات، تغییر مرحله، حذف | ✅ | ❌ | ✅ |
| ثبت شاخص | ✅ | ✅ | ❌ |
| دعوت و حذف عضو | ✅ | ❌ | ✅ |

## مرحله

فقط رو به جلو و فقط یک گام (§7.7)؛ هر گام معیار خروج دارد که پیش از
ارتقا خودکار بررسی می‌شود (`silp.domain.ventures`). توقف و بستن از هر
مرحله ممکن است و دلیل می‌خواهد؛ بازگشت از توقف به همان مرحلهٔ پیش از
توقف است. هر گذار یک ردیف `venture_stage_changes` است — هم تاریخچه، هم
منبع یکتای امتیاز `VENTURE_STAGE_UP`.

## حذف

فقط در مرحلهٔ `IDEA`. کسب‌وکاری که مرحله‌ای را طی کرده، تاریخ دارد و راه
پایانش «بستن» است، نه پاک کردن. حذف امتیاز ثبت را برمی‌گرداند؛ وگرنه
ساختن و پاک کردن پیاپی، ۲۰ امتیاز بی‌کار بود.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from slugify import slugify
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from silp.core.config import Settings, get_settings
from silp.core.exceptions import (
    Conflict,
    NotFound,
    PermissionDenied,
    ProfileIncomplete,
    StageCriteriaNotMet,
    ValidationFailed,
)
from silp.core.logging import get_logger
from silp.core.permissions import CurrentUser, Permission
from silp.domain import ventures as rules
from silp.domain.identity import onboarding
from silp.models.delivery import Deliverable, Milestone
from silp.models.profile import Profile
from silp.models.project import Project, Team, TeamMember
from silp.models.venture import (
    GROWTH_STAGES,
    MAX_NEEDED_ROLES,
    Venture,
    VentureMetric,
    VentureStageChange,
)
from silp.services import authz, events

log = get_logger("silp.venture")

SLUG_MAX_LENGTH = 80
SLUG_ATTEMPTS = 20
MAX_VENTURE_MEMBERS = 20
STAGE_ACTIONS = ("ADVANCE", "PAUSE", "RESUME", "CLOSE")


@dataclass(slots=True)
class VentureDraft:
    name: str
    pitch: str
    description: str | None = None
    problem: str | None = None
    target_market: str | None = None
    revenue_model: str | None = None
    current_status: str | None = None
    looking_for_cofounder: bool = False
    needed_roles: list[str] | None = None


def _now() -> datetime:
    return datetime.now(UTC)


def _clean(value: str | None) -> str | None:
    cleaned = (value or "").strip()
    return cleaned or None


def _clean_roles(roles: list[str] | None) -> list[str]:
    result: list[str] = []
    for raw in roles or []:
        role = " ".join(raw.split())
        if role and role not in result:
            result.append(role)
    if len(result) > MAX_NEEDED_ROLES:
        raise ValidationFailed(f"حداکثر {MAX_NEEDED_ROLES} نقش مورد نیاز.")
    return result


class VentureService:
    def __init__(self, session: AsyncSession, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()

    # ── خواندن ─────────────────────────────────────────────────────────
    async def get(self, venture_id: uuid.UUID) -> Venture | None:
        venture = await self.session.get(Venture, venture_id)
        if venture is None or venture.deleted_at is not None:
            return None
        return venture

    async def require(self, venture_id: uuid.UUID) -> Venture:
        venture = await self.get(venture_id)
        if venture is None:
            raise NotFound("کسب‌وکار پیدا نشد.")
        return venture

    async def team_of(self, venture_id: uuid.UUID) -> Team | None:
        team: Team | None = await self.session.scalar(
            select(Team).where(Team.venture_id == venture_id)
        )
        return team

    async def members(self, venture_id: uuid.UUID) -> list[TeamMember]:
        rows = await self.session.scalars(
            select(TeamMember)
            .join(Team, Team.id == TeamMember.team_id)
            .where(Team.venture_id == venture_id, TeamMember.status == "ACTIVE")
            .order_by(TeamMember.is_lead.desc(), TeamMember.joined_at)
        )
        return list(rows)

    async def is_member(self, venture_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        found = await self.session.scalar(
            select(TeamMember.id)
            .join(Team, Team.id == TeamMember.team_id)
            .where(
                Team.venture_id == venture_id,
                TeamMember.user_id == user_id,
                TeamMember.status == "ACTIVE",
            )
        )
        return found is not None

    async def can_manage(self, venture: Venture, actor: CurrentUser) -> bool:
        if venture.founder_id == actor.id:
            return True
        return await authz.has_permission(self.session, actor, Permission.VENTURE_MANAGE)

    async def require_manager(self, venture: Venture, actor: CurrentUser) -> None:
        if not await self.can_manage(venture, actor):
            raise PermissionDenied(
                "فقط بنیان‌گذار این کسب‌وکار می‌تواند این کار را انجام دهد.",
                permission=Permission.VENTURE_MANAGE.value,
            )

    async def require_member(self, venture: Venture, actor: CurrentUser) -> None:
        if not await self.is_member(venture.id, actor.id):
            raise PermissionDenied("شما عضو تیم این کسب‌وکار نیستید.", code="NOT_TEAM_MEMBER")

    async def mine(self, user_id: uuid.UUID) -> list[Venture]:
        rows = await self.session.scalars(
            select(Venture)
            .join(Team, Team.venture_id == Venture.id)
            .join(TeamMember, TeamMember.team_id == Team.id)
            .where(
                TeamMember.user_id == user_id,
                TeamMember.status == "ACTIVE",
                Venture.deleted_at.is_(None),
            )
            .order_by(Venture.updated_at.desc())
        )
        return list(rows)

    async def member_counts(self, venture_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
        if not venture_ids:
            return {}
        rows = await self.session.execute(
            select(Team.venture_id, func.count())
            .join(TeamMember, TeamMember.team_id == Team.id)
            .where(Team.venture_id.in_(venture_ids), TeamMember.status == "ACTIVE")
            .group_by(Team.venture_id)
        )
        return {vid: int(n) for vid, n in rows if vid is not None}

    async def projects(self, venture_id: uuid.UUID) -> list[Project]:
        rows = await self.session.scalars(
            select(Project)
            .where(Project.venture_id == venture_id, Project.deleted_at.is_(None))
            .order_by(Project.created_at)
        )
        return list(rows)

    async def history(self, venture_id: uuid.UUID) -> list[VentureStageChange]:
        rows = await self.session.scalars(
            select(VentureStageChange)
            .where(VentureStageChange.venture_id == venture_id)
            .order_by(VentureStageChange.created_at, VentureStageChange.id)
        )
        return list(rows)

    # ── ساخت و ویرایش ──────────────────────────────────────────────────
    async def create(self, *, actor: CurrentUser, draft: VentureDraft) -> Venture:
        """FR-VEN-01 — مرحلهٔ اول `IDEA`. §7.1: «ثبت کسب‌وکار نیمرخ کامل می‌خواهد»
        — هم‌بنیان‌گذار آینده از روی همان نیمرخ تصمیم می‌گیرد."""
        profile = await self.session.get(Profile, actor.id)
        snapshot = (
            None
            if profile is None
            else onboarding.ProfileSnapshot(
                first_name=profile.first_name,
                last_name=profile.last_name,
                survey_completed_steps=profile.survey_completed_steps,
            )
        )
        if onboarding.resolve(snapshot).state is not onboarding.OnboardingState.COMPLETE:
            raise ProfileIncomplete("برای ثبت کسب‌وکار، هر چهار گام نیمرخ را کامل کن.")
        venture = await self.build(founder_id=actor.id, draft=draft)
        await events.publish(self.session, events.VentureCreated(venture_id=venture.id))
        await self.session.commit()
        log.info("venture_created", venture_id=str(venture.id))
        return venture

    async def build(
        self,
        *,
        founder_id: uuid.UUID,
        draft: VentureDraft,
        origin_idea_id: uuid.UUID | None = None,
    ) -> Venture:
        """درج کسب‌وکار و تیمش بدون commit — برای `create` و ارتقای ایده."""
        venture = Venture(
            slug=await self._unique_slug(draft.name),
            founder_id=founder_id,
            origin_idea_id=origin_idea_id,
        )
        self._apply(venture, draft)
        self.session.add(venture)
        await self.session.flush()

        team = Team(venture_id=venture.id, name=venture.name)
        self.session.add(team)
        await self.session.flush()
        self.session.add(
            TeamMember(team_id=team.id, user_id=founder_id, is_lead=True, status="ACTIVE")
        )
        await self.session.flush()
        return venture

    async def update(self, *, venture: Venture, actor: CurrentUser, draft: VentureDraft) -> Venture:
        await self.require_manager(venture, actor)
        if venture.stage == "CLOSED":
            raise Conflict("کسب‌وکار بسته‌شده ویرایش نمی‌شود.")
        self._apply(venture, draft)
        team = await self.team_of(venture.id)
        if team is not None:
            team.name = venture.name
        await self.session.commit()
        await self.session.refresh(venture)
        return venture

    async def delete(self, *, venture: Venture, actor: CurrentUser) -> None:
        await self.require_manager(venture, actor)
        if venture.stage != "IDEA":
            raise Conflict("کسب‌وکاری که از مرحلهٔ ایده گذشته حذف نمی‌شود؛ می‌توانی آن را ببندی.")
        venture.deleted_at = _now()
        await events.publish(self.session, events.VentureDeleted(venture_id=venture.id))
        await self.session.commit()

    # ── مرحله — §7.7 ───────────────────────────────────────────────────
    async def facts(self, venture: Venture) -> rules.VentureFacts:
        filled = frozenset(
            name for name, _ in rules.PROFILE_FIELDS if _clean(getattr(venture, name)) is not None
        )
        project_ids = select(Project.id).where(Project.venture_id == venture.id)
        own_metrics = (VentureMetric.venture_id == venture.id) | (
            VentureMetric.project_id.in_(project_ids)
        )
        contacts = await self.session.scalar(
            select(func.coalesce(func.sum(VentureMetric.value), 0)).where(
                own_metrics,
                VentureMetric.status == "VERIFIED",
                VentureMetric.metric.in_(("MEETINGS", "LEADS")),
            )
        )
        sales = await self.session.scalar(
            select(func.coalesce(func.sum(VentureMetric.value), 0)).where(
                own_metrics,
                VentureMetric.status == "VERIFIED",
                VentureMetric.metric == "SALES_AMOUNT",
            )
        )
        deliverables = await self.session.scalar(
            select(func.count())
            .select_from(Deliverable)
            .join(Milestone, Milestone.id == Deliverable.milestone_id)
            .where(
                Milestone.project_id.in_(project_ids),
                Milestone.output_kind.in_(rules.MVP_OUTPUT_KINDS),
                Deliverable.status == "APPROVED",
            )
        )
        return rules.VentureFacts(
            filled_fields=filled,
            verified_contacts=int(contacts or 0),
            approved_mvp_deliverables=int(deliverables or 0),
            verified_sales_rial=int(sales or 0),
            growth_threshold_rial=self.settings.venture_growth_threshold_rial,
        )

    async def readiness(self, venture: Venture) -> rules.Readiness:
        return rules.readiness(venture.stage, await self.facts(venture))

    async def change_stage(
        self,
        *,
        venture: Venture,
        actor: CurrentUser,
        action: str,
        reason: str | None = None,
    ) -> VentureStageChange:
        await self.require_manager(venture, actor)
        if action not in STAGE_ACTIONS:
            raise ValidationFailed("عمل تغییر مرحله معتبر نیست.")
        # دو ارتقای هم‌زمان نباید هر دو از یک مرحله رد شوند.
        await self.session.execute(
            select(Venture.id).where(Venture.id == venture.id).with_for_update()
        )
        await self.session.refresh(venture)
        cleaned_reason = _clean(reason)
        current = venture.stage

        match action:
            case "ADVANCE":
                readiness = await self.readiness(venture)
                if readiness.next_stage is None:
                    raise Conflict("این کسب‌وکار در مرحله‌ای نیست که بتوان آن را ارتقا داد.")
                if not readiness.ready:
                    raise StageCriteriaNotMet(missing=readiness.missing)
                target = readiness.next_stage
                venture.paused_from_stage = None
            case "PAUSE":
                if current not in GROWTH_STAGES:
                    raise Conflict("فقط کسب‌وکار فعال متوقف می‌شود.")
                if cleaned_reason is None:
                    raise ValidationFailed("برای توقف کسب‌وکار دلیل بنویس.")
                target = "PAUSED"
                venture.paused_from_stage = current
            case "RESUME":
                if current != "PAUSED" or venture.paused_from_stage is None:
                    raise Conflict("این کسب‌وکار متوقف نیست.")
                target = venture.paused_from_stage
                venture.paused_from_stage = None
            case _:  # CLOSE
                if current == "CLOSED":
                    raise Conflict("این کسب‌وکار قبلاً بسته شده است.")
                if cleaned_reason is None:
                    raise ValidationFailed("برای بستن کسب‌وکار دلیل بنویس.")
                target = "CLOSED"
                venture.paused_from_stage = None

        venture.stage = target
        venture.stage_changed_at = _now()
        change = VentureStageChange(
            venture_id=venture.id,
            from_stage=current,
            to_stage=target,
            changed_by=actor.id,
            reason=cleaned_reason,
        )
        self.session.add(change)
        await self.session.flush()
        await events.publish(self.session, events.VentureStageChanged(change_id=change.id))
        await self.session.commit()
        log.info(
            "venture_stage_changed",
            venture_id=str(venture.id),
            from_stage=current,
            to_stage=target,
        )
        return change

    # ── تیم ────────────────────────────────────────────────────────────
    async def add_member(self, *, venture: Venture, user_id: uuid.UUID) -> TeamMember:
        """افزودن عضو — از پذیرش دعوت. فراخوان commit می‌کند."""
        if venture.stage == "CLOSED":
            raise Conflict("این کسب‌وکار بسته شده است.")
        team = await self.team_of(venture.id)
        if team is None:  # pragma: no cover — `build` همیشه تیم می‌سازد
            raise Conflict("این کسب‌وکار تیم ندارد.")
        existing = await self.session.scalar(
            select(TeamMember).where(TeamMember.team_id == team.id, TeamMember.user_id == user_id)
        )
        if existing is not None and existing.status == "ACTIVE":
            raise Conflict("این کاربر هم‌اکنون عضو تیم است.")
        if len(await self.members(venture.id)) >= MAX_VENTURE_MEMBERS:
            raise Conflict(f"تیم یک کسب‌وکار حداکثر {MAX_VENTURE_MEMBERS} نفر است.")
        if existing is not None:
            existing.status = "ACTIVE"
            existing.left_at = None
            existing.leave_reason = None
            member = existing
        else:
            member = TeamMember(team_id=team.id, user_id=user_id, status="ACTIVE")
            self.session.add(member)
        await self.session.flush()
        return member

    async def leave(self, *, venture: Venture, actor: CurrentUser) -> None:
        if actor.id == venture.founder_id:
            raise Conflict("بنیان‌گذار نمی‌تواند تیم را ترک کند؛ می‌تواند کسب‌وکار را ببندد.")
        await self._deactivate(venture, actor.id, status="LEFT", reason="ترک داوطلبانه")
        await self.session.commit()

    async def remove_member(
        self, *, venture: Venture, actor: CurrentUser, user_id: uuid.UUID, reason: str
    ) -> None:
        await self.require_manager(venture, actor)
        if user_id == venture.founder_id:
            raise Conflict("بنیان‌گذار را نمی‌توان از تیم حذف کرد.")
        if not reason.strip():
            raise ValidationFailed("برای حذف عضو دلیل بنویس.")
        await self._deactivate(venture, user_id, status="REMOVED", reason=reason)
        await self.session.commit()

    async def _deactivate(
        self, venture: Venture, user_id: uuid.UUID, *, status: str, reason: str
    ) -> None:
        member = await self.session.scalar(
            select(TeamMember)
            .join(Team, Team.id == TeamMember.team_id)
            .where(
                Team.venture_id == venture.id,
                TeamMember.user_id == user_id,
                TeamMember.status == "ACTIVE",
            )
        )
        if member is None:
            raise NotFound("این کاربر عضو فعال تیم نیست.")
        member.status = status
        member.left_at = _now()
        member.leave_reason = reason.strip() or None

    # ── درونی ──────────────────────────────────────────────────────────
    def _apply(self, venture: Venture, draft: VentureDraft) -> None:
        name = " ".join(draft.name.split())
        pitch = draft.pitch.strip()
        if not 2 <= len(name) <= 120:
            raise ValidationFailed("نام کسب‌وکار باید بین ۲ تا ۱۲۰ نویسه باشد.")
        if not 10 <= len(pitch) <= 280:
            raise ValidationFailed("معرفی یک‌خطی باید بین ۱۰ تا ۲۸۰ نویسه باشد.")
        venture.name = name
        venture.pitch = pitch
        venture.description = _clean(draft.description)
        venture.problem = _clean(draft.problem)
        venture.target_market = _clean(draft.target_market)
        venture.revenue_model = _clean(draft.revenue_model)
        venture.current_status = _clean(draft.current_status)
        venture.looking_for_cofounder = draft.looking_for_cofounder
        venture.needed_roles = _clean_roles(draft.needed_roles)

    async def _unique_slug(self, name: str) -> str:
        base = slugify(name, allow_unicode=True, max_length=SLUG_MAX_LENGTH) or "v"
        for attempt in range(SLUG_ATTEMPTS):
            candidate = base if attempt == 0 else f"{base}-{attempt + 1}"
            taken = await self.session.scalar(select(Venture.id).where(Venture.slug == candidate))
            if taken is None:
                return candidate
        return f"{base}-{uuid.uuid4().hex[:8]}"


async def require_venture_member_or_manager(
    session: AsyncSession, venture_id: uuid.UUID, actor: CurrentUser
) -> None:
    """پروژه‌ای که به کسب‌وکار وصل می‌شود — عضو تیم یا مدیر سامانه (§7.7)."""
    service = VentureService(session)
    venture = await service.require(venture_id)
    if await service.is_member(venture.id, actor.id) or await service.can_manage(venture, actor):
        return
    raise PermissionDenied("فقط اعضای تیم کسب‌وکار می‌توانند برایش پروژه بسازند.")


__all__ = [
    "MAX_VENTURE_MEMBERS",
    "STAGE_ACTIONS",
    "VentureDraft",
    "VentureService",
    "require_venture_member_or_manager",
]
