"""مدل‌های Pydantic برای /research — §5.8، FR-RES-01/02/03، ADR-0015."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

LevelState = Literal["LOCKED", "AVAILABLE", "IN_PROGRESS", "SUBMITTED", "APPROVED"]
SubmissionStatus = Literal["SUBMITTED", "APPROVED", "CHANGES_REQUESTED"]
EvidenceKind = Literal["int", "text", "url", "date"]
TopicStatus = Literal["PROPOSED", "OPEN", "RESERVED", "TAKEN", "CLOSED"]
OutputKind = Literal["JOURNAL", "CONFERENCE", "THESIS", "REPORT", "PREPRINT"]
OutputStatus = Literal[
    "DRAFT", "SUBMITTED", "UNDER_REVIEW", "REVISION", "ACCEPTED", "PUBLISHED", "REJECTED"
]
OutputStage = Literal["SUBMITTED", "ACCEPTED", "PUBLISHED"]
Quartile = Literal["Q1", "Q2", "Q3", "Q4", "NA"]
ReviewStatus = Literal["NONE", "PENDING", "VERIFIED", "REJECTED"]


class PersonOut(BaseModel):
    id: uuid.UUID
    name: str | None
    username: str | None


class FileRefOut(BaseModel):
    id: uuid.UUID
    original_name: str


# ── مسیر ───────────────────────────────────────────────────────────────
class EvidenceFieldOut(BaseModel):
    key: str
    label_fa: str
    kind: EvidenceKind
    hint_fa: str | None = None
    min_value: int | None = None
    min_length: int | None = None


class SubmissionOut(BaseModel):
    id: uuid.UUID
    level: int
    version: int
    status: SubmissionStatus
    status_fa: str
    summary: str
    links: list[str]
    evidence: dict[str, Any]
    files: list[FileRefOut] = Field(default_factory=list)
    topic_title: str | None = None
    feedback: str | None = None
    reviewer: PersonOut | None = None
    reviewed_at: datetime | None = None
    submitted_at: datetime


class LevelOut(BaseModel):
    level: int
    title_fa: str
    deliverable_fa: str
    points: Decimal | None = None
    state: LevelState
    state_fa: str
    steps: list[str]
    checklist: list[str]
    template_title_fa: str
    template_columns: list[str]
    evidence_fields: list[EvidenceFieldOut]
    min_attachments: int
    attachments_hint_fa: str | None = None
    mentor: PersonOut | None = None
    started_at: datetime | None = None
    approved_at: datetime | None = None
    #: نسخه‌های تحویل — تازه‌ترین اول. برای مهمان خالی است.
    submissions: list[SubmissionOut] = Field(default_factory=list)


class TopicBriefOut(BaseModel):
    id: uuid.UUID
    title: str
    status: TopicStatus
    status_fa: str
    idle_days_left: int | None = None


class TrackOut(BaseModel):
    levels: list[LevelOut]
    current_level: int | None
    topic: TopicBriefOut | None = None
    can_participate: bool = False
    can_review: bool = False
    completed: bool = False


class SubmitIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: Annotated[str, Field(min_length=1, max_length=4000)]
    links: Annotated[list[Annotated[str, Field(max_length=500)]], Field(max_length=10)] = Field(
        default_factory=list
    )
    file_ids: Annotated[list[uuid.UUID], Field(max_length=10)] = Field(default_factory=list)
    evidence: dict[str, Any] = Field(default_factory=dict)


class PreviousVersionOut(BaseModel):
    version: int
    status: SubmissionStatus
    feedback: str | None = None
    reviewed_at: datetime | None = None


class ReviewItemOut(SubmissionOut):
    student: PersonOut
    level_title_fa: str
    evidence_fields: list[EvidenceFieldOut]
    checklist: list[str]
    previous: list[PreviousVersionOut] = Field(default_factory=list)


class SubmissionReviewIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["APPROVED", "CHANGES_REQUESTED"]
    feedback: Annotated[str | None, Field(max_length=2000)] = None


class DownloadOut(BaseModel):
    download_url: str
    expires_in: int
    original_name: str


# ── بانک موضوع ─────────────────────────────────────────────────────────
class TopicIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Annotated[str, Field(min_length=5, max_length=200)]
    description: Annotated[str, Field(min_length=20, max_length=4000)]
    prerequisites: Annotated[str | None, Field(max_length=1000)] = None
    level: Annotated[int | None, Field(ge=1, le=4)] = None


class TopicOut(BaseModel):
    id: uuid.UUID
    title: str
    description: str
    prerequisites: str | None = None
    level: int | None = None
    status: TopicStatus
    status_fa: str
    proposer: PersonOut
    #: نام رزروکننده فقط برای کادر — دیگران فقط «رزروشده» را می‌بینند.
    reserved_by: PersonOut | None = None
    reserved_by_me: bool = False
    reserved_at: datetime | None = None
    idle_days_left: int | None = None
    review_note: str | None = None
    is_mine: bool = False
    can_edit: bool = False
    can_manage: bool = False
    can_reserve: bool = False
    can_release: bool = False
    created_at: datetime


class TopicReviewIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["APPROVE", "REJECT"]
    note: Annotated[str | None, Field(max_length=1000)] = None


class TopicCloseIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: Annotated[str, Field(min_length=1, max_length=1000)]


# ── خروجی پژوهشی ───────────────────────────────────────────────────────
class OutputIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: OutputKind
    title: Annotated[str, Field(min_length=3, max_length=300)]
    authors: Annotated[str, Field(min_length=2, max_length=500)]
    status: OutputStatus = "DRAFT"
    venue: Annotated[str | None, Field(max_length=300)] = None
    quartile: Quartile | None = None
    doi: Annotated[str | None, Field(max_length=200)] = None
    url: Annotated[str | None, Field(max_length=500)] = None
    file_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    submitted_on: date | None = None
    published_on: date | None = None


class ProjectRefOut(BaseModel):
    id: uuid.UUID
    title: str


class OutputOut(BaseModel):
    id: uuid.UUID
    kind: OutputKind
    kind_fa: str
    title: str
    authors: str
    venue: str | None = None
    quartile: Quartile | None = None
    status: OutputStatus
    status_fa: str
    doi: str | None = None
    url: str | None = None
    file: FileRefOut | None = None
    project: ProjectRefOut | None = None
    submitted_on: date | None = None
    published_on: date | None = None
    verified_stage: OutputStage | None = None
    verified_quartile: Quartile | None = None
    review_status: ReviewStatus
    review_status_fa: str
    review_note: str | None = None
    reviewed_at: datetime | None = None
    #: امتیاز پژوهش فعال این خروجی در دفتر کل.
    points: Decimal = Decimal(0)
    is_scored: bool
    can_delete: bool = False
    created_at: datetime


class OutputReviewItemOut(OutputOut):
    owner: PersonOut


class OutputReviewIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["VERIFIED", "REJECTED"]
    note: Annotated[str | None, Field(max_length=1000)] = None
