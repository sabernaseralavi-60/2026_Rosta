"""مدل‌های پروژه — PRD §4.6 و §4.9.

جداول این مرحله: projects، project_required_skills/assets، project_interests،
project_roles، teams، team_members، project_applications،
recommendation_feedback.
مهاجرت متناظر: 0010_projects (ADR-0004).

جداول تحویل (مرحله، تحویل‌دادنی، وظیفه، گفتگو) در M2 افزوده می‌شوند؛ آن‌ها
به `files` وابسته‌اند که هنوز ساخته نشده است.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from silp.db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin

PROJECT_KINDS = ("A_VENTURE", "B_RESEARCH", "C_PROBLEM", "D_PERSONAL")
PROJECT_STATUSES = ("DRAFT", "OPEN", "IN_PROGRESS", "PAUSED", "COMPLETED", "CANCELLED")
WORK_STYLES = ("SOLO", "TEAM", "EITHER")
HEALTH_STATES = ("HEALTHY", "AT_RISK", "STALLED")
MEMBER_STATUSES = ("ACTIVE", "LEFT", "REMOVED")
APPLICATION_STATUSES = ("PENDING", "ACCEPTED", "REJECTED", "WAITLISTED", "WITHDRAWN")
FEEDBACK_VERDICTS = ("NOT_RELEVANT", "INTERESTED", "DISMISSED")

# §11 سند v1 — چهار نوع پروژه با عنوان فارسی برای نمایش و متن دلیل.
KIND_TITLE_FA: dict[str, str] = {
    "A_VENTURE": "کارآفرینی",
    "B_RESEARCH": "پژوهشی",
    "C_PROBLEM": "حل مسئلهٔ واقعی",
    "D_PERSONAL": "پروژهٔ شخصی",
}

DIFFICULTY_TITLE_FA: dict[int, str] = {
    1: "خیلی آسان",
    2: "آسان",
    3: "متوسط",
    4: "دشوار",
    5: "خیلی دشوار",
}


def _in_list(column: str, values: tuple[str, ...]) -> str:
    joined = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({joined})"


class Project(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """واحد اصلی خلق ارزش — §00 «در SILP واحد ارزش پروژه است»."""

    __tablename__ = "projects"

    slug: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    title_fa: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'DRAFT'"))

    lead_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    # ارجاع‌های رو به جلو — قید در مهاجرت ۰۰۶، ۰۰۹ و ۰۰۸ افزوده می‌شود.
    offering_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True))
    venture_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True))
    origin_idea_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True))

    # ── مشخصات تطابق (§08) ─────────────────────────────────────────────
    time_commitment_hpw: Mapped[int | None] = mapped_column(Integer)
    team_size_min: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    team_size_max: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    work_style: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'EITHER'"))
    difficulty: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("3"))

    expected_output: Mapped[str] = mapped_column(Text, nullable=False)
    rewards: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    cover_key: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'::text[]")
    )

    starts_on: Mapped[date | None] = mapped_column(Date)
    deadline_on: Mapped[date | None] = mapped_column(Date)
    applications_close_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    health: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'HEALTHY'"))
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    # ستون تولیدشده: جستجوی فارسی با trigram، نه ILIKE '%…%' (§4.11).
    search_norm: Mapped[str | None] = mapped_column(
        Text, Computed("fa_normalize(title_fa || ' ' || summary)", persisted=True)
    )

    required_skills: Mapped[list[ProjectRequiredSkill]] = relationship(
        back_populates="project", cascade="all, delete-orphan", lazy="selectin"
    )
    required_assets: Mapped[list[ProjectRequiredAsset]] = relationship(
        back_populates="project", cascade="all, delete-orphan", lazy="selectin"
    )
    interests: Mapped[list[ProjectInterest]] = relationship(
        back_populates="project", cascade="all, delete-orphan", lazy="selectin"
    )
    roles: Mapped[list[ProjectRole]] = relationship(
        back_populates="project", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (
        CheckConstraint(_in_list("kind", PROJECT_KINDS), name="kind_valid"),
        CheckConstraint(_in_list("status", PROJECT_STATUSES), name="status_valid"),
        CheckConstraint(_in_list("work_style", WORK_STYLES), name="work_style_valid"),
        CheckConstraint(_in_list("health", HEALTH_STATES), name="health_valid"),
        CheckConstraint("length(summary) <= 280", name="summary_length"),
        CheckConstraint("difficulty BETWEEN 1 AND 5", name="difficulty_range"),
        CheckConstraint(
            "time_commitment_hpw IS NULL OR time_commitment_hpw BETWEEN 1 AND 60",
            name="time_commitment_range",
        ),
        CheckConstraint("team_size_min >= 1", name="team_size_min_positive"),
        CheckConstraint("team_size_max >= team_size_min", name="team_size"),
        CheckConstraint("jsonb_typeof(rewards) = 'object'", name="rewards_is_object"),
        Index("idx_projects_lead", "lead_id"),
        Index("idx_projects_tags", "tags", postgresql_using="gin"),
        Index(
            "idx_projects_open",
            "kind",
            "status",
            postgresql_where=text("status = 'OPEN' AND deleted_at IS NULL"),
        ),
        Index("idx_projects_health", "health", postgresql_where=text("health <> 'HEALTHY'")),
    )

    @property
    def is_open(self) -> bool:
        return self.status == "OPEN" and self.deleted_at is None


class ProjectRequiredSkill(Base):
    __tablename__ = "project_required_skills"

    project_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    skill_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("skills.id"), primary_key=True
    )
    min_level: Mapped[int] = mapped_column(Integer, nullable=False)
    weight: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    # «اگر بلد نیستی، در همین پروژه یاد می‌گیری» — جریمهٔ کمبود را نرم می‌کند.
    is_teachable: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )

    project: Mapped[Project] = relationship(back_populates="required_skills")

    __table_args__ = (
        CheckConstraint("min_level BETWEEN 1 AND 5", name="min_level_range"),
        CheckConstraint("weight BETWEEN 1 AND 3", name="weight_range"),
        Index("idx_project_required_skills_skill", "skill_id"),
    )


class ProjectRequiredAsset(Base):
    """§8.3 — امکان الزامی دروازه است: نداشتنش پروژه را از پیشنهاد حذف می‌کند."""

    __tablename__ = "project_required_assets"

    project_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("assets.id"), primary_key=True
    )
    is_mandatory: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )

    project: Mapped[Project] = relationship(back_populates="required_assets")

    __table_args__ = (
        Index(
            "idx_project_required_assets_mandatory",
            "project_id",
            "asset_id",
            postgresql_where=text("is_mandatory"),
        ),
    )


class ProjectInterest(Base):
    __tablename__ = "project_interests"

    project_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    interest_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("interests.id"), primary_key=True
    )

    project: Mapped[Project] = relationship(back_populates="interests")


class ProjectRole(UUIDPrimaryKeyMixin, Base):
    """نقش کاری درون پروژه — FR-VEN-02. «بازاریاب»، «تولیدکنندهٔ محتوا»."""

    __tablename__ = "project_roles"

    project_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    title_fa: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    slots: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    filled: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    project: Mapped[Project] = relationship(back_populates="roles")

    __table_args__ = (
        CheckConstraint("slots >= 1", name="slots_positive"),
        CheckConstraint("filled BETWEEN 0 AND slots", name="filled_bounded"),
        Index("idx_project_roles_project", "project_id"),
    )

    @property
    def has_opening(self) -> bool:
        return self.filled < self.slots


class Team(UUIDPrimaryKeyMixin, Base):
    """تیم یک پروژه یا یک کسب‌وکار — دقیقاً یکی، نه هر دو، نه هیچ‌کدام."""

    __tablename__ = "teams"

    project_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE")
    )
    # ارجاع رو به جلو — قید در مهاجرت ۰۰۹ افزوده می‌شود.
    venture_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True))
    name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    members: Mapped[list[TeamMember]] = relationship(
        back_populates="team", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (
        CheckConstraint(
            "(project_id IS NOT NULL)::int + (venture_id IS NOT NULL)::int = 1", name="owner"
        ),
        Index("idx_teams_project", "project_id"),
    )


class TeamMember(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "team_members"

    team_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    role_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("project_roles.id")
    )
    is_lead: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'ACTIVE'"))
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    leave_reason: Mapped[str | None] = mapped_column(Text)

    team: Mapped[Team] = relationship(back_populates="members")

    __table_args__ = (
        CheckConstraint(_in_list("status", MEMBER_STATUSES), name="status_valid"),
        CheckConstraint("(status = 'ACTIVE') = (left_at IS NULL)", name="left_at_matches_status"),
        Index(
            "idx_team_member_active",
            "team_id",
            "user_id",
            unique=True,
            postgresql_where=text("status = 'ACTIVE'"),
        ),
        Index("idx_team_members_user", "user_id", "status"),
    )


class ProjectApplication(UUIDPrimaryKeyMixin, Base):
    """درخواست پیوستن — §7.5.

    `match_score` عکس لحظهٔ ارسال است، نه مقدار زندهٔ توصیه‌گر: مدیر پروژه
    باید همان عددی را ببیند که دانشجو هنگام درخواست دیده بود.
    """

    __tablename__ = "project_applications"

    project_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    applicant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    role_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("project_roles.id")
    )
    motivation: Mapped[str] = mapped_column(Text, nullable=False)
    match_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    match_breakdown: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'PENDING'"))
    decision_note: Mapped[str | None] = mapped_column(Text)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id")
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        UniqueConstraint("project_id", "applicant_id", name="applicant"),
        CheckConstraint(_in_list("status", APPLICATION_STATUSES), name="status_valid"),
        CheckConstraint("length(motivation) <= 500", name="motivation_length"),
        CheckConstraint(
            "match_score IS NULL OR match_score BETWEEN 0 AND 100", name="match_score_range"
        ),
        Index(
            "idx_applications_pending", "project_id", postgresql_where=text("status = 'PENDING'")
        ),
        Index("idx_applications_user", "applicant_id", "status"),
    )


class RecommendationFeedback(Base):
    """§4.9 و §8.9 — «این به من نمی‌خورد» / «دیگر نشانم نده» / «فعلاً نه».

    یک ردیف در هر جفت (کاربر، پروژه): آخرین نظر کاربر معتبر است.
    """

    __tablename__ = "recommendation_feedback"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    verdict: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint(_in_list("verdict", FEEDBACK_VERDICTS), name="verdict_valid"),
    )


__all__ = [
    "APPLICATION_STATUSES",
    "DIFFICULTY_TITLE_FA",
    "FEEDBACK_VERDICTS",
    "KIND_TITLE_FA",
    "PROJECT_KINDS",
    "PROJECT_STATUSES",
    "Project",
    "ProjectApplication",
    "ProjectInterest",
    "ProjectRequiredAsset",
    "ProjectRequiredSkill",
    "ProjectRole",
    "RecommendationFeedback",
    "Team",
    "TeamMember",
]
