"""مدل‌های Pydantic برای /me/profile و /me/survey — قرارداد §5.3."""

from __future__ import annotations

import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from silp.schemas.project import RecommendationItemOut

DegreeLevel = Literal["ASSOCIATE", "BACHELOR", "MASTER", "PHD", "OTHER"]
Gender = Literal["M", "F", "UNDISCLOSED"]
WorkStyle = Literal["SOLO", "TEAM", "EITHER"]
PrimaryGoal = Literal["GRADE", "LEARNING", "PUBLICATION", "INCOME", "STARTUP", "EMPLOYMENT"]

Level = Annotated[int, Field(ge=1, le=5)]
MAX_SURVEY_ITEMS = 60


class UniversityRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title_fa: str


class ProfileOut(BaseModel):
    """نیمرخ در پاسخ `GET /me` — §5.3.

    کد ملی هرگز اینجا نمی‌آید، حتی پوشانده (NFR-01). مسیر اختصاصی با
    مجوز `profile.view.national_id` دارد.
    """

    first_name: str
    last_name: str
    display_name: str | None = None
    avatar_url: str | None = None
    university: UniversityRef | None = None
    field_of_study: str | None = None
    degree_level: DegreeLevel | None = None
    degree_level_fa: str | None = None
    entry_year: int | None = None
    bio: str | None = None
    work_style: WorkStyle | None = None
    primary_goal: PrimaryGoal | None = None
    weekly_hours: int | None = None
    is_public: bool = False


class ProfileUpdateIn(BaseModel):
    """`PATCH /me/profile` — همهٔ فیلدها اختیاری‌اند.

    `None` یعنی «تغییر نده». این قرارداد در §5.3 صریح است و باعث می‌شود
    فرم چندگامی بتواند فقط فیلدهای همان گام را بفرستد.
    """

    model_config = ConfigDict(extra="forbid")

    first_name: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    last_name: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    display_name: Annotated[str, Field(max_length=100)] | None = None
    birth_year: Annotated[int, Field(ge=1300, le=1420)] | None = None
    gender: Gender | None = None
    bio: Annotated[str, Field(max_length=500)] | None = None
    university_id: uuid.UUID | None = None
    field_of_study: Annotated[str, Field(max_length=150)] | None = None
    degree_level: DegreeLevel | None = None
    student_number: Annotated[str, Field(max_length=30)] | None = None
    entry_year: Annotated[int, Field(ge=1300, le=1420)] | None = None
    #: FR-PROF-03، FR-TEAM-01 — «فقط کسانی که نیمرخشان را عمومی کرده‌اند قابل
    #: جستجواند». پیش‌فرض خصوصی است؛ روشن کردنش انتخاب خود دانشجوست.
    is_public: bool | None = None

    @field_validator("first_name", "last_name", "display_name", "field_of_study")
    @classmethod
    def _trim(cls, v: str | None) -> str | None:
        return v.strip() if v else v


# ── گام‌های ارزیابی ────────────────────────────────────────────────────
class SkillAnswerIn(BaseModel):
    skill_id: uuid.UUID
    level: Level


class SkillsStepIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    skills: Annotated[list[SkillAnswerIn], Field(max_length=MAX_SURVEY_ITEMS)]


class AssetsStepIn(BaseModel):
    """گام ۲ جایگزینی کامل است: فهرست خالی یعنی «هیچ امکانی ندارم»."""

    model_config = ConfigDict(extra="forbid")

    asset_ids: Annotated[list[uuid.UUID], Field(max_length=MAX_SURVEY_ITEMS)]


class InterestAnswerIn(BaseModel):
    interest_id: uuid.UUID
    level: Level


class InterestsStepIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    interests: Annotated[list[InterestAnswerIn], Field(max_length=MAX_SURVEY_ITEMS)]


class PreferencesStepIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    work_style: WorkStyle | None = None
    primary_goal: PrimaryGoal | None = None
    weekly_hours: Annotated[int, Field(ge=0, le=80)] | None = None


class SurveyStepOut(BaseModel):
    """پاسخ هر گام — §5.3.

    `preview_recommendations` همان «لحظهٔ طلایی» §01 است: سرور بلافاصله
    پس از گام ۱ سه پیشنهاد برمی‌گرداند، حتی با نیمرخ ۲۵٪ کامل.
    """

    completed_steps: int
    total_steps: int
    preview_recommendations: list[RecommendationItemOut] = Field(default_factory=list)


class SurveySkillOut(BaseModel):
    skill_id: uuid.UUID
    level: int
    is_verified: bool = False


class SurveyInterestOut(BaseModel):
    interest_id: uuid.UUID
    level: int


class SurveyOut(BaseModel):
    """`GET /me/survey` — وضعیت کامل ارزیابی."""

    skills: list[SurveySkillOut]
    asset_ids: list[uuid.UUID]
    interests: list[SurveyInterestOut]
    work_style: WorkStyle | None = None
    primary_goal: PrimaryGoal | None = None
    weekly_hours: int | None = None
    completed_steps: int
    total_steps: int


__all__ = [
    "AssetsStepIn",
    "InterestAnswerIn",
    "InterestsStepIn",
    "PreferencesStepIn",
    "ProfileOut",
    "ProfileUpdateIn",
    "SkillAnswerIn",
    "SkillsStepIn",
    "SurveyInterestOut",
    "SurveyOut",
    "SurveySkillOut",
    "SurveyStepOut",
    "UniversityRef",
]
