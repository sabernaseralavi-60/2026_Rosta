"""0010 — پروژه: projects، مشخصات تطابق، تیم، درخواست، بازخورد پیشنهاد

مرجع: PRD §4.6 و §4.9 (`recommendation_feedback`).
وظیفهٔ نقشهٔ راه: M1-08 و بخشی از M2-01.

**پس از ۰۰۴ (نیمرخ) می‌آید، نه پس از ۰۰۹.** موتور توصیه‌گر M1 بدون
جدول `projects` نامزدی برای امتیازدهی ندارد. دلیل کامل و پیامدها در
docs/adr/0004.

سه ستون ارجاع رو به جلو دارند و **قیدشان اینجا افزوده نمی‌شود**:

| ستون | قید در مهاجرت |
|------|----------------|
| `offering_id` | ۰۰۶ آموزش |
| `origin_idea_id` | ۰۰۸ ایده |
| `venture_id` | ۰۰۹ کسب‌وکار |

جداول وابسته به `files` (مرحله، تحویل‌دادنی، وظیفه، گفتگو، گواهی) در
`0011_project_delivery` در M2 ساخته می‌شوند.

Revision ID: 0010
Revises: 0004
Create Date: 2026-09-22
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID_PK = sa.text("uuidv7()")
NOW = sa.text("now()")
TRUE = sa.text("true")
FALSE = sa.text("false")
ONE = sa.text("1")
ZERO = sa.text("0")
EMPTY_JSONB = sa.text("'{}'::jsonb")
EMPTY_ARRAY = sa.text("'{}'::text[]")

PROJECT_KINDS = ("A_VENTURE", "B_RESEARCH", "C_PROBLEM", "D_PERSONAL")
PROJECT_STATUSES = ("DRAFT", "OPEN", "IN_PROGRESS", "PAUSED", "COMPLETED", "CANCELLED")
WORK_STYLES = ("SOLO", "TEAM", "EITHER")
HEALTH_STATES = ("HEALTHY", "AT_RISK", "STALLED")
MEMBER_STATUSES = ("ACTIVE", "LEFT", "REMOVED")
APPLICATION_STATUSES = ("PENDING", "ACCEPTED", "REJECTED", "WAITLISTED", "WITHDRAWN")
FEEDBACK_VERDICTS = ("NOT_RELEVANT", "INTERESTED", "DISMISSED")


def _in_list(column: str, values: tuple[str, ...]) -> str:
    joined = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({joined})"


def upgrade() -> None:
    # ── projects ───────────────────────────────────────────────────────
    op.create_table(
        "projects",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=UUID_PK, nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("title_fa", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'DRAFT'"), nullable=False),
        sa.Column("lead_id", postgresql.UUID(as_uuid=True), nullable=False),
        # ── ارجاع‌های رو به جلو: قید در ۰۰۶، ۰۰۸ و ۰۰۹ افزوده می‌شود ──
        sa.Column("offering_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("venture_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("origin_idea_id", postgresql.UUID(as_uuid=True), nullable=True),
        # ── مشخصات تطابق (§08) ─────────────────────────────────────────
        sa.Column("time_commitment_hpw", sa.Integer(), nullable=True),
        sa.Column("team_size_min", sa.Integer(), server_default=ONE, nullable=False),
        sa.Column("team_size_max", sa.Integer(), server_default=ONE, nullable=False),
        sa.Column("work_style", sa.Text(), server_default=sa.text("'EITHER'"), nullable=False),
        sa.Column("difficulty", sa.Integer(), server_default=sa.text("3"), nullable=False),
        sa.Column("expected_output", sa.Text(), nullable=False),
        sa.Column("rewards", postgresql.JSONB(), server_default=EMPTY_JSONB, nullable=False),
        sa.Column("cover_key", sa.Text(), nullable=True),
        sa.Column("tags", postgresql.ARRAY(sa.Text()), server_default=EMPTY_ARRAY, nullable=False),
        sa.Column("starts_on", sa.Date(), nullable=True),
        sa.Column("deadline_on", sa.Date(), nullable=True),
        sa.Column("applications_close_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("health", sa.Text(), server_default=sa.text("'HEALTHY'"), nullable=False),
        sa.Column(
            "last_activity_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "search_norm",
            sa.Text(),
            sa.Computed("fa_normalize(title_fa || ' ' || summary)", persisted=True),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_projects"),
        sa.UniqueConstraint("slug", name="uq_projects_slug"),
        sa.ForeignKeyConstraint(["lead_id"], ["users.id"], name="fk_projects_lead_id_users"),
        sa.CheckConstraint(_in_list("kind", PROJECT_KINDS), name="ck_projects_kind_valid"),
        sa.CheckConstraint(_in_list("status", PROJECT_STATUSES), name="ck_projects_status_valid"),
        sa.CheckConstraint(
            _in_list("work_style", WORK_STYLES), name="ck_projects_work_style_valid"
        ),
        sa.CheckConstraint(_in_list("health", HEALTH_STATES), name="ck_projects_health_valid"),
        sa.CheckConstraint("length(summary) <= 280", name="ck_projects_summary_length"),
        sa.CheckConstraint("difficulty BETWEEN 1 AND 5", name="ck_projects_difficulty_range"),
        sa.CheckConstraint(
            "time_commitment_hpw IS NULL OR time_commitment_hpw BETWEEN 1 AND 60",
            name="ck_projects_time_commitment_range",
        ),
        sa.CheckConstraint("team_size_min >= 1", name="ck_projects_team_size_min_positive"),
        sa.CheckConstraint("team_size_max >= team_size_min", name="ck_projects_team_size"),
        sa.CheckConstraint(
            "jsonb_typeof(rewards) = 'object'", name="ck_projects_rewards_is_object"
        ),
    )
    op.execute("CREATE INDEX idx_projects_search ON projects USING GIN (search_norm gin_trgm_ops)")
    op.create_index(
        "idx_projects_open",
        "projects",
        ["kind", "status"],
        postgresql_where=sa.text("status = 'OPEN' AND deleted_at IS NULL"),
    )
    op.create_index("idx_projects_tags", "projects", ["tags"], postgresql_using="gin")
    op.create_index(
        "idx_projects_health",
        "projects",
        ["health"],
        postgresql_where=sa.text("health <> 'HEALTHY'"),
    )
    op.create_index("idx_projects_lead", "projects", ["lead_id"])
    op.execute("SELECT attach_updated_at('projects')")

    # ── مشخصات تطابق (§8.2 تا §8.4) ────────────────────────────────────
    op.create_table(
        "project_required_skills",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("skill_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("min_level", sa.Integer(), nullable=False),
        sa.Column("weight", sa.Integer(), server_default=ONE, nullable=False),
        sa.Column("is_teachable", sa.Boolean(), server_default=FALSE, nullable=False),
        sa.PrimaryKeyConstraint("project_id", "skill_id", name="pk_project_required_skills"),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_project_required_skills_project_id_projects",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["skill_id"], ["skills.id"], name="fk_project_required_skills_skill_id_skills"
        ),
        sa.CheckConstraint(
            "min_level BETWEEN 1 AND 5", name="ck_project_required_skills_min_level_range"
        ),
        sa.CheckConstraint(
            "weight BETWEEN 1 AND 3", name="ck_project_required_skills_weight_range"
        ),
    )
    op.create_index("idx_project_required_skills_skill", "project_required_skills", ["skill_id"])

    op.create_table(
        "project_required_assets",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("is_mandatory", sa.Boolean(), server_default=FALSE, nullable=False),
        sa.PrimaryKeyConstraint("project_id", "asset_id", name="pk_project_required_assets"),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_project_required_assets_project_id_projects",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["asset_id"], ["assets.id"], name="fk_project_required_assets_asset_id_assets"
        ),
    )
    # کوئری نامزد §8.12 روی امکانات الزامی NOT EXISTS می‌زند.
    op.create_index(
        "idx_project_required_assets_mandatory",
        "project_required_assets",
        ["project_id", "asset_id"],
        postgresql_where=sa.text("is_mandatory"),
    )

    op.create_table(
        "project_interests",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("interest_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.PrimaryKeyConstraint("project_id", "interest_id", name="pk_project_interests"),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_project_interests_project_id_projects",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["interest_id"], ["interests.id"], name="fk_project_interests_interest_id_interests"
        ),
    )

    # ── نقش‌های کاری درون پروژه — FR-VEN-02 ─────────────────────────────
    op.create_table(
        "project_roles",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=UUID_PK, nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title_fa", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("slots", sa.Integer(), server_default=ONE, nullable=False),
        sa.Column("filled", sa.Integer(), server_default=ZERO, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_project_roles"),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_project_roles_project_id_projects",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("slots >= 1", name="ck_project_roles_slots_positive"),
        sa.CheckConstraint("filled BETWEEN 0 AND slots", name="ck_project_roles_filled_bounded"),
    )
    op.create_index("idx_project_roles_project", "project_roles", ["project_id"])

    # ── تیم و عضویت ────────────────────────────────────────────────────
    # `venture_id` هم ارجاع رو به جلوست و قیدش در ۰۰۹ افزوده می‌شود؛ قید
    # «دقیقاً یک مالک» اما همین حالا برقرار است.
    op.create_table(
        "teams",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=UUID_PK, nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("venture_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_teams"),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name="fk_teams_project_id_projects", ondelete="CASCADE"
        ),
        sa.CheckConstraint(
            "(project_id IS NOT NULL)::int + (venture_id IS NOT NULL)::int = 1",
            name="ck_teams_owner",
        ),
    )
    op.create_index("idx_teams_project", "teams", ["project_id"])

    op.create_table(
        "team_members",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=UUID_PK, nullable=False),
        sa.Column("team_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("is_lead", sa.Boolean(), server_default=FALSE, nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'ACTIVE'"), nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("left_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("leave_reason", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_team_members"),
        sa.ForeignKeyConstraint(
            ["team_id"], ["teams.id"], name="fk_team_members_team_id_teams", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_team_members_user_id_users"),
        sa.ForeignKeyConstraint(
            ["role_id"], ["project_roles.id"], name="fk_team_members_role_id_project_roles"
        ),
        sa.CheckConstraint(
            _in_list("status", MEMBER_STATUSES), name="ck_team_members_status_valid"
        ),
        sa.CheckConstraint(
            "(status = 'ACTIVE') = (left_at IS NULL)", name="ck_team_members_left_at_matches_status"
        ),
    )
    op.create_index(
        "idx_team_member_active",
        "team_members",
        ["team_id", "user_id"],
        unique=True,
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )
    op.create_index("idx_team_members_user", "team_members", ["user_id", "status"])

    # ── درخواست پیوستن ─────────────────────────────────────────────────
    op.create_table(
        "project_applications",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=UUID_PK, nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("applicant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("motivation", sa.Text(), nullable=False),
        # عکس‌برداری از امتیاز تطابق در لحظهٔ ارسال — §7.5
        sa.Column("match_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("match_breakdown", postgresql.JSONB(), nullable=True),
        sa.Column("status", sa.Text(), server_default=sa.text("'PENDING'"), nullable=False),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column("decided_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_project_applications"),
        sa.UniqueConstraint("project_id", "applicant_id", name="uq_project_applications_applicant"),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_project_applications_project_id_projects",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["applicant_id"], ["users.id"], name="fk_project_applications_applicant_id_users"
        ),
        sa.ForeignKeyConstraint(
            ["role_id"], ["project_roles.id"], name="fk_project_applications_role_id_project_roles"
        ),
        sa.ForeignKeyConstraint(
            ["decided_by"], ["users.id"], name="fk_project_applications_decided_by_users"
        ),
        sa.CheckConstraint(
            _in_list("status", APPLICATION_STATUSES), name="ck_project_applications_status_valid"
        ),
        sa.CheckConstraint(
            "length(motivation) <= 500", name="ck_project_applications_motivation_length"
        ),
        sa.CheckConstraint(
            "match_score IS NULL OR match_score BETWEEN 0 AND 100",
            name="ck_project_applications_match_score_range",
        ),
    )
    op.create_index(
        "idx_applications_pending",
        "project_applications",
        ["project_id"],
        postgresql_where=sa.text("status = 'PENDING'"),
    )
    op.create_index("idx_applications_user", "project_applications", ["applicant_id", "status"])

    # ── بازخورد پیشنهاد — §4.9، ضرایب §8.9 ──────────────────────────────
    # §4.10 این جدول را در ۰۱۴ گذاشته بود؛ چون ضرایب f_dismissed و
    # f_interested بخشی از موتور M1 هستند، اینجا ساخته می‌شود (ADR-0004).
    op.create_table(
        "recommendation_feedback",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("verdict", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("user_id", "project_id", name="pk_recommendation_feedback"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_recommendation_feedback_user_id_users",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_recommendation_feedback_project_id_projects",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            _in_list("verdict", FEEDBACK_VERDICTS), name="ck_recommendation_feedback_verdict_valid"
        ),
    )


def downgrade() -> None:
    op.drop_table("recommendation_feedback")
    op.drop_table("project_applications")
    op.drop_table("team_members")
    op.drop_table("teams")
    op.drop_table("project_roles")
    op.drop_table("project_interests")
    op.drop_table("project_required_assets")
    op.drop_table("project_required_skills")
    op.execute("DROP TRIGGER IF EXISTS trg_projects_updated ON projects")
    op.drop_table("projects")
