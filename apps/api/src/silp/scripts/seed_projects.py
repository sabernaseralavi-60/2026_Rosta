"""بانک پروژهٔ اولیه — §14.5، M7-16.

داده در `silp.content.project_bank` است (۲۵ پروژه)؛ اینجا فقط درجش.
هم `seed` توسعه و هم `seed_launch` تولید از همین تابع استفاده می‌کنند.

اسکریپت بی‌اثر در تکرار است: کلید یکتایی `slug` است. پروژه‌ای که پیش از
M7-16 با سه مرحلهٔ عمومی ساخته شده و هنوز تحویلی نگرفته، مراحل واقعی‌اش
را می‌گیرد.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from silp.content.project_bank import PROJECTS, MilestoneSpec, ProjectSeed
from silp.core.logging import get_logger
from silp.models.delivery import Deliverable, Milestone
from silp.models.identity import User
from silp.models.project import (
    Project,
    ProjectInterest,
    ProjectRequiredAsset,
    ProjectRequiredSkill,
    ProjectRole,
    Team,
    TeamMember,
)
from silp.models.taxonomy import Asset, Interest, Skill
from silp.services.city_service import CityService

log = get_logger("silp.seed.projects")

# سه مرحلهٔ عمومی M2 — پیش از M7-16 همهٔ پروژه‌های نمونه همین را داشتند.
# فقط برای شناختن و جایگزین کردنشان نگه داشته شده است.
LEGACY_MILESTONE_TITLES = ("شناخت و برنامه‌ریزی", "اجرا", "گزارش و تحویل نهایی")


async def _code_map(
    session: AsyncSession, model: type[Skill] | type[Asset] | type[Interest]
) -> dict[str, uuid.UUID]:
    """نگاشت کد ← شناسه. داده‌های اولیه با کد نوشته شده‌اند، نه UUID:
    UUIDها در هر محیط فرق می‌کنند و در سند §14 جایی ندارند."""
    rows = (await session.execute(select(model.code, model.id))).all()
    return {row.code: row.id for row in rows}


async def seed_projects(session: AsyncSession, lead_id: uuid.UUID) -> tuple[int, int]:
    """درج پروژه‌های §14.5. خروجی: (ساخته‌شده، از قبل موجود)."""
    skills = await _code_map(session, Skill)
    assets = await _code_map(session, Asset)
    interests = await _code_map(session, Interest)

    created = 0
    existing = 0

    for seed in PROJECTS:
        found = await session.scalar(select(Project).where(Project.slug == seed.slug))
        if found is not None:
            existing += 1
            if seed.workflow and found.workflow is None:
                await _adopt_workflow(session, found)
            elif seed.milestones:
                await _adopt_milestones(session, found, seed)
            continue

        project = Project(
            slug=seed.slug,
            title_fa=seed.title_fa,
            summary=seed.summary,
            description=seed.description,
            kind=seed.kind,
            # پروژهٔ نمونه باید بلافاصله در پیشنهادها دیده شود.
            status="OPEN",
            lead_id=lead_id,
            time_commitment_hpw=seed.time_commitment_hpw,
            team_size_min=seed.team_size_min,
            team_size_max=seed.team_size_max,
            work_style=seed.work_style,
            difficulty=seed.difficulty,
            expected_output=seed.expected_output,
            rewards=seed.rewards,
            tags=list(seed.tags),
        )
        session.add(project)
        await session.flush()

        for skill in seed.skills:
            if skill.code not in skills:
                log.warning("seed_unknown_skill", code=skill.code, project=seed.slug)
                continue
            session.add(
                ProjectRequiredSkill(
                    project_id=project.id,
                    skill_id=skills[skill.code],
                    min_level=skill.min_level,
                    weight=skill.weight,
                    is_teachable=skill.teachable,
                )
            )

        for asset in seed.assets:
            if asset.code not in assets:
                log.warning("seed_unknown_asset", code=asset.code, project=seed.slug)
                continue
            session.add(
                ProjectRequiredAsset(
                    project_id=project.id,
                    asset_id=assets[asset.code],
                    is_mandatory=asset.mandatory,
                )
            )

        for code in seed.interests:
            if code not in interests:
                log.warning("seed_unknown_interest", code=code, project=seed.slug)
                continue
            session.add(ProjectInterest(project_id=project.id, interest_id=interests[code]))

        for role in seed.roles:
            session.add(
                ProjectRole(project_id=project.id, title_fa=role.title_fa, slots=role.slots)
            )

        # §7.12 — پروژهٔ `OPEN` تیم دارد و مدیرش عضو `is_lead` آن است؛
        # همان کاری که `publish` می‌کند، اینجا دستی انجام می‌شود چون
        # پروژهٔ نمونه مستقیم `OPEN` ساخته می‌شود.
        team = Team(project_id=project.id, name=f"تیم {seed.title_fa}")
        session.add(team)
        await session.flush()
        session.add(TeamMember(team_id=team.id, user_id=lead_id, is_lead=True, status="ACTIVE"))

        if seed.workflow:
            await CityService(session).apply_workflow(project)
            created += 1
            log.info("seed_project_created", slug=seed.slug, kind=seed.kind)
            continue

        _add_milestones(session, project.id, seed.milestones)

        created += 1
        log.info("seed_project_created", slug=seed.slug, kind=seed.kind)

    return created, existing


def _add_milestones(
    session: AsyncSession, project_id: uuid.UUID, milestones: tuple[MilestoneSpec, ...]
) -> None:
    for order, spec in enumerate(milestones, start=1):
        session.add(
            Milestone(
                project_id=project_id,
                title_fa=spec.title_fa,
                description=spec.description,
                sort_order=order,
                points=Decimal(spec.points),
                output_kind=spec.output_kind,
                checklist=list(spec.checklist),
            )
        )


async def _has_deliverables(session: AsyncSession, project_id: uuid.UUID) -> bool:
    count = await session.scalar(
        select(func.count())
        .select_from(Deliverable)
        .join(Milestone, Milestone.id == Deliverable.milestone_id)
        .where(Milestone.project_id == project_id)
    )
    return bool(count)


async def _adopt_milestones(session: AsyncSession, project: Project, seed: ProjectSeed) -> None:
    """سه مرحلهٔ عمومی M2 را با مراحل واقعی بانک جایگزین می‌کند.

    فقط وقتی مراحل فعلی **دقیقاً** همان الگوی عمومی‌اند و تحویلی نگرفته‌اند؛
    مرحله‌ای که استاد ویرایش کرده یا دانشجو رویش کار کرده، دست نمی‌خورد.
    """
    titles = tuple(
        (
            await session.scalars(
                select(Milestone.title_fa)
                .where(Milestone.project_id == project.id)
                .order_by(Milestone.sort_order)
            )
        ).all()
    )
    if titles != LEGACY_MILESTONE_TITLES:
        return
    if await _has_deliverables(session, project.id):
        log.warning("seed_milestones_skipped", slug=project.slug, reason="has_deliverables")
        return
    await session.execute(delete(Milestone).where(Milestone.project_id == project.id))
    _add_milestones(session, project.id, seed.milestones)
    log.info("seed_milestones_adopted", slug=project.slug)


async def _adopt_workflow(session: AsyncSession, project: Project) -> None:
    """پروژهٔ نمونه‌ای که پیش از ADR-0016 با سه مرحلهٔ عمومی ساخته شد.

    فقط اگر هنوز هیچ تحویلی نگرفته باشد، مراحلش با الگو جایگزین می‌شوند؛
    تحویل‌دادنی واقعی هرگز برای یک دادهٔ نمونه دور ریخته نمی‌شود.
    """
    if await _has_deliverables(session, project.id):
        log.warning("seed_workflow_skipped", slug=project.slug, reason="has_deliverables")
        return
    await session.execute(delete(Milestone).where(Milestone.project_id == project.id))
    await CityService(session).apply_workflow(project)
    log.info("seed_workflow_adopted", slug=project.slug)


async def ensure_lead(session: AsyncSession, mobile: str) -> uuid.UUID:
    """مدیر پروژه‌های نمونه — حساب استاد §14.8."""
    user = await session.scalar(select(User).where(User.mobile == mobile))
    if user is None:
        stmt = insert(User).values(mobile=mobile).on_conflict_do_nothing().returning(User.id)
        created_id = await session.scalar(stmt)
        if created_id is not None:
            return created_id
        user = await session.scalar(select(User).where(User.mobile == mobile))
    if user is None:  # pragma: no cover — درج و خواندن هر دو شکست خورده
        msg = f"حساب مدیر پروژه ({mobile}) ساخته نشد."
        raise RuntimeError(msg)
    return user.id


__all__ = ["PROJECTS", "ProjectSeed", "ensure_lead", "seed_projects"]
