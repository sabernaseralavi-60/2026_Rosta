"""طرح‌های تعریف درس، نیم‌سال و ارائه — `/admin/courses` §3.6، ADR-0020.

ویرایش‌ها `PATCH` جزئی‌اند: فقط فیلد فرستاده‌شده عوض می‌شود. فیلدی که
خالی‌شدنی است (`title_en`، `description`، `credits`) با `null` پاک می‌شود؛
فیلدی که نیست، `null` را نمی‌پذیرد.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from silp.schemas.education import AccessTier, DegreeLevel, OfferingStatus

WeekSource = Literal["SYLLABUS", "OFFERING", "NONE"]

TermCode = Annotated[str, Field(min_length=2, max_length=20, pattern=r"^[0-9A-Za-z][0-9A-Za-z-]*$")]
CourseCode = Annotated[
    str, Field(min_length=2, max_length=32, pattern=r"^[0-9A-Za-z][0-9A-Za-z-]*$")
]
CourseSlug = Annotated[
    str, Field(min_length=2, max_length=64, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
]
TitleFa = Annotated[str, Field(min_length=2, max_length=200)]
Topic = Annotated[str, Field(min_length=1, max_length=60)]


def _not_null(value: object) -> object:
    if value is None:
        raise ValueError("این فیلد خالی نمی‌شود.")
    return value


# ── نیم‌سال ────────────────────────────────────────────────────────────
class AdminTermOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    title_fa: str
    starts_on: date
    ends_on: date
    is_current: bool
    offering_count: int = 0


class TermCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: TermCode
    title_fa: TitleFa
    starts_on: date
    ends_on: date
    is_current: bool = False


class TermUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: TermCode | None = None
    title_fa: TitleFa | None = None
    starts_on: date | None = None
    ends_on: date | None = None
    is_current: bool | None = None

    @field_validator("code", "title_fa", "starts_on", "ends_on", "is_current")
    @classmethod
    def reject_null(cls, value: object) -> object:
        return _not_null(value)


# ── درس ────────────────────────────────────────────────────────────────
class AdminCourseOut(BaseModel):
    id: uuid.UUID
    code: str
    slug: str
    title_fa: str
    title_en: str | None
    description: str | None
    degree_level: DegreeLevel | None
    credits: int | None
    is_public: bool
    is_active: bool
    default_access_tier: AccessTier
    topics: list[str]
    source_dir: str | None
    """نام پوشه در `Courses/`؛ درس پوشه‌ای در پنل فقط‌خواندنی است."""
    offering_count: int
    material_count: int
    syllabus_weeks: int | None
    """هفته‌های برنامهٔ درسی `course.yml`؛ `null` یعنی پوشه‌ای روی این سرور نیست."""
    created_at: datetime


class CourseCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: CourseCode
    slug: CourseSlug | None = None
    """خالی: از کد ساخته می‌شود (`TRAFFIC-ENG` ← `traffic-eng`)."""
    title_fa: TitleFa
    title_en: Annotated[str | None, Field(max_length=200)] = None
    description: Annotated[str | None, Field(max_length=4000)] = None
    degree_level: DegreeLevel | None = None
    credits: Annotated[int | None, Field(ge=1, le=12)] = None
    is_public: bool = False
    is_active: bool = True
    default_access_tier: AccessTier = "SUBSCRIBER"
    topics: Annotated[list[Topic], Field(max_length=20)] = Field(default_factory=list)


class CourseUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: CourseCode | None = None
    slug: CourseSlug | None = None
    title_fa: TitleFa | None = None
    title_en: Annotated[str | None, Field(max_length=200)] = None
    description: Annotated[str | None, Field(max_length=4000)] = None
    degree_level: DegreeLevel | None = None
    credits: Annotated[int | None, Field(ge=1, le=12)] = None
    is_public: bool | None = None
    is_active: bool | None = None
    default_access_tier: AccessTier | None = None
    topics: Annotated[list[Topic] | None, Field(max_length=20)] = None

    @field_validator(
        "code", "slug", "title_fa", "is_public", "is_active", "default_access_tier", "topics"
    )
    @classmethod
    def reject_null(cls, value: object) -> object:
        return _not_null(value)


# ── ارائه ──────────────────────────────────────────────────────────────
class AdminOfferingOut(BaseModel):
    id: uuid.UUID
    course_id: uuid.UUID
    course_code: str
    course_title_fa: str
    term_id: uuid.UUID
    term_code: str
    term_title_fa: str
    instructor_id: uuid.UUID
    instructor_name: str | None
    status: OfferingStatus
    capacity: int | None
    requires_approval: bool
    has_enrollment_code: bool
    active_students: int
    pending_students: int
    week_count: int
    published_weeks: int
    created_at: datetime


class OfferingCreatedOut(AdminOfferingOut):
    weeks_created: int
    """هفته‌هایی که از برنامهٔ درسی یا ارائهٔ مبدأ ساخته شد."""


class OfferingCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    course_id: uuid.UUID
    term_id: uuid.UUID
    instructor_id: uuid.UUID
    status: Literal["DRAFT", "OPEN"] = "DRAFT"
    capacity: Annotated[int | None, Field(ge=1, le=2000)] = None
    enrollment_code: Annotated[str | None, Field(max_length=32)] = None
    requires_approval: bool = False
    grading_policy: dict[str, Annotated[int, Field(ge=0, le=100)]] | None = None
    """خالی: وزن پیش‌فرض (آزمون ۳۰، پروژه ۵۰، حضور ۱۰، مشارکت ۱۰)."""
    weeks_from: WeekSource = "NONE"
    copy_from_offering_id: uuid.UUID | None = None


class OfferingReassignIn(BaseModel):
    """`PATCH /admin/offerings/{id}` — استاد یا نیم‌سال. بقیه در `/teach`."""

    model_config = ConfigDict(extra="forbid")

    instructor_id: uuid.UUID | None = None
    term_id: uuid.UUID | None = None


class InstructorCandidateOut(BaseModel):
    id: uuid.UUID
    name: str | None
    username: str | None
    mobile: str | None
    """پوشانده، مگر برای کسی که `profile.view.contact` دارد."""
    active_offerings: int


__all__ = [
    "AdminCourseOut",
    "AdminOfferingOut",
    "AdminTermOut",
    "CourseCreateIn",
    "CourseUpdateIn",
    "InstructorCandidateOut",
    "OfferingCreateIn",
    "OfferingCreatedOut",
    "OfferingReassignIn",
    "TermCreateIn",
    "TermUpdateIn",
    "WeekSource",
]
