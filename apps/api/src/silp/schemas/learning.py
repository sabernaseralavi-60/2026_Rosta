"""مدل‌های حلقهٔ یادگیری روزانه — ADR-0036."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

MasteryLevelOut = Literal["STRONG", "MEDIUM", "WEAK", "LOW_DATA"]
CheckpointState = Literal["AVAILABLE", "IN_PROGRESS", "DONE", "UPCOMING"]


# ── درس‌نامه ───────────────────────────────────────────────────────────
class LessonIn(BaseModel):
    title_fa: Annotated[str, Field(min_length=1, max_length=200)]
    body_md: Annotated[str, Field(min_length=1, max_length=60000)]
    est_minutes: Annotated[int, Field(ge=1, le=120)] = 5
    module_id: uuid.UUID | None = None
    week_id: uuid.UUID | None = None
    publish_at: datetime | None = None
    publish: bool = False


class LessonPatchIn(BaseModel):
    title_fa: Annotated[str, Field(min_length=1, max_length=200)]
    body_md: Annotated[str, Field(min_length=1, max_length=60000)]
    est_minutes: Annotated[int, Field(ge=1, le=120)] = 5
    module_id: uuid.UUID | None = None
    publish_at: datetime | None = None


class PublishIn(BaseModel):
    published: bool


class LessonOut(BaseModel):
    """نمای کادر — با متن کامل برای ویرایش."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    offering_id: uuid.UUID
    module_id: uuid.UUID | None
    week_id: uuid.UUID | None
    title_fa: str
    body_md: str
    est_minutes: int
    status: Literal["DRAFT", "PUBLISHED"]
    publish_at: datetime | None
    sort_order: int
    updated_at: datetime


class LessonSummaryOut(BaseModel):
    """نمای دانشجو در فهرست — بدون متن."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    offering_id: uuid.UUID
    module_id: uuid.UUID | None
    title_fa: str
    est_minutes: int
    publish_at: datetime | None
    updated_at: datetime


class LessonCheckpointOut(BaseModel):
    quiz_id: uuid.UUID
    title_fa: str
    opens_at: datetime
    closes_at: datetime
    duration_min: int
    status: str


class LessonDetailOut(LessonSummaryOut):
    body_md: str
    checkpoints: list[LessonCheckpointOut] = Field(default_factory=list)


class ModuleIn(BaseModel):
    title_fa: Annotated[str, Field(min_length=1, max_length=200)]


class ModuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title_fa: str
    sort_order: int


# ── زنجیرهٔ دانش ───────────────────────────────────────────────────────
class ConceptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    title_fa: str


class CompetencyOut(BaseModel):
    id: uuid.UUID
    code: str
    title_fa: str
    domain: str | None
    concepts: list[ConceptOut]


class CompetencyIn(BaseModel):
    code: Annotated[str, Field(min_length=1, max_length=60, pattern=r"^[a-z0-9][a-z0-9_-]*$")]
    title_fa: Annotated[str, Field(min_length=1, max_length=120)]
    domain: Annotated[str | None, Field(max_length=60)] = None


class ConceptIn(BaseModel):
    code: Annotated[str, Field(min_length=1, max_length=60, pattern=r"^[a-z0-9][a-z0-9_-]*$")]
    title_fa: Annotated[str, Field(min_length=1, max_length=120)]


# ── چالش ───────────────────────────────────────────────────────────────
class CheckpointIn(BaseModel):
    title_fa: Annotated[str, Field(min_length=1, max_length=200)]
    lesson_id: uuid.UUID | None = None
    concept_ids: Annotated[list[uuid.UUID], Field(min_length=1, max_length=50)]
    draw_count: Annotated[int, Field(ge=1, le=30)] = 8
    opens_at: datetime
    closes_at: datetime
    duration_min: Annotated[int, Field(ge=1, le=30)] = 8
    publish: bool = True


class CheckpointOut(BaseModel):
    id: uuid.UUID
    title_fa: str
    status: str
    draw_count: int | None
    pool_size: int


# ── امروز ──────────────────────────────────────────────────────────────
class MasteryOut(BaseModel):
    competency_id: uuid.UUID
    code: str
    title: str
    score: float
    evidence_n: int
    level: MasteryLevelOut


class CheckpointCardOut(BaseModel):
    quiz_id: uuid.UUID
    title: str
    state: CheckpointState
    opens_at: datetime
    closes_at: datetime
    duration_min: int
    question_count: int
    attempt_id: uuid.UUID | None


class LessonCardOut(BaseModel):
    id: uuid.UUID
    title: str
    est_minutes: int
    published_at: datetime


class SkillOutcomeOut(BaseModel):
    title: str
    correct: int
    total: int


class LastResultOut(BaseModel):
    quiz_title: str
    day: date
    correct: int
    total: int
    skills: list[SkillOutcomeOut]


class StreakOut(BaseModel):
    current: int
    longest: int
    alive: bool


class TodayOfferingOut(BaseModel):
    offering_id: uuid.UUID
    course_title: str
    lesson: LessonCardOut | None
    checkpoint: CheckpointCardOut | None
    streak: StreakOut
    last_result: LastResultOut | None


class SuggestionOut(BaseModel):
    kind: Literal["REVIEW", "KEEP_GOING"]
    competency_id: uuid.UUID | None
    title: str | None


class TodayOut(BaseModel):
    offerings: list[TodayOfferingOut]
    mastery: list[MasteryOut]
    suggestion: SuggestionOut | None
