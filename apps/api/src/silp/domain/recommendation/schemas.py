"""ساختارهای دادهٔ موتور توصیه‌گر — PRD §8.12.

این ماژول عمداً هیچ وابستگی به SQLAlchemy، FastAPI یا Redis ندارد. همهٔ
ساختارها `frozen` هستند تا امتیازدهی هرگز ورودی‌اش را تغییر ندهد؛ این
شرط لازم برای `test_score_is_deterministic_for_same_input` است.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum

# ── مقادیر پیش‌فرض وقتی دانشجو پاسخ نداده است ──────────────────────────
# §8.2 مهارت پاسخ‌نداده = سطح ۱ (بدترین حالت، چون خودارزیابی نکرده)
DEFAULT_SKILL_LEVEL = 1
# §8.4 علاقهٔ پاسخ‌نداده = سطح ۳ (خنثی، چون بی‌علاقگی ثابت نشده)
DEFAULT_INTEREST_LEVEL = 3
# §8.5 زمان نامشخص = ۱۰ ساعت در هفته
DEFAULT_WEEKLY_HOURS = 10
# §8.5 پروژه‌ای که تعهد زمانی اعلام نکرده
DEFAULT_TIME_COMMITMENT_HPW = 10

MIN_LEVEL = 1
MAX_LEVEL = 5
MIN_SCORE = 0.0
MAX_SCORE = 100.0


class WorkStyle(StrEnum):
    SOLO = "SOLO"
    TEAM = "TEAM"
    EITHER = "EITHER"


class Goal(StrEnum):
    GRADE = "GRADE"
    LEARNING = "LEARNING"
    PUBLICATION = "PUBLICATION"
    INCOME = "INCOME"
    STARTUP = "STARTUP"
    EMPLOYMENT = "EMPLOYMENT"


class ProjectKind(StrEnum):
    A_VENTURE = "A_VENTURE"
    B_RESEARCH = "B_RESEARCH"
    C_PROBLEM = "C_PROBLEM"
    D_PERSONAL = "D_PERSONAL"


# عنوان فارسی برای متن دلیل §8.10 و نمایش در رابط کاربری. اینجا تعریف
# می‌شود، نه در لایهٔ مدل، تا دامنه به SQLAlchemy وابسته نشود.
GOAL_TITLE_FA: dict[Goal, str] = {
    Goal.GRADE: "نمرهٔ درس",
    Goal.LEARNING: "یادگیری",
    Goal.PUBLICATION: "مقاله",
    Goal.INCOME: "کسب درآمد",
    Goal.STARTUP: "راه‌اندازی استارتاپ",
    Goal.EMPLOYMENT: "استخدام",
}

WORK_STYLE_TITLE_FA: dict[WorkStyle, str] = {
    WorkStyle.SOLO: "انفرادی کار می‌کنم",
    WorkStyle.TEAM: "تیمی کار می‌کنم",
    WorkStyle.EITHER: "فرقی ندارد",
}

KIND_TITLE_FA: dict[ProjectKind, str] = {
    ProjectKind.A_VENTURE: "کارآفرینی",
    ProjectKind.B_RESEARCH: "پژوهشی",
    ProjectKind.C_PROBLEM: "حل مسئلهٔ واقعی",
    ProjectKind.D_PERSONAL: "پروژهٔ شخصی",
}


# دلیل حذف از فهرست پیشنهاد — §8.3 و §8.9. متن فارسی همین‌جاست تا صفحهٔ
# جزئیات به‌جای «۰٪» خالی، بتواند بگوید چرا صفر است.
EXCLUSION_NOTE_FA: dict[str, str] = {
    "MISSING_MANDATORY_ASSET": (
        "امکانات الزامی این پروژه را در نیمرخت ثبت نکرده‌ای، برای همین در پیشنهادها نمی‌آید."
    ),
    "ALREADY_APPLIED": "قبلاً برای این پروژه درخواست داده‌ای.",
    "DISMISSED_BY_USER": "خودت خواسته‌ای این پروژه دیگر پیشنهاد نشود.",
}


class Verdict(StrEnum):
    """§8.9 — سه حالت بازخورد دانشجو روی یک پیشنهاد."""

    NOT_RELEVANT = "NOT_RELEVANT"
    INTERESTED = "INTERESTED"
    DISMISSED = "DISMISSED"


class Component(StrEnum):
    """شش زیرامتیاز §8.2 تا §8.7. کلید وزن‌ها و کلید `breakdown` در API."""

    SKILL = "skill"
    ASSET = "asset"
    INTEREST = "interest"
    TIME = "time"
    STYLE = "style"
    GOAL = "goal"


class Polarity(StrEnum):
    POSITIVE = "POSITIVE"
    WARNING = "WARNING"


class ReasonType(StrEnum):
    """§8.10 — انواع دلیل. متن هر کدام در `explainer.py` ساخته می‌شود."""

    SKILL_STRONG = "SKILL_STRONG"
    SKILL_GAP = "SKILL_GAP"
    ASSET_MATCH = "ASSET_MATCH"
    ASSET_MISSING = "ASSET_MISSING"
    INTEREST_HIGH = "INTEREST_HIGH"
    TIME_FIT = "TIME_FIT"
    TIME_TIGHT = "TIME_TIGHT"
    GOAL_FIT = "GOAL_FIT"
    COURSE_LINK = "COURSE_LINK"
    TEAM_NEED = "TEAM_NEED"


@dataclass(frozen=True, slots=True)
class SkillReq:
    skill_id: uuid.UUID
    title_fa: str
    min_level: int
    weight: int = 1
    is_teachable: bool = False


@dataclass(frozen=True, slots=True)
class AssetReq:
    asset_id: uuid.UUID
    title_fa: str
    is_mandatory: bool = False


@dataclass(frozen=True, slots=True)
class InterestRef:
    interest_id: uuid.UUID
    title_fa: str


@dataclass(frozen=True, slots=True)
class ProjectSpec:
    """مشخصات تطابق یک پروژه — فقط آنچه امتیازدهی لازم دارد.

    عمداً کل ردیف `projects` نیست: امتیازدهی نباید به توضیحات، تصویر یا
    وضعیت سلامت دسترسی داشته باشد.
    """

    id: uuid.UUID
    title_fa: str
    kind: ProjectKind
    difficulty: int = 3
    work_style: WorkStyle = WorkStyle.EITHER
    time_commitment_hpw: int | None = None
    team_size_min: int = 1
    team_size_max: int = 1
    active_members: int = 0
    required_skills: tuple[SkillReq, ...] = ()
    required_assets: tuple[AssetReq, ...] = ()
    interests: tuple[InterestRef, ...] = ()
    offering_id: uuid.UUID | None = None
    offering_title_fa: str | None = None
    published_at: datetime | None = None
    applications_close_at: datetime | None = None
    deadline_on: date | None = None
    pending_applications: int = 0

    @property
    def open_seats(self) -> int:
        return max(0, self.team_size_max - self.active_members)

    @property
    def members_short_of_min(self) -> int:
        return max(0, self.team_size_min - self.active_members)


@dataclass(frozen=True, slots=True)
class StudentContext:
    """نیمرخ دانشجو در شکلی که امتیازدهی می‌فهمد — §8.12.

    `answered_*` از `skills`/`interests` جدا نیست چون کلیدِ موجود یعنی
    پاسخ‌داده؛ اما `completed_steps` لازم است تا §8.8 بفهمد کدام مؤلفه
    اصلاً داده دارد.
    """

    user_id: uuid.UUID
    skills: dict[uuid.UUID, int] = field(default_factory=dict)
    verified_skills: frozenset[uuid.UUID] = frozenset()
    assets: frozenset[uuid.UUID] = frozenset()
    interests: dict[uuid.UUID, int] = field(default_factory=dict)
    weekly_hours: int | None = None
    work_style: WorkStyle | None = None
    primary_goal: Goal | None = None
    enrolled_offerings: frozenset[uuid.UUID] = frozenset()
    completed_steps: int = 0
    # مهارت‌های پاسخ‌داده‌شده، برای برآورد «سطح دانشجو» در §8.11
    applied_project_ids: frozenset[uuid.UUID] = frozenset()
    feedback: dict[uuid.UUID, Verdict] = field(default_factory=dict)

    def skill_level(self, skill_id: uuid.UUID) -> int:
        return self.skills.get(skill_id, DEFAULT_SKILL_LEVEL)

    def interest_level(self, interest_id: uuid.UUID) -> int:
        return self.interests.get(interest_id, DEFAULT_INTEREST_LEVEL)

    @property
    def effective_weekly_hours(self) -> int:
        return DEFAULT_WEEKLY_HOURS if self.weekly_hours is None else self.weekly_hours

    @property
    def average_skill_level(self) -> float:
        """برآورد «سطح» دانشجو برای انتخاب پروژهٔ کشش‌دار (§8.11)."""
        if not self.skills:
            return float(DEFAULT_SKILL_LEVEL)
        return sum(self.skills.values()) / len(self.skills)

    def has_data_for(self, component: Component) -> bool:
        """§8.8 — آیا این مؤلفه داده‌ای برای امتیازدهی دارد؟

        نبود داده یعنی وزنش صفر و بقیه بازنرمال می‌شوند؛ نه اینکه امتیاز
        بدی بگیرد.
        """
        match component:
            case Component.SKILL:
                return bool(self.skills)
            case Component.ASSET:
                # مثل مهارت و علاقه: وجود ردیف یعنی داده داریم.
                #
                # `completed_steps` اینجا به کار نمی‌آید چون یکنواخت افزایشی
                # است: دانشجویی که فقط گام ۴ را زده هم شمارنده‌اش ۴ می‌شود،
                # بدون اینکه دربارهٔ امکاناتش چیزی گفته باشد.
                #
                # نتیجه‌اش این است که دانشجوی «هیچ امکانی ندارم» هم مثل
                # «نگفته‌ام» رفتار می‌شود و دروازهٔ §8.3 برایش باز نمی‌ماند.
                # این عمدی است: فهرست پیشنهاد خالی، بدترین حالت ممکن است
                # (اصل ۲ §00) و شش پروژهٔ §14.5 همگی لپ‌تاپ را الزامی
                # کرده‌اند. دروازه به‌محض ثبت اولین امکان فعال می‌شود.
                return bool(self.assets)
            case Component.INTEREST:
                return bool(self.interests)
            case Component.TIME:
                return self.weekly_hours is not None
            case Component.STYLE:
                return self.work_style is not None
            case Component.GOAL:
                return self.primary_goal is not None


@dataclass(frozen=True, slots=True)
class Weights:
    """§8.8 — وزن‌های پیش‌فرض. در `app_settings` قابل تنظیم‌اند."""

    skill: float = 0.30
    asset: float = 0.20
    interest: float = 0.20
    time: float = 0.10
    style: float = 0.10
    goal: float = 0.10

    def as_dict(self) -> dict[Component, float]:
        return {
            Component.SKILL: self.skill,
            Component.ASSET: self.asset,
            Component.INTEREST: self.interest,
            Component.TIME: self.time,
            Component.STYLE: self.style,
            Component.GOAL: self.goal,
        }


DEFAULT_WEIGHTS = Weights()


@dataclass(frozen=True, slots=True)
class Reason:
    """یک دلیل آمادهٔ نمایش — §8.10. متن در بک‌اند ساخته می‌شود."""

    type: ReasonType
    polarity: Polarity
    contribution: float
    text: str


@dataclass(frozen=True, slots=True)
class MatchResult:
    """خروجی امتیازدهی یک پروژه برای یک دانشجو."""

    project: ProjectSpec
    score: float
    base_score: float
    breakdown: dict[Component, float]
    weights: dict[Component, float]
    factors: dict[str, float]
    reasons: tuple[Reason, ...] = ()
    is_excluded: bool = False
    exclusion_reason: str | None = None
    is_stretch: bool = False

    @property
    def kind(self) -> ProjectKind:
        return self.project.kind


__all__ = [
    "DEFAULT_INTEREST_LEVEL",
    "DEFAULT_SKILL_LEVEL",
    "DEFAULT_TIME_COMMITMENT_HPW",
    "DEFAULT_WEEKLY_HOURS",
    "DEFAULT_WEIGHTS",
    "EXCLUSION_NOTE_FA",
    "GOAL_TITLE_FA",
    "KIND_TITLE_FA",
    "MAX_LEVEL",
    "MAX_SCORE",
    "MIN_LEVEL",
    "MIN_SCORE",
    "AssetReq",
    "Component",
    "Goal",
    "InterestRef",
    "MatchResult",
    "Polarity",
    "ProjectKind",
    "ProjectSpec",
    "Reason",
    "ReasonType",
    "SkillReq",
    "StudentContext",
    "Verdict",
    "WORK_STYLE_TITLE_FA",
    "Weights",
    "WorkStyle",
]
