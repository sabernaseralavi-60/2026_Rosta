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
    "AssetRequirementOut",
    "BreakdownOut",
    "InterestRefOut",
    "MatchOut",
    "ProjectDetailOut",
    "ProjectSummaryOut",
    "ReasonOut",
    "RecommendationFeedbackIn",
    "RecommendationItemOut",
    "RecommendationsOut",
    "SkillRequirementOut",
    "SortOrder",
    "breakdown_of",
    "reasons_of",
]
