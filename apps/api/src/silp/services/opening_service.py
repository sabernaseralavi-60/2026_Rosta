"""آگهی نیاز به هم‌تیمی — FR-TEAM-02/03، M7-08، ADR-0015.

## چه کسی چه می‌کند

| عمل | پروژه | کسب‌وکار |
|-----|--------|----------|
| ثبت، ویرایش، بستن، تمدید، تصمیم | `project.application.decide` (قلمرو پروژه) | بنیان‌گذار |
| درخواست | هر کسی با نیمرخ کامل که عضو تیم نیست | همان |

## چرخه

```
OPEN ──پذیرش یک درخواست──► FILLED   (بقیهٔ درخواست‌های باز خودکار رد می‌شوند)
  │
  ├──بستن──► CLOSED
  └──گذشتن expires_at──► «منقضی» (ذخیره نمی‌شود؛ تمدید آن را باز می‌کند)
```

«منقضی» مثل دعوت (ADR-0014) از `expires_at` خوانده می‌شود، نه از ستون
وضعیت: آگهی منقضی درخواست تازه نمی‌پذیرد و در فهرست عمومی نیست، ولی
آگهی‌دهنده هنوز می‌تواند دربارهٔ درخواست‌هایی که پیش از مهلت رسیده‌اند
تصمیم بگیرد.

## امتیاز

`TEAM_FORMED` (۱۵، `COMMUNITY`) به آگهی‌دهنده می‌رسد، ولی نه در لحظهٔ
پذیرش: §9.8 «تشکیل تیم صوری ⇒ فقط پس از اولین تحویل‌دادنی تأییدشدهٔ تیم».
شنونده‌اش در `point_listeners` است.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from silp.core.exceptions import (
    Conflict,
    DuplicateApplication,
    NotFound,
    OpeningClosed,
    PermissionDenied,
    ProfileIncomplete,
    TooManyOpenApplications,
    ValidationFailed,
)
from silp.core.logging import get_logger
from silp.core.permissions import CurrentUser, Permission
from silp.domain.identity import onboarding
from silp.models.delivery import (
    MAX_OPENING_SKILLS,
    OPENING_DESCRIPTION_MAX,
    OPENING_MESSAGE_MAX,
    OPENING_TITLE_MAX,
    OpeningApplication,
    TeamOpening,
)
from silp.models.profile import Profile, ProfileSkill
from silp.models.project import Project, ProjectRole, Team, TeamMember
from silp.models.taxonomy import Skill
from silp.models.venture import Venture
from silp.services import authz, events
from silp.services.notification_service import NotificationService
from silp.services.project_service import ProjectService
from silp.services.venture_service import VentureService

log = get_logger("silp.openings")

OPENING_LIFETIME = timedelta(days=30)
EXPIRY_NOTICE_WINDOW = timedelta(days=7)
DECISIONS = ("ACCEPTED", "DECLINED")
MAX_OPEN_APPLICATIONS = 5
ACTIVE_PROJECT_STATUSES = ("OPEN", "IN_PROGRESS")
#: اعلان هدفمند — «واجد شرایط» یعنی دست‌کم یک مهارت لازم در سطح ۳ به بالا.
MATCH_MIN_LEVEL = 3
MATCH_LIMIT = 20
FILLED_NOTE = "این جای خالی پر شد."


@dataclass(slots=True)
class OpeningDraft:
    title: str
    description: str
    needed_skills: list[uuid.UUID]
    commitment_hpw: int | None = None
    role_id: uuid.UUID | None = None


@dataclass(frozen=True, slots=True)
class OpeningTarget:
    """پروژه یا کسب‌وکاری که آگهی برای تیمش است."""

    project: Project | None = None
    venture: Venture | None = None

    @property
    def kind(self) -> str:
        return "PROJECT" if self.project is not None else "VENTURE"

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
        assert self.venture is not None
        return f"/ventures/{self.venture.id}"

    @property
    def is_closed(self) -> bool:
        if self.project is not None:
            return self.project.status not in ACTIVE_PROJECT_STATUSES
        assert self.venture is not None
        return self.venture.stage == "CLOSED"


def _now() -> datetime:
    return datetime.now(UTC)


class OpeningService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.projects = ProjectService(session)
        self.ventures = VentureService(session)

    # ── هدف و دسترسی ───────────────────────────────────────────────────
    async def target_of(self, opening: TeamOpening) -> OpeningTarget:
        if opening.project_id is not None:
            return OpeningTarget(project=await self.projects.require(opening.project_id))
        assert opening.venture_id is not None
        return OpeningTarget(venture=await self.ventures.require(opening.venture_id))

    async def can_manage(self, target: OpeningTarget, actor: CurrentUser | None) -> bool:
        if actor is None:
            return False
        if target.project is not None:
            return await authz.has_permission(
                self.session, actor, Permission.PROJECT_APPLICATION_DECIDE, target.project.id
            )
        assert target.venture is not None
        return await self.ventures.can_manage(target.venture, actor)

    async def _require_manager(self, target: OpeningTarget, actor: CurrentUser) -> None:
        if not await self.can_manage(target, actor):
            raise PermissionDenied(
                "آگهی این تیم را مدیر پروژه یا بنیان‌گذار کسب‌وکار مدیریت می‌کند.",
                permission=Permission.PROJECT_APPLICATION_DECIDE.value,
            )

    async def team_of(self, target: OpeningTarget) -> Team | None:
        if target.project is not None:
            return await self.projects.team_of(target.project.id)
        assert target.venture is not None
        return await self.ventures.team_of(target.venture.id)

    async def is_member(self, target: OpeningTarget, user_id: uuid.UUID) -> bool:
        team = await self.team_of(target)
        if team is None:
            return False
        found = await self.session.scalar(
            select(TeamMember.id).where(
                TeamMember.team_id == team.id,
                TeamMember.user_id == user_id,
                TeamMember.status == "ACTIVE",
            )
        )
        return found is not None

    # ── خواندن ─────────────────────────────────────────────────────────
    async def require(self, opening_id: uuid.UUID) -> TeamOpening:
        opening = await self.session.get(TeamOpening, opening_id)
        if opening is None:
            raise NotFound("آگهی پیدا نشد.")
        return opening

    async def require_visible(
        self, opening_id: uuid.UUID, actor: CurrentUser | None
    ) -> tuple[TeamOpening, OpeningTarget]:
        """آگهی باز برای همه؛ آگهی بسته، پر یا منقضی فقط برای مدیرانش و درخواست‌دهندگانش."""
        opening = await self.require(opening_id)
        target = await self.target_of(opening)
        if opening.is_open_at(_now()) or await self.can_manage(target, actor):
            return opening, target
        if actor is not None:
            applied = await self.session.scalar(
                select(OpeningApplication.id).where(
                    OpeningApplication.opening_id == opening.id,
                    OpeningApplication.applicant_id == actor.id,
                )
            )
            if applied is not None:
                return opening, target
        raise NotFound("آگهی پیدا نشد.")

    def list_query(
        self,
        *,
        q: str | None = None,
        skill_id: uuid.UUID | None = None,
        kind: str | None = None,
        project_id: uuid.UUID | None = None,
        venture_id: uuid.UUID | None = None,
        poster_id: uuid.UUID | None = None,
        include_closed: bool = False,
    ) -> Select[tuple[TeamOpening]]:
        stmt = select(TeamOpening)
        if not include_closed:
            stmt = stmt.where(TeamOpening.status == "OPEN", TeamOpening.expires_at > func.now())
        if project_id is not None:
            stmt = stmt.where(TeamOpening.project_id == project_id)
        if venture_id is not None:
            stmt = stmt.where(TeamOpening.venture_id == venture_id)
        if poster_id is not None:
            stmt = stmt.where(TeamOpening.poster_id == poster_id)
        if kind == "PROJECT":
            stmt = stmt.where(TeamOpening.project_id.is_not(None))
        elif kind == "VENTURE":
            stmt = stmt.where(TeamOpening.venture_id.is_not(None))
        if skill_id is not None:
            stmt = stmt.where(TeamOpening.needed_skills.contains([skill_id]))
        if q and q.strip():
            needle = func.concat("%", func.fa_normalize(q.strip()), "%")
            stmt = stmt.where(
                func.fa_normalize(TeamOpening.title + " " + TeamOpening.description).like(needle)
            )
        return stmt.order_by(TeamOpening.created_at.desc(), TeamOpening.id)

    async def page(
        self, stmt: Select[tuple[TeamOpening]], *, offset: int, limit: int
    ) -> tuple[list[TeamOpening], int]:
        total = await self.session.scalar(select(func.count()).select_from(stmt.subquery()))
        rows = await self.session.scalars(stmt.offset(offset).limit(limit))
        return list(rows), int(total or 0)

    async def targets_for(self, openings: list[TeamOpening]) -> dict[uuid.UUID, OpeningTarget]:
        """هدف هر آگهی — دو کوئری برای کل فهرست، نه یکی به‌ازای هر ردیف."""
        project_ids = {o.project_id for o in openings if o.project_id is not None}
        venture_ids = {o.venture_id for o in openings if o.venture_id is not None}
        projects = (
            {
                p.id: p
                for p in await self.session.scalars(
                    select(Project).where(Project.id.in_(project_ids))
                )
            }
            if project_ids
            else {}
        )
        ventures = (
            {
                v.id: v
                for v in await self.session.scalars(
                    select(Venture).where(Venture.id.in_(venture_ids))
                )
            }
            if venture_ids
            else {}
        )
        result: dict[uuid.UUID, OpeningTarget] = {}
        for opening in openings:
            if opening.project_id is not None and opening.project_id in projects:
                result[opening.id] = OpeningTarget(project=projects[opening.project_id])
            elif opening.venture_id is not None and opening.venture_id in ventures:
                result[opening.id] = OpeningTarget(venture=ventures[opening.venture_id])
        return result

    async def pending_counts(self, opening_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
        if not opening_ids:
            return {}
        rows = await self.session.execute(
            select(OpeningApplication.opening_id, func.count())
            .where(
                OpeningApplication.opening_id.in_(opening_ids),
                OpeningApplication.status == "PENDING",
            )
            .group_by(OpeningApplication.opening_id)
        )
        return {oid: int(n) for oid, n in rows}

    async def my_application(
        self, opening_id: uuid.UUID, user_id: uuid.UUID
    ) -> OpeningApplication | None:
        result: OpeningApplication | None = await self.session.scalar(
            select(OpeningApplication).where(
                OpeningApplication.opening_id == opening_id,
                OpeningApplication.applicant_id == user_id,
            )
        )
        return result

    async def applications(self, opening: TeamOpening) -> list[OpeningApplication]:
        rows = await self.session.scalars(
            select(OpeningApplication)
            .where(OpeningApplication.opening_id == opening.id)
            .order_by(OpeningApplication.created_at)
        )
        return list(rows)

    async def applications_of(self, user_id: uuid.UUID) -> list[OpeningApplication]:
        rows = await self.session.scalars(
            select(OpeningApplication)
            .where(OpeningApplication.applicant_id == user_id)
            .order_by(OpeningApplication.created_at.desc())
        )
        return list(rows)

    async def skill_titles(self, skill_ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
        if not skill_ids:
            return {}
        rows = await self.session.execute(
            select(Skill.id, Skill.title_fa).where(Skill.id.in_(skill_ids))
        )
        return dict(rows.tuples().all())

    # ── ثبت و مدیریت ───────────────────────────────────────────────────
    async def create(
        self,
        *,
        actor: CurrentUser,
        project_id: uuid.UUID | None,
        venture_id: uuid.UUID | None,
        draft: OpeningDraft,
    ) -> TeamOpening:
        if (project_id is None) == (venture_id is None):
            raise ValidationFailed("آگهی باید دقیقاً به یک پروژه یا یک کسب‌وکار وصل باشد.")
        target = (
            OpeningTarget(project=await self.projects.require(project_id))
            if project_id is not None
            else OpeningTarget(venture=await self.ventures.require(venture_id))  # type: ignore[arg-type]
        )
        await self._require_manager(target, actor)
        if target.is_closed:
            raise Conflict("این تیم دیگر فعال نیست.")
        if await self.team_of(target) is None:
            raise Conflict("پیش از آگهی، پروژه را منتشر کن تا تیمش ساخته شود.")
        opening = TeamOpening(
            poster_id=actor.id,
            project_id=target.project.id if target.project else None,
            venture_id=target.venture.id if target.venture else None,
            expires_at=_now() + OPENING_LIFETIME,
        )
        await self._apply(opening, target, draft)
        self.session.add(opening)
        await self.session.flush()
        await events.publish(self.session, events.OpeningCreated(opening_id=opening.id))
        await self.session.commit()
        await self.session.refresh(opening)
        log.info("opening_created", opening_id=str(opening.id), target=target.kind)
        return opening

    async def update(
        self, *, opening: TeamOpening, actor: CurrentUser, draft: OpeningDraft
    ) -> TeamOpening:
        target = await self.target_of(opening)
        await self._require_manager(target, actor)
        if opening.status != "OPEN":
            raise Conflict("آگهی پرشده یا بسته ویرایش نمی‌شود.")
        await self._apply(opening, target, draft)
        await self.session.commit()
        await self.session.refresh(opening)
        return opening

    async def close(self, *, opening: TeamOpening, actor: CurrentUser) -> TeamOpening:
        """بستن — درخواست‌های باز با یادداشت رد می‌شوند تا کسی بی‌جواب نماند."""
        target = await self.target_of(opening)
        await self._require_manager(target, actor)
        if opening.status != "OPEN":
            raise Conflict("این آگهی باز نیست.")
        opening.status = "CLOSED"
        await self._decline_pending(opening, actor.id, note="آگهی بسته شد.")
        await self.session.commit()
        await self.session.refresh(opening)
        return opening

    async def renew(self, *, opening: TeamOpening, actor: CurrentUser) -> TeamOpening:
        """۳۰ روز از امروز — برای آگهی باز، منقضی یا بسته؛ نه پرشده."""
        target = await self.target_of(opening)
        await self._require_manager(target, actor)
        if opening.status == "FILLED":
            raise Conflict("این آگهی پر شده است؛ برای جای خالی تازه آگهی تازه بده.")
        if target.is_closed:
            raise Conflict("این تیم دیگر فعال نیست.")
        opening.status = "OPEN"
        opening.expires_at = _now() + OPENING_LIFETIME
        await self.session.commit()
        await self.session.refresh(opening)
        return opening

    # ── درخواست ────────────────────────────────────────────────────────
    async def apply(
        self, *, opening_id: uuid.UUID, actor: CurrentUser, message: str
    ) -> OpeningApplication:
        opening = await self.require(opening_id)
        if not opening.is_open_at(_now()):
            raise OpeningClosed
        target = await self.target_of(opening)
        if target.is_closed:
            raise OpeningClosed
        if opening.poster_id == actor.id or await self.is_member(target, actor.id):
            raise Conflict("تو هم‌اکنون عضو این تیمی.")
        cleaned = message.strip()
        if not cleaned:
            raise ValidationFailed("در چند جمله بنویس چرا برای این نقش مناسبی.")
        if len(cleaned) > OPENING_MESSAGE_MAX:
            raise ValidationFailed(f"پیام حداکثر {OPENING_MESSAGE_MAX} نویسه است.")
        await self._require_complete_profile(actor.id)
        if await self.my_application(opening.id, actor.id) is not None:
            raise DuplicateApplication("برای این آگهی قبلاً درخواست داده‌ای.")
        open_count = (
            await self.session.scalar(
                select(func.count())
                .select_from(OpeningApplication)
                .where(
                    OpeningApplication.applicant_id == actor.id,
                    OpeningApplication.status == "PENDING",
                )
            )
            or 0
        )
        if open_count >= MAX_OPEN_APPLICATIONS:
            raise TooManyOpenApplications

        application = OpeningApplication(
            opening_id=opening.id, applicant_id=actor.id, message=cleaned
        )
        self.session.add(application)
        await self.session.flush()
        await events.publish(self.session, events.OpeningApplied(application_id=application.id))
        await self.session.commit()
        await self.session.refresh(application)
        return application

    async def withdraw(self, *, application_id: uuid.UUID, actor: CurrentUser) -> None:
        application = await self.session.get(OpeningApplication, application_id)
        if application is None or application.applicant_id != actor.id:
            raise NotFound("درخواست پیدا نشد.")
        if application.status != "PENDING":
            raise Conflict("فقط درخواست در انتظار پس گرفته می‌شود.")
        application.status = "WITHDRAWN"
        application.decided_at = _now()
        await self.session.commit()

    async def decide(
        self,
        *,
        application_id: uuid.UUID,
        actor: CurrentUser,
        decision: str,
        note: str | None = None,
    ) -> OpeningApplication:
        if decision not in DECISIONS:
            raise ValidationFailed("تصمیم معتبر نیست.")
        application = await self.session.scalar(
            select(OpeningApplication)
            .where(OpeningApplication.id == application_id)
            .with_for_update()
        )
        if application is None:
            raise NotFound("درخواست پیدا نشد.")
        opening = await self.session.scalar(
            select(TeamOpening).where(TeamOpening.id == application.opening_id).with_for_update()
        )
        assert opening is not None
        target = await self.target_of(opening)
        if not await self.can_manage(target, actor):
            raise NotFound("درخواست پیدا نشد.")
        if application.status != "PENDING":
            raise Conflict("دربارهٔ این درخواست قبلاً تصمیم گرفته شده است.")
        cleaned = (note or "").strip() or None
        if cleaned is not None and len(cleaned) > OPENING_MESSAGE_MAX:
            raise ValidationFailed(f"یادداشت حداکثر {OPENING_MESSAGE_MAX} نویسه است.")

        now = _now()
        if decision == "ACCEPTED":
            if opening.status != "OPEN":
                raise OpeningClosed
            if target.is_closed:
                raise Conflict("این تیم دیگر فعال نیست.")
            await self._add_member(target, opening, application.applicant_id, actor.id)
            opening.status = "FILLED"
            opening.filled_at = now
        application.status = decision
        application.decided_by = actor.id
        application.decided_at = now
        application.decision_note = cleaned
        await self.session.flush()
        await events.publish(self.session, events.OpeningDecided(application_id=application.id))
        if decision == "ACCEPTED":
            await self._decline_pending(opening, actor.id, note=FILLED_NOTE)
        await self.session.commit()
        if decision == "ACCEPTED":
            await authz.invalidate_roles(application.applicant_id)
        await self.session.refresh(application)
        log.info("opening_decided", application_id=str(application.id), decision=decision)
        return application

    # ── اعلان هدفمند — FR-TEAM-02 ──────────────────────────────────────
    async def matching_users(
        self, opening: TeamOpening, *, limit: int = MATCH_LIMIT
    ) -> list[tuple[uuid.UUID, list[str]]]:
        """دانشجویانی که دست‌کم یک مهارت لازم را در سطح ۳ به بالا دارند.

        اعضای تیم، آگهی‌دهنده و نیمرخ ناقص بیرون‌اند. کسی که وقت هفتگی‌اش
        کمتر از تعهد آگهی است هم — اعلانی که نمی‌تواند به آن عمل کند مزاحمت است.
        `is_public` لازم نیست: اعلان به خود شخص می‌رسد و چیزی از او فاش نمی‌کند.
        """
        if not opening.needed_skills:
            return []
        target = await self.target_of(opening)
        team = await self.team_of(target)
        members = (
            select(TeamMember.user_id).where(
                TeamMember.team_id == team.id, TeamMember.status == "ACTIVE"
            )
            if team is not None
            else None
        )
        stmt = (
            select(ProfileSkill.user_id, func.array_agg(Skill.title_fa))
            .join(Skill, Skill.id == ProfileSkill.skill_id)
            .join(Profile, Profile.user_id == ProfileSkill.user_id)
            .where(
                ProfileSkill.skill_id.in_(opening.needed_skills),
                ProfileSkill.level >= MATCH_MIN_LEVEL,
                ProfileSkill.user_id != opening.poster_id,
                Profile.survey_completed_steps >= onboarding.TOTAL_SURVEY_STEPS,
            )
            .group_by(ProfileSkill.user_id)
            .order_by(func.count().desc(), func.max(ProfileSkill.level).desc())
            .limit(limit)
        )
        if members is not None:
            stmt = stmt.where(ProfileSkill.user_id.not_in(members))
        if opening.commitment_hpw:
            stmt = stmt.where(
                (Profile.weekly_hours.is_(None)) | (Profile.weekly_hours >= opening.commitment_hpw)
            )
        rows = await self.session.execute(stmt)
        return [(uid, sorted(titles)) for uid, titles in rows]

    # ── کار شبانه — §7.11 `expire_team_openings` ───────────────────────
    async def notify_expired(self, *, now: datetime | None = None) -> int:
        """آگهی‌دهندهٔ آگهی‌هایی که در ۷ روز گذشته منقضی شده‌اند — یک‌بار برای هر مهلت.

        پنجرهٔ ۷ روزه جاماندهٔ خرابی کارگر را می‌گیرد؛ `dedup_key` با مهلت
        ساخته می‌شود تا تمدید و انقضای دوباره، اعلان دوباره داشته باشد.
        """
        moment = now or _now()
        rows = list(
            await self.session.scalars(
                select(TeamOpening).where(
                    TeamOpening.status == "OPEN",
                    TeamOpening.expires_at <= moment,
                    TeamOpening.expires_at > moment - EXPIRY_NOTICE_WINDOW,
                )
            )
        )
        notifications = NotificationService(self.session)
        sent = 0
        for opening in rows:
            created = await notifications.notify(
                "OPENING_EXPIRED",
                [opening.poster_id],
                {"opening": opening.title},
                action_url=f"/teams/openings/{opening.id}",
                dedup_key=f"OPENING_EXPIRED:{opening.id}:{opening.expires_at.isoformat()}",
            )
            sent += len(created)
        await self.session.commit()
        return sent

    # ── درونی ──────────────────────────────────────────────────────────
    async def _add_member(
        self,
        target: OpeningTarget,
        opening: TeamOpening,
        user_id: uuid.UUID,
        actor_id: uuid.UUID,
    ) -> None:
        if target.project is not None:
            project = target.project
            # ظرفیت پروژه تحت رقابت — §7.12، همان قفل پذیرش درخواست.
            await self.session.execute(
                select(Project.id).where(Project.id == project.id).with_for_update()
            )
            await self.projects.add_member(
                project=project, user_id=user_id, role_id=opening.role_id
            )
            await self.projects.record_activity(
                project,
                actor_id,
                "MEMBER_JOINED",
                "عضو تازه‌ای از راه آگهی هم‌تیمی به تیم پیوست.",
                entity_type="opening",
                entity_id=opening.id,
                commit=False,
            )
            return
        assert target.venture is not None
        await self.session.execute(
            select(Venture.id).where(Venture.id == target.venture.id).with_for_update()
        )
        await self.ventures.add_member(venture=target.venture, user_id=user_id)

    async def _decline_pending(
        self, opening: TeamOpening, actor_id: uuid.UUID, *, note: str
    ) -> None:
        pending = list(
            await self.session.scalars(
                select(OpeningApplication).where(
                    OpeningApplication.opening_id == opening.id,
                    OpeningApplication.status == "PENDING",
                )
            )
        )
        now = _now()
        for other in pending:
            other.status = "DECLINED"
            other.decided_by = actor_id
            other.decided_at = now
            other.decision_note = note
        await self.session.flush()
        for other in pending:
            await events.publish(self.session, events.OpeningDecided(application_id=other.id))

    async def _apply(
        self, opening: TeamOpening, target: OpeningTarget, draft: OpeningDraft
    ) -> None:
        title = " ".join(draft.title.split())
        description = draft.description.strip()
        if not 3 <= len(title) <= OPENING_TITLE_MAX:
            raise ValidationFailed(f"نقش مورد نیاز باید بین ۳ تا {OPENING_TITLE_MAX} نویسه باشد.")
        if not 10 <= len(description) <= OPENING_DESCRIPTION_MAX:
            raise ValidationFailed("شرح آگهی دست‌کم ۱۰ نویسه باشد.")
        skills = list(dict.fromkeys(draft.needed_skills))
        if len(skills) > MAX_OPENING_SKILLS:
            raise ValidationFailed(f"حداکثر {MAX_OPENING_SKILLS} مهارت لازم.")
        if skills:
            known = set(
                await self.session.scalars(
                    select(Skill.id).where(Skill.id.in_(skills), Skill.is_active.is_(True))
                )
            )
            if len(known) != len(skills):
                raise ValidationFailed("یکی از مهارت‌ها معتبر نیست.")
        if draft.commitment_hpw is not None and not 1 <= draft.commitment_hpw <= 60:
            raise ValidationFailed("تعهد زمانی باید بین ۱ تا ۶۰ ساعت در هفته باشد.")
        if draft.role_id is not None:
            if target.project is None:
                raise ValidationFailed("نقش پروژه فقط برای آگهی پروژه معنا دارد.")
            role = await self.session.get(ProjectRole, draft.role_id)
            if role is None or role.project_id != target.project.id:
                raise ValidationFailed("این نقش مال این پروژه نیست.")
        opening.title = title
        opening.description = description
        opening.needed_skills = skills
        opening.commitment_hpw = draft.commitment_hpw
        opening.role_id = draft.role_id

    async def _require_complete_profile(self, user_id: uuid.UUID) -> None:
        profile = await self.session.get(Profile, user_id)
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
            raise ProfileIncomplete(
                "برای درخواست پیوستن، هر چهار گام نیمرخ را کامل کن؛"
                " تیم باید بداند با چه کسی طرف است."
            )


__all__ = ["DECISIONS", "OpeningDraft", "OpeningService", "OpeningTarget"]
