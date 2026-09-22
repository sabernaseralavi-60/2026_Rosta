"""مدل‌های Pydantic برای /courses و /offerings — قرارداد §5.5.

قاعدهٔ حاکم بر این فایل: **کلاینت هیچ منطقی را بازتولید نمی‌کند.**
سطح دسترسی، دلیلش، و متن فارسی قفل همه از سرور می‌آیند (§5.5 دربارهٔ
`quiz.state` همین را می‌گوید). رابط کاربری فقط نمایش می‌دهد.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

AccessTier = Literal["PUBLIC", "SUBSCRIBER", "ENROLLED"]
MaterialKind = Literal[
    "BOOK", "NOTE", "SLIDE", "VIDEO", "PODCAST", "DATASET", "CODE", "QUESTION_BANK", "LINK", "OTHER"
]
ResourceKind = Literal["PDF", "VIDEO", "LINK", "SLIDE", "DATASET", "CODE", "OTHER"]
DegreeLevel = Literal["BACHELOR", "MASTER", "PHD", "PUBLIC"]
WeekStatus = Literal["DRAFT", "PUBLISHED", "ARCHIVED"]
EnrollmentStatus = Literal["PENDING", "ACTIVE", "DROPPED", "COMPLETED", "REJECTED"]
OfferingStatus = Literal["DRAFT", "OPEN", "IN_PROGRESS", "CLOSED", "ARCHIVED"]
ProgressStatus = Literal["NOT_STARTED", "IN_PROGRESS", "COMPLETED"]
AttendanceStatus = Literal["PRESENT", "ABSENT", "LATE", "EXCUSED"]
AnnouncementPriority = Literal["NORMAL", "IMPORTANT", "URGENT"]
AccessReasonOut = Literal["PUBLIC", "ENROLLED", "SUBSCRIPTION", "STAFF"]
AccessBlockerOut = Literal["SUBSCRIPTION", "ENROLLMENT"]

MAX_TITLE = 200
MAX_BODY = 4000


# ── دسترسی ─────────────────────────────────────────────────────────────
class AccessOut(BaseModel):
    """سنجش دسترسی یک ماده برای کاربر جاری — ADR-0009.

    `note_fa` جمله‌ای است که کنار قفل نشان داده می‌شود. کلاینت آن را
    نمی‌سازد تا منطق توضیح یکجا بماند.
    """

    allowed: bool
    tier: AccessTier
    reason: AccessReasonOut | None = None
    blocker: AccessBlockerOut | None = None
    note_fa: str


# ── درس ────────────────────────────────────────────────────────────────
class CourseSummaryOut(BaseModel):
    id: uuid.UUID
    slug: str
    code: str
    title_fa: str
    title_en: str | None = None
    description: str | None = None
    degree_level: DegreeLevel | None = None
    degree_level_fa: str | None = None
    credits: int | None = None
    topics: list[str] = Field(default_factory=list)
    material_count: int = 0
    free_material_count: int = 0
    open_offering_count: int = 0


class MaterialOut(BaseModel):
    """یک ماده از کتابخانهٔ درس.

    `download_url` فقط وقتی پر است که کاربر اجازه داشته باشد؛ در غیر
    این صورت خودِ ماده دیده می‌شود و لینکش نه — کاربر باید بداند چه
    چیزی پشت اشتراک است.
    """

    id: uuid.UUID
    kind: MaterialKind
    kind_fa: str
    title_fa: str
    description: str | None = None
    authors: list[str] = Field(default_factory=list)
    edition: str | None = None
    language: str = "fa"
    size_bytes: int | None = None
    page_count: int | None = None
    duration_sec: int | None = None
    is_downloadable: bool = True
    external_url: str | None = None
    section: str | None = None
    is_required: bool = True
    access: AccessOut


class SubscriptionPlanRefOut(BaseModel):
    id: uuid.UUID
    code: str
    title_fa: str
    price_irr: int
    duration_days: int
    scope: Literal["ALL_COURSES", "SINGLE_COURSE"]


class OfferingRefOut(BaseModel):
    id: uuid.UUID
    term_code: str
    term_title_fa: str
    instructor_name: str | None = None
    status: OfferingStatus
    requires_approval: bool
    has_enrollment_code: bool
    capacity: int | None = None
    active_students: int = 0


class CourseDetailOut(CourseSummaryOut):
    """جزئیات درس — §5.5 `GET /courses/{slug}`.

    `plans` اینجا می‌آید تا صفحهٔ درس بتواند بدون درخواست دوم، دکمهٔ
    «اشتراک بگیر» را با قیمت درست نشان دهد.
    """

    materials: list[MaterialOut] = Field(default_factory=list)
    offerings: list[OfferingRefOut] = Field(default_factory=list)
    plans: list[SubscriptionPlanRefOut] = Field(default_factory=list)
    my_enrollment_offering_id: uuid.UUID | None = None


# ── ارائه ──────────────────────────────────────────────────────────────
class EnrollmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    offering_id: uuid.UUID
    student_id: uuid.UUID
    status: EnrollmentStatus
    final_grade: float | None = None
    enrolled_at: datetime


class WeekSummaryOut(BaseModel):
    id: uuid.UUID
    week_number: int
    title_fa: str
    description: str | None = None
    status: WeekStatus
    published_at: datetime | None = None
    publish_at: datetime | None = None
    resource_count: int = 0
    material_count: int = 0
    completed_count: int = 0
    progress_percent: int = 0


class AnnouncementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    body: str
    priority: AnnouncementPriority
    published_at: datetime
    expires_at: datetime | None = None


class OfferingSummaryOut(BaseModel):
    id: uuid.UUID
    course_id: uuid.UUID
    course_slug: str
    course_title_fa: str
    term_code: str
    term_title_fa: str
    instructor_id: uuid.UUID
    instructor_name: str | None = None
    status: OfferingStatus
    requires_approval: bool
    has_enrollment_code: bool
    capacity: int | None = None
    active_students: int = 0
    my_status: EnrollmentStatus | None = None
    progress_percent: int = 0
    current_week_number: int | None = None


class OfferingDetailOut(OfferingSummaryOut):
    description: str | None = None
    grading_policy: dict[str, int] = Field(default_factory=dict)
    weeks: list[WeekSummaryOut] = Field(default_factory=list)
    announcements: list[AnnouncementOut] = Field(default_factory=list)
    final_grade: float | None = None


class ResourceProgressOut(BaseModel):
    status: ProgressStatus
    percent: float = 0
    position_sec: int | None = None
    completed_at: datetime | None = None


class ResourceOut(BaseModel):
    id: uuid.UUID
    kind: ResourceKind
    title_fa: str
    description: str | None = None
    external_url: str | None = None
    duration_sec: int | None = None
    is_downloadable: bool = True
    is_required: bool = True
    has_file: bool = False
    progress: ResourceProgressOut | None = None


class WeekDetailOut(BaseModel):
    week_number: int
    title_fa: str
    description: str | None = None
    objectives: list[str] = Field(default_factory=list)
    status: WeekStatus
    published_at: datetime | None = None
    resources: list[ResourceOut] = Field(default_factory=list)
    # کتابخانهٔ درس، فیلترشده به موادی که این هفته به آن‌ها ارجاع می‌دهد.
    materials: list[MaterialOut] = Field(default_factory=list)


# ── ورودی‌ها ───────────────────────────────────────────────────────────
class EnrollIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enrollment_code: Annotated[str | None, Field(max_length=64)] = None


class ProgressIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    percent: Annotated[float | None, Field(ge=0, le=100)] = None
    position_sec: Annotated[int | None, Field(ge=0)] = None
    completed: bool | None = None


class WeekIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    week_number: Annotated[int, Field(ge=1, le=17)]
    title_fa: Annotated[str, Field(min_length=1, max_length=MAX_TITLE)]
    description: Annotated[str | None, Field(max_length=MAX_BODY)] = None
    objectives: Annotated[list[str] | None, Field(max_length=20)] = None
    publish_at: datetime | None = None


class PublishWeekIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # خالی یعنی «همین حالا»؛ تاریخ آینده یعنی انتشار زمان‌بندی‌شده.
    publish_at: datetime | None = None


class ResourceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: ResourceKind
    title_fa: Annotated[str, Field(min_length=1, max_length=MAX_TITLE)]
    description: Annotated[str | None, Field(max_length=MAX_BODY)] = None
    file_id: uuid.UUID | None = None
    external_url: Annotated[str | None, Field(max_length=2000)] = None
    duration_sec: Annotated[int | None, Field(ge=0)] = None
    is_downloadable: bool = True
    is_required: bool = True
    sort_order: int = 0


class LinkMaterialIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    material_id: uuid.UUID
    section: Annotated[str | None, Field(max_length=200)] = None
    is_required: bool = True
    sort_order: int = 0


class AnnouncementIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Annotated[str, Field(min_length=1, max_length=MAX_TITLE)]
    body: Annotated[str, Field(min_length=1, max_length=MAX_BODY)]
    priority: AnnouncementPriority = "NORMAL"
    expires_at: datetime | None = None


class AttendanceEntryIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    student_id: uuid.UUID
    status: AttendanceStatus
    note: Annotated[str | None, Field(max_length=500)] = None


class AttendanceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    held_on: date
    week_number: Annotated[int | None, Field(ge=1, le=17)] = None
    topic: Annotated[str | None, Field(max_length=MAX_TITLE)] = None
    entries: Annotated[list[AttendanceEntryIn], Field(max_length=500)]


class EnrollmentDecisionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approve: bool
    note: Annotated[str | None, Field(max_length=500)] = None


class FinalGradeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    grade: Annotated[float, Field(ge=0, le=20)]


class GradingPolicyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quiz: Annotated[int, Field(ge=0, le=100)] = 0
    project: Annotated[int, Field(ge=0, le=100)] = 0
    attendance: Annotated[int, Field(ge=0, le=100)] = 0
    participation: Annotated[int, Field(ge=0, le=100)] = 0


class CopyContentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_offering_id: uuid.UUID


class DownloadOut(BaseModel):
    download_url: str
    expires_in: int
    original_name: str


class CopyResultOut(BaseModel):
    weeks_copied: int


class RosterEntryOut(BaseModel):
    enrollment_id: uuid.UUID
    student_id: uuid.UUID
    student_name: str | None = None
    status: EnrollmentStatus
    final_grade: float | None = None
    enrolled_at: datetime
    progress_percent: int = 0


__all__ = [
    "AccessOut",
    "AnnouncementIn",
    "AnnouncementOut",
    "AttendanceIn",
    "CopyContentIn",
    "CopyResultOut",
    "CourseDetailOut",
    "CourseSummaryOut",
    "DownloadOut",
    "EnrollIn",
    "EnrollmentDecisionIn",
    "EnrollmentOut",
    "FinalGradeIn",
    "GradingPolicyIn",
    "LinkMaterialIn",
    "MaterialOut",
    "OfferingDetailOut",
    "OfferingRefOut",
    "OfferingSummaryOut",
    "ProgressIn",
    "PublishWeekIn",
    "ResourceIn",
    "ResourceOut",
    "RosterEntryOut",
    "SubscriptionPlanRefOut",
    "WeekDetailOut",
    "WeekIn",
    "WeekSummaryOut",
]
