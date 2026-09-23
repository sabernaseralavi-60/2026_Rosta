"""جستجوی هم‌تیمی — FR-TEAM-01، §8.14، M7-07، ADR-0015.

* **فقط نیمرخ عمومی.** کسی که `is_public` را روشن نکرده، در هیچ نتیجه‌ای
  نیست (FR-TEAM-01) — نه حتی با فیلتر دقیق.
* **مکملیت، نه شباهت.** با `complement_project_id` هر نامزد با فرمول §8.14
  نسبت به **کمبود** تیم آن پروژه سنجیده و مرتب می‌شود؛ اعضای فعلی از
  نتیجه بیرون‌اند. بدون پروژه، «تیم» خودِ جستجوکننده است و هر نتیجه
  می‌گوید در چه چیزی از او قوی‌تر است.
* **مقیاس فاز ۱.** نامزدها پس از فیلتر SQL حداکثر `CANDIDATE_LIMIT` نفرند و
  امتیاز در پایتون حساب می‌شود — همان منطق خالص توصیه‌گر، بی‌نیاز به
  تکرارش در SQL. با چند صد دانشجو، این یک کوئری سبک است.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy import Select, and_, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from silp.core.exceptions import NotFound, PermissionDenied
from silp.core.permissions import CurrentUser, Permission
from silp.domain import teams as rules
from silp.models.education import Enrollment
from silp.models.identity import User
from silp.models.profile import Profile, ProfileAsset, ProfileInterest, ProfileSkill
from silp.models.project import Project, ProjectRequiredSkill, Team, TeamMember
from silp.models.taxonomy import Asset, Skill
from silp.services import authz

CANDIDATE_LIMIT = 300
TOP_SKILLS = 6
ENROLLED_STATUSES = ("ACTIVE", "COMPLETED")


@dataclass(slots=True)
class SearchFilters:
    skill_id: uuid.UUID | None = None
    min_level: int = 1
    asset_id: uuid.UUID | None = None
    interest_id: uuid.UUID | None = None
    offering_id: uuid.UUID | None = None
    university_id: uuid.UUID | None = None
    q: str | None = None


@dataclass(frozen=True, slots=True)
class SkillOut:
    skill_id: uuid.UUID
    title_fa: str
    level: int
    verified: bool


@dataclass(slots=True)
class Match:
    user_id: uuid.UUID
    username: str | None
    display_name: str
    university: str | None
    bio: str | None
    weekly_hours: int | None
    top_skills: list[SkillOut]
    assets: list[str]
    shares_course: bool
    complement: rules.Complement | None = None
    stronger: list[rules.CoveredSkill] = field(default_factory=list)
    #: برای مرتب‌سازی بدون پروژه — سطح مهارتِ فیلترشده.
    filtered_level: int = 0


@dataclass(slots=True)
class SearchContext:
    project: Project | None = None
    gaps: list[rules.Need] = field(default_factory=list)
    can_invite: bool = False


class TeamSearchService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def search(
        self,
        *,
        actor: CurrentUser,
        filters: SearchFilters,
        complement_project_id: uuid.UUID | None = None,
    ) -> tuple[list[Match], SearchContext]:
        if not await authz.has_permission(self.session, actor, Permission.TEAM_SEARCH):
            raise PermissionDenied(permission=Permission.TEAM_SEARCH.value)

        titles = await self._skill_titles()
        context = SearchContext()
        excluded: set[uuid.UUID] = {actor.id}
        shared_offerings: set[uuid.UUID]
        if complement_project_id is not None:
            context = await self._project_context(complement_project_id, actor, titles)
            assert context.project is not None
            excluded |= set(await self._active_member_ids(context.project.id))
            shared_offerings = (
                {context.project.offering_id}
                if context.project.offering_id is not None
                else await self._offerings_of(actor.id)
            )
        else:
            shared_offerings = await self._offerings_of(actor.id)

        rows = list(
            (await self.session.execute(self._candidates(filters, excluded))).tuples().all()
        )
        user_ids = [profile.user_id for profile, _ in rows]
        skills = await self._skills_of(user_ids)
        assets = await self._assets_of(user_ids)
        sharing = await self._sharing_course(user_ids, shared_offerings)
        history = await self._project_history(user_ids)
        my_skills = (
            {s.skill_id: s.level for s in (await self._skills_of([actor.id])).get(actor.id, [])}
            if context.project is None
            else {}
        )

        matches: list[Match] = []
        for profile, username in rows:
            uid = profile.user_id
            own = skills.get(uid, [])
            completed, dropped = history.get(uid, (0, 0))
            candidate = rules.Candidate(
                user_id=uid,
                skills={s.skill_id: s.level for s in own},
                verified_skills=frozenset(s.skill_id for s in own if s.verified),
                weekly_hours=profile.weekly_hours,
                completed_projects=completed,
                dropped_projects=dropped,
                shares_course=uid in sharing,
            )
            match = Match(
                user_id=uid,
                username=username,
                display_name=profile.public_name,
                university=profile.university.title_fa if profile.university else None,
                bio=profile.bio,
                weekly_hours=profile.weekly_hours,
                top_skills=sorted(own, key=lambda s: (-s.level, not s.verified, s.title_fa))[
                    :TOP_SKILLS
                ],
                assets=assets.get(uid, []),
                shares_course=uid in sharing,
                filtered_level=candidate.skills.get(filters.skill_id, 0) if filters.skill_id else 0,
            )
            if context.project is not None:
                match.complement = rules.complement(
                    candidate, context.gaps, commitment_hpw=context.project.time_commitment_hpw
                )
            else:
                match.stronger = rules.stronger_skills(candidate, my_skills, titles)
            matches.append(match)

        if context.project is not None:
            matches.sort(
                key=lambda m: (-(m.complement.score if m.complement else 0.0), m.display_name)
            )
        else:
            matches.sort(
                key=lambda m: (
                    -m.filtered_level,
                    -len(m.stronger),
                    not m.shares_course,
                    m.display_name,
                )
            )
        return matches, context

    # ── کوئری نامزدها ──────────────────────────────────────────────────
    def _candidates(
        self, filters: SearchFilters, excluded: set[uuid.UUID]
    ) -> Select[tuple[Profile, str | None]]:
        stmt = (
            select(Profile, User.username)
            .join(User, User.id == Profile.user_id)
            .where(
                Profile.is_public.is_(True),
                User.status == "ACTIVE",
                User.deleted_at.is_(None),
                Profile.user_id.not_in(excluded),
            )
        )
        if filters.skill_id is not None:
            stmt = stmt.where(
                exists().where(
                    ProfileSkill.user_id == Profile.user_id,
                    ProfileSkill.skill_id == filters.skill_id,
                    ProfileSkill.level >= filters.min_level,
                )
            )
        if filters.asset_id is not None:
            stmt = stmt.where(
                exists().where(
                    ProfileAsset.user_id == Profile.user_id,
                    ProfileAsset.asset_id == filters.asset_id,
                )
            )
        if filters.interest_id is not None:
            # «علاقه‌مند» یعنی دست‌کم ۴ از ۵ — سطح ۳ خنثی است (§8.4).
            stmt = stmt.where(
                exists().where(
                    ProfileInterest.user_id == Profile.user_id,
                    ProfileInterest.interest_id == filters.interest_id,
                    ProfileInterest.level >= 4,
                )
            )
        if filters.offering_id is not None:
            stmt = stmt.where(
                exists().where(
                    Enrollment.student_id == Profile.user_id,
                    Enrollment.offering_id == filters.offering_id,
                    Enrollment.status.in_(ENROLLED_STATUSES),
                )
            )
        if filters.university_id is not None:
            stmt = stmt.where(Profile.university_id == filters.university_id)
        if filters.q and filters.q.strip():
            needle = func.concat("%", func.fa_normalize(filters.q.strip()), "%")
            name = func.fa_normalize(
                func.concat_ws(" ", Profile.first_name, Profile.last_name, Profile.display_name)
            )
            stmt = stmt.where(or_(name.like(needle), User.username.ilike(needle)))
        return stmt.order_by(Profile.updated_at.desc()).limit(CANDIDATE_LIMIT)

    # ── زمینهٔ پروژه ───────────────────────────────────────────────────
    async def _project_context(
        self, project_id: uuid.UUID, actor: CurrentUser, titles: dict[uuid.UUID, str]
    ) -> SearchContext:
        project = await self.session.get(Project, project_id)
        if project is None or project.deleted_at is not None:
            raise NotFound("پروژه پیدا نشد.")
        is_member = await self.session.scalar(
            select(TeamMember.id)
            .join(Team, Team.id == TeamMember.team_id)
            .where(
                Team.project_id == project.id,
                TeamMember.user_id == actor.id,
                TeamMember.status == "ACTIVE",
            )
        )
        can_invite = await authz.has_permission(
            self.session, actor, Permission.PROJECT_APPLICATION_DECIDE, project.id
        )
        # تیم پروژهٔ دیگران برای جستجوکننده «وجود ندارد» — §6.4 قاعدهٔ ۴.
        if is_member is None and not can_invite:
            raise NotFound("پروژه پیدا نشد.")

        needs = [
            rules.Need(
                skill_id=req.skill_id,
                title_fa=titles.get(req.skill_id, "مهارت"),
                min_level=req.min_level,
                weight=req.weight,
            )
            for req in await self.session.scalars(
                select(ProjectRequiredSkill).where(ProjectRequiredSkill.project_id == project.id)
            )
        ]
        member_ids = await self._active_member_ids(project.id)
        team_levels: dict[uuid.UUID, int] = {}
        if member_ids:
            for skill_id, level in await self.session.execute(
                select(ProfileSkill.skill_id, func.max(ProfileSkill.level))
                .where(ProfileSkill.user_id.in_(member_ids))
                .group_by(ProfileSkill.skill_id)
            ):
                team_levels[skill_id] = int(level)
        return SearchContext(
            project=project,
            gaps=rules.team_gaps(needs, team_levels),
            can_invite=can_invite,
        )

    async def _active_member_ids(self, project_id: uuid.UUID) -> list[uuid.UUID]:
        rows = await self.session.scalars(
            select(TeamMember.user_id)
            .join(Team, Team.id == TeamMember.team_id)
            .where(Team.project_id == project_id, TeamMember.status == "ACTIVE")
        )
        return list(rows)

    # ── داده‌های گروهی — بدون N+1 (§5.14) ──────────────────────────────
    async def _skill_titles(self) -> dict[uuid.UUID, str]:
        rows = await self.session.execute(select(Skill.id, Skill.title_fa))
        return dict(rows.tuples().all())

    async def _skills_of(self, user_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[SkillOut]]:
        if not user_ids:
            return {}
        rows = await self.session.execute(
            select(
                ProfileSkill.user_id,
                ProfileSkill.skill_id,
                Skill.title_fa,
                ProfileSkill.level,
                ProfileSkill.verified_at.is_not(None),
            )
            .join(Skill, Skill.id == ProfileSkill.skill_id)
            .where(ProfileSkill.user_id.in_(user_ids))
        )
        result: dict[uuid.UUID, list[SkillOut]] = defaultdict(list)
        for uid, sid, title, level, verified in rows:
            result[uid].append(
                SkillOut(skill_id=sid, title_fa=title, level=level, verified=bool(verified))
            )
        return result

    async def _assets_of(self, user_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[str]]:
        if not user_ids:
            return {}
        rows = await self.session.execute(
            select(ProfileAsset.user_id, Asset.title_fa)
            .join(Asset, Asset.id == ProfileAsset.asset_id)
            .where(ProfileAsset.user_id.in_(user_ids))
            .order_by(Asset.sort_order)
        )
        result: dict[uuid.UUID, list[str]] = defaultdict(list)
        for uid, title in rows:
            result[uid].append(title)
        return result

    async def _offerings_of(self, user_id: uuid.UUID) -> set[uuid.UUID]:
        rows = await self.session.scalars(
            select(Enrollment.offering_id).where(
                Enrollment.student_id == user_id, Enrollment.status.in_(ENROLLED_STATUSES)
            )
        )
        return set(rows)

    async def _sharing_course(
        self, user_ids: list[uuid.UUID], offerings: set[uuid.UUID]
    ) -> set[uuid.UUID]:
        if not user_ids or not offerings:
            return set()
        rows = await self.session.scalars(
            select(Enrollment.student_id)
            .where(
                Enrollment.student_id.in_(user_ids),
                Enrollment.offering_id.in_(offerings),
                Enrollment.status.in_(ENROLLED_STATUSES),
            )
            .distinct()
        )
        return set(rows)

    async def _project_history(self, user_ids: list[uuid.UUID]) -> dict[uuid.UUID, tuple[int, int]]:
        """(پروژهٔ تمام‌شده با ماندن تا آخر، پروژهٔ نیمه‌کاره‌رها) — نرخ تکمیل §8.14."""
        if not user_ids:
            return {}
        completed = func.count().filter(
            and_(TeamMember.status == "ACTIVE", Project.status == "COMPLETED")
        )
        dropped = func.count().filter(TeamMember.status.in_(("LEFT", "REMOVED")))
        rows = await self.session.execute(
            select(TeamMember.user_id, completed, dropped)
            .join(Team, Team.id == TeamMember.team_id)
            .join(Project, Project.id == Team.project_id)
            .where(TeamMember.user_id.in_(user_ids))
            .group_by(TeamMember.user_id)
        )
        return {uid: (int(c), int(d)) for uid, c, d in rows}


__all__ = ["Match", "SearchContext", "SearchFilters", "SkillOut", "TeamSearchService"]
