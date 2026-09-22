"""مدل‌های Pydantic امتیاز، نشان، رتبه‌بندی و داشبورد — §5.3، §5.8، §5.11، §5.12.

اعداد امتیاز `Decimal` هستند و در JSON رشته می‌شوند (`"12.50"`)، مثل نمرهٔ
آزمون (§5.6). کلاینت آن‌ها را فقط نمایش می‌دهد؛ جمع و سطح و «چند امتیاز
تا سطح بعد» از سرور می‌آید — §5.5 «کلاینت هیچ منطقی را بازتولید نمی‌کند».
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, Field

PointCategory = Literal["LEARNING", "RESEARCH", "STARTUP", "COMMUNITY"]
BadgeTier = Literal["BRONZE", "SILVER", "GOLD", "PLATINUM"]
LeaderboardScope = Literal["GLOBAL", "OFFERING", "UNIVERSITY"]
Health = Literal["HEALTHY", "AT_RISK", "STALLED"]


# ── دفتر کل — §5.3 `GET /me/points` ────────────────────────────────────
class PointEntryOut(BaseModel):
    id: uuid.UUID
    rule_code: str
    rule_title_fa: str
    category: PointCategory
    category_fa: str
    amount: Decimal
    source_type: str
    source_type_fa: str | None = None
    source_id: uuid.UUID | None = None
    source_label: str | None = None
    """«آزمون هفتهٔ ۳ — آمار» — منشأ خوانا (§9.10 شفافیت)."""
    source_href: str | None = None
    note: str | None = None
    created_at: datetime
    reverses_id: uuid.UUID | None = None
    is_reversed: bool = False
    """این ردیف اصلی بعداً اصلاح شده — در رابط خط می‌خورد، پاک نمی‌شود."""


class PointLedgerOut(BaseModel):
    items: list[PointEntryOut]
    next_cursor: uuid.UUID | None = None


class LevelOut(BaseModel):
    level: int
    title_fa: str
    current_at: int
    next_at: int | None = None
    to_next: Decimal
    """«۱۳۰ امتیاز تا سطح بعد» — §9.4 نمایش."""
    ratio: Decimal


class PointsSummaryOut(BaseModel):
    total: Decimal
    level: LevelOut
    by_category: dict[str, Decimal]
    term_total: Decimal
    term_by_category: dict[str, Decimal]
    latest_entry_id: uuid.UUID | None = None
    """کلاینت با مقایسهٔ این با آخرین دیده‌شده، Toast «+۵۰» را نشان می‌دهد."""
    recent: list[PointEntryOut] = Field(default_factory=list)


class MePointsOut(BaseModel):
    """خلاصهٔ امتیاز در پاسخ `GET /me` — §5.3."""

    total: Decimal
    level: int
    next_level_at: int | None = None


# ── نشان — §5.3 `GET /me/badges` ───────────────────────────────────────
class BadgeOut(BaseModel):
    code: str
    title_fa: str
    description: str
    icon: str
    tier: BadgeTier
    tier_fa: str
    earned: bool
    awarded_at: datetime | None = None
    seen: bool = True
    """نشان کسب‌شده‌ای که جشنش هنوز دیده نشده — مودال باز می‌شود."""
    progress_current: Decimal
    progress_target: Decimal
    progress_ratio: Decimal


class BadgesOut(BaseModel):
    earned: list[BadgeOut]
    locked: list[BadgeOut]


class BadgesSeenIn(BaseModel):
    codes: Annotated[list[str], Field(max_length=50)] | None = None
    """خالی یعنی همه."""


class BadgesSeenOut(BaseModel):
    updated: int


# ── رتبه‌بندی — §5.8 `GET /leaderboard` ────────────────────────────────
class LeaderUserOut(BaseModel):
    user_id: uuid.UUID
    display_name: str | None = None
    username: str | None = None


class LeaderRowOut(BaseModel):
    rank: int
    user: LeaderUserOut
    total: Decimal
    level: int
    is_me: bool = False


class MyStandingOut(BaseModel):
    rank: int | None = None
    total: Decimal
    level: int
    percentile: int | None = None
    hidden: bool = False
    excluded_reason: Literal["OPTED_OUT", "STAFF"] | None = None


class LeaderboardOut(BaseModel):
    scope: LeaderboardScope
    scope_id: uuid.UUID | None = None
    category: PointCategory | None = None
    term_title_fa: str | None = None
    entries: list[LeaderRowOut]
    growth: list[LeaderRowOut]
    me: MyStandingOut


# ── نمرهٔ یادگیری — §9.6 ───────────────────────────────────────────────
class LearningComponentOut(BaseModel):
    key: Literal["quiz", "study", "project", "attendance"]
    title_fa: str
    ratio: Decimal | None = None
    """`None` یعنی این مؤلفه در این ارائه وجود ندارد — وزنش بازتوزیع شد."""
    weight: Decimal
    earned: Decimal
    possible: Decimal


class LearningScoreOut(BaseModel):
    offering_id: uuid.UUID
    student_id: uuid.UUID
    display_name: str | None = None
    score: Decimal | None = None
    suggested_grade: Decimal | None = None
    """`LS × 0.2` روی مقیاس ۲۰ — فقط پیشنهاد؛ نمرهٔ نهایی را استاد ثبت می‌کند."""
    components: list[LearningComponentOut]


# ── داشبورد دانشجو — FR-DASH-01 ───────────────────────────────────────
class NextStepOut(BaseModel):
    kind: str
    title: str
    description: str
    href: str
    due_at: datetime | None = None


class CourseCardOut(BaseModel):
    offering_id: uuid.UUID
    course_title_fa: str
    term_title_fa: str
    study_ratio: Decimal | None = None
    learning_score: Decimal | None = None
    current_week_number: int | None = None


class ProjectCardOut(BaseModel):
    project_id: uuid.UUID
    title_fa: str
    kind: str
    status: str
    health: Health
    health_fa: str
    next_milestone_title: str | None = None
    next_milestone_due_on: date | None = None
    next_milestone_status: str | None = None
    approved_milestones: int
    required_milestones: int


class TrendPointOut(BaseModel):
    week_start: date
    total: Decimal


class UpcomingEventOut(BaseModel):
    kind: Literal["QUIZ_OPENS", "QUIZ_CLOSES", "MILESTONE_DUE"]
    title: str
    at: datetime
    href: str


class StudentDashboardOut(BaseModel):
    next_step: NextStepOut | None = None
    points: PointsSummaryOut
    courses: list[CourseCardOut]
    projects: list[ProjectCardOut]
    recent_badges: list[BadgeOut]
    trend: list[TrendPointOut]
    upcoming: list[UpcomingEventOut]


# ── داشبورد استاد — §5.11 `GET /teach/dashboard` ───────────────────────
class QueueOut(BaseModel):
    count: int
    oldest_days: int | None = None


class ProjectAtRiskOut(BaseModel):
    id: uuid.UUID
    title_fa: str
    health: Health
    health_fa: str
    days_inactive: int


class StudentAtRiskOut(BaseModel):
    user_id: uuid.UUID
    display_name: str | None = None
    reason: str
    offering_id: uuid.UUID
    course_title_fa: str


class NeedsAttentionOut(BaseModel):
    deliverables_pending: QueueOut
    essays_pending: QueueOut
    enrollment_requests: QueueOut
    grade_appeals: QueueOut
    projects_at_risk: list[ProjectAtRiskOut]
    students_at_risk: list[StudentAtRiskOut]


class OfferingStatsOut(BaseModel):
    id: uuid.UUID
    title_fa: str
    status: str
    students: int
    avg_progress: Decimal | None = None
    avg_quiz_score: Decimal | None = None
    """روی مقیاس ۲۰."""
    avg_learning_score: Decimal | None = None


class TeachDashboardOut(BaseModel):
    needs_attention: NeedsAttentionOut
    offerings: list[OfferingStatsOut]


# ── مدیریت — §5.12 ─────────────────────────────────────────────────────
class PointRuleOut(BaseModel):
    code: str
    title_fa: str
    category: PointCategory
    base_points: Decimal
    formula: str | None = None
    daily_cap: int | None = None
    weekly_cap: int | None = None
    term_cap: int | None = None
    is_active: bool
    updated_at: datetime


CapName = Literal["daily_cap", "weekly_cap", "term_cap"]


class PointRuleUpdateIn(BaseModel):
    """`PATCH` جزئی. **گذشته‌نگر نیست** — برای بازنویسی گذشته، بازمحاسبه."""

    title_fa: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    base_points: Annotated[Decimal, Field(ge=0, le=9999)] | None = None
    daily_cap: Annotated[int, Field(ge=1, le=10_000)] | None = None
    weekly_cap: Annotated[int, Field(ge=1, le=10_000)] | None = None
    term_cap: Annotated[int, Field(ge=1, le=10_000)] | None = None
    clear_caps: list[CapName] = Field(default_factory=list)
    is_active: bool | None = None


class RecalculateIn(BaseModel):
    rule_code: str
    since: datetime | None = None
    until: datetime | None = None


class RecalculateOut(BaseModel):
    rule_code: str
    reversed: int
    reawarded: int
    users: int


class ReverseEntryIn(BaseModel):
    reason: Annotated[str, Field(min_length=3, max_length=500)]


__all__ = [
    "BadgeOut",
    "BadgesOut",
    "BadgesSeenIn",
    "BadgesSeenOut",
    "LeaderboardOut",
    "LearningScoreOut",
    "MePointsOut",
    "PointEntryOut",
    "PointLedgerOut",
    "PointRuleOut",
    "PointRuleUpdateIn",
    "PointsSummaryOut",
    "RecalculateIn",
    "RecalculateOut",
    "ReverseEntryIn",
    "StudentDashboardOut",
    "TeachDashboardOut",
]
