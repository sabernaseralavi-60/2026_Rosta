"""آزمایشگاه شهر هوشمند و کتابخانهٔ فایل پروژه — FR-CITY-01، FR-PRJ-06، ADR-0016.

* `GET /city/workflow` — الگوی ثابت هشت‌مرحله‌ای؛ عمومی، مثل راهنمای مسیر
  پژوهش. فرم تحویل هر مرحله از روی همین ساخته می‌شود.
* `GET /city/projects` — پروژه‌های شهری منتشرشده با پیشرفت گردش‌کار.
* `GET /projects/{id}/city` — تختهٔ گردش‌کار یک پروژه، برای تیم و سرپرستان.
* `GET /projects/{id}/files` — کتابخانهٔ فایل پروژه با نسخه‌های فایل مدل.

دانلود فایل پروژه تا امروز فقط برای آپلودکننده بود (`/files/{id}`)؛
هم‌تیمی و بازبین پیوست‌های همدیگر را نمی‌دیدند. مسیر دانلود کتابخانه
همان دسترسی فضای کاری را می‌خواهد و فقط فایلی را می‌دهد که واقعاً به این
پروژه پیوست شده باشد.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter
from sqlalchemy import func, select

from silp.core.exceptions import NotFound
from silp.core.permissions import Permission
from silp.domain import city as rules
from silp.models.delivery import DELIVERABLE_STATUS_TITLE_FA, Deliverable
from silp.routers.deps import (
    CurrentUserDep,
    FileServiceDep,
    ProjectServiceDep,
    SessionDep,
    SettingsDep,
)
from silp.routers.v1.projects import _summary_of_row
from silp.routers.v1.workspace import milestones_out
from silp.schemas.city import (
    ArtifactOut,
    ArtifactVersionOut,
    CityAreaOut,
    CityArtifactSummaryOut,
    CityBoardOut,
    CityChecklistItemOut,
    CityEvidenceFieldOut,
    CityFileRuleOut,
    CityKpiOut,
    CityOptionOut,
    CityProjectOut,
    CityStageOut,
    CityStageSpecOut,
    CityWorkflowOut,
    LibraryFileOut,
    ProjectLibraryOut,
)
from silp.schemas.common import ErrorResponse
from silp.schemas.file import DownloadUrlOut, FileOut
from silp.services import authz
from silp.services.city_service import CityService
from silp.services.directory import display_names, name_of

router = APIRouter(prefix="/city", tags=["city"])
project_router = APIRouter(prefix="/projects", tags=["city"])


def _options(titles: dict[str, str]) -> list[CityOptionOut]:
    return [CityOptionOut(code=code, title_fa=title) for code, title in titles.items()]


def _stage_spec(stage: rules.Stage) -> CityStageSpecOut:
    return CityStageSpecOut(
        number=stage.number,
        code=stage.code,
        title_fa=stage.title_fa,
        deliverable_fa=stage.deliverable_fa,
        points=stage.points,
        duration_days=stage.duration_days,
        guide=list(stage.guide),
        checklist=[CityChecklistItemOut(text=i.text, auto=i.auto) for i in stage.checklist],
        evidence=[
            CityEvidenceFieldOut(
                key=f.key,
                label_fa=f.label_fa,
                kind=f.kind,
                hint_fa=f.hint_fa,
                min_value=f.min_value,
                max_value=f.max_value,
                min_length=f.min_length,
                max_length=f.max_length,
            )
            for f in stage.evidence
        ],
        structured=stage.structured,
        files=[
            CityFileRuleOut(kind=r.kind, label_fa=r.label_fa, exactly_one=r.exactly_one)
            for r in stage.files
        ],
        min_attachments=stage.min_attachments,
        attachments_hint_fa=stage.attachments_hint_fa,
    )


# ── الگو و صفحهٔ عمومی ─────────────────────────────────────────────────
@router.get("/workflow", response_model=CityWorkflowOut, summary="الگوی گردش‌کار شهر هوشمند")
async def workflow() -> CityWorkflowOut:
    return CityWorkflowOut(
        stages=[_stage_spec(s) for s in rules.STAGES],
        total_points=rules.TOTAL_POINTS,
        total_days=rules.TOTAL_DAYS,
        area_min_km2=rules.AREA_MIN_KM2,
        area_max_km2=rules.AREA_MAX_KM2,
        area_max_vertices=rules.AREA_MAX_VERTICES,
        sources=_options(rules.SOURCE_TITLE_FA),
        verdicts=_options(rules.VERDICT_TITLE_FA),
        severities=_options(rules.SEVERITY_TITLE_FA),
        scenario_kpis=[CityKpiOut(key=k, title_fa=t) for k, t in rules.SCENARIO_KPIS],
        artifacts=_options(rules.ARTIFACT_TITLE_FA),
    )


@router.get("/projects", response_model=list[CityProjectOut], summary="پروژه‌های شهری")
async def city_projects(session: SessionDep, projects: ProjectServiceDep) -> list[CityProjectOut]:
    result: list[CityProjectOut] = []
    for project, statuses, area in await CityService(session).public_projects():
        active = await projects.active_member_count(project.id)
        result.append(
            CityProjectOut(
                project=_summary_of_row(project, active),
                current_stage=rules.current_stage(statuses),
                approved_count=sum(1 for s in statuses.values() if s == "APPROVED"),
                area_km2=area.area_km2 if area else None,
                workflow_completed_at=project.workflow_completed_at,
            )
        )
    return result


# ── تختهٔ گردش‌کار پروژه ───────────────────────────────────────────────
@project_router.get(
    "/{project_id}/city",
    response_model=CityBoardOut,
    summary="گردش‌کار شهری پروژه",
    responses={403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
async def city_board(
    project_id: uuid.UUID,
    current: CurrentUserDep,
    projects: ProjectServiceDep,
    session: SessionDep,
) -> CityBoardOut:
    project = await projects.require(project_id)
    await projects.require_member(project_id, current)
    service = CityService(session)
    stage_rows = await service.stage_milestones(project_id)
    if not stage_rows:
        raise NotFound("این پروژه گردش‌کار شهر هوشمند ندارد.")

    ordered = [stage_rows[n] for n in sorted(stage_rows)]
    presented = await milestones_out(session, ordered, current.id)
    statuses = {n: m.status for n, m in stage_rows.items()}
    open_rows = await session.execute(
        select(Deliverable.milestone_id, func.count())
        .where(
            Deliverable.milestone_id.in_([m.id for m in ordered]),
            Deliverable.status.in_(("SUBMITTED", "UNDER_REVIEW")),
        )
        .group_by(Deliverable.milestone_id)
    )
    open_counts = dict(open_rows.tuples().all())

    area = await service.area_of(project_id)
    histories = await service.artifact_histories(project_id)
    return CityBoardOut(
        project_id=project.id,
        title_fa=project.title_fa,
        status=project.status,
        lead_id=project.lead_id,
        workflow_completed_at=project.workflow_completed_at,
        current_stage=rules.current_stage(statuses),
        approved_count=sum(1 for s in statuses.values() if s == "APPROVED"),
        area=(
            CityAreaOut(
                geometry=area.geometry,
                area_km2=area.area_km2,
                bbox=area.bbox,
                approved=area.approved,
            )
            if area
            else None
        ),
        stages=[
            CityStageOut(
                number=int(m.workflow_stage or 0),
                milestone=out,
                locked=rules.is_locked(int(m.workflow_stage or 0), statuses),
                open_deliverables=int(open_counts.get(m.id, 0)),
            )
            for m, out in zip(ordered, presented, strict=True)
        ],
        artifacts=[
            CityArtifactSummaryOut(
                artifact=h.artifact,
                title_fa=rules.ARTIFACT_TITLE_FA[h.artifact],
                extension=rules.ARTIFACT_EXTENSION_FA[h.artifact],
                current_version=h.current.version if h.current else None,
                latest_version=max((v.version for v, *_ in h.versions), default=None),
                versions=len(h.versions),
            )
            for h in histories
        ],
        can_review=await authz.has_permission(
            session, current, Permission.DELIVERABLE_REVIEW, project_id
        ),
        can_manage=await authz.has_permission(
            session, current, Permission.PROJECT_MILESTONE_MANAGE, project_id
        ),
    )


# ── کتابخانهٔ فایل پروژه ───────────────────────────────────────────────
@project_router.get(
    "/{project_id}/files",
    response_model=ProjectLibraryOut,
    summary="کتابخانهٔ فایل پروژه",
    responses={403: {"model": ErrorResponse}},
)
async def project_library(
    project_id: uuid.UUID,
    current: CurrentUserDep,
    projects: ProjectServiceDep,
    session: SessionDep,
) -> ProjectLibraryOut:
    await projects.require(project_id)
    await projects.require_member(project_id, current)
    service = CityService(session)
    histories = await service.artifact_histories(project_id)
    entries = await service.library(project_id)
    names = await display_names(
        session,
        [
            *(v.created_by for h in histories for v, *_ in h.versions),
            *(e.attached_by for e in entries),
        ],
    )
    artifacts = []
    for history in histories:
        current_version = history.current
        artifacts.append(
            ArtifactOut(
                artifact=history.artifact,
                title_fa=rules.ARTIFACT_TITLE_FA[history.artifact],
                extension=rules.ARTIFACT_EXTENSION_FA[history.artifact],
                versions=[
                    ArtifactVersionOut(
                        id=version.id,
                        version=version.version,
                        file=FileOut.model_validate(file),
                        deliverable_id=deliverable.id,
                        deliverable_version=deliverable.version,
                        deliverable_status=deliverable.status,
                        deliverable_status_fa=DELIVERABLE_STATUS_TITLE_FA.get(
                            deliverable.status, deliverable.status
                        ),
                        milestone_id=milestone.id,
                        milestone_title_fa=milestone.title_fa,
                        created_by=version.created_by,
                        created_by_name=name_of(names, version.created_by),
                        created_at=version.created_at,
                        is_current=current_version is not None and current_version.id == version.id,
                    )
                    for version, file, deliverable, milestone in history.versions
                ],
            )
        )
    has_versions = any(a.versions for a in artifacts)
    project = await projects.require(project_id)
    return ProjectLibraryOut(
        # پروژهٔ غیرشهری فایل مدل ندارد؛ فهرست خالی سه نوع فقط شلوغی است.
        artifacts=artifacts if has_versions or project.workflow else [],
        files=[
            LibraryFileOut(
                file=FileOut.model_validate(e.file),
                source=e.source,
                milestone_id=e.milestone.id if e.milestone else None,
                milestone_title_fa=e.milestone.title_fa if e.milestone else None,
                deliverable_id=e.deliverable.id if e.deliverable else None,
                deliverable_version=e.deliverable.version if e.deliverable else None,
                deliverable_status=(e.deliverable.status if e.deliverable else None),
                deliverable_status_fa=(
                    DELIVERABLE_STATUS_TITLE_FA.get(e.deliverable.status, e.deliverable.status)
                    if e.deliverable
                    else None
                ),
                attached_by=e.attached_by,
                attached_by_name=name_of(names, e.attached_by),
                attached_at=e.attached_at,
            )
            for e in entries
        ],
    )


@project_router.get(
    "/{project_id}/files/{file_id}/download-url",
    response_model=DownloadUrlOut,
    summary="دانلود فایل کتابخانهٔ پروژه",
    responses={403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
async def project_file_download(
    project_id: uuid.UUID,
    file_id: uuid.UUID,
    current: CurrentUserDep,
    projects: ProjectServiceDep,
    files: FileServiceDep,
    session: SessionDep,
    settings: SettingsDep,
) -> DownloadUrlOut:
    await projects.require(project_id)
    await projects.require_member(project_id, current)
    file = await CityService(session).project_file(project_id, file_id)
    url = await files.download_url(file=file)
    return DownloadUrlOut(
        download_url=url,
        expires_in=settings.download_url_ttl_seconds,
        original_name=file.original_name,
    )


__all__ = ["project_router", "router"]
