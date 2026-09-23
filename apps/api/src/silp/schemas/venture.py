"""مدل‌های Pydantic برای /ventures، شاخص‌ها و دعوت — قرارداد §5.8."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

VentureStage = Literal["IDEA", "VALIDATION", "MVP", "FIRST_REVENUE", "GROWTH", "PAUSED", "CLOSED"]
StageAction = Literal["ADVANCE", "PAUSE", "RESUME", "CLOSE"]
MetricKind = Literal[
    "CALLS", "MEETINGS", "LEADS", "SALES_COUNT", "SALES_AMOUNT", "CONTENT_PIECES", "CUSTOMERS"
]
MetricStatus = Literal["PENDING", "VERIFIED", "REJECTED"]
ReviewDecision = Literal["VERIFIED", "REJECTED"]


class VentureIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, Field(min_length=2, max_length=120)]
    pitch: Annotated[str, Field(min_length=10, max_length=280)]
    description: Annotated[str | None, Field(max_length=4000)] = None
    problem: Annotated[str | None, Field(max_length=2000)] = None
    target_market: Annotated[str | None, Field(max_length=2000)] = None
    revenue_model: Annotated[str | None, Field(max_length=2000)] = None
    current_status: Annotated[str | None, Field(max_length=2000)] = None
    looking_for_cofounder: bool = False
    needed_roles: Annotated[list[str], Field(max_length=10)] = Field(default_factory=list)


class MemberOut(BaseModel):
    user_id: uuid.UUID
    name: str | None
    username: str | None
    is_founder: bool
    joined_at: datetime


class VentureSummaryOut(BaseModel):
    id: uuid.UUID
    slug: str
    name: str
    pitch: str
    stage: VentureStage
    stage_fa: str
    founder: MemberOut | None = None
    looking_for_cofounder: bool
    needed_roles: list[str] = Field(default_factory=list)
    member_count: int = 0
    created_at: datetime


class CriterionOut(BaseModel):
    code: str
    text: str
    met: bool
    current: int
    target: int


class ReadinessOut(BaseModel):
    next_stage: VentureStage | None
    next_stage_fa: str | None
    ready: bool
    criteria: list[CriterionOut]


class StageChangeOut(BaseModel):
    id: uuid.UUID
    from_stage: VentureStage
    to_stage: VentureStage
    from_stage_fa: str
    to_stage_fa: str
    reason: str | None = None
    changed_by_name: str | None = None
    created_at: datetime


class LinkedProjectOut(BaseModel):
    id: uuid.UUID
    title_fa: str
    status: str
    kind: str


class MetricTotalsOut(BaseModel):
    verified: dict[str, int] = Field(default_factory=dict)
    pending: dict[str, int] = Field(default_factory=dict)


class VentureDetailOut(VentureSummaryOut):
    description: str | None = None
    problem: str | None = None
    target_market: str | None = None
    revenue_model: str | None = None
    current_status: str | None = None
    paused_from_stage: VentureStage | None = None
    stage_changed_at: datetime
    origin_idea_id: uuid.UUID | None = None
    members: list[MemberOut] = Field(default_factory=list)
    projects: list[LinkedProjectOut] = Field(default_factory=list)
    history: list[StageChangeOut] = Field(default_factory=list)
    # فقط برای اعضا و مدیران — داده‌ٔ فروش عمومی نیست.
    readiness: ReadinessOut | None = None
    totals: MetricTotalsOut | None = None
    is_member: bool = False
    can_manage: bool = False


class StageChangeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: StageAction
    reason: Annotated[str | None, Field(max_length=500)] = None


# ── شاخص ───────────────────────────────────────────────────────────────
class MetricIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric: MetricKind
    value: Annotated[int, Field(gt=0)]
    occurred_on: date
    note: Annotated[str | None, Field(max_length=500)] = None
    evidence_file_id: uuid.UUID | None = None


class MetricOut(BaseModel):
    id: uuid.UUID
    venture_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    owner_title: str | None = None
    user_id: uuid.UUID
    user_name: str | None = None
    metric: MetricKind
    metric_fa: str
    value: int
    occurred_on: date
    note: str | None = None
    evidence_file_id: uuid.UUID | None = None
    status: MetricStatus
    status_fa: str
    reviewed_by_name: str | None = None
    reviewed_at: datetime | None = None
    review_note: str | None = None
    can_review: bool = False
    is_mine: bool = False
    created_at: datetime


class MemberTotalsOut(MetricTotalsOut):
    user_id: uuid.UUID
    name: str | None = None


class MetricsOut(BaseModel):
    items: list[MetricOut]
    totals: MetricTotalsOut
    by_member: list[MemberTotalsOut] = Field(default_factory=list)
    metric_titles: dict[str, str] = Field(default_factory=dict)


class MetricReviewIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: ReviewDecision
    note: Annotated[str | None, Field(max_length=500)] = None


# ── دعوت ───────────────────────────────────────────────────────────────
class InviteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: Annotated[str, Field(min_length=3, max_length=40)]
    message: Annotated[str | None, Field(max_length=500)] = None
    role_id: uuid.UUID | None = None


class InvitationOut(BaseModel):
    id: uuid.UUID
    target_type: Literal["PROJECT", "VENTURE"]
    target_id: uuid.UUID
    target_title: str
    href: str
    inviter_name: str | None = None
    invitee_name: str | None = None
    message: str | None = None
    role_title: str | None = None
    source: Literal["DIRECT", "IDEA_PROMOTION", "OPENING"]
    status: Literal["PENDING", "ACCEPTED", "DECLINED", "CANCELLED"]
    expires_at: datetime
    created_at: datetime


class AcceptedOut(BaseModel):
    target_type: Literal["PROJECT", "VENTURE"]
    target_id: uuid.UUID
    href: str


class RemoveMemberIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: Annotated[str, Field(min_length=1, max_length=500)]
