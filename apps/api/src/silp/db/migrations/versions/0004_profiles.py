"""0004 — نیمرخ: profiles, profile_skills/assets/interests, survey_versions

مرجع: PRD §4.3.
وظیفهٔ نقشهٔ راه: M1-01.

پس از ۰۰۳ (طبقه‌بندی‌ها) می‌آید.

کد ملی با `pgcrypto` رمز می‌شود و جداگانه هش می‌گردد (§11): هش برای بررسی
یکتایی بدون رمزگشایی است. هیچ کوئری‌ای نباید روی `national_id_enc` فیلتر
کند.

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-22
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID_PK = sa.text("uuidv7()")
NOW = sa.text("now()")
TRUE = sa.text("true")
FALSE = sa.text("false")
ZERO = sa.text("0")
EMPTY_JSONB = sa.text("'{}'::jsonb")

GENDERS = ("M", "F", "UNDISCLOSED")
DEGREE_LEVELS = ("ASSOCIATE", "BACHELOR", "MASTER", "PHD", "OTHER")
WORK_STYLES = ("SOLO", "TEAM", "EITHER")
GOALS = ("GRADE", "LEARNING", "PUBLICATION", "INCOME", "STARTUP", "EMPLOYMENT")
EVIDENCE_TYPES = ("DELIVERABLE", "QUIZ", "MANUAL")

# §FR-PROF-01 — چهار گام ارزیابی.
TOTAL_SURVEY_STEPS = 4


def _in_list(column: str, values: tuple[str, ...]) -> str:
    joined = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({joined})"


def upgrade() -> None:
    # ── profiles ───────────────────────────────────────────────────────
    op.create_table(
        "profiles",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("first_name", sa.Text(), nullable=False),
        sa.Column("last_name", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=True),
        sa.Column("national_id_enc", postgresql.BYTEA(), nullable=True),
        sa.Column("national_id_hash", sa.Text(), nullable=True),
        sa.Column("birth_year", sa.Integer(), nullable=True),
        sa.Column("gender", sa.Text(), nullable=True),
        sa.Column("avatar_key", sa.Text(), nullable=True),
        sa.Column("bio", sa.Text(), nullable=True),
        # اطلاعات دانشگاهی
        sa.Column("university_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("field_of_study", sa.Text(), nullable=True),
        sa.Column("degree_level", sa.Text(), nullable=True),
        sa.Column("student_number", sa.Text(), nullable=True),
        sa.Column("entry_year", sa.Integer(), nullable=True),
        # ترجیحات کاری — گام ۴
        sa.Column("work_style", sa.Text(), nullable=True),
        sa.Column("primary_goal", sa.Text(), nullable=True),
        sa.Column("weekly_hours", sa.Integer(), nullable=True),
        # حریم خصوصی
        sa.Column("is_public", sa.Boolean(), server_default=FALSE, nullable=False),
        sa.Column(
            "privacy_settings", postgresql.JSONB(), server_default=EMPTY_JSONB, nullable=False
        ),
        sa.Column("show_in_leaderboard", sa.Boolean(), server_default=TRUE, nullable=False),
        sa.Column("survey_completed_steps", sa.Integer(), server_default=ZERO, nullable=False),
        sa.Column("survey_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("user_id", name="pk_profiles"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_profiles_user_id_users", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["university_id"],
            ["universities.id"],
            name="fk_profiles_university_id_universities",
        ),
        sa.UniqueConstraint("national_id_hash", name="uq_profiles_national_id_hash"),
        sa.CheckConstraint(
            "birth_year IS NULL OR birth_year BETWEEN 1300 AND 1420",
            name="ck_profiles_birth_year_jalali",
        ),
        sa.CheckConstraint(
            f"gender IS NULL OR {_in_list('gender', GENDERS)}", name="ck_profiles_gender_valid"
        ),
        sa.CheckConstraint(
            f"degree_level IS NULL OR {_in_list('degree_level', DEGREE_LEVELS)}",
            name="ck_profiles_degree_level_valid",
        ),
        sa.CheckConstraint(
            f"work_style IS NULL OR {_in_list('work_style', WORK_STYLES)}",
            name="ck_profiles_work_style_valid",
        ),
        sa.CheckConstraint(
            f"primary_goal IS NULL OR {_in_list('primary_goal', GOALS)}",
            name="ck_profiles_primary_goal_valid",
        ),
        sa.CheckConstraint(
            "weekly_hours IS NULL OR weekly_hours BETWEEN 0 AND 80",
            name="ck_profiles_weekly_hours_range",
        ),
        sa.CheckConstraint("bio IS NULL OR length(bio) <= 500", name="ck_profiles_bio_length"),
        sa.CheckConstraint(
            f"survey_completed_steps BETWEEN 0 AND {TOTAL_SURVEY_STEPS}",
            name="ck_profiles_survey_steps_range",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(privacy_settings) = 'object'", name="ck_profiles_privacy_is_object"
        ),
    )
    op.create_index(
        "idx_profiles_public", "profiles", ["is_public"], postgresql_where=sa.text("is_public")
    )
    op.create_index("idx_profiles_university", "profiles", ["university_id"])
    op.execute("SELECT attach_updated_at('profiles')")

    # ── profile_skills ─────────────────────────────────────────────────
    op.create_table(
        "profile_skills",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("skill_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("verified_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("evidence_type", sa.Text(), nullable=True),
        sa.Column("evidence_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("user_id", "skill_id", name="pk_profile_skills"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_profile_skills_user_id_users", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["skill_id"], ["skills.id"], name="fk_profile_skills_skill_id_skills"
        ),
        sa.ForeignKeyConstraint(
            ["verified_by"], ["users.id"], name="fk_profile_skills_verified_by_users"
        ),
        sa.CheckConstraint("level BETWEEN 1 AND 5", name="ck_profile_skills_level_range"),
        sa.CheckConstraint(
            f"evidence_type IS NULL OR {_in_list('evidence_type', EVIDENCE_TYPES)}",
            name="ck_profile_skills_evidence_type_valid",
        ),
        # FR-PROF-04: تأیید بر اساس شواهد است. تأییدکننده بدون زمان تأیید
        # یا برعکس، یعنی نوشتن ناقص در سرویس.
        sa.CheckConstraint(
            "(verified_by IS NULL) = (verified_at IS NULL)",
            name="ck_profile_skills_verification_complete",
        ),
    )
    op.create_index(
        "idx_profile_skills_lookup", "profile_skills", ["skill_id", sa.text("level DESC")]
    )

    # ── profile_assets ─────────────────────────────────────────────────
    op.create_table(
        "profile_assets",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("user_id", "asset_id", name="pk_profile_assets"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_profile_assets_user_id_users", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["asset_id"], ["assets.id"], name="fk_profile_assets_asset_id_assets"
        ),
    )
    op.create_index("idx_profile_assets_lookup", "profile_assets", ["asset_id"])

    # ── profile_interests ──────────────────────────────────────────────
    op.create_table(
        "profile_interests",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("interest_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("user_id", "interest_id", name="pk_profile_interests"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_profile_interests_user_id_users", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["interest_id"], ["interests.id"], name="fk_profile_interests_interest_id_interests"
        ),
        sa.CheckConstraint("level BETWEEN 1 AND 5", name="ck_profile_interests_level_range"),
    )
    op.create_index(
        "idx_profile_interests_lookup", "profile_interests", ["interest_id", sa.text("level DESC")]
    )

    # ── profile_survey_versions ────────────────────────────────────────
    # چرا تاریخچه؟ تحلیل رشد مهارت دانشجو در طول تحصیل، خروجی پژوهشی است.
    op.create_table(
        "profile_survey_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=UUID_PK, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_profile_survey_versions"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_profile_survey_versions_user_id_users",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(snapshot) = 'object'",
            name="ck_profile_survey_versions_snapshot_is_object",
        ),
    )
    op.create_index(
        "idx_survey_versions_user",
        "profile_survey_versions",
        ["user_id", sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.drop_table("profile_survey_versions")
    op.drop_table("profile_interests")
    op.drop_table("profile_assets")
    op.drop_table("profile_skills")
    op.execute("DROP TRIGGER IF EXISTS trg_profiles_updated ON profiles")
    op.drop_table("profiles")
