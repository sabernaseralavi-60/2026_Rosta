"""مدل‌های Pydantic برای /projects — قرارداد §5.7."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from silp.domain.recommendation.schemas import MatchResult

ProjectKind = Literal["A_VENTURE", "B_RESEARCH", "C_PROBLEM", "D_PERSONAL"]
ProjectStatus = Literal["DRAFT", "OPEN", "IN_PROGRESS", "PAUSED", "COMPLETED", "CANCELLED"]
WorkStyle = Literal["SOLO", "TEAM", "EITHER"]
Polarity = Literal["POSITIVE", "WARNING"]
FeedbackVerdict = Literal["NOT_RELEVANT", "INTERESTED", "DISMISSED"]
SortOrder = Literal["match", "newest", "popular", "deadline"]


class SkillRequirementOut(BaseModel):
    skill_id: uuid.UUID
    title_fa: str
    min_level: int
    weight: int
    is_teachable: bool


class AssetRequirementOut(BaseModel):
    asset_id: uuid.UUID
    title_fa: str
    is_mandatory: bool


class InterestRefOut(BaseModel):
    interest_id: uuid.UUID
    title_fa: str


class ProjectSummaryOut(BaseModel):
    """پروژه در فهرست‌ها و داخل کارت پیشنهاد — §5.7."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slug: str
    title_fa: str
    summary: str
    kind: ProjectKind
    kind_fa: str
    status: ProjectStatus
    difficulty: int
    difficulty_fa: str
    time_commitment_hpw: int | None = None
    work_style: WorkStyle
    team_size_min: int
    team_size_max: int
    active_members: int = 0
    open_seats: int = 0
    tags: list[str] = Field(default_factory=list)
    deadline_on: date | None = None
    applications_close_at: datetime | None = None


class ProjectDetailOut(ProjectSummaryOut):
    description: str
    expected_output: str
    rewards: dict[str, object] = Field(default_factory=dict)
    required_skills: list[SkillRequirementOut] = Field(default_factory=list)
    required_assets: list[AssetRequirementOut] = Field(default_factory=list)
    interests: list[InterestRefOut] = Field(default_factory=list)
    # تطابق من — فقط وقتی کاربر وارد شده و دانشجوست.
    match: MatchOut | None = None


class ReasonOut(BaseModel):
    """دلیل آمادهٔ نمایش — §8.10. متن را بک‌اند می‌سازد، نه کلاینت."""

    type: str
    polarity: Polarity
    contribution: float
    text: str


class BreakdownOut(BaseModel):
    """شش زیرامتیاز §8.2 تا §8.7، برای شفافیت امتیاز (اصل ۳ §00)."""

    skill: float
    asset: float
    interest: float
    time: float
    style: float
    goal: float


class MatchOut(BaseModel):
    """تطابق من با یک پروژه — §5.7.

    اگر پروژه از فهرست پیشنهاد حذف شده باشد (§8.3 امکانات الزامی، یا §8.9
    بازخورد کاربر)، امتیاز صفر است. بدون `exclusion_note` کاربر یک «۰٪»
    بی‌توضیح می‌بیند در حالی که همهٔ زیرامتیازها بالا هستند — که دقیقاً
    همان جعبهٔ سیاهی است که اصل ۳ §00 منع می‌کند.
    """

    match_score: float
    breakdown: BreakdownOut
    reasons: list[ReasonOut]
    is_stretch: bool = False
    is_excluded: bool = False
    exclusion_note: str | None = None


class RecommendationItemOut(BaseModel):
    """یک پیشنهاد — §5.7 `GET /projects/recommended`."""

    project: ProjectSummaryOut
    match_score: float
    reasons: list[ReasonOut]
    breakdown: BreakdownOut
    # §8.11 — «چالش‌برانگیز، اگر آماده‌ای»
    is_stretch: bool = False


class RecommendationsOut(BaseModel):
    items: list[RecommendationItemOut]
    profile_completeness: float
    computed_at: datetime


class RecommendationFeedbackIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdict: FeedbackVerdict
    reason: Annotated[str, Field(max_length=300)] | None = None


# ── ساخت و ویرایش پروژه — FR-PRJ-01 ────────────────────────────────────
MAX_TITLE = 200
MAX_SUMMARY = 280
MAX_DESCRIPTION = 20_000
MAX_TAGS = 10
MAX_MOTIVATION = 500


class SkillRequirementIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    skill_id: uuid.UUID
    min_level: Annotated[int, Field(ge=1, le=5)]
    weight: Annotated[int, Field(ge=1, le=3)] = 1
    is_teachable: bool = False


class AssetRequirementIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_id: uuid.UUID
    is_mandatory: bool = False


class ProjectRoleIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title_fa: Annotated[str, Field(min_length=1, max_length=100)]
    description: Annotated[str, Field(max_length=1000)] | None = None
    slots: Annotated[int, Field(ge=1, le=20)] = 1


class ProjectRoleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title_fa: str
    description: str | None = None
    slots: int
    filled: int

    @property
    def has_opening(self) -> bool:
        return self.filled < self.slots


