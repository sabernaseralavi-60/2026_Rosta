"""دادهٔ عمومی سامانه — صفحهٔ اصلی و نیمرخ عمومی. M7-10، M7-11، ADR-0017.

هیچ‌چیز اینجا احراز هویت نمی‌خواهد، پس دو قاعده سخت‌گیرانه‌اند:

* **آمار واقعی، نه ساختگی** (§10.10). هر عدد از یک کوئری می‌آید و فقط
  چیزی شمرده می‌شود که کسی تأییدش کرده: مقالهٔ راستی‌آزمایی‌شده، فروش
  تأییدشده، مرحلهٔ تأییدشده. سرور صفر را هم برمی‌گرداند؛ تصمیم نمایش با
  رابط است (§5.3.1).
* **فقط آنچه صاحبش عمومی کرده.** نیمرخ بی `is_public` وجود ندارد (۴۰۴)،
  بخش خاموش‌شده اصلاً از سرور بیرون نمی‌رود، و در «داستان‌ها» نام عضوی
  که نیمرخش خصوصی است نمی‌آید.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from silp.core.exceptions import NotFound
from silp.core.permissions import CurrentUser
from silp.domain import public_profile as rules
from silp.domain.gamification.levels import LevelProgress
from silp.domain.research import OUTPUT_KIND_TITLE_FA
from silp.domain.research import level_spec as research_level
from silp.models.delivery import Certificate, Milestone, ProjectActivity
from silp.models.education import Course, CourseOffering
from silp.models.gamification import Badge, UserBadge
from silp.models.identity import User, UserRole
from silp.models.profile import DEGREE_TITLE_FA, Profile, ProfileSkill
from silp.models.project import KIND_TITLE_FA, Project, Team, TeamMember
from silp.models.research import ResearchOutput, ResearchTrack
from silp.models.taxonomy import Skill
from silp.models.venture import VentureMetric
from silp.services.points_service import PointsService

STORY_LIMIT = 3


@dataclass(frozen=True, slots=True)
class PublicStats:
    students: int
    active_projects: int
    completed_projects: int
    completed_milestones: int
    research_outputs: int
    verified_revenue_rial: int
    active_courses: int
    certificates: int


@dataclass(frozen=True, slots=True)
class StoryMember:
    name: str
    username: str
    is_lead: bool


@dataclass(frozen=True, slots=True)
class Story:
    project: Project
    completed_at: datetime | None
    team_size: int
    approved_milestones: int
    #: فقط اعضای دارای نیمرخ عمومی.
    members: list[StoryMember]
    course_title: str | None


@dataclass(slots=True)
class PublicProfile:
    user: User
    profile: Profile
    sections: dict[str, bool]
    is_owner: bool
    university_title: str | None = None
    skills: list[tuple[Skill, ProfileSkill]] = field(default_factory=list)
    projects: list[tuple[Project, bool, datetime | None]] = field(default_factory=list)
    certificates: list[Certificate] = field(default_factory=list)
    research_level: int | None = None
    research_outputs: list[ResearchOutput] = field(default_factory=list)
    badges: list[tuple[Badge, datetime]] = field(default_factory=list)
    level: LevelProgress | None = None


class PublicService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ── آمار زنده — `GET /public/stats` ────────────────────────────────
    async def stats(self) -> PublicStats:
        async def count(stmt: Any) -> int:
            return int(await self.session.scalar(stmt) or 0)

        active_users = select(User.id).where(User.deleted_at.is_(None), User.status == "ACTIVE")
        students = await count(
            select(func.count(func.distinct(UserRole.user_id))).where(
                UserRole.role_code == "STUDENT", UserRole.user_id.in_(active_users)
            )
        )
        live = Project.deleted_at.is_(None)
        active_projects = await count(
            select(func.count())
            .select_from(Project)
            .where(live, Project.status.in_(("OPEN", "IN_PROGRESS")))
        )
        completed_projects = await count(
            select(func.count()).select_from(Project).where(live, Project.status == "COMPLETED")
        )
        milestones = await count(
            select(func.count())
            .select_from(Milestone)
            .join(Project, Project.id == Milestone.project_id)
            .where(live, Milestone.status == "APPROVED")
        )
        outputs = await count(
            select(func.count())
            .select_from(ResearchOutput)
            .where(ResearchOutput.review_status == "VERIFIED")
        )
        revenue = await count(
            select(func.coalesce(func.sum(VentureMetric.value), 0)).where(
                VentureMetric.metric == "SALES_AMOUNT", VentureMetric.status == "VERIFIED"
            )
        )
        courses = await count(
            select(func.count(func.distinct(CourseOffering.course_id)))
            .join(Course, Course.id == CourseOffering.course_id)
            .where(
                CourseOffering.status.in_(("OPEN", "IN_PROGRESS")),
                CourseOffering.deleted_at.is_(None),
                Course.deleted_at.is_(None),
                Course.is_active.is_(True),
            )
        )
        certificates = await count(
            select(func.count()).select_from(Certificate).where(Certificate.revoked_at.is_(None))
        )
        return PublicStats(
            students=students,
            active_projects=active_projects,
            completed_projects=completed_projects,
            completed_milestones=milestones,
            research_outputs=outputs,
            verified_revenue_rial=revenue,
            active_courses=courses,
            certificates=certificates,
        )

    # ── داستان‌های واقعی — §10.10 «نه تستیمونیال ساختگی» ────────────────
    async def stories(self, limit: int = STORY_LIMIT) -> list[Story]:
        """آخرین پروژه‌های تکمیل‌شده — هرکدام با تیم و مراحل تأییدشده‌اش."""
        completed_at = (
            select(func.max(ProjectActivity.created_at))
            .where(
                ProjectActivity.project_id == Project.id,
                ProjectActivity.kind == "PROJECT_COMPLETED",
            )
            .scalar_subquery()
        )
        rows = list(
            await self.session.execute(
                select(Project, completed_at.label("completed_at"))
                .where(Project.status == "COMPLETED", Project.deleted_at.is_(None))
                .order_by(completed_at.desc().nulls_last(), Project.updated_at.desc())
                .limit(limit)
            )
        )
        stories: list[Story] = []
        for project, done_at in rows:
            members = list(
                await self.session.execute(
                    select(
                        TeamMember.is_lead,
                        User.username,
                        Profile.first_name,
                        Profile.last_name,
                        Profile.display_name,
                        Profile.is_public,
                    )
                    .join(Team, Team.id == TeamMember.team_id)
                    .join(User, User.id == TeamMember.user_id)
                    .outerjoin(Profile, Profile.user_id == User.id)
                    .where(Team.project_id == project.id, TeamMember.status == "ACTIVE")
                    .order_by(TeamMember.is_lead.desc(), TeamMember.joined_at)
                )
            )
            approved = int(
                await self.session.scalar(
                    select(func.count())
                    .select_from(Milestone)
                    .where(Milestone.project_id == project.id, Milestone.status == "APPROVED")
                )
                or 0
            )
            course_title = None
            if project.offering_id is not None:
                course_title = await self.session.scalar(
                    select(Course.title_fa)
                    .join(CourseOffering, CourseOffering.course_id == Course.id)
                    .where(CourseOffering.id == project.offering_id)
                )
            stories.append(
                Story(
                    project=project,
                    completed_at=done_at,
                    team_size=len(members),
                    approved_milestones=approved,
                    members=[
                        StoryMember(
                            name=display or f"{first} {last}".strip(),
                            username=username,
                            is_lead=is_lead,
                        )
                        for is_lead, username, first, last, display, is_public in members
                        if is_public and username and first
                    ],
                    course_title=course_title,
                )
            )
        return stories

    # ── نیمرخ عمومی — `GET /profiles/{username}` ───────────────────────
    async def profile(self, username: str, viewer: CurrentUser | None) -> PublicProfile:
        """FR-PROF-03. صاحب نیمرخ همیشه پیش‌نمایش خودش را می‌بیند."""
        row = (
            await self.session.execute(
                select(User, Profile)
                .join(Profile, Profile.user_id == User.id)
                .where(
                    User.username == username.strip().lower(),
                    User.deleted_at.is_(None),
                    User.status == "ACTIVE",
                )
            )
        ).first()
        if row is None:
            raise NotFound("این نیمرخ پیدا نشد یا عمومی نیست.")
        user, profile = row
        is_owner = viewer is not None and viewer.id == user.id
        if not profile.is_public and not is_owner:
            # ۴۰۴، نه ۴۰۳ — §6.4 قاعدهٔ ۴: وجود حساب خصوصی فاش نمی‌شود.
            raise NotFound("این نیمرخ پیدا نشد یا عمومی نیست.")

        sections = rules.sections(profile.privacy_settings)
        result = PublicProfile(user=user, profile=profile, sections=sections, is_owner=is_owner)
        if sections["university"] and profile.university is not None:
            result.university_title = profile.university.title_fa
        if sections["skills"]:
            result.skills = await self._top_skills(user.id)
        if sections["projects"]:
            result.projects = await self._completed_projects(user.id)
        if sections["certificates"]:
            result.certificates = list(
                await self.session.scalars(
                    select(Certificate)
                    .where(Certificate.user_id == user.id, Certificate.revoked_at.is_(None))
                    .order_by(Certificate.issued_at.desc())
                )
            )
        if sections["research"]:
            result.research_level = await self.session.scalar(
                select(func.max(ResearchTrack.level)).where(
                    ResearchTrack.user_id == user.id, ResearchTrack.status == "APPROVED"
                )
            )
            result.research_outputs = list(
                await self.session.scalars(
                    select(ResearchOutput)
                    .where(
                        ResearchOutput.owner_id == user.id,
                        ResearchOutput.review_status == "VERIFIED",
                    )
                    .order_by(ResearchOutput.created_at.desc())
                )
            )
        if sections["badges"]:
            result.badges = [
                tuple(row)
                for row in await self.session.execute(
                    select(Badge, UserBadge.awarded_at)
                    .join(UserBadge, UserBadge.badge_code == Badge.code)
                    .where(UserBadge.user_id == user.id)
                    .order_by(UserBadge.awarded_at.desc())
                )
            ]
        if sections["points"]:
            result.level = (await PointsService(self.session).summary(user.id)).level
        return result

    async def _top_skills(self, user_id: uuid.UUID) -> list[tuple[Skill, ProfileSkill]]:
        rows = await self.session.execute(
            select(Skill, ProfileSkill)
            .join(ProfileSkill, ProfileSkill.skill_id == Skill.id)
            .where(
                ProfileSkill.user_id == user_id,
                ProfileSkill.level >= rules.TOP_SKILL_MIN_LEVEL,
                Skill.is_active.is_(True),
            )
            # مهارت تأییدشده (FR-PROF-04) پیش از اعلام‌شده با همان سطح.
            .order_by(
                ProfileSkill.level.desc(),
                ProfileSkill.verified_at.is_(None),
                Skill.sort_order,
            )
            .limit(rules.TOP_SKILL_LIMIT)
        )
        return [tuple(row) for row in rows]

    async def _completed_projects(
        self, user_id: uuid.UUID
    ) -> list[tuple[Project, bool, datetime | None]]:
        """پروژه‌هایی که کاربر تا پایان عضو فعالشان بود (FR-PRJ-08)."""
        completed_at = (
            select(func.max(ProjectActivity.created_at))
            .where(
                ProjectActivity.project_id == Project.id,
                ProjectActivity.kind == "PROJECT_COMPLETED",
            )
            .scalar_subquery()
        )
        rows = await self.session.execute(
            select(Project, TeamMember.is_lead, completed_at)
            .join(Team, Team.project_id == Project.id)
            .join(TeamMember, TeamMember.team_id == Team.id)
            .where(
                TeamMember.user_id == user_id,
                TeamMember.status == "ACTIVE",
                Project.status == "COMPLETED",
                Project.deleted_at.is_(None),
            )
            .order_by(completed_at.desc().nulls_last())
        )
        return [tuple(row) for row in rows]


def degree_fa(level: str | None) -> str | None:
    return DEGREE_TITLE_FA.get(level or "")


def project_kind_fa(kind: str) -> str:
    return KIND_TITLE_FA.get(kind, kind)


def output_kind_fa(kind: str) -> str:
    return OUTPUT_KIND_TITLE_FA.get(kind, kind)


def research_level_title(level: int | None) -> str | None:
    return research_level(level).title_fa if level else None


__all__ = [
    "PublicProfile",
    "PublicService",
    "PublicStats",
    "Story",
    "StoryMember",
    "degree_fa",
    "output_kind_fa",
    "project_kind_fa",
    "research_level_title",
]
