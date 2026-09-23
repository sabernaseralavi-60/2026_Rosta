"""مدل‌های Pydantic برای /teams — §5.8، FR-TEAM-01/02/03، ADR-0015."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

TargetKind = Literal["PROJECT", "VENTURE"]
OpeningStatus = Literal["OPEN", "FILLED", "CLOSED"]
#: «منقضی» ذخیره نمی‌شود؛ از `expires_at` خوانده می‌شود (ADR-0015).
EffectiveOpeningStatus = Literal["OPEN", "FILLED", "CLOSED", "EXPIRED"]
ApplicationStatus = Literal["PENDING", "ACCEPTED", "DECLINED", "WITHDRAWN"]


class PersonOut(BaseModel):
    id: uuid.UUID
    name: str | None
    username: str | None


# ── جستجوی هم‌تیمی ─────────────────────────────────────────────────────
class TeammateUserOut(BaseModel):
    id: uuid.UUID
    username: str | None
    display_name: str
    university: str | None = None


class SkillLevelOut(BaseModel):
    skill_id: uuid.UUID
    title_fa: str
    level: int
    verified: bool


class TeammateOut(BaseModel):
    user: TeammateUserOut
    bio: str | None = None
    weekly_hours: int | None = None
    top_skills: list[SkillLevelOut]
    assets: list[str]
    shares_course: bool
    #: §8.14 — فقط با `complement_project_id`؛ بدون پروژه `null`.
    complement_score: float | None = None
    complement_reason: str | None = None
    complement_skills: list[str] = Field(default_factory=list)
    #: بدون پروژه — مهارت‌هایی که در آن‌ها از جستجوکننده قوی‌تر است.
    stronger_skills: list[str] = Field(default_factory=list)
    stronger_reason: str | None = None


class GapOut(BaseModel):
    title_fa: str
    min_level: int


class ProjectBriefOut(BaseModel):
    id: uuid.UUID
    title: str


class SearchContextOut(BaseModel):
    project: ProjectBriefOut | None = None
    #: مهارت‌هایی که هیچ عضو تیم در سطح لازم ندارد.
    gaps: list[GapOut] = Field(default_factory=list)
    can_invite: bool = False
    #: نیمرخ خود جستجوکننده عمومی است؟ اگر نه، دیگران او را پیدا نمی‌کنند.
    my_profile_is_public: bool = False


class TeamSearchOut(BaseModel):
    items: list[TeammateOut]
    total: int
    page: int
    page_size: int
    has_next: bool
    context: SearchContextOut


class ManagedTeamOut(BaseModel):
    """تیمی که کاربر می‌تواند برایش آگهی بدهد یا دعوت بفرستد."""

    kind: TargetKind
    id: uuid.UUID
    title: str
    roles: list[ProjectBriefOut] = Field(default_factory=list)


# ── آگهی ───────────────────────────────────────────────────────────────
class OpeningIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: uuid.UUID | None = None
    venture_id: uuid.UUID | None = None
    title: Annotated[str, Field(min_length=3, max_length=120)]
    description: Annotated[str, Field(min_length=10, max_length=2000)]
    needed_skill_ids: Annotated[list[uuid.UUID], Field(max_length=10)] = Field(default_factory=list)
    commitment_hpw: Annotated[int | None, Field(ge=1, le=60)] = None
    role_id: uuid.UUID | None = None


class OpeningUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Annotated[str, Field(min_length=3, max_length=120)]
    description: Annotated[str, Field(min_length=10, max_length=2000)]
    needed_skill_ids: Annotated[list[uuid.UUID], Field(max_length=10)] = Field(default_factory=list)
    commitment_hpw: Annotated[int | None, Field(ge=1, le=60)] = None
    role_id: uuid.UUID | None = None


class TargetOut(BaseModel):
    kind: TargetKind
    id: uuid.UUID
    title: str
    href: str


class SkillRefOut(BaseModel):
    id: uuid.UUID
    title_fa: str


class OpeningApplicationOut(BaseModel):
    id: uuid.UUID
    opening_id: uuid.UUID
    applicant: PersonOut
    message: str
    status: ApplicationStatus
    status_fa: str
    decision_note: str | None = None
    decided_at: datetime | None = None
    created_at: datetime


class OpeningOut(BaseModel):
    id: uuid.UUID
    title: str
    description: str
    needed_skills: list[SkillRefOut]
    commitment_hpw: int | None = None
    role: ProjectBriefOut | None = None
    status: OpeningStatus
    effective_status: EffectiveOpeningStatus
    status_fa: str
    expires_at: datetime
    created_at: datetime
    target: TargetOut
    poster: PersonOut
    #: تعداد درخواست‌های در انتظار — فقط برای مدیران آگهی.
    pending_count: int | None = None
    has_applied: bool = False
    can_manage: bool = False


class OpeningDetailOut(OpeningOut):
    my_application: OpeningApplicationOut | None = None
    #: فقط برای مدیران آگهی.
    applications: list[OpeningApplicationOut] = Field(default_factory=list)


class ApplyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: Annotated[str, Field(min_length=1, max_length=500)]


class DecideIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["ACCEPTED", "DECLINED"]
    note: Annotated[str | None, Field(max_length=500)] = None


class MyApplicationOut(OpeningApplicationOut):
    opening_title: str
    target: TargetOut