class ProjectIn(BaseModel):
    """ورودی ساخت و ویرایش — همان بدنه برای هر دو (§5.7 `POST`/`PATCH`).

    `PATCH` اینجا جایگزینی کامل است، نه وصلهٔ جزئی: فرم ویرایش پروژه همهٔ
    میدان‌ها را با هم می‌فرستد و وصلهٔ جزئی روی فهرست‌هایی مثل
    `required_skills` معنای روشنی ندارد.
    """

    model_config = ConfigDict(extra="forbid")

    title_fa: Annotated[str, Field(min_length=3, max_length=MAX_TITLE)]
    summary: Annotated[str, Field(min_length=10, max_length=MAX_SUMMARY)]
    description: Annotated[str, Field(min_length=10, max_length=MAX_DESCRIPTION)]
    kind: ProjectKind
    expected_output: Annotated[str, Field(min_length=3, max_length=1000)]
    difficulty: Annotated[int, Field(ge=1, le=5)] = 3
    work_style: WorkStyle = "EITHER"
    team_size_min: Annotated[int, Field(ge=1, le=20)] = 1
    team_size_max: Annotated[int, Field(ge=1, le=20)] = 1
    time_commitment_hpw: Annotated[int, Field(ge=1, le=60)] | None = None
    tags: Annotated[list[str], Field(max_length=MAX_TAGS)] = Field(default_factory=list)
    rewards: dict[str, object] = Field(default_factory=dict)
    starts_on: date | None = None
    deadline_on: date | None = None
    applications_close_at: datetime | None = None
    required_skills: Annotated[list[SkillRequirementIn], Field(max_length=20)] = Field(
        default_factory=list
    )
    required_assets: Annotated[list[AssetRequirementIn], Field(max_length=20)] = Field(
        default_factory=list
    )
    interests: Annotated[list[uuid.UUID], Field(max_length=20)] = Field(default_factory=list)
    roles: Annotated[list[ProjectRoleIn], Field(max_length=20)] = Field(default_factory=list)


class ReasonIn(BaseModel):
    """بدنهٔ اقدام‌هایی که سند برایشان «با ذکر دلیل» نوشته است — §7.4."""

    model_config = ConfigDict(extra="forbid")

    reason: Annotated[str, Field(min_length=3, max_length=500)]


class CompleteProjectIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    final_report: Annotated[str, Field(min_length=10, max_length=20_000)]


# ── تیم — FR-TEAM-03 ───────────────────────────────────────────────────
class TeamMemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: uuid.UUID
    full_name: str | None = None
    username: str | None = None
    role_id: uuid.UUID | None = None
    role_title_fa: str | None = None
    is_lead: bool = False
    status: Literal["ACTIVE", "LEFT", "REMOVED"]
    joined_at: datetime
    left_at: datetime | None = None


class TeamOut(BaseModel):
    project_id: uuid.UUID
    name: str
    members: list[TeamMemberOut] = Field(default_factory=list)
    active_members: int = 0
    open_seats: int = 0


# ── درخواست پیوستن — FR-PRJ-04 ─────────────────────────────────────────
ApplicationStatus = Literal["PENDING", "ACCEPTED", "REJECTED", "WAITLISTED", "WITHDRAWN"]
ApplicationDecision = Literal["ACCEPTED", "REJECTED", "WAITLISTED"]


class ApplicationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    motivation: Annotated[str, Field(min_length=10, max_length=MAX_MOTIVATION)]
    role_id: uuid.UUID | None = None


class ApplicationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    project_title_fa: str | None = None
    applicant_id: uuid.UUID
    applicant_name: str | None = None
    role_id: uuid.UUID | None = None
    role_title_fa: str | None = None
    motivation: str
    # عکس لحظهٔ ارسال — §7.5. نه عدد زندهٔ امروز.
    match_score: float | None = None
    match_breakdown: dict[str, float] | None = None
    status: ApplicationStatus
    status_fa: str
    decision_note: str | None = None
    decided_at: datetime | None = None
    created_at: datetime


class DecisionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: ApplicationDecision
    note: Annotated[str, Field(max_length=1000)] | None = None


class AlternativeOut(BaseModel):
    """یک پروژهٔ جایگزین همراه پاسخ رد — §7.5."""

    project: ProjectSummaryOut
    match_score: float
    reasons: list[ReasonOut] = Field(default_factory=list)


class DecisionOut(BaseModel):
    application: ApplicationOut
    # §7.5 «رد محترمانه»: پاسخ رد همیشه با سه جایگزین می‌آید.
    alternatives: list[AlternativeOut] = Field(default_factory=list)


# ── تبدیل از دامنه به قرارداد API ──────────────────────────────────────
def breakdown_of(match: MatchResult) -> BreakdownOut:
    from silp.domain.recommendation.schemas import Component

    return BreakdownOut(
        skill=round(match.breakdown[Component.SKILL], 1),
        asset=round(match.breakdown[Component.ASSET], 1),
        interest=round(match.breakdown[Component.INTEREST], 1),
        time=round(match.breakdown[Component.TIME], 1),
        style=round(match.breakdown[Component.STYLE], 1),
        goal=round(match.breakdown[Component.GOAL], 1),
    )


def reasons_of(match: MatchResult) -> list[ReasonOut]:
    return [
        ReasonOut(
            type=r.type.value,
            polarity=r.polarity.value,
            contribution=round(r.contribution, 1),
            text=r.text,
        )
        for r in match.reasons
    ]


ProjectDetailOut.model_rebuild()

__all__ = [
    "AlternativeOut",
    "ApplicationIn",
    "ApplicationOut",
    "ApplicationStatus",
    "AssetRequirementIn",
    "AssetRequirementOut",
    "BreakdownOut",
    "CompleteProjectIn",
    "DecisionIn",
    "DecisionOut",
    "InterestRefOut",
    "MatchOut",
    "ProjectDetailOut",
    "ProjectIn",
    "ProjectRoleIn",
    "ProjectRoleOut",
    "ProjectSummaryOut",
    "ReasonIn",
    "ReasonOut",
    "RecommendationFeedbackIn",
    "RecommendationItemOut",
    "RecommendationsOut",
    "SkillRequirementIn",
    "SkillRequirementOut",
    "SortOrder",
    "TeamMemberOut",
    "TeamOut",
    "breakdown_of",
    "reasons_of",
]
