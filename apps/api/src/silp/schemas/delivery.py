"""مدل‌های Pydantic برای مرحله، تحویل‌دادنی، وظیفه و گفتگو — §5.7."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from silp.schemas.file import FileOut

MilestoneStatus = Literal["PENDING", "IN_PROGRESS", "SUBMITTED", "APPROVED", "OVERDUE"]
OutputKind = Literal["DOCUMENT", "CODE", "DATA", "MEDIA", "SALES", "MIXED"]
DeliverableStatus = Literal[
    "SUBMITTED", "UNDER_REVIEW", "APPROVED", "CHANGES_REQUESTED", "REJECTED"
]
ReviewDecision = Literal["APPROVED", "CHANGES_REQUESTED", "REJECTED"]
TaskStatus = Literal["TODO", "DOING", "DONE"]

MAX_TITLE = 200
MAX_TEXT = 5000
MAX_CHECKLIST_ITEMS = 20


# ── مرحله ──────────────────────────────────────────────────────────────
class MilestoneIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title_fa: Annotated[str, Field(min_length=1, max_length=MAX_TITLE)]
    description: Annotated[str, Field(max_length=MAX_TEXT)] | None = None
    sort_order: Annotated[int, Field(ge=0, le=100)] = 0
    due_on: date | None = None
    points: Annotated[float, Field(ge=0, le=1000)] = 0
    is_required: bool = True
    output_kind: OutputKind | None = None
    checklist: Annotated[list[str], Field(max_length=MAX_CHECKLIST_ITEMS)] = Field(
        default_factory=list
    )


class MilestoneOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    title_fa: str
    description: str | None = None
    sort_order: int
    due_on: date | None = None
    points: float
    is_required: bool
    output_kind: OutputKind | None = None
    output_kind_fa: str | None = None
    checklist: list[str] = Field(default_factory=list)
    status: MilestoneStatus
    status_fa: str
    approved_at: datetime | None = None
    #: شمارهٔ مرحله در الگوی گردش‌کار (ADR-0016)؛ تهی یعنی مرحلهٔ آزاد.
    workflow_stage: int | None = None
    #: مسئول مرحله — FR-CITY-01.
    owner_id: uuid.UUID | None = None
    owner_name: str | None = None
    # فقط برای عضو تیم پر می‌شود؛ بیرون فضای کاری معنا ندارد.
    my_deliverable: DeliverableOut | None = None
    deliverable_count: int = 0


# ── تحویل‌دادنی ────────────────────────────────────────────────────────
class DeliverableIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body: Annotated[str, Field(max_length=MAX_TEXT)] | None = None
    file_ids: Annotated[list[uuid.UUID], Field(max_length=10)] = Field(default_factory=list)
    links: Annotated[list[str], Field(max_length=10)] = Field(default_factory=list)
    #: شاهد ساختاریافتهٔ مرحلهٔ گردش‌کار شهری — شکلش را `GET /city/workflow` می‌گوید.
    evidence: dict[str, Any] | None = None
    #: شمارهٔ موارد چک‌لیست که تحویل‌دهنده تأیید کرد (از صفر).
    checklist_confirmed: Annotated[list[int], Field(max_length=20)] = Field(default_factory=list)


class MilestoneOwnerIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    #: تهی یعنی بی‌مسئول — برای مرحلهٔ گردش‌کار شهری پذیرفته نیست.
    owner_id: uuid.UUID | None = None


class DeliverableOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    milestone_id: uuid.UUID
    submitter_id: uuid.UUID
    submitter_name: str | None = None
    version: int
    body: str | None = None
    links: list[str] = Field(default_factory=list)
    status: DeliverableStatus
    status_fa: str
    is_late: bool = False
    score: float | None = None
    feedback: str | None = None
    rubric_scores: dict[str, Any] | None = None
    evidence: dict[str, Any] | None = None
    reviewed_by: uuid.UUID | None = None
    reviewed_at: datetime | None = None
    submitted_at: datetime
    files: list[FileOut] = Field(default_factory=list)


class ReviewIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: ReviewDecision
    # §7.6 — برای «اصلاح کن» و «رد» اجباری است؛ سرور هم بررسی می‌کند.
    feedback: Annotated[str, Field(max_length=MAX_TEXT)] | None = None
    score: Annotated[float, Field(ge=0, le=1000)] | None = None
    rubric_scores: dict[str, float] | None = None


class ReviewOut(BaseModel):
    deliverable: DeliverableOut
    milestone: MilestoneOut
    # §7.6 — «آیا همهٔ مراحل الزامی تأیید شد؟ ⇒ پیشنهاد بستن پروژه»
    project_ready_to_close: bool = False
    #: گردش‌کار شهری با همین تأیید کامل شد (ADR-0016).
    workflow_completed: bool = False


# ── تختهٔ وظایف ────────────────────────────────────────────────────────
class TaskIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Annotated[str, Field(min_length=1, max_length=MAX_TITLE)]
    description: Annotated[str, Field(max_length=MAX_TEXT)] | None = None
    assignee_id: uuid.UUID | None = None
    milestone_id: uuid.UUID | None = None
    due_on: date | None = None
    status: TaskStatus = "TODO"
    sort_order: Annotated[int, Field(ge=0, le=10_000)] = 0


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    milestone_id: uuid.UUID | None = None
    title: str
    description: str | None = None
    assignee_id: uuid.UUID | None = None
    assignee_name: str | None = None
    status: TaskStatus
    status_fa: str
    due_on: date | None = None
    sort_order: int
    created_at: datetime


# ── گفتگو ──────────────────────────────────────────────────────────────
class MessageIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body: Annotated[str, Field(min_length=1, max_length=4000)]
    parent_id: uuid.UUID | None = None
    file_id: uuid.UUID | None = None


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    parent_id: uuid.UUID | None = None
    author_id: uuid.UUID
    author_name: str | None = None
    body: str
    file_id: uuid.UUID | None = None
    created_at: datetime
    edited_at: datetime | None = None


class ActivityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    actor_id: uuid.UUID | None = None
    actor_name: str | None = None
    kind: str
    summary: str
    entity_type: str | None = None
    entity_id: uuid.UUID | None = None
    created_at: datetime


# ── بازتاب پایان پروژه — ADR-0024 ──────────────────────────────────────
class ReflectionIn(BaseModel):
    """حداقل نویسه در سرویس سنجیده می‌شود (پس از `strip`) تا عدد در یک جا بماند."""

    model_config = ConfigDict(extra="forbid")

    learned: Annotated[str, Field(min_length=1, max_length=4000)]
    challenges: Annotated[str | None, Field(max_length=4000)] = None
    would_do_differently: Annotated[str | None, Field(max_length=4000)] = None
    satisfaction: Annotated[int | None, Field(ge=1, le=5)] = None


class ReflectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    learned: str
    challenges: str | None = None
    would_do_differently: str | None = None
    satisfaction: int | None = None
    created_at: datetime


class ReflectionStateOut(BaseModel):
    """`GET /projects/{id}/reflection` — وضعیت بازتاب خودِ کاربر."""

    can_submit: bool
    reason: str | None = None
    reflection: ReflectionOut | None = None
    #: امتیاز فعلی قاعده؛ `null` اگر مدیر آن را غیرفعال کرده باشد.
    points: float | None = None
    min_learned_chars: int


# ── ارزیابی همتا — ADR-0024 برش ب ──────────────────────────────────────
class PeerRatingIn(BaseModel):
    """بازه را سرویس هم می‌سنجد؛ اینجا فقط از پذیرفتن مقدار پوچ جلو می‌گیریم.

    `note` عمداً نیست (ADR-0024 بند ۱۰): متنی که هیچ‌کس نمی‌بیند، یا ناشناسی را
    می‌شکند یا جمع‌آوری بی‌مصرف است. `extra="forbid"` آن را ۴۲۲ می‌کند.
    """

    model_config = ConfigDict(extra="forbid")

    evaluatee_id: uuid.UUID
    contribution: Annotated[int, Field(ge=1, le=5)]
    reliability: Annotated[int | None, Field(ge=1, le=5)] = None


class PeerEvaluationsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evaluations: Annotated[list[PeerRatingIn], Field(min_length=1, max_length=50)]


class PeerOut(BaseModel):
    user_id: uuid.UUID
    full_name: str | None = None
    is_lead: bool = False


class MyPeerRatingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    evaluatee_id: uuid.UUID
    contribution: int
    reliability: int | None = None


class PeerEvaluationStateOut(BaseModel):
    """`GET /projects/{id}/peer-evaluations` — وضعیت ارزیابی خودِ کاربر."""

    can_submit: bool
    reason: str | None = None
    peers: list[PeerOut]
    #: ارزیابی‌های ثبت‌شدهٔ خودِ کاربر؛ خالی تا وقتی ثبت نکرده.
    mine: list[MyPeerRatingOut]
    #: امتیاز فعلی قاعده؛ `null` اگر مدیر آن را غیرفعال کرده باشد.
    points: float | None = None


class PeerAverageOut(BaseModel):
    user_id: uuid.UUID
    full_name: str | None = None
    #: ارزیابی‌های «دیگران» (بدون نظر خودِ مدیر).
    evaluations: int
    #: `null` یعنی ارزیابی کافی نیست تا ناشناسی حفظ شود.
    contribution_avg: float | None = None
    reliability_avg: float | None = None


class PeerEvaluationSummaryOut(BaseModel):
    min_evaluations: int
    members: list[PeerAverageOut]


class ContributionSignalOut(BaseModel):
    dimension: str
    #: شمار خام — مدیر عدد را قضاوت می‌کند، نه فقط درصد.
    count: int
    #: `null` وقتی کل تیم در این بُعد صفر است.
    share_percent: float | None = None


class ContributionMemberOut(BaseModel):
    user_id: uuid.UUID
    full_name: str | None = None
    status: str
    is_lead: bool
    joined_at: datetime
    left_at: datetime | None = None
    #: `null` وقتی هیچ بُعدی در کل تیم داده ندارد.
    share_percent: float | None = None
    #: عضو فعالی که در هیچ بُعد چیزی ثبت نکرده — واقعیت است، نه اتهام.
    is_silent: bool
    signals: list[ContributionSignalOut]


class ContributionDimensionOut(BaseModel):
    dimension: str
    title: str
    #: وزن مؤثر پس از حذف بُعدهای کل‌تیم‌صفر؛ `0` یعنی بُعد دادهٔ کل‌تیم ندارد.
    weight: float
    #: `null` برای عضو عادی (`scope = SELF`).
    team_total: int | None = None


class ContributionOut(BaseModel):
    #: `TEAM` (مدیر، ناظر) همهٔ اعضا؛ `SELF` (عضو عادی) فقط ردیف خودش.
    scope: Literal["TEAM", "SELF"]
    dimensions: list[ContributionDimensionOut]
    members: list[ContributionMemberOut]


MilestoneOut.model_rebuild()

__all__ = [
    "ActivityOut",
    "ContributionDimensionOut",
    "ContributionMemberOut",
    "ContributionOut",
    "ContributionSignalOut",
    "DeliverableIn",
    "DeliverableOut",
    "MessageIn",
    "MessageOut",
    "MilestoneIn",
    "MilestoneOut",
    "MilestoneOwnerIn",
    "MyPeerRatingOut",
    "PeerAverageOut",
    "PeerEvaluationStateOut",
    "PeerEvaluationSummaryOut",
    "PeerEvaluationsIn",
    "PeerOut",
    "PeerRatingIn",
    "ReflectionIn",
    "ReflectionOut",
    "ReflectionStateOut",
    "ReviewIn",
    "ReviewOut",
    "TaskIn",
    "TaskOut",
]
