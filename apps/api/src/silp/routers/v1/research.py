"""مسیرهای /research — §5.8، FR-RES-01/02/03، M7-05 و M7-06، ADR-0015.

* مسیر چهارسطحی (`/research/tracks`) برای مهمان هم پاسخ می‌دهد: راهنما و
  الگوی هر سطح عمومی است (§3.4 «/research — همه»)؛ وضعیت و تحویل‌ها فقط
  برای خود کاربر.
* بانک موضوع عمومی است جز پیشنهادهای تأییدنشده و موضوع بسته. نام کسی که
  موضوعی را رزرو کرده فقط برای کادر است.
* خروجی‌های پژوهشی فعلاً فقط برای خود نویسنده و بازبین دیده می‌شوند؛
  نمایش در نیمرخ عمومی با M7-11 می‌آید.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select

from silp.core.exceptions import NotFound
from silp.core.permissions import CurrentUser, Permission
from silp.domain import research as rules
from silp.models.file import File
from silp.models.gamification import PointEntry
from silp.models.project import Project
from silp.models.research import (
    REVIEW_STATUS_TITLE_FA,
    SUBMISSION_STATUS_TITLE_FA,
    ResearchOutput,
    ResearchSubmission,
    ResearchTopic,
)
from silp.routers.deps import (
    CurrentUserDep,
    FileServiceDep,
    OptionalUserDep,
    SessionDep,
    SettingsDep,
)
from silp.schemas.common import ErrorResponse, Page, PageParams
from silp.schemas.research import (
    DownloadOut,
    EvidenceFieldOut,
    FileRefOut,
    LevelOut,
    OutputIn,
    OutputOut,
    OutputReviewIn,
    OutputReviewItemOut,
    PersonOut,
    PreviousVersionOut,
    ProjectRefOut,
    ReviewItemOut,
    SubmissionOut,
    SubmissionReviewIn,
    SubmitIn,
    TopicBriefOut,
    TopicCloseIn,
    TopicIn,
    TopicOut,
    TopicReviewIn,
    TopicStatus,
    TrackOut,
)
from silp.services import authz
from silp.services.directory import DisplayName, display_names
from silp.services.output_service import OutputDraft, OutputService
from silp.services.points_service import PointsService
from silp.services.research_service import ResearchService
from silp.services.topic_service import TopicDraft, TopicService

router = APIRouter(prefix="/research", tags=["research"])


def get_research_service(session: SessionDep) -> ResearchService:
    return ResearchService(session)


def get_topic_service(session: SessionDep) -> TopicService:
    return TopicService(session)


def get_output_service(session: SessionDep) -> OutputService:
    return OutputService(session)


ResearchServiceDep = Annotated[ResearchService, Depends(get_research_service)]
TopicServiceDep = Annotated[TopicService, Depends(get_topic_service)]
OutputServiceDep = Annotated[OutputService, Depends(get_output_service)]


def _now() -> datetime:
    return datetime.now(UTC)


def _person(names: dict[uuid.UUID, DisplayName], user_id: uuid.UUID | None) -> PersonOut | None:
    if user_id is None:
        return None
    entry = names.get(user_id)
    return PersonOut(
        id=user_id,
        name=entry.full_name if entry else None,
        username=entry.username if entry else None,
    )


def _idle_days_left(topic: ResearchTopic) -> int | None:
    if topic.status != "RESERVED" or topic.last_activity_at is None:
        return None
    idle = (_now() - topic.last_activity_at).days
    return max(rules.RESERVATION_IDLE_DAYS - idle, 0)


def _evidence_fields(level: int) -> list[EvidenceFieldOut]:
    return [
        EvidenceFieldOut(
            key=f.key,
            label_fa=f.label_fa,
            kind=f.kind,
            hint_fa=f.hint_fa,
            min_value=f.min_value,
            min_length=f.min_length,
        )
        for f in rules.level_spec(level).evidence
    ]


async def _files(
    session: SessionDep, submissions: list[ResearchSubmission]
) -> dict[uuid.UUID, File]:
    ids = {link.file_id for s in submissions for link in s.files}
    if not ids:
        return {}
    rows = await session.scalars(select(File).where(File.id.in_(ids)))
    return {f.id: f for f in rows}


async def _topic_titles(
    session: SessionDep, submissions: list[ResearchSubmission]
) -> dict[uuid.UUID, str]:
    ids = {s.topic_id for s in submissions if s.topic_id is not None}
    if not ids:
        return {}
    rows = await session.execute(
        select(ResearchTopic.id, ResearchTopic.title).where(ResearchTopic.id.in_(ids))
    )
    return dict(rows.tuples().all())


def _submission(
    row: ResearchSubmission,
    names: dict[uuid.UUID, DisplayName],
    files: dict[uuid.UUID, File],
    topics: dict[uuid.UUID, str],
) -> SubmissionOut:
    return SubmissionOut(
        id=row.id,
        level=row.level,
        version=row.version,
        status=row.status,
        status_fa=SUBMISSION_STATUS_TITLE_FA[row.status],
        summary=row.summary,
        links=list(row.links),
        evidence=dict(row.evidence),
        files=[
            FileRefOut(id=link.file_id, original_name=files[link.file_id].original_name)
            for link in row.files
            if link.file_id in files
        ],
        topic_title=topics.get(row.topic_id) if row.topic_id else None,
        feedback=row.feedback,
        reviewer=_person(names, row.reviewed_by),
        reviewed_at=row.reviewed_at,
        submitted_at=row.submitted_at,
    )


# ── مسیر چهارسطحی — FR-RES-01 ──────────────────────────────────────────
@router.get("/tracks", response_model=TrackOut, summary="مسیر پژوهشی من")
async def my_track(
    service: ResearchServiceDep, viewer: OptionalUserDep, session: SessionDep
) -> TrackOut:
    """چهار سطح با راهنما، الگو و شاهدهای لازم؛ برای کاربر واردشده، وضعیت و تحویل‌ها."""
    points = PointsService(session)
    tracks = await service.tracks(viewer.id) if viewer else {}
    submissions = await service.submissions(viewer.id) if viewer else {}
    flat = [s for versions in submissions.values() for s in versions]
    names = await display_names(
        session, [*(t.mentor_id for t in tracks.values()), *(s.reviewed_by for s in flat)]
    )
    files = await _files(session, flat)
    topics = await _topic_titles(session, flat)
    statuses = {level: t.status for level, t in tracks.items()}

    levels: list[LevelOut] = []
    for level in rules.LEVELS:
        spec = rules.level_spec(level)
        rule = await points.rule(spec.rule_code)
        state = (
            rules.level_state(level, statuses)
            if viewer
            else ("AVAILABLE" if level == 1 else "LOCKED")
        )
        track = tracks.get(level)
        levels.append(
            LevelOut(
                level=level,
                title_fa=spec.title_fa,
                deliverable_fa=spec.deliverable_fa,
                points=rule.base_points if rule else None,
                state=state,
                state_fa=rules.LEVEL_STATE_TITLE_FA[state],
                steps=list(spec.steps),
                checklist=list(spec.checklist),
                template_title_fa=spec.template_title_fa,
                template_columns=list(spec.template_columns),
                evidence_fields=_evidence_fields(level),
                min_attachments=spec.min_attachments,
                attachments_hint_fa=spec.attachments_hint_fa,
                mentor=_person(names, track.mentor_id) if track else None,
                started_at=track.started_at if track else None,
                approved_at=track.approved_at if track else None,
                submissions=[
                    _submission(s, names, files, topics) for s in submissions.get(level, [])
                ],
            )
        )

    topic = None
    can_participate = can_review = False
    if viewer is not None:
        current = await service.topics.current_for(viewer.id)
        if current is not None:
            topic = TopicBriefOut(
                id=current.id,
                title=current.title,
                status=current.status,
                status_fa=rules.TOPIC_STATUS_TITLE_FA[current.status],
                idle_days_left=_idle_days_left(current),
            )
        can_participate = await authz.has_permission(
            session, viewer, Permission.RESEARCH_PARTICIPATE
        )
        can_review = await service.can_review(viewer)
    current_level = rules.current_level(statuses)
    return TrackOut(
        levels=levels,
        current_level=current_level,
        topic=topic,
        can_participate=can_participate,
        can_review=can_review,
        completed=current_level is None,
    )


@router.post(
    "/tracks/{level}/submit",
    response_model=SubmissionOut,
    status_code=status.HTTP_201_CREATED,
    summary="ارسال تحویل‌دادنی سطح",
    responses={
        409: {"model": ErrorResponse, "description": "سطح قفل، تأییدشده یا در انتظار بررسی"},
        422: {"model": ErrorResponse, "description": "`details.missing` — شاهدهای کم"},
    },
)
async def submit_level(
    level: int,
    payload: SubmitIn,
    current: CurrentUserDep,
    service: ResearchServiceDep,
    files: FileServiceDep,
    session: SessionDep,
) -> SubmissionOut:
    attachments = await files.load_attachable(list(payload.file_ids), owner_id=current.id)
    row = await service.submit(
        actor=current,
        level=level,
        summary=payload.summary,
        links=list(payload.links),
        file_ids=[f.id for f in attachments],
        evidence=dict(payload.evidence),
    )
    return _submission(
        row,
        {},
        {f.id: f for f in attachments},
        await _topic_titles(session, [row]),
    )


@router.get(
    "/review-queue",
    response_model=list[ReviewItemOut],
    summary="صف بررسی مسیر پژوهش",
    responses={403: {"model": ErrorResponse}},
)
async def review_queue(
    current: CurrentUserDep, service: ResearchServiceDep, session: SessionDep
) -> list[ReviewItemOut]:
    rows = await service.review_queue(current)
    previous: dict[tuple[uuid.UUID, int], list[ResearchSubmission]] = defaultdict(list)
    if rows:
        keys = {(r.user_id, r.level) for r in rows}
        for old in await session.scalars(
            select(ResearchSubmission)
            .where(
                ResearchSubmission.user_id.in_({k[0] for k in keys}),
                ResearchSubmission.status != "SUBMITTED",
            )
            .order_by(ResearchSubmission.version.desc())
        ):
            if (old.user_id, old.level) in keys:
                previous[(old.user_id, old.level)].append(old)
    names = await display_names(session, [r.user_id for r in rows])
    files = await _files(session, rows)
    topics = await _topic_titles(session, rows)
    items: list[ReviewItemOut] = []
    for row in rows:
        spec = rules.level_spec(row.level)
        student = _person(names, row.user_id)
        assert student is not None
        items.append(
            ReviewItemOut(
                **_submission(row, names, files, topics).model_dump(),
                student=student,
                level_title_fa=spec.title_fa,
                evidence_fields=_evidence_fields(row.level),
                checklist=list(spec.checklist),
                previous=[
                    PreviousVersionOut(
                        version=p.version,
                        status=p.status,
                        feedback=p.feedback,
                        reviewed_at=p.reviewed_at,
                    )
                    for p in previous.get((row.user_id, row.level), [])
                ],
            )
        )
    return items


@router.post(
    "/submissions/{submission_id}/review",
    response_model=SubmissionOut,
    summary="تأیید یا درخواست اصلاح تحویل سطح",
    responses={403: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
async def review_submission(
    submission_id: uuid.UUID,
    payload: SubmissionReviewIn,
    current: CurrentUserDep,
    service: ResearchServiceDep,
    session: SessionDep,
) -> SubmissionOut:
    row = await service.review(
        submission_id=submission_id,
        actor=current,
        decision=payload.decision,
        feedback=payload.feedback,
    )
    names = await display_names(session, [row.reviewed_by])
    return _submission(
        row, names, await _files(session, [row]), await _topic_titles(session, [row])
    )


@router.get(
    "/submissions/{submission_id}/files/{file_id}/download-url",
    response_model=DownloadOut,
    summary="دانلود پیوست تحویل — دانشجو یا بازبین",
    responses={404: {"model": ErrorResponse}},
)
async def submission_file(
    submission_id: uuid.UUID,
    file_id: uuid.UUID,
    current: CurrentUserDep,
    service: ResearchServiceDep,
    files: FileServiceDep,
    session: SessionDep,
    settings: SettingsDep,
) -> DownloadOut:
    row = await service.require_visible(submission_id, current)
    if file_id not in {link.file_id for link in row.files}:
        raise NotFound("فایل پیدا نشد.")
    file = await session.get(File, file_id)
    if file is None or file.deleted_at is not None:
        raise NotFound("فایل پیدا نشد.")
    return DownloadOut(
        download_url=await files.download_url(file=file),
        expires_in=settings.download_url_ttl_seconds,
        original_name=file.original_name,
    )


# ── بانک موضوع — FR-RES-03 ─────────────────────────────────────────────
async def _topic_out(
    service: TopicService,
    topic: ResearchTopic,
    viewer: CurrentUser | None,
    *,
    manager: bool,
    names: dict[uuid.UUID, DisplayName],
    holds_reservation: bool,
) -> TopicOut:
    mine = viewer is not None and viewer.id == topic.proposer_id
    reserved_by_me = viewer is not None and topic.reserved_by == viewer.id
    proposer = _person(names, topic.proposer_id)
    assert proposer is not None
    return TopicOut(
        id=topic.id,
        title=topic.title,
        description=topic.description,
        prerequisites=topic.prerequisites,
        level=topic.level,
        status=topic.status,
        status_fa=rules.TOPIC_STATUS_TITLE_FA[topic.status],
        proposer=proposer,
        reserved_by=_person(names, topic.reserved_by) if manager else None,
        reserved_by_me=reserved_by_me,
        reserved_at=topic.reserved_at if (manager or reserved_by_me) else None,
        idle_days_left=_idle_days_left(topic) if (manager or reserved_by_me) else None,
        review_note=topic.review_note if (manager or mine) else None,
        is_mine=mine,
        can_edit=manager or (mine and topic.status == "PROPOSED"),
        can_manage=manager,
        can_reserve=viewer is not None and topic.status == "OPEN" and not holds_reservation,
        can_release=topic.status == "RESERVED" and (reserved_by_me or manager),
        created_at=topic.created_at,
    )


async def _holds_reservation(service: TopicService, viewer: CurrentUser | None) -> bool:
    if viewer is None:
        return False
    held = await service.session.scalar(
        select(ResearchTopic.id).where(
            ResearchTopic.reserved_by == viewer.id, ResearchTopic.status == "RESERVED"
        )
    )
    return held is not None


async def _one_topic(
    service: TopicService, topic: ResearchTopic, viewer: CurrentUser | None
) -> TopicOut:
    names = await display_names(service.session, [topic.proposer_id, topic.reserved_by])
    return await _topic_out(
        service,
        topic,
        viewer,
        manager=await service.can_manage(viewer),
        names=names,
        holds_reservation=await _holds_reservation(service, viewer),
    )


@router.get("/topics", response_model=Page[TopicOut], summary="بانک موضوع پژوهشی")
async def list_topics(
    service: TopicServiceDep,
    viewer: OptionalUserDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    status_filter: Annotated[TopicStatus | None, Query(alias="status")] = None,
    level: Annotated[int | None, Query(ge=1, le=4)] = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    mine: Annotated[bool, Query()] = False,
) -> Page[TopicOut]:
    params = PageParams(page=page, page_size=page_size)
    manager = await service.can_manage(viewer)
    stmt = service.list_query(
        actor=viewer, manager=manager, status=status_filter, level=level, q=q, mine=mine
    )
    topics, total = await service.page(stmt, offset=params.offset, limit=params.page_size)
    names = await display_names(
        service.session, [*(t.proposer_id for t in topics), *(t.reserved_by for t in topics)]
    )
    holds = await _holds_reservation(service, viewer)
    return Page.of(
        [
            await _topic_out(
                service, t, viewer, manager=manager, names=names, holds_reservation=holds
            )
            for t in topics
        ],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )


@router.post(
    "/topics",
    response_model=TopicOut,
    status_code=status.HTTP_201_CREATED,
    summary="ثبت یا پیشنهاد موضوع",
)
async def create_topic(
    payload: TopicIn, current: CurrentUserDep, service: TopicServiceDep
) -> TopicOut:
    """کادر آموزشی موضوع **باز** ثبت می‌کند؛ دانشجو **پیشنهاد** می‌دهد که تا تأیید پنهان است."""
    topic = await service.create(
        actor=current,
        draft=TopicDraft(
            title=payload.title,
            description=payload.description,
            prerequisites=payload.prerequisites,
            level=payload.level,
        ),
    )
    return await _one_topic(service, topic, current)


@router.get(
    "/topics/{topic_id}",
    response_model=TopicOut,
    summary="جزئیات موضوع",
    responses={404: {"model": ErrorResponse}},
)
async def get_topic(
    topic_id: uuid.UUID, service: TopicServiceDep, viewer: OptionalUserDep
) -> TopicOut:
    return await _one_topic(service, await service.require(topic_id, viewer), viewer)


@router.patch("/topics/{topic_id}", response_model=TopicOut, summary="ویرایش موضوع")
async def update_topic(
    topic_id: uuid.UUID, payload: TopicIn, current: CurrentUserDep, service: TopicServiceDep
) -> TopicOut:
    topic = await service.require(topic_id, current)
    topic = await service.update(
        topic=topic,
        actor=current,
        draft=TopicDraft(
            title=payload.title,
            description=payload.description,
            prerequisites=payload.prerequisites,
            level=payload.level,
        ),
    )
    return await _one_topic(service, topic, current)


@router.post("/topics/{topic_id}/review", response_model=TopicOut, summary="تأیید یا رد پیشنهاد")
async def review_topic(
    topic_id: uuid.UUID,
    payload: TopicReviewIn,
    current: CurrentUserDep,
    service: TopicServiceDep,
) -> TopicOut:
    topic = await service.require(topic_id, current)
    topic = await service.review(
        topic=topic, actor=current, decision=payload.decision, note=payload.note
    )
    return await _one_topic(service, topic, current)


@router.post(
    "/topics/{topic_id}/reserve",
    response_model=TopicOut,
    summary="رزرو موضوع",
    responses={409: {"model": ErrorResponse, "description": "TOPIC_ALREADY_RESERVED"}},
)
async def reserve_topic(
    topic_id: uuid.UUID, current: CurrentUserDep, service: TopicServiceDep
) -> TopicOut:
    topic = await service.reserve(topic_id=topic_id, actor=current)
    return await _one_topic(service, topic, current)


@router.post("/topics/{topic_id}/release", response_model=TopicOut, summary="آزاد کردن رزرو")
async def release_topic(
    topic_id: uuid.UUID, current: CurrentUserDep, service: TopicServiceDep
) -> TopicOut:
    topic = await service.require(topic_id, current)
    topic = await service.release(topic=topic, actor=current)
    return await _one_topic(service, topic, current)


@router.post("/topics/{topic_id}/close", response_model=TopicOut, summary="بستن موضوع")
async def close_topic(
    topic_id: uuid.UUID,
    payload: TopicCloseIn,
    current: CurrentUserDep,
    service: TopicServiceDep,
) -> TopicOut:
    topic = await service.require(topic_id, current)
    topic = await service.close(topic=topic, actor=current, reason=payload.reason)
    return await _one_topic(service, topic, current)


@router.post("/topics/{topic_id}/reopen", response_model=TopicOut, summary="بازگشایی موضوع")
async def reopen_topic(
    topic_id: uuid.UUID, current: CurrentUserDep, service: TopicServiceDep
) -> TopicOut:
    topic = await service.require(topic_id, current)
    topic = await service.reopen(topic=topic, actor=current)
    return await _one_topic(service, topic, current)


# ── خروجی پژوهشی — FR-RES-02 ───────────────────────────────────────────
async def _outputs(
    session: SessionDep, outputs: list[ResearchOutput], viewer_id: uuid.UUID | None = None
) -> list[OutputOut]:
    file_ids = {o.file_id for o in outputs if o.file_id is not None}
    project_ids = {o.project_id for o in outputs if o.project_id is not None}
    files = (
        {f.id: f for f in await session.scalars(select(File).where(File.id.in_(file_ids)))}
        if file_ids
        else {}
    )
    projects = (
        dict(
            (
                await session.execute(
                    select(Project.id, Project.title_fa).where(Project.id.in_(project_ids))
                )
            )
            .tuples()
            .all()
        )
        if project_ids
        else {}
    )
    points: dict[uuid.UUID, Decimal] = {}
    if outputs:
        for source_id, total in await session.execute(
            select(PointEntry.source_id, func.sum(PointEntry.amount))
            .where(
                PointEntry.source_type == "RESEARCH_OUTPUT",
                PointEntry.source_id.in_([o.id for o in outputs]),
            )
            .group_by(PointEntry.source_id)
        ):
            if source_id is not None:
                points[source_id] = total or Decimal(0)
    result: list[OutputOut] = []
    for o in outputs:
        file = files.get(o.file_id) if o.file_id else None
        result.append(
            OutputOut(
                id=o.id,
                kind=o.kind,
                kind_fa=rules.OUTPUT_KIND_TITLE_FA[o.kind],
                title=o.title,
                authors=o.authors,
                venue=o.venue,
                quartile=o.quartile,
                status=o.status,
                status_fa=rules.OUTPUT_STATUS_TITLE_FA[o.status],
                doi=o.doi,
                url=o.url,
                file=FileRefOut(id=file.id, original_name=file.original_name) if file else None,
                project=ProjectRefOut(id=o.project_id, title=projects[o.project_id])
                if o.project_id and o.project_id in projects
                else None,
                submitted_on=o.submitted_on,
                published_on=o.published_on,
                verified_stage=o.verified_stage,
                verified_quartile=o.verified_quartile,
                review_status=o.review_status,
                review_status_fa=REVIEW_STATUS_TITLE_FA[o.review_status],
                review_note=o.review_note,
                reviewed_at=o.reviewed_at,
                points=points.get(o.id, Decimal(0)),
                is_scored=o.kind in rules.SCORED_KINDS,
                can_delete=viewer_id == o.owner_id and o.verified_stage is None,
                created_at=o.created_at,
            )
        )
    return result


def _output_draft(payload: OutputIn) -> OutputDraft:
    return OutputDraft(
        kind=payload.kind,
        title=payload.title,
        authors=payload.authors,
        status=payload.status,
        venue=payload.venue,
        quartile=payload.quartile,
        doi=payload.doi,
        url=payload.url,
        file_id=payload.file_id,
        project_id=payload.project_id,
        submitted_on=payload.submitted_on,
        published_on=payload.published_on,
    )


@router.get("/outputs", response_model=list[OutputOut], summary="خروجی‌های پژوهشی من")
async def my_outputs(
    current: CurrentUserDep, service: OutputServiceDep, session: SessionDep
) -> list[OutputOut]:
    return await _outputs(session, await service.mine(current.id), current.id)


@router.post(
    "/outputs",
    response_model=OutputOut,
    status_code=status.HTTP_201_CREATED,
    summary="ثبت خروجی پژوهشی",
)
async def create_output(
    payload: OutputIn, current: CurrentUserDep, service: OutputServiceDep, session: SessionDep
) -> OutputOut:
    output = await service.create(actor=current, draft=_output_draft(payload))
    return (await _outputs(session, [output], current.id))[0]


@router.get(
    "/outputs/review-queue",
    response_model=list[OutputReviewItemOut],
    summary="صف راستی‌آزمایی خروجی‌ها",
    responses={403: {"model": ErrorResponse}},
)
async def output_review_queue(
    current: CurrentUserDep, service: OutputServiceDep, session: SessionDep
) -> list[OutputReviewItemOut]:
    rows = await service.review_queue(current)
    names = await display_names(session, [r.owner_id for r in rows])
    items: list[OutputReviewItemOut] = []
    for row, out in zip(rows, await _outputs(session, rows), strict=True):
        owner = _person(names, row.owner_id)
        assert owner is not None
        items.append(OutputReviewItemOut(**out.model_dump(), owner=owner))
    return items


@router.patch("/outputs/{output_id}", response_model=OutputOut, summary="ویرایش خروجی")
async def update_output(
    output_id: uuid.UUID,
    payload: OutputIn,
    current: CurrentUserDep,
    service: OutputServiceDep,
    session: SessionDep,
) -> OutputOut:
    output = await service.require_own(output_id, current)
    output = await service.update(output=output, actor=current, draft=_output_draft(payload))
    return (await _outputs(session, [output], current.id))[0]


@router.delete(
    "/outputs/{output_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="حذف خروجی راستی‌آزمایی‌نشده",
)
async def delete_output(
    output_id: uuid.UUID, current: CurrentUserDep, service: OutputServiceDep
) -> None:
    await service.delete(output=await service.require_own(output_id, current))


@router.post(
    "/outputs/{output_id}/review",
    response_model=OutputOut,
    summary="راستی‌آزمایی یا رد ادعای خروجی",
    responses={403: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
async def review_output(
    output_id: uuid.UUID,
    payload: OutputReviewIn,
    current: CurrentUserDep,
    service: OutputServiceDep,
    session: SessionDep,
) -> OutputOut:
    output = await service.review(
        output_id=output_id, actor=current, decision=payload.decision, note=payload.note
    )
    return (await _outputs(session, [output]))[0]


@router.get(
    "/outputs/{output_id}/download-url",
    response_model=DownloadOut,
    summary="دانلود فایل خروجی — نویسنده یا بازبین",
    responses={404: {"model": ErrorResponse}},
)
async def output_file(
    output_id: uuid.UUID,
    current: CurrentUserDep,
    service: OutputServiceDep,
    files: FileServiceDep,
    session: SessionDep,
    settings: SettingsDep,
) -> DownloadOut:
    output = await session.get(ResearchOutput, output_id)
    if output is None or (output.owner_id != current.id and not await service.can_review(current)):
        raise NotFound("این خروجی پیدا نشد.")
    file = await session.get(File, output.file_id) if output.file_id else None
    if file is None or file.deleted_at is not None:
        raise NotFound("فایل پیدا نشد.")
    return DownloadOut(
        download_url=await files.download_url(file=file),
        expires_in=settings.download_url_ttl_seconds,
        original_name=file.original_name,
    )


__all__ = ["router"]
