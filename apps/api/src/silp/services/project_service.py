"""چرخهٔ حیات پروژه و تیم — FR-PRJ-01/06/07/08، §7.4، §7.12.

سه چیز اینجا حساس است و هر سه صریح نوشته شده‌اند:

* **تیم هنگام انتشار ساخته می‌شود، نه هنگام پذیرش اولین عضو** (§7.12).
  وگرنه مدیر پروژه تا آمدن نفر دوم عضو تیم خودش نیست.
* **مدیر پروژه در ظرفیت حساب می‌شود.** `team_size_max = 3` یعنی مدیر و
  دو نفر دیگر.
* **نقش‌های `PROJECT_LEAD` و `PROJECT_MEMBER` مشتق‌اند** (§6.1). هر
  تغییری در عضویت باید کش نقش را باطل کند، وگرنه عضو حذف‌شده تا ۶۰
  ثانیه هنوز دسترسی دارد.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from slugify import slugify
from sqlalchemy import delete as sa_delete
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from silp.core.exceptions import (
    Conflict,
    NotFound,
    NotTeamMember,
    PermissionDenied,
    ProjectCapacityFull,
    ValidationFailed,
)
from silp.core.logging import get_logger
from silp.core.permissions import CurrentUser, Permission
from silp.domain import city as city_rules
from silp.models.delivery import Milestone, ProjectActivity
from silp.models.project import (
    PROJECT_KINDS,
    Project,
    ProjectInterest,
    ProjectRequiredAsset,
    ProjectRequiredSkill,
    ProjectRole,
    Team,
    TeamMember,
)
from silp.services import authz, events
from silp.services.city_service import CityService
from silp.services.venture_service import require_venture_member_or_manager

log = get_logger("silp.project")

# §11.8 — مرزهای مقیاس.
MAX_TEAM_MEMBERS = 20
MAX_MILESTONES_PER_PROJECT = 30

# نوع D پروژهٔ شخصی است و هر دانشجو می‌تواند بسازد (§6.2). بقیه مجوز
# `project.create.managed` می‌خواهند.
SELF_SERVICE_KIND = "D_PERSONAL"

SLUG_MAX_LENGTH = 80
SLUG_ATTEMPTS = 20

# §7.4 — گذارهای مجاز وضعیت پروژه. هر چیز دیگری ۴۰۹ است.
ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "DRAFT": frozenset({"OPEN", "CANCELLED"}),
    "OPEN": frozenset({"IN_PROGRESS", "PAUSED", "CANCELLED"}),
    "IN_PROGRESS": frozenset({"PAUSED", "COMPLETED", "CANCELLED"}),
    "PAUSED": frozenset({"IN_PROGRESS", "OPEN", "CANCELLED"}),
    "COMPLETED": frozenset(),
    "CANCELLED": frozenset(),
}


@dataclass(frozen=True, slots=True)
class SkillRequirement:
    skill_id: uuid.UUID
    min_level: int
    weight: int = 1
    is_teachable: bool = False


@dataclass(frozen=True, slots=True)
class AssetRequirement:
    asset_id: uuid.UUID
    is_mandatory: bool = False


@dataclass(frozen=True, slots=True)
class RoleSpec:
    title_fa: str
    slots: int = 1
    description: str | None = None


@dataclass(slots=True)
class ProjectDraft:
    """ورودی ساخت پروژه — FR-PRJ-01."""

    title_fa: str
    summary: str
    description: str
    kind: str
    expected_output: str
    difficulty: int = 3
    work_style: str = "EITHER"
    team_size_min: int = 1
    team_size_max: int = 1
    time_commitment_hpw: int | None = None
    tags: list[str] | None = None
    rewards: dict[str, Any] | None = None
    starts_on: date | None = None
    deadline_on: date | None = None
    applications_close_at: datetime | None = None
    required_skills: list[SkillRequirement] | None = None
    required_assets: list[AssetRequirement] | None = None
    interests: list[uuid.UUID] | None = None
    roles: list[RoleSpec] | None = None
    #: پروژهٔ یک کسب‌وکار (§7.7 «تحویل‌دادنی در پروژه‌های کسب‌وکار»).
    venture_id: uuid.UUID | None = None
    #: الگوی گردش‌کار ثابت — `CITY` هشت مرحلهٔ §7.9 را می‌سازد (ADR-0016).
    workflow: str | None = None


def _now() -> datetime:
    return datetime.now(UTC)


class ProjectService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ── خواندن ─────────────────────────────────────────────────────────
    async def get(self, project_id: uuid.UUID) -> Project | None:
        project = await self.session.get(Project, project_id)
        if project is None or project.deleted_at is not None:
            return None
        return project

    async def require(self, project_id: uuid.UUID) -> Project:
        project = await self.get(project_id)
        if project is None:
            raise NotFound("پروژه پیدا نشد.")
        return project

    async def team_of(self, project_id: uuid.UUID) -> Team | None:
        result: Team | None = await self.session.scalar(
            select(Team).where(Team.project_id == project_id)
        )
        return result

    async def active_member_count(self, project_id: uuid.UUID) -> int:
        return (
            await self.session.scalar(
                select(func.count())
                .select_from(TeamMember)
                .join(Team, Team.id == TeamMember.team_id)
                .where(Team.project_id == project_id, TeamMember.status == "ACTIVE")
            )
            or 0
        )

    async def membership(self, project_id: uuid.UUID, user_id: uuid.UUID) -> TeamMember | None:
        result: TeamMember | None = await self.session.scalar(
            select(TeamMember)
            .join(Team, Team.id == TeamMember.team_id)
            .where(
                Team.project_id == project_id,
                TeamMember.user_id == user_id,
                TeamMember.status == "ACTIVE",
            )
        )
        return result

    async def members(self, project_id: uuid.UUID) -> list[TeamMember]:
        rows = await self.session.scalars(
            select(TeamMember)
            .join(Team, Team.id == TeamMember.team_id)
            .where(Team.project_id == project_id)
            .order_by(TeamMember.is_lead.desc(), TeamMember.joined_at)
        )
        return list(rows)

    async def require_member(self, project_id: uuid.UUID, actor: CurrentUser) -> None:
        """عضویت فعال یا دسترسی سرپرستی — §6.2 «مشاهدهٔ فضای کاری»."""
        if await self.membership(project_id, actor.id) is not None:
            return
        if await authz.has_permission(
            self.session, actor, Permission.PROJECT_WORKSPACE_VIEW, project_id
        ):
            return
        raise NotTeamMember

    # ── ساخت و ویرایش ──────────────────────────────────────────────────
    async def create(self, *, actor: CurrentUser, draft: ProjectDraft) -> Project:
        """FR-PRJ-01 — پروژهٔ تازه همیشه `DRAFT` است.

        نوع `D_PERSONAL` برای همه باز است؛ A/B/C مجوز
        `project.create.managed` می‌خواهد (§6.2).
        """
        if draft.kind not in PROJECT_KINDS:
            raise ValidationFailed("نوع پروژه معتبر نیست.")
        if draft.kind != SELF_SERVICE_KIND and not await authz.has_permission(
            self.session, actor, Permission.PROJECT_CREATE_MANAGED
        ):
            raise PermissionDenied(
                "ساخت پروژهٔ کارآفرینی، پژوهشی یا حل مسئله از عهدهٔ استاد یا منتور برمی‌آید."
                " شما می‌توانید پروژهٔ شخصی بسازید.",
                permission=Permission.PROJECT_CREATE_MANAGED.value,
            )
        if draft.venture_id is not None:
            await require_venture_member_or_manager(self.session, draft.venture_id, actor)
        project = await self.build(lead_id=actor.id, draft=draft)
        await self.session.commit()

        # نقش `PROJECT_LEAD` مشتق است و همین حالا برای سازنده برقرار شد.
        await authz.invalidate_roles(actor.id)
        log.info("project_created", project_id=str(project.id), kind=draft.kind)
        return project

    async def build(
        self,
        *,
        lead_id: uuid.UUID,
        draft: ProjectDraft,
        origin_idea_id: uuid.UUID | None = None,
    ) -> Project:
        """درج پروژهٔ `DRAFT` بدون commit و بدون بررسی مجوز ساخت.

        فراخوان مسئول مجوز است: `create` مجوز ساخت را می‌سنجد، و ارتقای
        ایده (FR-IDEA-03) مجوز `idea.promote` را — استادی که ایده‌ای را
        ارتقا می‌دهد، پروژه را در همان تراکنشِ تغییر وضعیت ایده می‌سازد.
        """
        _validate_sizes(draft.team_size_min, draft.team_size_max)
        _validate_dates(draft.starts_on, draft.deadline_on)
        _validate_workflow(draft.workflow, draft.kind)

        project = Project(
            slug=await self._unique_slug(draft.title_fa),
            title_fa=draft.title_fa.strip(),
            summary=draft.summary.strip(),
            description=draft.description.strip(),
            kind=draft.kind,
            status="DRAFT",
            lead_id=lead_id,
            expected_output=draft.expected_output.strip(),
            difficulty=draft.difficulty,
            work_style=draft.work_style,
            team_size_min=draft.team_size_min,
            team_size_max=draft.team_size_max,
            time_commitment_hpw=draft.time_commitment_hpw,
            tags=list(draft.tags or []),
            rewards=dict(draft.rewards or {}),
            starts_on=draft.starts_on,
            deadline_on=draft.deadline_on,
            applications_close_at=draft.applications_close_at,
            venture_id=draft.venture_id,
            origin_idea_id=origin_idea_id,
        )
        self.session.add(project)
        await self.session.flush()
        await self._replace_requirements(project, draft)
        if draft.workflow == city_rules.WORKFLOW_CITY:
            await CityService(self.session).apply_workflow(project, starts_on=draft.starts_on)
        return project

    async def ensure_team(self, project: Project) -> Team:
        """تیم پروژه، با مدیر به‌عنوان عضو `is_lead` — اگر هنوز نیست، ساخته می‌شود.

        معمولاً انتشار تیم را می‌سازد (§7.12). ارتقای ایده زودتر می‌سازد
        تا نویسندهٔ ایده بتواند دعوت را پیش از انتشار هم بپذیرد.
        """
        team = await self.team_of(project.id)
        if team is not None:
            return team
        team = Team(project_id=project.id, name=project.title_fa)
        self.session.add(team)
        await self.session.flush()
        self.session.add(
            TeamMember(team_id=team.id, user_id=project.lead_id, is_lead=True, status="ACTIVE")
        )
        await self.session.flush()
        return team

    async def update(self, *, project: Project, actor: CurrentUser, draft: ProjectDraft) -> Project:
        """ویرایش پروژه. نوع و مدیر عوض نمی‌شوند."""
        if project.status in ("COMPLETED", "CANCELLED"):
            raise Conflict("پروژهٔ بسته‌شده ویرایش نمی‌شود.")
        _validate_sizes(draft.team_size_min, draft.team_size_max)
        _validate_dates(draft.starts_on, draft.deadline_on)

        active = await self.active_member_count(project.id)
        if draft.team_size_max < active:
            raise Conflict(
                f"این پروژه هم‌اکنون {active} عضو فعال دارد؛ ظرفیت را کمتر از آن نمی‌توان کرد."
            )

        project.title_fa = draft.title_fa.strip()
        project.summary = draft.summary.strip()
        project.description = draft.description.strip()
        project.expected_output = draft.expected_output.strip()
        project.difficulty = draft.difficulty
        project.work_style = draft.work_style
        project.team_size_min = draft.team_size_min
        project.team_size_max = draft.team_size_max
        project.time_commitment_hpw = draft.time_commitment_hpw
        project.tags = list(draft.tags or [])
        project.rewards = dict(draft.rewards or {})
        project.starts_on = draft.starts_on
        project.deadline_on = draft.deadline_on
        project.applications_close_at = draft.applications_close_at

        await self._replace_requirements(project, draft)
        await self._record(project, actor.id, "PROJECT_UPDATED", "مشخصات پروژه به‌روز شد.")
        await self.session.commit()
        return project

    # ── گذارهای وضعیت — §7.4 ───────────────────────────────────────────
    async def publish(self, *, project: Project, actor: CurrentUser) -> Project:
        """`DRAFT → OPEN` با ساخت تیم در همان تراکنش — §7.12."""
        self._require_transition(project, "OPEN")
        if project.status == "DRAFT":
            await self._require_publishable(project)

        project.status = "OPEN"
        project.last_activity_at = _now()

        await self.ensure_team(project)
        await self._record(project, actor.id, "PROJECT_PUBLISHED", "پروژه منتشر شد.")
        await self.session.commit()
        await authz.invalidate_roles(project.lead_id)
        log.info("project_published", project_id=str(project.id))
        return project

    async def start(self, *, project: Project, actor: CurrentUser) -> Project:
        """`OPEN → IN_PROGRESS` — تیم به حد نصاب رسیده یا مدیر دستی شروع کرد."""
        self._require_transition(project, "IN_PROGRESS")
        active = await self.active_member_count(project.id)
        if active < project.team_size_min:
            raise Conflict(
                f"برای شروع، دست‌کم {project.team_size_min} عضو فعال لازم است"
                f" (اکنون {active} نفر)."
            )
        project.status = "IN_PROGRESS"
        project.last_activity_at = _now()
        # §7.6 — مراحل با شروع پروژه فعال می‌شوند.
        for milestone in await self._milestones(project.id):
            if milestone.status == "PENDING":
                milestone.status = "IN_PROGRESS"
        await self._record(project, actor.id, "PROJECT_STARTED", "کار پروژه شروع شد.")
        await self.session.commit()
        return project

    async def pause(self, *, project: Project, actor: CurrentUser, reason: str) -> Project:
        self._require_transition(project, "PAUSED")
        if not reason.strip():
            raise ValidationFailed("برای توقف پروژه باید دلیل بنویسید.")
        project.status = "PAUSED"
        await self._record(
            project, actor.id, "PROJECT_PAUSED", f"پروژه موقتاً متوقف شد: {reason.strip()}"
        )
        await self.session.commit()
        return project

    async def resume(self, *, project: Project, actor: CurrentUser) -> Project:
        """`PAUSED → OPEN`.

        همیشه به `OPEN` برمی‌گردد، نه به `IN_PROGRESS`. حدس زدن وضعیت
        پیش از توقف ممکن نیست (مدیر همیشه عضو فعال است، پس «تیم دارد»
        سیگنال نیست)، و پروژه‌ای که ماه‌ها متوقف بوده احتمالاً عضو تازه
        هم لازم دارد. برای شروع دوبارهٔ کار، `POST /start` هست.
        """
        self._require_transition(project, "OPEN")
        project.status = "OPEN"
        project.last_activity_at = _now()
        await self._record(project, actor.id, "PROJECT_RESUMED", "پروژه از سر گرفته شد.")
        await self.session.commit()
        return project

    async def cancel(self, *, project: Project, actor: CurrentUser, reason: str) -> Project:
        """§7.4 — لغو پروژه امتیازهای کسب‌شده را پس نمی‌گیرد."""
        self._require_transition(project, "CANCELLED")
        if not reason.strip():
            raise ValidationFailed("برای لغو پروژه باید دلیل بنویسید.")
        project.status = "CANCELLED"
        await self._record(
            project, actor.id, "PROJECT_CANCELLED", f"پروژه لغو شد: {reason.strip()}"
        )
        await self.session.commit()
        return project

    async def complete(self, *, project: Project, actor: CurrentUser, final_report: str) -> Project:
        """FR-PRJ-08 — بستن پروژه: همهٔ مراحل الزامی تأیید + گزارش نهایی."""
        self._require_transition(project, "COMPLETED")
        if not final_report.strip():
            raise ValidationFailed("بستن پروژه بدون گزارش نهایی ممکن نیست.")

        pending = [
            m
            for m in await self._milestones(project.id)
            if m.is_required and m.status != "APPROVED"
        ]
        if pending:
            titles = "، ".join(m.title_fa for m in pending[:3])
            raise Conflict(f"این مراحل الزامی هنوز تأیید نشده‌اند: {titles}")

        project.status = "COMPLETED"
        project.health = "HEALTHY"
        rewards = dict(project.rewards)
        rewards["final_report"] = final_report.strip()
        project.rewards = rewards
        await self._record(project, actor.id, "PROJECT_COMPLETED", "پروژه با موفقیت بسته شد.")
        await events.publish(
            self.session, events.ProjectCompleted(project_id=project.id, completed_by=actor.id)
        )
        await self.session.commit()
        log.info("project_completed", project_id=str(project.id))
        return project

    # ── تیم — FR-TEAM-03 ───────────────────────────────────────────────
    async def add_member(
        self,
        *,
        project: Project,
        user_id: uuid.UUID,
        role_id: uuid.UUID | None = None,
    ) -> TeamMember:
        """افزودن عضو با احترام به ظرفیت. فراخوان باید ردیف پروژه را قفل کرده باشد.

        قفل در `ApplicationService.decide` گرفته می‌شود (§7.12 «ظرفیت
        پروژه تحت رقابت»)؛ اینجا دوباره گرفته نمی‌شود تا قفل تودرتو
        نشود، ولی شمارش ظرفیت باز هم انجام می‌گیرد — دفاع در عمق.
        """
        team = await self.team_of(project.id)
        if team is None:
            raise Conflict("این پروژه هنوز منتشر نشده است.")

        existing = await self.session.scalar(
            select(TeamMember).where(TeamMember.team_id == team.id, TeamMember.user_id == user_id)
        )
        if existing is not None and existing.status == "ACTIVE":
            raise Conflict("این کاربر هم‌اکنون عضو تیم است.")

        active = await self.active_member_count(project.id)
        if active >= min(project.team_size_max, MAX_TEAM_MEMBERS):
            raise ProjectCapacityFull

        if existing is not None:
            # عضوی که قبلاً رفته بود، برمی‌گردد: همان ردیف زنده می‌شود تا
            # ایندکس یکتای عضویت فعال نشکند.
            existing.status = "ACTIVE"
            existing.left_at = None
            existing.leave_reason = None
            existing.role_id = role_id
            member = existing
        else:
            member = TeamMember(team_id=team.id, user_id=user_id, role_id=role_id, status="ACTIVE")
            self.session.add(member)

        if role_id is not None:
            await self._bump_role_filled(role_id, +1)
        project.last_activity_at = _now()
        await self.session.flush()
        return member

    async def remove_member(
        self, *, project: Project, user_id: uuid.UUID, actor: CurrentUser, reason: str
    ) -> None:
        """حذف عضو توسط مدیر پروژه — FR-TEAM-03."""
        if user_id == project.lead_id:
            raise Conflict("مدیر پروژه را نمی‌توان از تیم حذف کرد.")
        member = await self.membership(project.id, user_id)
        if member is None:
            raise NotFound("این کاربر عضو فعال تیم نیست.")
        await self._deactivate(member, status="REMOVED", reason=reason)
        await CityService(self.session).release_ownership(project, user_id)
        await self._record(
            project, actor.id, "MEMBER_REMOVED", "یکی از اعضا از تیم کنار گذاشته شد."
        )
        await self.session.commit()
        await authz.invalidate_roles(user_id)

    async def leave(self, *, project: Project, actor: CurrentUser, reason: str) -> None:
        """ترک داوطلبانهٔ تیم."""
        if actor.id == project.lead_id:
            raise Conflict(
                "مدیر پروژه نمی‌تواند تیم را ترک کند؛ اول مدیریت را واگذار یا پروژه را لغو کنید."
            )
        member = await self.membership(project.id, actor.id)
        if member is None:
            raise NotTeamMember
        await self._deactivate(member, status="LEFT", reason=reason)
        await CityService(self.session).release_ownership(project, actor.id)
        await self._record(project, actor.id, "MEMBER_LEFT", "یکی از اعضا تیم را ترک کرد.")
        await self.session.commit()
        await authz.invalidate_roles(actor.id)

    # ── جریان فعالیت ───────────────────────────────────────────────────
    async def activity(self, project_id: uuid.UUID, *, limit: int = 50) -> list[ProjectActivity]:
        rows = await self.session.scalars(
            select(ProjectActivity)
            .where(ProjectActivity.project_id == project_id)
            # شناسه تساوی `created_at` را می‌شکند — §همان نکتهٔ گفتگو.
            .order_by(ProjectActivity.created_at.desc(), ProjectActivity.id.desc())
            .limit(limit)
        )
        return list(rows)

    async def record_activity(
        self,
        project: Project,
        actor_id: uuid.UUID | None,
        kind: str,
        summary: str,
        *,
        entity_type: str | None = None,
        entity_id: uuid.UUID | None = None,
        commit: bool = True,
    ) -> None:
        """ثبت رویداد + به‌روزرسانی `last_activity_at` — §7.4."""
        await self._record(
            project, actor_id, kind, summary, entity_type=entity_type, entity_id=entity_id
        )
        if commit:
            await self.session.commit()

    # ── درونی ──────────────────────────────────────────────────────────
    async def _record(
        self,
        project: Project,
        actor_id: uuid.UUID | None,
        kind: str,
        summary: str,
        *,
        entity_type: str | None = None,
        entity_id: uuid.UUID | None = None,
    ) -> None:
        self.session.add(
            ProjectActivity(
                project_id=project.id,
                actor_id=actor_id,
                kind=kind,
                summary=summary,
                entity_type=entity_type,
                entity_id=entity_id,
            )
        )
        project.last_activity_at = _now()

    async def _milestones(self, project_id: uuid.UUID) -> list[Milestone]:
        rows = await self.session.scalars(
            select(Milestone)
            .where(Milestone.project_id == project_id)
            .order_by(Milestone.sort_order)
        )
        return list(rows)

    async def _require_publishable(self, project: Project) -> None:
        """§7.4 — شرط `DRAFT → OPEN`: دست‌کم یک مرحله و یک مهارت لازم.

        بدون مرحله، پروژه تحویل‌دادنی ندارد و بدون مهارت لازم، توصیه‌گر
        نمی‌داند به چه کسی پیشنهادش بدهد.
        """
        problems: list[str] = []
        if not await self._milestones(project.id):
            problems.append("دست‌کم یک مرحله تعریف کنید")
        has_skill = await self.session.scalar(
            select(func.count())
            .select_from(ProjectRequiredSkill)
            .where(ProjectRequiredSkill.project_id == project.id)
        )
        if not has_skill:
            problems.append("دست‌کم یک مهارت مورد نیاز مشخص کنید")
        if problems:
            raise Conflict("برای انتشار پروژه: " + "، ".join(problems) + ".")

    def _require_transition(self, project: Project, target: str) -> None:
        if target not in ALLOWED_TRANSITIONS.get(project.status, frozenset()):
            raise Conflict(f"پروژه در وضعیت «{project.status}» است و این تغییر روی آن ممکن نیست.")

    async def _deactivate(self, member: TeamMember, *, status: str, reason: str) -> None:
        member.status = status
        member.left_at = _now()
        member.leave_reason = reason.strip() or None
        if member.role_id is not None:
            await self._bump_role_filled(member.role_id, -1)

    async def _bump_role_filled(self, role_id: uuid.UUID, delta: int) -> None:
        """§7.12 — `project_roles.filled` در لایهٔ سرویس نگه داشته می‌شود."""
        role = await self.session.get(ProjectRole, role_id)
        if role is None:
            return
        role.filled = max(0, min(role.slots, role.filled + delta))

    async def _replace_requirements(self, project: Project, draft: ProjectDraft) -> None:
        """جایگزینی کامل مشخصات تطابق — ویرایش جزئی معنا ندارد.

        **به مجموعه‌های ORM مقدار داده نمی‌شود.** انتساب به یک رابطه،
        SQLAlchemy را وادار می‌کند اول مقدار قبلی را بخواند، و آن خواندن
        از دل یک تابع async بیرون از greenlet انجام می‌شود و با
        `MissingGreenlet` می‌شکند. پس حذف و درج صریح‌اند.
        """
        await self.session.execute(
            sa_delete(ProjectRequiredSkill).where(ProjectRequiredSkill.project_id == project.id)
        )
        await self.session.execute(
            sa_delete(ProjectRequiredAsset).where(ProjectRequiredAsset.project_id == project.id)
        )
        await self.session.execute(
            sa_delete(ProjectInterest).where(ProjectInterest.project_id == project.id)
        )
        self.session.add_all(
            [
                ProjectRequiredSkill(
                    project_id=project.id,
                    skill_id=r.skill_id,
                    min_level=r.min_level,
                    weight=r.weight,
                    is_teachable=r.is_teachable,
                )
                for r in (draft.required_skills or [])
            ]
        )
        self.session.add_all(
            [
                ProjectRequiredAsset(
                    project_id=project.id, asset_id=r.asset_id, is_mandatory=r.is_mandatory
                )
                for r in (draft.required_assets or [])
            ]
        )
        self.session.add_all(
            [ProjectInterest(project_id=project.id, interest_id=i) for i in (draft.interests or [])]
        )

        if draft.roles is not None:
            await self._replace_roles(project, draft.roles)
        await self.session.flush()
        # مجموعه‌های بارگذاری‌شدهٔ قبلی کهنه‌اند؛ پاسخ باید تازه‌ها را
        # نشان بدهد، نه چیزی که پیش از این تراکنش خوانده شده بود.
        await self.session.refresh(project)

    async def _replace_roles(self, project: Project, specs: list[RoleSpec]) -> None:
        """نقش‌های پرشده حذف نمی‌شوند: عضوی روی آن نقش نشسته است."""
        rows = await self.session.scalars(
            select(ProjectRole).where(ProjectRole.project_id == project.id)
        )
        existing = {role.title_fa: role for role in rows}
        for spec in specs:
            role = existing.pop(spec.title_fa, None)
            if role is None:
                self.session.add(
                    ProjectRole(
                        project_id=project.id,
                        title_fa=spec.title_fa,
                        description=spec.description,
                        slots=spec.slots,
                    )
                )
                continue
            role.description = spec.description
            role.slots = max(spec.slots, role.filled)
        for orphan in existing.values():
            if orphan.filled == 0:
                await self.session.delete(orphan)

    async def _unique_slug(self, title: str) -> str:
        """نشانی یکتا از عنوان فارسی.

        `slugify` با `allow_unicode` نام فارسی را نگه می‌دارد؛ اگر عنوان
        هیچ نویسهٔ قابل استفاده‌ای نداشته باشد، به `p-<شناسه>` برمی‌گردد.
        """
        base = slugify(title, allow_unicode=True, max_length=SLUG_MAX_LENGTH) or "p"
        for attempt in range(SLUG_ATTEMPTS):
            candidate = base if attempt == 0 else f"{base}-{attempt + 1}"
            taken = await self.session.scalar(select(Project.id).where(Project.slug == candidate))
            if taken is None:
                return candidate
        return f"{base}-{uuid.uuid4().hex[:8]}"


def _validate_sizes(minimum: int, maximum: int) -> None:
    if minimum < 1:
        raise ValidationFailed("حداقل اندازهٔ تیم باید دست‌کم ۱ باشد.")
    if maximum < minimum:
        raise ValidationFailed("حداکثر اندازهٔ تیم نمی‌تواند از حداقل کمتر باشد.")
    if maximum > MAX_TEAM_MEMBERS:
        raise ValidationFailed(f"حداکثر اندازهٔ تیم {MAX_TEAM_MEMBERS} نفر است.")


def _validate_workflow(workflow: str | None, kind: str) -> None:
    if workflow is None:
        return
    if workflow not in city_rules.WORKFLOWS:
        raise ValidationFailed("الگوی گردش‌کار معتبر نیست.")
    if kind != city_rules.WORKFLOW_KIND:
        raise ValidationFailed(
            "الگوی گردش‌کار شهر هوشمند فقط برای پروژهٔ «حل مسئلهٔ واقعی» (نوع C) است."
        )


def _validate_dates(starts_on: date | None, deadline_on: date | None) -> None:
    if starts_on and deadline_on and deadline_on < starts_on:
        raise ValidationFailed("مهلت پروژه نمی‌تواند پیش از تاریخ شروع باشد.")


__all__ = [
    "ALLOWED_TRANSITIONS",
    "MAX_MILESTONES_PER_PROJECT",
    "MAX_TEAM_MEMBERS",
    "AssetRequirement",
    "ProjectDraft",
    "ProjectService",
    "RoleSpec",
    "SkillRequirement",
]
