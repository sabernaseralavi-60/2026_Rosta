"""درخواست پیوستن به پروژه — FR-PRJ-04، §7.5.

دو جزئیات این جریان، تفاوت بین یک سامانهٔ اداری و یک سامانهٔ محترم است:

* **امتیاز تطابق در لحظهٔ ارسال عکس‌برداری می‌شود.** مدیر پروژه باید
  همان عددی را ببیند که دانشجو موقع درخواست دیده بود، نه عدد زندهٔ
  امروز که با هر ویرایش نیمرخ تکان می‌خورد.
* **رد کردن همیشه با سه جایگزین همراه است** (§7.5). «رد شدم» و «مسیر
  بهتری پیدا کردم» دو تجربهٔ متفاوت‌اند و فاصله‌شان همین سه پیشنهاد است.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from silp.core.exceptions import (
    Conflict,
    DuplicateApplication,
    NotFound,
    ProfileIncomplete,
    ProjectCapacityFull,
    ProjectNotOpen,
    TooManyOpenApplications,
    ValidationFailed,
)
from silp.core.logging import get_logger
from silp.core.permissions import CurrentUser
from silp.domain.identity import onboarding
from silp.domain.recommendation import service as recommendation
from silp.domain.recommendation.schemas import MatchResult
from silp.domain.recommendation.scorer import score_project
from silp.models.profile import Profile
from silp.models.project import Project, ProjectApplication, ProjectRole
from silp.services import authz, events
from silp.services.project_service import ProjectService

log = get_logger("silp.application")

# §7.5 و §11.8 — حداکثر درخواست باز هم‌زمان برای هر دانشجو.
MAX_OPEN_APPLICATIONS = 5
OPEN_STATUSES = ("PENDING", "WAITLISTED")
ALTERNATIVES_ON_REJECT = 3
MAX_MOTIVATION_LENGTH = 500

DECISIONS = ("ACCEPTED", "REJECTED", "WAITLISTED")


@dataclass(frozen=True, slots=True)
class Decision:
    """نتیجهٔ تصمیم مدیر پروژه."""

    application: ProjectApplication
    # §7.5 — فقط برای رد: سه پروژهٔ جایگزین از موتور توصیه‌گر.
    alternatives: tuple[MatchResult, ...] = ()


def _now() -> datetime:
    return datetime.now(UTC)


class ApplicationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.projects = ProjectService(session)

    # ── ارسال ──────────────────────────────────────────────────────────
    async def apply(
        self,
        *,
        project: Project,
        actor: CurrentUser,
        motivation: str,
        role_id: uuid.UUID | None = None,
    ) -> ProjectApplication:
        """§7.5 — چهار شرط، سپس عکس‌برداری از امتیاز تطابق."""
        text = motivation.strip()
        if not text:
            raise ValidationFailed("انگیزه‌نامه را خالی نگذارید.")
        if len(text) > MAX_MOTIVATION_LENGTH:
            raise ValidationFailed(f"انگیزه‌نامه حداکثر {MAX_MOTIVATION_LENGTH} نویسه است.")

        if not project.is_open:
            raise ProjectNotOpen
        if project.applications_close_at and project.applications_close_at <= _now():
            raise ProjectNotOpen("مهلت درخواست برای این پروژه تمام شده است.")
        if project.lead_id == actor.id:
            raise Conflict("شما مدیر این پروژه‌اید.")
        if await self.projects.membership(project.id, actor.id) is not None:
            raise Conflict("شما هم‌اکنون عضو تیم این پروژه‌اید.")

        await self._require_complete_profile(actor.id)
        await self._require_application_budget(actor.id)

        existing = await self.session.scalar(
            select(ProjectApplication).where(
                ProjectApplication.project_id == project.id,
                ProjectApplication.applicant_id == actor.id,
            )
        )
        if existing is not None and existing.status in OPEN_STATUSES:
            raise DuplicateApplication
        if existing is not None and existing.status == "ACCEPTED":
            raise Conflict("درخواست شما قبلاً پذیرفته شده است.")

        role = await self._validate_role(project, role_id)
        score, breakdown = await self._match_snapshot(project, actor.id)

        if existing is not None:
            # درخواست ردشده یا انصراف‌داده‌شده دوباره باز می‌شود؛ قید
            # یکتای (project, applicant) اجازهٔ ردیف دوم نمی‌دهد.
            existing.status = "PENDING"
            existing.motivation = text
            existing.role_id = role.id if role else None
            existing.match_score = score
            existing.match_breakdown = breakdown
            existing.decision_note = None
            existing.decided_by = None
            existing.decided_at = None
            application = existing
        else:
            application = ProjectApplication(
                project_id=project.id,
                applicant_id=actor.id,
                role_id=role.id if role else None,
                motivation=text,
                match_score=score,
                match_breakdown=breakdown,
                status="PENDING",
            )
            self.session.add(application)

        await self.projects.record_activity(
            project,
            actor.id,
            "APPLICATION_SUBMITTED",
            "یک درخواست پیوستن تازه رسید.",
            entity_type="application",
            commit=False,
        )
        await self.session.commit()
        log.info("application_submitted", project_id=str(project.id), applicant=str(actor.id))
        return application

    async def withdraw(self, *, application_id: uuid.UUID, actor: CurrentUser) -> None:
        """انصراف متقاضی — §7.5."""
        application = await self.require(application_id)
        if application.applicant_id != actor.id:
            # §6.4 قاعدهٔ ۴ — درخواست دیگری برای این کاربر وجود ندارد.
            raise NotFound("درخواست پیدا نشد.")
        if application.status not in OPEN_STATUSES:
            raise Conflict("این درخواست دیگر باز نیست.")
        application.status = "WITHDRAWN"
        application.decided_at = _now()
        await self.session.commit()

    # ── تصمیم ──────────────────────────────────────────────────────────
    async def decide(
        self,
        *,
        application_id: uuid.UUID,
        actor: CurrentUser,
        decision: str,
        note: str | None = None,
    ) -> Decision:
        """پذیرش، رد یا فهرست انتظار — §7.5.

        پذیرش، ردیف پروژه را `FOR UPDATE` قفل می‌کند (§7.12 «ظرفیت پروژه
        تحت رقابت»): دو پذیرش هم‌زمان نباید ظرفیت را بشکنند.
        """
        if decision not in DECISIONS:
            raise ValidationFailed("تصمیم معتبر نیست.")
        application = await self.require(application_id)
        if application.status not in OPEN_STATUSES:
            raise Conflict("این درخواست قبلاً تعیین تکلیف شده است.")

        project = await self.projects.require(application.project_id)
        alternatives: tuple[MatchResult, ...] = ()

        if decision == "ACCEPTED":
            # قفل سطر پروژه پیش از شمارش ظرفیت.
            await self.session.execute(
                select(Project.id).where(Project.id == project.id).with_for_update()
            )
            active = await self.projects.active_member_count(project.id)
            if active >= project.team_size_max:
                raise ProjectCapacityFull
            await self.projects.add_member(
                project=project, user_id=application.applicant_id, role_id=application.role_id
            )
            await self.projects.record_activity(
                project,
                actor.id,
                "MEMBER_JOINED",
                "عضو تازه‌ای به تیم پیوست.",
                entity_type="application",
                entity_id=application.id,
                commit=False,
            )
        elif decision == "REJECTED":
            alternatives = await self._alternatives(
                applicant_id=application.applicant_id, exclude=project.id
            )

        application.status = decision
        application.decision_note = (note or "").strip() or None
        application.decided_by = actor.id
        application.decided_at = _now()
        if decision == "ACCEPTED":
            await events.publish(
                self.session, events.ApplicationAccepted(application_id=application.id)
            )
        await self.session.commit()

        if decision == "ACCEPTED":
            # نقش مشتق `PROJECT_MEMBER` همین الان برقرار شد.
            await authz.invalidate_roles(application.applicant_id)
        log.info(
            "application_decided",
            application_id=str(application.id),
            decision=decision,
            alternatives=len(alternatives),
        )
        return Decision(application=application, alternatives=alternatives)

    async def promote_waitlisted(self, *, project: Project) -> ProjectApplication | None:
        """§7.5 — وقتی جا باز شد، بهترین نفر فهرست انتظار بالا می‌آید.

        «بهترین» یعنی بالاترین امتیاز تطابق ثبت‌شده در لحظهٔ درخواست؛
        در تساوی، هر که زودتر درخواست داده است.
        """
        if await self.projects.active_member_count(project.id) >= project.team_size_max:
            return None
        best: ProjectApplication | None = await self.session.scalar(
            select(ProjectApplication)
            .where(
                ProjectApplication.project_id == project.id,
                ProjectApplication.status == "WAITLISTED",
            )
            .order_by(
                ProjectApplication.match_score.desc().nullslast(),
                ProjectApplication.created_at,
            )
            .limit(1)
        )
        return best

    # ── خواندن ─────────────────────────────────────────────────────────
    async def require(self, application_id: uuid.UUID) -> ProjectApplication:
        application = await self.session.get(ProjectApplication, application_id)
        if application is None:
            raise NotFound("درخواست پیدا نشد.")
        return application

    async def for_project(
        self, project_id: uuid.UUID, *, status: str | None = None
    ) -> list[ProjectApplication]:
        stmt = select(ProjectApplication).where(ProjectApplication.project_id == project_id)
        if status:
            stmt = stmt.where(ProjectApplication.status == status)
        rows = await self.session.scalars(
            stmt.order_by(
                ProjectApplication.match_score.desc().nullslast(),
                ProjectApplication.created_at,
            )
        )
        return list(rows)

    async def mine(self, user_id: uuid.UUID) -> list[ProjectApplication]:
        rows = await self.session.scalars(
            select(ProjectApplication)
            .where(ProjectApplication.applicant_id == user_id)
            .order_by(ProjectApplication.created_at.desc())
        )
        return list(rows)

    # ── درونی ──────────────────────────────────────────────────────────
    async def _require_complete_profile(self, user_id: uuid.UUID) -> None:
        """§7.5 «نیمرخ کامل» — هر چهار گام ارزیابی.

        سخت‌گیری عمدی است: امتیاز تطابقی که همین‌جا عکس‌برداری می‌شود،
        روی هر شش مؤلفهٔ §8 حساب می‌شود. نیمرخ نیمه‌کاره عددی می‌سازد که
        مدیر پروژه بر اساسش تصمیم می‌گیرد و دانشجو بعداً حقش را نگرفته.
        """
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
                "برای درخواست پیوستن، هر چهار گام نیمرخ را کامل کنید؛"
                " مدیر پروژه باید بداند با چه کسی طرف است."
            )

    async def _require_application_budget(self, user_id: uuid.UUID) -> None:
        open_count = (
            await self.session.scalar(
                select(func.count())
                .select_from(ProjectApplication)
                .where(
                    ProjectApplication.applicant_id == user_id,
                    ProjectApplication.status.in_(OPEN_STATUSES),
                )
            )
            or 0
        )
        if open_count >= MAX_OPEN_APPLICATIONS:
            raise TooManyOpenApplications

    async def _validate_role(
        self, project: Project, role_id: uuid.UUID | None
    ) -> ProjectRole | None:
        if role_id is None:
            return None
        role = await self.session.get(ProjectRole, role_id)
        if role is None or role.project_id != project.id:
            raise NotFound("این نقش در پروژه تعریف نشده است.")
        if not role.has_opening:
            raise Conflict(f"ظرفیت نقش «{role.title_fa}» تکمیل است.")
        return role

    async def _match_snapshot(
        self, project: Project, user_id: uuid.UUID
    ) -> tuple[Decimal, dict[str, float]]:
        """عکس امتیاز تطابق در لحظهٔ ارسال — §7.5."""
        ctx = await recommendation.load_student_context(self.session, user_id)
        spec = await recommendation.spec_for_project(self.session, project)
        match = score_project(ctx, spec, now=_now())
        breakdown = {
            component.value.lower(): round(value, 1) for component, value in match.breakdown.items()
        }
        return Decimal(str(round(match.score, 2))), breakdown

    async def _alternatives(
        self, *, applicant_id: uuid.UUID, exclude: uuid.UUID
    ) -> tuple[MatchResult, ...]:
        """§7.5 — سه پروژهٔ جایگزین همراه پاسخ رد.

        کش عمداً دور زده می‌شود: ممکن است همین حالا پروژه‌ای پر شده باشد
        و پیشنهاد دادن یک پروژهٔ بسته، بدتر از پیشنهاد ندادن است.
        """
        try:
            results, _, _ = await recommendation.recommend(
                self.session,
                applicant_id,
                limit=ALTERNATIVES_ON_REJECT + 1,
                use_cache=False,
            )
        except Exception:  # noqa: BLE001 — پیشنهاد جایگزین نباید تصمیم را بشکند
            log.warning("alternatives_failed", applicant=str(applicant_id))
            return ()
        return tuple(m for m in results if m.project.id != exclude)[:ALTERNATIVES_ON_REJECT]


__all__ = [
    "ALTERNATIVES_ON_REJECT",
    "DECISIONS",
    "MAX_OPEN_APPLICATIONS",
    "OPEN_STATUSES",
    "ApplicationService",
    "Decision",
]
