"""منشأ خوانای هر امتیاز — PRD §9.10 «شفافیت»، M5-09.

«هر عدد در رابط، قابل کلیک و منتهی به `/me/points` با فیلتر همان منبع.»
عکسش هم لازم است: هر ردیف دفتر کل باید بگوید از کجا آمده — نه
`QUIZ_ATTEMPT 018f…`، بلکه «آزمون هفتهٔ ۳ — آمار کاربردی» با پیوند به نتیجه.

یک کوئری به‌ازای هر **نوع** منبع، نه به‌ازای هر ردیف (§5.14 «بدون N+1»).
منبعی که دیگر وجود ندارد (پروژهٔ حذف‌شده) برچسب ندارد؛ ردیف امتیاز
می‌ماند، چون دفتر کل تاریخ است نه نما.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from silp.models.delivery import Deliverable, Milestone
from silp.models.education import (
    ClassSession,
    Course,
    CourseOffering,
    CourseWeek,
    Enrollment,
    Resource,
)
from silp.models.gamification import PointEntry
from silp.models.idea import Idea
from silp.models.project import Project, ProjectApplication
from silp.models.quiz import Quiz, QuizAttempt
from silp.models.venture import (
    METRIC_TITLE_FA,
    STAGE_TITLE_FA,
    Venture,
    VentureMetric,
    VentureStageChange,
)


@dataclass(frozen=True, slots=True)
class SourceLabel:
    label: str
    href: str | None


SourceRef = tuple[str, uuid.UUID]


async def describe(
    session: AsyncSession, entries: Iterable[PointEntry]
) -> dict[SourceRef, SourceLabel]:
    by_type: dict[str, set[uuid.UUID]] = defaultdict(set)
    for entry in entries:
        if entry.source_id is not None:
            by_type[entry.source_type].add(entry.source_id)

    labels: dict[SourceRef, SourceLabel] = {}
    for source_type, ids in by_type.items():
        resolver = _RESOLVERS.get(source_type)
        if resolver is not None:
            for source_id, label in (await resolver(session, ids)).items():
                labels[(source_type, source_id)] = label
    return labels


async def _resources(session: AsyncSession, ids: set[uuid.UUID]) -> dict[uuid.UUID, SourceLabel]:
    rows = await session.execute(
        select(Resource.id, Resource.title_fa, CourseWeek.offering_id, CourseWeek.week_number)
        .join(CourseWeek, CourseWeek.id == Resource.week_id)
        .where(Resource.id.in_(ids))
    )
    return {
        rid: SourceLabel(title, f"/courses/{offering}/weeks/{week}")
        for rid, title, offering, week in rows
    }


async def _weeks(session: AsyncSession, ids: set[uuid.UUID]) -> dict[uuid.UUID, SourceLabel]:
    rows = await session.execute(
        select(
            CourseWeek.id, CourseWeek.title_fa, CourseWeek.offering_id, CourseWeek.week_number
        ).where(CourseWeek.id.in_(ids))
    )
    return {
        wid: SourceLabel(f"هفتهٔ {week} — {title}", f"/courses/{offering}/weeks/{week}")
        for wid, title, offering, week in rows
    }


async def _quizzes(session: AsyncSession, ids: set[uuid.UUID]) -> dict[uuid.UUID, SourceLabel]:
    rows = await session.execute(
        select(Quiz.id, Quiz.title_fa, Quiz.offering_id).where(Quiz.id.in_(ids))
    )
    return {
        qid: SourceLabel(f"آزمون «{title}»", f"/courses/{offering}/quizzes")
        for qid, title, offering in rows
    }


async def _attempts(session: AsyncSession, ids: set[uuid.UUID]) -> dict[uuid.UUID, SourceLabel]:
    rows = await session.execute(
        select(QuizAttempt.id, QuizAttempt.attempt_no, Quiz.title_fa)
        .join(Quiz, Quiz.id == QuizAttempt.quiz_id)
        .where(QuizAttempt.id.in_(ids))
    )
    return {
        aid: SourceLabel(f"آزمون «{title}» — تلاش {no}", f"/quiz/{aid}/result")
        for aid, no, title in rows
    }


async def _sessions(session: AsyncSession, ids: set[uuid.UUID]) -> dict[uuid.UUID, SourceLabel]:
    rows = await session.execute(
        select(ClassSession.id, ClassSession.held_on, ClassSession.offering_id, Course.title_fa)
        .join(CourseOffering, CourseOffering.id == ClassSession.offering_id)
        .join(Course, Course.id == CourseOffering.course_id)
        .where(ClassSession.id.in_(ids))
    )
    return {
        sid: SourceLabel(f"جلسهٔ {course}", f"/courses/{offering}")
        for sid, _held_on, offering, course in rows
    }


async def _enrollments(session: AsyncSession, ids: set[uuid.UUID]) -> dict[uuid.UUID, SourceLabel]:
    rows = await session.execute(
        select(Enrollment.id, Enrollment.offering_id, Course.title_fa)
        .join(CourseOffering, CourseOffering.id == Enrollment.offering_id)
        .join(Course, Course.id == CourseOffering.course_id)
        .where(Enrollment.id.in_(ids))
    )
    return {
        eid: SourceLabel(f"درس {course}", f"/courses/{offering}") for eid, offering, course in rows
    }


async def _projects(session: AsyncSession, ids: set[uuid.UUID]) -> dict[uuid.UUID, SourceLabel]:
    rows = await session.execute(select(Project.id, Project.title_fa).where(Project.id.in_(ids)))
    return {pid: SourceLabel(f"پروژهٔ {title}", f"/projects/{pid}") for pid, title in rows}


async def _applications(session: AsyncSession, ids: set[uuid.UUID]) -> dict[uuid.UUID, SourceLabel]:
    rows = await session.execute(
        select(ProjectApplication.id, Project.id, Project.title_fa)
        .join(Project, Project.id == ProjectApplication.project_id)
        .where(ProjectApplication.id.in_(ids))
    )
    return {aid: SourceLabel(f"پروژهٔ {title}", f"/projects/{pid}") for aid, pid, title in rows}


async def _milestones(session: AsyncSession, ids: set[uuid.UUID]) -> dict[uuid.UUID, SourceLabel]:
    rows = await session.execute(
        select(Milestone.id, Milestone.title_fa, Project.id, Project.title_fa)
        .join(Project, Project.id == Milestone.project_id)
        .where(Milestone.id.in_(ids))
    )
    return {
        mid: SourceLabel(f"{title} — {project}", f"/projects/{pid}/workspace")
        for mid, title, pid, project in rows
    }


async def _deliverables(session: AsyncSession, ids: set[uuid.UUID]) -> dict[uuid.UUID, SourceLabel]:
    rows = await session.execute(
        select(Deliverable.id, Milestone.title_fa, Milestone.project_id)
        .join(Milestone, Milestone.id == Deliverable.milestone_id)
        .where(Deliverable.id.in_(ids))
    )
    return {
        did: SourceLabel(f"بازبینی «{title}»", f"/projects/{pid}/workspace")
        for did, title, pid in rows
    }


async def _profile(session: AsyncSession, ids: set[uuid.UUID]) -> dict[uuid.UUID, SourceLabel]:
    return {uid: SourceLabel("تکمیل نیمرخ", "/onboarding/results") for uid in ids}


async def _ideas(session: AsyncSession, ids: set[uuid.UUID]) -> dict[uuid.UUID, SourceLabel]:
    rows = await session.execute(select(Idea.id, Idea.title).where(Idea.id.in_(ids)))
    return {iid: SourceLabel(f"ایدهٔ «{title}»", f"/ideas/{iid}") for iid, title in rows}


async def _ventures(session: AsyncSession, ids: set[uuid.UUID]) -> dict[uuid.UUID, SourceLabel]:
    rows = await session.execute(select(Venture.id, Venture.name).where(Venture.id.in_(ids)))
    return {vid: SourceLabel(f"کسب‌وکار {name}", f"/ventures/{vid}") for vid, name in rows}


async def _stage_changes(
    session: AsyncSession, ids: set[uuid.UUID]
) -> dict[uuid.UUID, SourceLabel]:
    rows = await session.execute(
        select(VentureStageChange.id, VentureStageChange.to_stage, Venture.id, Venture.name)
        .join(Venture, Venture.id == VentureStageChange.venture_id)
        .where(VentureStageChange.id.in_(ids))
    )
    return {
        cid: SourceLabel(f"{name} — مرحلهٔ {STAGE_TITLE_FA.get(stage, stage)}", f"/ventures/{vid}")
        for cid, stage, vid, name in rows
    }


async def _metrics(session: AsyncSession, ids: set[uuid.UUID]) -> dict[uuid.UUID, SourceLabel]:
    rows = await session.execute(
        select(
            VentureMetric.id,
            VentureMetric.metric,
            VentureMetric.venture_id,
            VentureMetric.project_id,
            Venture.name,
            Project.title_fa,
        )
        .outerjoin(Venture, Venture.id == VentureMetric.venture_id)
        .outerjoin(Project, Project.id == VentureMetric.project_id)
        .where(VentureMetric.id.in_(ids))
    )
    labels: dict[uuid.UUID, SourceLabel] = {}
    for mid, metric, vid, pid, venture, project in rows:
        title = METRIC_TITLE_FA.get(metric, metric)
        if vid is not None:
            labels[mid] = SourceLabel(f"{title} — {venture}", f"/ventures/{vid}")
        else:
            labels[mid] = SourceLabel(f"{title} — {project}", f"/projects/{pid}/workspace")
    return labels


_RESOLVERS = {
    "RESOURCE": _resources,
    "COURSE_WEEK": _weeks,
    "QUIZ": _quizzes,
    "QUIZ_ATTEMPT": _attempts,
    "CLASS_SESSION": _sessions,
    "ENROLLMENT": _enrollments,
    "PROJECT": _projects,
    "APPLICATION": _applications,
    "MILESTONE": _milestones,
    "DELIVERABLE": _deliverables,
    "PROFILE": _profile,
    "IDEA": _ideas,
    "VENTURE": _ventures,
    "VENTURE_STAGE": _stage_changes,
    "METRIC": _metrics,
}

SOURCE_TYPE_TITLE_FA: dict[str, str] = {
    "RESOURCE": "منبع درسی",
    "COURSE_WEEK": "هفتهٔ درس",
    "QUIZ": "آزمون",
    "QUIZ_ATTEMPT": "تلاش آزمون",
    "CLASS_SESSION": "جلسهٔ کلاس",
    "ENROLLMENT": "درس",
    "PROJECT": "پروژه",
    "APPLICATION": "درخواست پروژه",
    "MILESTONE": "مرحلهٔ پروژه",
    "DELIVERABLE": "تحویل‌دادنی",
    "PROFILE": "نیمرخ",
    "IDEA": "ایده",
    "VENTURE": "کسب‌وکار",
    "VENTURE_STAGE": "مرحلهٔ کسب‌وکار",
    "METRIC": "فعالیت و فروش",
}


__all__ = ["SOURCE_TYPE_TITLE_FA", "SourceLabel", "describe"]
