"""مدل‌های نیمرخ و ارزیابی — PRD §4.3.

جداول: profiles, profile_skills, profile_assets, profile_interests,
profile_survey_versions.
مهاجرت متناظر: 0004_profiles.

کد ملی هرگز به‌صورت خام ذخیره نمی‌شود (§11): مقدار رمزشده در
`national_id_enc` و هش یک‌طرفه در `national_id_hash` می‌نشیند. هیچ کوئری‌ای
نباید روی ستون رمزشده فیلتر کند — یکتایی با هش بررسی می‌شود.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from silp.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from silp.domain.recommendation.schemas import GOAL_TITLE_FA as _GOAL_TITLES
from silp.domain.recommendation.schemas import WORK_STYLE_TITLE_FA as _WORK_STYLE_TITLES
from silp.models.taxonomy import University

GENDERS = ("M", "F", "UNDISCLOSED")
DEGREE_LEVELS = ("ASSOCIATE", "BACHELOR", "MASTER", "PHD", "OTHER")
WORK_STYLES = ("SOLO", "TEAM", "EITHER")
GOALS = ("GRADE", "LEARNING", "PUBLICATION", "INCOME", "STARTUP", "EMPLOYMENT")
EVIDENCE_TYPES = ("DELIVERABLE", "QUIZ", "MANUAL")

TOTAL_SURVEY_STEPS = 4

DEGREE_TITLE_FA: dict[str, str] = {
    "ASSOCIATE": "کاردانی",
    "BACHELOR": "کارشناسی",
    "MASTER": "کارشناسی ارشد",
    "PHD": "دکتری",
    "OTHER": "سایر",
}

# عنوان فارسی سبک کار و هدف در `silp.domain.recommendation.schemas` تعریف
# شده — همان متنی که موتور توصیه‌گر در دلیل §8.10 به کار می‌برد. اینجا با
# کلید رشته‌ای بازتاب می‌شود تا لایهٔ API بدون تبدیل Enum از آن بخواند.
WORK_STYLE_TITLE_FA: dict[str, str] = {k.value: v for k, v in _WORK_STYLE_TITLES.items()}
GOAL_TITLE_FA: dict[str, str] = {k.value: v for k, v in _GOAL_TITLES.items()}


def _in_list(column: str, values: tuple[str, ...]) -> str:
    joined = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({joined})"


class Profile(TimestampMixin, Base):
    """§4.3 — کلید اصلی، خودِ `user_id` است؛ رابطهٔ یک‌به‌یک با کاربر."""

    __tablename__ = "profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    first_name: Mapped[str] = mapped_column(Text, nullable=False)
    last_name: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str | None] = mapped_column(Text)

    national_id_enc: Mapped[bytes | None] = mapped_column(LargeBinary)
    national_id_hash: Mapped[str | None] = mapped_column(Text, unique=True)

    birth_year: Mapped[int | None] = mapped_column(Integer)
    gender: Mapped[str | None] = mapped_column(Text)
    avatar_key: Mapped[str | None] = mapped_column(Text)
    bio: Mapped[str | None] = mapped_column(Text)

    # ── اطلاعات دانشگاهی ───────────────────────────────────────────────
    university_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("universities.id")
    )
    field_of_study: Mapped[str | None] = mapped_column(Text)
    degree_level: Mapped[str | None] = mapped_column(Text)
    student_number: Mapped[str | None] = mapped_column(Text)
    entry_year: Mapped[int | None] = mapped_column(Integer)

    # ── ترجیحات کاری — گام ۴ ارزیابی ───────────────────────────────────
    work_style: Mapped[str | None] = mapped_column(Text)
    primary_goal: Mapped[str | None] = mapped_column(Text)
    weekly_hours: Mapped[int | None] = mapped_column(Integer)

    # ── حریم خصوصی — FR-PROF-03 ────────────────────────────────────────
    is_public: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    privacy_settings: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    show_in_leaderboard: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )

    survey_completed_steps: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    survey_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    university: Mapped[University | None] = relationship(lazy="joined")

    __table_args__ = (
        CheckConstraint(
            "birth_year IS NULL OR birth_year BETWEEN 1300 AND 1420", name="birth_year_jalali"
        ),
        CheckConstraint(f"gender IS NULL OR {_in_list('gender', GENDERS)}", name="gender_valid"),
        CheckConstraint(
            f"degree_level IS NULL OR {_in_list('degree_level', DEGREE_LEVELS)}",
            name="degree_level_valid",
        ),
        CheckConstraint(
            f"work_style IS NULL OR {_in_list('work_style', WORK_STYLES)}", name="work_style_valid"
        ),
        CheckConstraint(
            f"primary_goal IS NULL OR {_in_list('primary_goal', GOALS)}", name="primary_goal_valid"
        ),
        CheckConstraint(
            "weekly_hours IS NULL OR weekly_hours BETWEEN 0 AND 80", name="weekly_hours_range"
        ),
        CheckConstraint("bio IS NULL OR length(bio) <= 500", name="bio_length"),
        CheckConstraint(
            f"survey_completed_steps BETWEEN 0 AND {TOTAL_SURVEY_STEPS}", name="survey_steps_range"
        ),
        CheckConstraint("jsonb_typeof(privacy_settings) = 'object'", name="privacy_is_object"),
        Index("idx_profiles_public", "is_public", postgresql_where=text("is_public")),
        Index("idx_profiles_university", "university_id"),
    )

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def public_name(self) -> str:
        """نامی که در رابط کاربری دیده می‌شود."""
        return self.display_name or self.full_name


class ProfileSkill(Base):
    """پاسخ گام ۱. نبود ردیف یعنی «پاسخ نداده»، نه «سطح ۱».

    تمایز مهم است: §8.2 نبود پاسخ را سطح ۱ فرض می‌کند ولی §8.8 آن را در
    محاسبهٔ کامل بودن نیمرخ به حساب نمی‌آورد.
    """

    __tablename__ = "profile_skills"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    skill_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("skills.id"), primary_key=True
    )
    level: Mapped[int] = mapped_column(Integer, nullable=False)

    # FR-PROF-04 — تأیید استاد، با ضریب ۱.۲۵ در §8.2
    verified_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id")
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    evidence_type: Mapped[str | None] = mapped_column(Text)
    evidence_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True))

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint("level BETWEEN 1 AND 5", name="level_range"),
        CheckConstraint(
            f"evidence_type IS NULL OR {_in_list('evidence_type', EVIDENCE_TYPES)}",
            name="evidence_type_valid",
        ),
        CheckConstraint(
            "(verified_by IS NULL) = (verified_at IS NULL)", name="verification_complete"
        ),
        Index("idx_profile_skills_lookup", "skill_id", text("level DESC")),
    )

    @property
    def is_verified(self) -> bool:
        return self.verified_at is not None


class ProfileAsset(Base):
    """پاسخ گام ۲. نبود ردیف یعنی «ندارد» — اینجا برخلاف مهارت، صریح است."""

    __tablename__ = "profile_assets"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("assets.id"), primary_key=True
    )
    note: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (Index("idx_profile_assets_lookup", "asset_id"),)


class ProfileInterest(Base):
    """پاسخ گام ۳. نبود ردیف یعنی «پاسخ نداده» = سطح خنثی ۳ در §8.4."""

    __tablename__ = "profile_interests"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    interest_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("interests.id"), primary_key=True
    )
    level: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        CheckConstraint("level BETWEEN 1 AND 5", name="level_range"),
        Index("idx_profile_interests_lookup", "interest_id", text("level DESC")),
    )


class ProfileSurveyVersion(UUIDPrimaryKeyMixin, Base):
    """عکس کامل ارزیابی پیش از هر ویرایش — FR-PROF-01.

    رشد مهارت دانشجو در طول تحصیل، خودش یک خروجی پژوهشی است؛ بدون این
    جدول، هر ویرایش تاریخ را پاک می‌کند.
    """

    __tablename__ = "profile_survey_versions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint("jsonb_typeof(snapshot) = 'object'", name="snapshot_is_object"),
        Index("idx_survey_versions_user", "user_id", text("created_at DESC")),
    )


__all__ = [
    "DEGREE_LEVELS",
    "DEGREE_TITLE_FA",
    "GOALS",
    "GOAL_TITLE_FA",
    "TOTAL_SURVEY_STEPS",
    "WORK_STYLES",
    "WORK_STYLE_TITLE_FA",
    "Profile",
    "ProfileAsset",
    "ProfileInterest",
    "ProfileSkill",
    "ProfileSurveyVersion",
]
