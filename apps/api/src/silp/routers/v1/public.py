"""مسیرهای عمومی — صفحهٔ اصلی و نیمرخ عمومی. §5.3، §5.3.1، M7-10، M7-11.

| مسیر | مرجع |
|------|------|
| `GET /public/stats` | §5.3.1، §10.10 — آمار زنده، `Cache-Control: max-age=300` |
| `GET /public/stories` | §10.10 «سه داستان واقعی» |
| `GET /profiles/{username}` | FR-PROF-03 |

هیچ‌کدام احراز هویت نمی‌خواهد. نیمرخ عمومی اگر کاربر وارد باشد، به صاحبش
پیش‌نمایش نیمرخ خصوصی‌اش را هم نشان می‌دهد.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Path, Response

from silp.routers.deps import OptionalUserDep, SessionDep
from silp.schemas.common import ErrorResponse
from silp.schemas.public import (
    PublicBadgeOut,
    PublicCertificateOut,
    PublicLevelOut,
    PublicOutputOut,
    PublicProfileOut,
    PublicProjectOut,
    PublicSkillOut,
    PublicStatsOut,
    StoryMemberOut,
    StoryOut,
)
from silp.services.public_service import (
    PublicService,
    degree_fa,
    output_kind_fa,
    project_kind_fa,
    research_level_title,
)

#: §5.3.1 — آمار پنج دقیقه در کش مرورگر و پروکسی می‌ماند.
STATS_CACHE = "public, max-age=300"

router = APIRouter(prefix="/public", tags=["public"])
profiles_router = APIRouter(prefix="/profiles", tags=["public"])


@router.get("/stats", response_model=PublicStatsOut, summary="آمار زندهٔ سامانه")
async def public_stats(session: SessionDep, response: Response) -> PublicStatsOut:
    stats = await PublicService(session).stats()
    response.headers["Cache-Control"] = STATS_CACHE
    return PublicStatsOut(
        students=stats.students,
        active_projects=stats.active_projects,
        completed_projects=stats.completed_projects,
        completed_milestones=stats.completed_milestones,
        research_outputs=stats.research_outputs,
        verified_revenue_rial=stats.verified_revenue_rial,
        active_courses=stats.active_courses,
        certificates=stats.certificates,
    )


@router.get("/stories", response_model=list[StoryOut], summary="داستان‌های واقعی صفحهٔ اصلی")
async def public_stories(session: SessionDep, response: Response) -> list[StoryOut]:
    """آخرین پروژه‌های تکمیل‌شده. فهرست خالی یعنی بخش در صفحه دیده نشود."""
    stories = await PublicService(session).stories()
    response.headers["Cache-Control"] = STATS_CACHE
    return [
        StoryOut(
            project_id=story.project.id,
            title_fa=story.project.title_fa,
            summary=story.project.summary,
            kind=story.project.kind,
            kind_fa=project_kind_fa(story.project.kind),
            course_title=story.course_title,
            completed_at=story.completed_at,
            team_size=story.team_size,
            approved_milestones=story.approved_milestones,
            members=[
                StoryMemberOut(name=m.name, username=m.username, is_lead=m.is_lead)
                for m in story.members
            ],
        )
        for story in stories
    ]


@profiles_router.get(
    "/{username}",
    response_model=PublicProfileOut,
    summary="نیمرخ عمومی",
    responses={404: {"model": ErrorResponse}},
)
async def public_profile(
    username: Annotated[str, Path(min_length=2, max_length=40)],
    session: SessionDep,
    viewer: OptionalUserDep,
    response: Response,
) -> PublicProfileOut:
    data = await PublicService(session).profile(username, viewer)
    profile = data.profile
    # صفحهٔ صاحب نیمرخ پیش‌نمایش است و نباید در کش مشترک بنشیند.
    response.headers["Cache-Control"] = (
        "private, no-store" if data.is_owner else "public, max-age=60"
    )
    level = data.level
    return PublicProfileOut(
        username=data.user.username or username,
        name=profile.public_name,
        bio=profile.bio,
        is_owner=data.is_owner,
        is_public=profile.is_public,
        sections=data.sections,
        university=data.university_title,
        field_of_study=profile.field_of_study if data.sections["university"] else None,
        degree_level_fa=degree_fa(profile.degree_level) if data.sections["university"] else None,
        skills=[
            PublicSkillOut(
                title_fa=skill.title_fa, level=answer.level, verified=answer.verified_at is not None
            )
            for skill, answer in data.skills
        ],
        projects=[
            PublicProjectOut(
                id=project.id,
                title_fa=project.title_fa,
                kind=project.kind,
                kind_fa=project_kind_fa(project.kind),
                role_fa="مدیر پروژه" if is_lead else "عضو تیم",
                completed_at=completed_at,
            )
            for project, is_lead, completed_at in data.projects
        ],
        certificates=[
            PublicCertificateOut(
                public_code=c.public_code,
                kind=c.kind,
                title_fa=c.title_fa,
                issued_at=c.issued_at,
            )
            for c in data.certificates
        ],
        research_level=data.research_level,
        research_level_fa=research_level_title(data.research_level),
        research_outputs=[
            PublicOutputOut(
                title=o.title, kind_fa=output_kind_fa(o.kind), venue=o.venue, doi=o.doi, url=o.url
            )
            for o in data.research_outputs
        ],
        badges=[
            PublicBadgeOut(
                code=badge.code,
                title_fa=badge.title_fa,
                description=badge.description,
                icon=badge.icon,
                tier=badge.tier,
                awarded_at=awarded_at,
            )
            for badge, awarded_at in data.badges
        ],
        points=(
            PublicLevelOut(total=int(level.total), level=level.level, title_fa=level.title_fa)
            if level is not None
            else None
        ),
        member_since=data.user.created_at,
    )


__all__ = ["profiles_router", "router"]
