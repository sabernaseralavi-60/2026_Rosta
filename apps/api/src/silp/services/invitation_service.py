"""دعوت به تیم — FR-TEAM-03، §7.8، M7-02.

دعوت به **تیم** است؛ تیم یا مال پروژه است یا مال کسب‌وکار، و پذیرش در
هر دو یعنی یک ردیف فعال `team_members`. قواعد:

* دعوت دوباره به همان کاربر، همان دعوت باز را برمی‌گرداند (ایندکس یکتای
  `idx_team_invitations_open`) — نه خطا، نه دعوت دوم.
* دعوت ۱۴ روز اعتبار دارد. «منقضی» وضعیت ذخیره‌شده نیست؛ دعوتی که
  مهلتش گذشته پذیرفته نمی‌شود و در فهرست نمی‌آید.
* پذیرش پروژه همان ظرفیت درخواست پیوستن را رعایت می‌کند: سطر پروژه
  `FOR UPDATE` قفل می‌شود (§7.12).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from silp.core.exceptions import (
    Conflict,
    InvitationClosed,
    NotFound,
    PermissionDenied,
    ValidationFailed,
)
from silp.core.permissions import CurrentUser, Permission
from silp.models.identity import User
from silp.models.project import Project, Team, TeamInvitation, TeamMember
from silp.models.venture import Venture
from silp.services import authz, events
from silp.services.project_service import ProjectService
from silp.services.venture_service import VentureService

MESSAGE_MAX = 500
CLOSED_PROJECT_STATUSES = ("COMPLETED", "CANCELLED")


@dataclass(frozen=True, slots=True)
class InvitationTarget:
    """پروژه یا کسب‌وکارِ تیمی که دعوت به آن است."""

    team: Team
    project: Project | None = None
    venture: Venture | None = None

    @property
    def kind(self) -> str:
        return "PROJECT" if self.project is not None else "VENTURE"

    @property
    def target_id(self) -> uuid.UUID:
        entity = self.project or self.venture
        assert entity is not None
        return entity.id

    @property
    def title(self) -> str:
        if self.project is not None:
            return self.project.title_fa
        assert self.venture is not None
        return self.venture.name

    @property
    def href(self) -> str:
        if self.project is not None:
            return f"/projects/{self.project.id}"
        return f"/ventures/{self.target_id}"


def _now() -> datetime:
    return datetime.now(UTC)


class InvitationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.projects = ProjectService(session)
        self.ventures = VentureService(session)

    # ── ساخت ───────────────────────────────────────────────────────────
    async def invite(
        self,
        *,
        team: Team,
        inviter_id: uuid.UUID,
        invitee_id: uuid.UUID,
        source: str = "DIRECT",
        message: str | None = None,
        role_id: uuid.UUID | None = None,
        commit: bool = True,
    ) -> TeamInvitation:
        """دعوت، یا همان دعوت باز قبلی. مجوز دعوت‌کننده را فراخوان سنجیده است."""
        if inviter_id == invitee_id:
            raise ValidationFailed("نمی‌توانی خودت را دعوت کنی.")
        invitee = await self.session.get(User, invitee_id)
        if invitee is None or invitee.deleted_at is not None or invitee.status != "ACTIVE":
            raise NotFound("کاربر پیدا نشد.")
        active = await self.session.scalar(
            select(TeamMember.id).where(
                TeamMember.team_id == team.id,
                TeamMember.user_id == invitee_id,
                TeamMember.status == "ACTIVE",
            )
        )
        if active is not None:
            raise Conflict("این کاربر هم‌اکنون عضو تیم است.")
        cleaned = (message or "").strip() or None
        if cleaned is not None and len(cleaned) > MESSAGE_MAX:
            raise ValidationFailed(f"پیام دعوت حداکثر {MESSAGE_MAX} نویسه است.")

        existing = await self._open_invitation(team.id, invitee_id)
        if existing is not None and existing.expires_at > _now():
            return existing
        if existing is not None:
            # دعوت منقضی جای دعوت تازه را گرفته بود؛ بسته می‌شود.
            existing.status = "CANCELLED"
            existing.responded_at = _now()
            await self.session.flush()

        created = await self.session.scalar(
            insert(TeamInvitation)
            .values(
                team_id=team.id,
                inviter_id=inviter_id,
                invitee_id=invitee_id,
                role_id=role_id,
                message=cleaned,
                source=source,
            )
            .on_conflict_do_nothing()
            .returning(TeamInvitation.id)
        )
        if created is None:
            # دو دعوت هم‌زمان — دیگری زودتر ثبت شد.
            existing = await self._open_invitation(team.id, invitee_id)
            assert existing is not None
            return existing
        invitation = await self.session.get(TeamInvitation, created)
        assert invitation is not None
        await events.publish(self.session, events.InvitationSent(invitation_id=invitation.id))
        if commit:
            await self.session.commit()
        return invitation

    async def invite_to_project(
        self,
        *,
        project: Project,
        actor: CurrentUser,
        invitee_id: uuid.UUID,
        message: str | None = None,
        role_id: uuid.UUID | None = None,
    ) -> TeamInvitation:
        """FR-TEAM-03 «دعوت مستقیم از نیمرخ» — همان مجوز تصمیم دربارهٔ درخواست."""
        if not await authz.has_permission(
            self.session, actor, Permission.PROJECT_APPLICATION_DECIDE, project.id
        ):
            raise PermissionDenied(permission=Permission.PROJECT_APPLICATION_DECIDE.value)
        if project.status in CLOSED_PROJECT_STATUSES:
            raise Conflict("این پروژه بسته شده است.")
        team = await self.projects.team_of(project.id)
        if team is None:
            raise Conflict("پیش از دعوت، پروژه را منتشر کن.")
        return await self.invite(
            team=team, inviter_id=actor.id, invitee_id=invitee_id, message=message, role_id=role_id
        )

    async def invite_to_venture(
        self,
        *,
        venture: Venture,
        actor: CurrentUser,
        invitee_id: uuid.UUID,
        message: str | None = None,
    ) -> TeamInvitation:
        await self.ventures.require_manager(venture, actor)
        if venture.stage == "CLOSED":
            raise Conflict("این کسب‌وکار بسته شده است.")
        team = await self.ventures.team_of(venture.id)
        if team is None:  # pragma: no cover
            raise Conflict("این کسب‌وکار تیم ندارد.")
        return await self.invite(
            team=team, inviter_id=actor.id, invitee_id=invitee_id, message=message
        )

    # ── خواندن ─────────────────────────────────────────────────────────
    async def require(self, invitation_id: uuid.UUID) -> TeamInvitation:
        invitation = await self.session.get(TeamInvitation, invitation_id)
        if invitation is None:
            raise NotFound("دعوت پیدا نشد.")
        return invitation

    async def target_of(self, team_id: uuid.UUID) -> InvitationTarget:
        team = await self.session.get(Team, team_id)
        if team is None:
            raise NotFound("تیم پیدا نشد.")
        if team.project_id is not None:
            return InvitationTarget(team=team, project=await self.projects.require(team.project_id))
        assert team.venture_id is not None
        return InvitationTarget(team=team, venture=await self.ventures.require(team.venture_id))

    async def pending_for(self, user_id: uuid.UUID) -> list[TeamInvitation]:
        rows = await self.session.scalars(
            select(TeamInvitation)
            .where(
                TeamInvitation.invitee_id == user_id,
                TeamInvitation.status == "PENDING",
                TeamInvitation.expires_at > _now(),
            )
            .order_by(TeamInvitation.created_at.desc())
        )
        return list(rows)

    async def sent_for_team(self, team_id: uuid.UUID) -> list[TeamInvitation]:
        rows = await self.session.scalars(
            select(TeamInvitation)
            .where(
                TeamInvitation.team_id == team_id,
                TeamInvitation.status == "PENDING",
                TeamInvitation.expires_at > _now(),
            )
            .order_by(TeamInvitation.created_at.desc())
        )
        return list(rows)

    # ── پاسخ ───────────────────────────────────────────────────────────
    async def accept(self, *, invitation_id: uuid.UUID, actor: CurrentUser) -> InvitationTarget:
        invitation = await self._require_own_open(invitation_id, actor)
        target = await self.target_of(invitation.team_id)
        if target.project is not None:
            project = target.project
            if project.status in CLOSED_PROJECT_STATUSES:
                raise Conflict("این پروژه بسته شده است.")
            await self.session.execute(
                select(Project.id).where(Project.id == project.id).with_for_update()
            )
            await self.projects.add_member(
                project=project, user_id=actor.id, role_id=invitation.role_id
            )
            await self.projects.record_activity(
                project,
                actor.id,
                "MEMBER_JOINED",
                "عضو تازه‌ای با دعوت به تیم پیوست.",
                entity_type="invitation",
                entity_id=invitation.id,
                commit=False,
            )
        else:
            assert target.venture is not None
            await self.session.execute(
                select(Venture.id).where(Venture.id == target.venture.id).with_for_update()
            )
            await self.ventures.add_member(venture=target.venture, user_id=actor.id)

        invitation.status = "ACCEPTED"
        invitation.responded_at = _now()
        await events.publish(self.session, events.InvitationAccepted(invitation_id=invitation.id))
        await self.session.commit()
        await authz.invalidate_roles(actor.id)
        return target

    async def decline(self, *, invitation_id: uuid.UUID, actor: CurrentUser) -> None:
        invitation = await self._require_own_open(invitation_id, actor)
        invitation.status = "DECLINED"
        invitation.responded_at = _now()
        await self.session.commit()

    async def cancel(self, *, invitation_id: uuid.UUID, actor: CurrentUser) -> None:
        """دعوت‌کننده، یا کسی که همین حالا حق دعوت به این تیم را دارد."""
        invitation = await self.require(invitation_id)
        if invitation.status != "PENDING":
            raise InvitationClosed
        if invitation.inviter_id != actor.id and not await self._may_invite(
            invitation.team_id, actor
        ):
            raise NotFound("دعوت پیدا نشد.")
        invitation.status = "CANCELLED"
        invitation.responded_at = _now()
        await self.session.commit()

    # ── درونی ──────────────────────────────────────────────────────────
    async def _open_invitation(
        self, team_id: uuid.UUID, invitee_id: uuid.UUID
    ) -> TeamInvitation | None:
        found: TeamInvitation | None = await self.session.scalar(
            select(TeamInvitation).where(
                TeamInvitation.team_id == team_id,
                TeamInvitation.invitee_id == invitee_id,
                TeamInvitation.status == "PENDING",
            )
        )
        return found

    async def _require_own_open(
        self, invitation_id: uuid.UUID, actor: CurrentUser
    ) -> TeamInvitation:
        invitation = await self.session.scalar(
            select(TeamInvitation).where(TeamInvitation.id == invitation_id).with_for_update()
        )
        # دعوت دیگران برای این کاربر «وجود ندارد» — §6.4 قاعدهٔ ۴.
        if invitation is None or invitation.invitee_id != actor.id:
            raise NotFound("دعوت پیدا نشد.")
        if invitation.status != "PENDING" or invitation.expires_at <= _now():
            raise InvitationClosed
        return invitation

    async def _may_invite(self, team_id: uuid.UUID, actor: CurrentUser) -> bool:
        target = await self.target_of(team_id)
        if target.project is not None:
            return await authz.has_permission(
                self.session, actor, Permission.PROJECT_APPLICATION_DECIDE, target.project.id
            )
        assert target.venture is not None
        return await self.ventures.can_manage(target.venture, actor)


__all__ = ["InvitationService", "InvitationTarget"]
