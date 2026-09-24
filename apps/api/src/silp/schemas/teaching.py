"""طرح‌های ناحیهٔ استاد — §3.5، §5.11، ADR-0019.

آنچه صفحه‌های `/teach` لازم داشتند و `schemas.education` نداشت: نمای
کادر آموزشی از یک ارائه (با پیش‌نویس‌ها و کد ثبت‌نام)، تنظیمات ارائه،
خواندن حضور و غیاب، و دفتر نمره.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from silp.schemas.education import (
    AnnouncementOut,
    AttendanceStatus,
    EnrollmentStatus,
    OfferingStatus,
    OfferingSummaryOut,
    WeekSummaryOut,
)
from silp.schemas.gamification import LearningComponentOut

StaffRole = Literal["INSTRUCTOR", "TA", "COORDINATOR", "ADMIN"]


class TeachOfferingOut(OfferingSummaryOut):
    """یک ارائه از دید کادر آموزشی — `GET /teach/offerings[/{id}]`."""

    staff_role: StaffRole | None = None
    """نقش بیننده در همین ارائه؛ رابط کاربری اقدام‌های ناممکن را پنهان می‌کند."""
    pending_enrollments: int = 0


class OfferingPermissionsOut(BaseModel):
    """آنچه بیننده در این ارائه می‌تواند — آینهٔ `require()` سرور، نه جایگزینش."""

    manage: bool
    edit_weeks: bool
    publish_weeks: bool
    upload_resources: bool
    record_attendance: bool
    approve_enrollments: bool
    submit_final_grades: bool
    publish_announcements: bool
    create_quizzes: bool
    grade_quizzes: bool


class TeachAnnouncementOut(AnnouncementOut):
    can_edit: bool = False
    """نویسندهٔ اعلان، یا استاد درس — آینهٔ قاعدهٔ سرور (ADR-0021)."""


class TeachOfferingDetailOut(TeachOfferingOut):
    """`GET /teach/offerings/{id}` — هفته‌ها با پیش‌نویس، و کد ثبت‌نام خوانا."""

    enrollment_code: str | None = None
    grading_policy: dict[str, int] = Field(default_factory=dict)
    weeks: list[WeekSummaryOut] = Field(default_factory=list)
    announcements: list[TeachAnnouncementOut] = Field(default_factory=list)
    quiz_count: int = 0
    allowed_statuses: list[OfferingStatus] = Field(default_factory=list)
    """وضعیت‌هایی که از وضعیت فعلی می‌شود به آن‌ها رفت."""
    permissions: OfferingPermissionsOut


class OfferingSettingsIn(BaseModel):
    """`PATCH /teach/offerings/{id}` — فقط فیلدهای فرستاده‌شده عوض می‌شوند."""

    model_config = ConfigDict(extra="forbid")

    status: OfferingStatus | None = None
    requires_approval: bool | None = None
    capacity: Annotated[int | None, Field(ge=1, le=2000)] = None
    enrollment_code: Annotated[str | None, Field(min_length=4, max_length=32)] = None
    clear_capacity: bool = False
    clear_enrollment_code: bool = False


# ── حضور و غیاب — FR-EDU-05 ────────────────────────────────────────────
class AttendanceSessionOut(BaseModel):
    """یک جلسهٔ ثبت‌شده با شمارش هر وضعیت."""

    held_on: date
    week_number: int | None = None
    topic: str | None = None
    present: int = 0
    late: int = 0
    absent: int = 0
    excused: int = 0


class AttendanceMarkOut(BaseModel):
    student_id: uuid.UUID
    status: AttendanceStatus
    note: str | None = None


class AttendanceSheetOut(AttendanceSessionOut):
    """`GET /teach/offerings/{id}/attendance/{held_on}` — برای اصلاح همان روز."""

    marks: list[AttendanceMarkOut] = Field(default_factory=list)


# ── دفتر نمره — §3.5، §9.6 ─────────────────────────────────────────────
class GradebookQuizOut(BaseModel):
    id: uuid.UUID
    title_fa: str
    status: str
    total_points: Decimal
    closes_at: datetime


class GradebookCellOut(BaseModel):
    """بهترین تلاش تصحیح‌شدهٔ یک دانشجو در یک آزمون."""

    quiz_id: uuid.UUID
    score: Decimal | None = None
    is_provisional: bool = False
    attempts: int = 0


class AttendanceTallyOut(BaseModel):
    present: int = 0
    late: int = 0
    absent: int = 0
    excused: int = 0


class GradebookRowOut(BaseModel):
    enrollment_id: uuid.UUID
    student_id: uuid.UUID
    student_name: str | None = None
    status: EnrollmentStatus
    quizzes: list[GradebookCellOut] = Field(default_factory=list)
    attendance: AttendanceTallyOut
    learning_score: Decimal | None = None
    suggested_grade: Decimal | None = None
    """`LS × ۰٫۲` روی مقیاس ۲۰ — پیشنهاد، نه نمره (§9.6)."""
    components: list[LearningComponentOut] = Field(default_factory=list)
    final_grade: float | None = None


class GradebookOut(BaseModel):
    offering_id: uuid.UUID
    sessions_held: int
    quizzes: list[GradebookQuizOut] = Field(default_factory=list)
    rows: list[GradebookRowOut] = Field(default_factory=list)


__all__ = [
    "AttendanceMarkOut",
    "AttendanceSessionOut",
    "AttendanceSheetOut",
    "AttendanceTallyOut",
    "GradebookCellOut",
    "GradebookOut",
    "GradebookQuizOut",
    "GradebookRowOut",
    "OfferingPermissionsOut",
    "OfferingSettingsIn",
    "StaffRole",
    "TeachOfferingDetailOut",
    "TeachOfferingOut",
]
