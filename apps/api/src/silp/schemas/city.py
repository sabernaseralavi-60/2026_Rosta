"""مدل‌های Pydantic آزمایشگاه شهر هوشمند و کتابخانهٔ پروژه — §7.9، ADR-0016."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from silp.schemas.delivery import DeliverableStatus, MilestoneOut
from silp.schemas.file import FileOut
from silp.schemas.project import ProjectSummaryOut

ArtifactKind = Literal["OSM", "SUMO_NET", "SUMO_ROUTES"]


# ── الگو ───────────────────────────────────────────────────────────────
class CityEvidenceFieldOut(BaseModel):
    key: str
    label_fa: str
    kind: Literal["int", "number", "text", "url", "date"]
    hint_fa: str | None = None
    min_value: float | None = None
    max_value: float | None = None
    min_length: int | None = None
    max_length: int


class CityChecklistItemOut(BaseModel):
    text: str
    #: سامانه خودش می‌سنجد؛ بقیه را تحویل‌دهنده تأیید می‌کند.
    auto: bool


class CityFileRuleOut(BaseModel):
    kind: Literal["OSM", "SUMO_NET", "SUMO_ROUTES", "PDF", "DATASET"]
    label_fa: str
    exactly_one: bool


class CityStageSpecOut(BaseModel):
    number: int
    code: str
    title_fa: str
    deliverable_fa: str
    points: int
    duration_days: int
    guide: list[str]
    checklist: list[CityChecklistItemOut]
    evidence: list[CityEvidenceFieldOut]
    structured: Literal["AREA", "CHECKS", "SCENARIOS"] | None = None
    files: list[CityFileRuleOut]
    min_attachments: int
    attachments_hint_fa: str | None = None


class CityOptionOut(BaseModel):
    code: str
    title_fa: str


class CityKpiOut(BaseModel):
    key: str
    title_fa: str


class CityWorkflowOut(BaseModel):
    """الگوی ثابت هشت‌مرحله‌ای — `GET /city/workflow`، عمومی."""

    stages: list[CityStageSpecOut]
    total_points: int
    total_days: int
    area_min_km2: float
    area_max_km2: float
    area_max_vertices: int
    sources: list[CityOptionOut]
    verdicts: list[CityOptionOut]
    severities: list[CityOptionOut]
    scenario_kpis: list[CityKpiOut]
    artifacts: list[CityOptionOut]


# ── گردش‌کار یک پروژه ──────────────────────────────────────────────────
class CityAreaOut(BaseModel):
    geometry: dict[str, Any]
    area_km2: float
    bbox: list[float]
    #: تحویل مرحلهٔ ۱ تأیید شده است، یا هنوز فقط ادعاست؟
    approved: bool


class CityStageOut(BaseModel):
    number: int
    milestone: MilestoneOut
    #: مرحلهٔ قبل هنوز تأیید نشده — تحویل نمی‌پذیرد.
    locked: bool
    #: تحویل‌های بازِ این مرحله (همهٔ اعضا) — برای بازبین.
    open_deliverables: int = 0


class CityArtifactSummaryOut(BaseModel):
    artifact: ArtifactKind
    title_fa: str
    extension: str
    #: آخرین نسخهٔ تأییدشده — «نسخهٔ جاری» مدل.
    current_version: int | None = None
    latest_version: int | None = None
    versions: int = 0


class CityBoardOut(BaseModel):
    """`GET /projects/{id}/city` — برای عضو تیم و سرپرستان پروژه."""

    project_id: uuid.UUID
    title_fa: str
    status: str
    lead_id: uuid.UUID
    workflow_completed_at: datetime | None = None
    #: اولین مرحلهٔ تأییدنشده؛ تهی یعنی کامل.
    current_stage: int | None = None
    approved_count: int
    area: CityAreaOut | None = None
    stages: list[CityStageOut]
    artifacts: list[CityArtifactSummaryOut]
    can_review: bool = False
    can_manage: bool = False


class CityProjectOut(BaseModel):
    """پروژهٔ شهری در صفحهٔ عمومی آزمایشگاه."""

    project: ProjectSummaryOut
    current_stage: int | None = None
    approved_count: int
    area_km2: float | None = None
    workflow_completed_at: datetime | None = None


# ── کتابخانهٔ پروژه ────────────────────────────────────────────────────
class ArtifactVersionOut(BaseModel):
    id: uuid.UUID
    version: int
    file: FileOut
    deliverable_id: uuid.UUID
    deliverable_version: int
    deliverable_status: DeliverableStatus
    deliverable_status_fa: str
    milestone_id: uuid.UUID
    milestone_title_fa: str
    created_by: uuid.UUID
    created_by_name: str | None = None
    created_at: datetime
    is_current: bool = False


class ArtifactOut(BaseModel):
    artifact: ArtifactKind
    title_fa: str
    extension: str
    versions: list[ArtifactVersionOut] = Field(default_factory=list)


class LibraryFileOut(BaseModel):
    file: FileOut
    source: Literal["DELIVERABLE", "MESSAGE"]
    milestone_id: uuid.UUID | None = None
    milestone_title_fa: str | None = None
    deliverable_id: uuid.UUID | None = None
    deliverable_version: int | None = None
    deliverable_status: DeliverableStatus | None = None
    deliverable_status_fa: str | None = None
    attached_by: uuid.UUID | None = None
    attached_by_name: str | None = None
    attached_at: datetime | None = None


class ProjectLibraryOut(BaseModel):
    """`GET /projects/{id}/files` — کتابخانهٔ فایل پروژه (FR-PRJ-06، FR-CITY-01)."""

    artifacts: list[ArtifactOut] = Field(default_factory=list)
    files: list[LibraryFileOut] = Field(default_factory=list)


__all__ = [
    "ArtifactOut",
    "ArtifactVersionOut",
    "CityAreaOut",
    "CityArtifactSummaryOut",
    "CityBoardOut",
    "CityChecklistItemOut",
    "CityEvidenceFieldOut",
    "CityFileRuleOut",
    "CityKpiOut",
    "CityOptionOut",
    "CityProjectOut",
    "CityStageOut",
    "CityStageSpecOut",
    "CityWorkflowOut",
    "LibraryFileOut",
    "ProjectLibraryOut",
]
