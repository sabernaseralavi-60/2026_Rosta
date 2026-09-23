"""0009 — کارآفرینی: کسب‌وکار، تاریخچهٔ مرحله، شاخص، و دعوت به تیم

مرجع: PRD §4.7، §7.7، FR-VEN-01/02، FR-TEAM-03.
وظیفهٔ نقشهٔ راه: M7-02، M7-03، M7-04.

پس از ۰۰۰۸ اجرا می‌شود (ADR-0004). انحراف‌ها از §4.7، همه در ADR-0014:

* `ventures.current_status`، `paused_from_stage`، `stage_changed_at` —
  FR-VEN-01 «وضعیت فعلی» را می‌خواهد؛ بازگشت از `PAUSED` بدون دانستن
  مرحلهٔ پیش از توقف ممکن نیست.
* جدول تازهٔ `venture_stage_changes` — امتیاز `VENTURE_STAGE_UP` برای هر
  ارتقا یک منبع یکتا لازم دارد، و «کی به MVP رسیدیم» خودش داده است.
* `venture_metrics.status`، `reviewed_*` به‌جای `verified_*` — شاخص رد هم
  می‌شود، نه فقط تأیید. قید `owner` «دقیقاً یکی» است، نه «دست‌کم یکی»:
  شاخص پروژهٔ یک کسب‌وکار از راه `projects.venture_id` به آن می‌رسد و
  ثبت دوگانه یعنی شمارش دوگانه.
* جدول تازهٔ `team_invitations` — FR-TEAM-03 و §7.8 «دعوت خودکار به
  عضویت» جدولی در §4 نداشتند.

## ارجاع‌های رو به جلو

`projects.venture_id`، `teams.venture_id` و `team_openings.venture_id` از
۰۰۱۰ و ۰۰۱۱ بی‌قید مانده بودند.

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-23
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID_PK = sa.text("uuidv7()")
NOW = sa.text("now()")
FALSE = sa.text("false")
EMPTY_TEXT_ARRAY = sa.text("'{}'::text[]")

GROWTH_STAGES = ("IDEA", "VALIDATION", "MVP", "FIRST_REVENUE", "GROWTH")
VENTURE_STAGES = (*GROWTH_STAGES, "PAUSED", "CLOSED")
METRIC_KINDS = (
    "CALLS",
    "MEETINGS",
    "LEADS",
    "SALES_COUNT",
    "SALES_AMOUNT",
    "CONTENT_PIECES",
    "CUSTOMERS",
)
METRIC_STATUSES = ("PENDING", "VERIFIED", "REJECTED")
INVITATION_STATUSES = ("PENDING", "ACCEPTED", "DECLINED", "CANCELLED")
INVITATION_SOURCES = ("DIRECT", "IDEA_PROMOTION", "OPENING")

TEMPLATES: tuple[tuple[str, str, str | None, str, tuple[str, ...]], ...] = (
    (
        "TEAM_INVITATION",
        "IN_APP",
        "دعوت به تیم «{{team}}»",
        "{{inviter}} تو را به تیم «{{team}}» دعوت کرد. {{message}}",
        ("inviter", "team", "message"),
    ),
    (
        "TEAM_INVITATION",
        "SMS",
        None,
        "{{inviter}} تو را به تیم «{{team}}» دعوت کرد.",
        ("inviter", "team", "message"),
    ),
    (
        "INVITATION_ACCEPTED",
        "IN_APP",
        "{{invitee}} به تیم پیوست",
        "{{invitee}} دعوتت را پذیرفت و به تیم «{{team}}» پیوست.",
        ("invitee", "team"),
    ),
    (
        "METRIC_REVIEWED",
        "IN_APP",
        "«{{metric}}» {{decision}}",
        "ثبت «{{metric}}» ({{value}}) در «{{owner}}» {{decision}}. {{detail}}",
        ("metric", "value", "owner", "decision", "detail"),
    ),
    (
        "VENTURE_STAGE_CHANGED",
        "IN_APP",
        "«{{venture}}» به مرحلهٔ {{stage}} رسید",
        "کسب‌وکار «{{venture}}» از مرحلهٔ {{from_stage}} به {{stage}} رفت.",
        ("venture", "stage", "from_stage"),
    ),
)


def _in_list(column: str, values: tuple[str, ...]) -> str:
    joined = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({joined})"


def upgrade() -> None:
    _create_ventures()
    _create_stage_changes()
    _create_metrics()
    _create_invitations()
    _attach_forward_references()
    _seed_templates()


def _create_ventures() -> None:
    op.create_table(
        "ventures",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=UUID_PK, nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("pitch", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("problem", sa.Text(), nullable=True),
        sa.Column("target_market", sa.Text(), nullable=True),
        sa.Column("revenue_model", sa.Text(), nullable=True),
        sa.Column("current_status", sa.Text(), nullable=True),
        sa.Column("stage", sa.Text(), server_default=sa.text("'IDEA'"), nullable=False),
        sa.Column("paused_from_stage", sa.Text(), nullable=True),
        sa.Column(
            "stage_changed_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False
        ),
        sa.Column("founder_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("looking_for_cofounder", sa.Boolean(), server_default=FALSE, nullable=False),
        sa.Column(
            "needed_roles",
            postgresql.ARRAY(sa.Text()),
            server_default=EMPTY_TEXT_ARRAY,
            nullable=False,
        ),
        sa.Column("logo_key", sa.Text(), nullable=True),
        sa.Column("origin_idea_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "search_norm",
            sa.Text(),
            sa.Computed("fa_normalize(name || ' ' || pitch)", persisted=True),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ventures"),
        sa.UniqueConstraint("slug", name="uq_ventures_slug"),
        sa.ForeignKeyConstraint(["founder_id"], ["users.id"], name="fk_ventures_founder_id_users"),
        sa.ForeignKeyConstraint(
            ["origin_idea_id"], ["ideas.id"], name="fk_ventures_origin_idea_id_ideas"
        ),
        sa.CheckConstraint(_in_list("stage", VENTURE_STAGES), name="ck_ventures_stage_valid"),
        sa.CheckConstraint(
            "paused_from_stage IS NULL OR " + _in_list("paused_from_stage", GROWTH_STAGES),
            name="ck_ventures_paused_from_stage_valid",
        ),
        sa.CheckConstraint(
            "(stage = 'PAUSED') = (paused_from_stage IS NOT NULL)",
            name="ck_ventures_paused_from_matches",
        ),
        sa.CheckConstraint("length(pitch) BETWEEN 10 AND 280", name="ck_ventures_pitch_length"),
        sa.CheckConstraint("length(name) BETWEEN 2 AND 120", name="ck_ventures_name_length"),
        sa.CheckConstraint(
            "cardinality(needed_roles) <= 10", name="ck_ventures_needed_roles_count"
        ),
    )
    op.execute("CREATE INDEX idx_ventures_search ON ventures USING GIN (search_norm gin_trgm_ops)")
    op.create_index("idx_ventures_founder", "ventures", ["founder_id"])
    op.create_index(
        "idx_ventures_cofounder",
        "ventures",
        ["created_at"],
        postgresql_where=sa.text("looking_for_cofounder AND deleted_at IS NULL"),
    )
    op.execute("SELECT attach_updated_at('ventures')")


def _create_stage_changes() -> None:
    op.create_table(
        "venture_stage_changes",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=UUID_PK, nullable=False),
        sa.Column("venture_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("from_stage", sa.Text(), nullable=False),
        sa.Column("to_stage", sa.Text(), nullable=False),
        sa.Column("changed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_venture_stage_changes"),
        sa.ForeignKeyConstraint(
            ["venture_id"],
            ["ventures.id"],
            name="fk_venture_stage_changes_venture_id_ventures",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["changed_by"], ["users.id"], name="fk_venture_stage_changes_changed_by_users"
        ),
        sa.CheckConstraint(
            _in_list("from_stage", VENTURE_STAGES), name="ck_venture_stage_changes_from_stage_valid"
        ),
        sa.CheckConstraint(
            _in_list("to_stage", VENTURE_STAGES), name="ck_venture_stage_changes_to_stage_valid"
        ),
        sa.CheckConstraint("from_stage <> to_stage", name="ck_venture_stage_changes_stage_changes"),
    )
    op.create_index(
        "idx_venture_stage_changes", "venture_stage_changes", ["venture_id", "created_at"]
    )


def _create_metrics() -> None:
    op.create_table(
        "venture_metrics",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=UUID_PK, nullable=False),
        sa.Column("venture_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("metric", sa.Text(), nullable=False),
        sa.Column("value", sa.BigInteger(), nullable=False),
        sa.Column("occurred_on", sa.Date(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("evidence_file_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.Text(), server_default=sa.text("'PENDING'"), nullable=False),
        sa.Column("reviewed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_venture_metrics"),
        sa.ForeignKeyConstraint(
            ["venture_id"],
            ["ventures.id"],
            name="fk_venture_metrics_venture_id_ventures",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_venture_metrics_project_id_projects",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_venture_metrics_user_id_users"),
        sa.ForeignKeyConstraint(
            ["evidence_file_id"], ["files.id"], name="fk_venture_metrics_evidence_file_id_files"
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by"], ["users.id"], name="fk_venture_metrics_reviewed_by_users"
        ),
        sa.CheckConstraint(
            _in_list("metric", METRIC_KINDS), name="ck_venture_metrics_metric_valid"
        ),
        sa.CheckConstraint(
            _in_list("status", METRIC_STATUSES), name="ck_venture_metrics_status_valid"
        ),
        sa.CheckConstraint("value > 0", name="ck_venture_metrics_value_positive"),
        sa.CheckConstraint(
            "(venture_id IS NOT NULL)::int + (project_id IS NOT NULL)::int = 1",
            name="ck_venture_metrics_owner",
        ),
        sa.CheckConstraint(
            "(status = 'PENDING') = (reviewed_at IS NULL)",
            name="ck_venture_metrics_reviewed_matches_status",
        ),
        sa.CheckConstraint(
            "note IS NULL OR length(note) <= 500", name="ck_venture_metrics_note_length"
        ),
        sa.CheckConstraint(
            "reviewed_by IS NULL OR reviewed_by <> user_id",
            name="ck_venture_metrics_not_self_reviewed",
        ),
    )
    op.create_index(
        "idx_venture_metrics_lookup", "venture_metrics", ["venture_id", "metric", "occurred_on"]
    )
    op.create_index(
        "idx_venture_metrics_project", "venture_metrics", ["project_id", "metric", "occurred_on"]
    )
    op.create_index(
        "idx_venture_metrics_user", "venture_metrics", ["user_id", sa.text("occurred_on DESC")]
    )
    op.create_index(
        "idx_venture_metrics_pending",
        "venture_metrics",
        ["created_at"],
        postgresql_where=sa.text("status = 'PENDING'"),
    )


def _create_invitations() -> None:
    op.create_table(
        "team_invitations",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=UUID_PK, nullable=False),
        sa.Column("team_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("inviter_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("invitee_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("source", sa.Text(), server_default=sa.text("'DIRECT'"), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'PENDING'"), nullable=False),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now() + interval '14 days'"),
            nullable=False,
        ),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_team_invitations"),
        sa.ForeignKeyConstraint(
            ["team_id"], ["teams.id"], name="fk_team_invitations_team_id_teams", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["inviter_id"], ["users.id"], name="fk_team_invitations_inviter_id_users"
        ),
        sa.ForeignKeyConstraint(
            ["invitee_id"], ["users.id"], name="fk_team_invitations_invitee_id_users"
        ),
        sa.ForeignKeyConstraint(
            ["role_id"],
            ["project_roles.id"],
            name="fk_team_invitations_role_id_project_roles",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            _in_list("status", INVITATION_STATUSES), name="ck_team_invitations_status_valid"
        ),
        sa.CheckConstraint(
            _in_list("source", INVITATION_SOURCES), name="ck_team_invitations_source_valid"
        ),
        sa.CheckConstraint("inviter_id <> invitee_id", name="ck_team_invitations_not_self"),
        sa.CheckConstraint(
            "message IS NULL OR length(message) <= 500", name="ck_team_invitations_message_length"
        ),
        sa.CheckConstraint(
            "(status = 'PENDING') = (responded_at IS NULL)",
            name="ck_team_invitations_responded_matches_status",
        ),
    )
    op.create_index(
        "idx_team_invitations_open",
        "team_invitations",
        ["team_id", "invitee_id"],
        unique=True,
        postgresql_where=sa.text("status = 'PENDING'"),
    )
    op.create_index("idx_team_invitations_invitee", "team_invitations", ["invitee_id", "status"])


def _attach_forward_references() -> None:
    """قیدهای `venture_id` در ۰۰۱۰ و ۰۰۱۱ — §4.10."""
    op.create_foreign_key(
        "fk_projects_venture_id_ventures", "projects", "ventures", ["venture_id"], ["id"]
    )
    op.create_index(
        "idx_projects_venture",
        "projects",
        ["venture_id"],
        postgresql_where=sa.text("venture_id IS NOT NULL"),
    )
    op.create_foreign_key(
        "fk_teams_venture_id_ventures",
        "teams",
        "ventures",
        ["venture_id"],
        ["id"],
        ondelete="CASCADE",
    )
    # هر کسب‌وکار یک تیم — مثل پروژه، که تیمش در انتشار ساخته می‌شود.
    op.create_index(
        "idx_teams_venture",
        "teams",
        ["venture_id"],
        unique=True,
        postgresql_where=sa.text("venture_id IS NOT NULL"),
    )
    op.create_foreign_key(
        "fk_team_openings_venture_id_ventures",
        "team_openings",
        "ventures",
        ["venture_id"],
        ["id"],
        ondelete="CASCADE",
    )


def _seed_templates() -> None:
    op.bulk_insert(
        sa.table(
            "message_templates",
            sa.column("code", sa.Text),
            sa.column("channel", sa.Text),
            sa.column("subject", sa.Text),
            sa.column("body", sa.Text),
            sa.column("variables", postgresql.ARRAY(sa.Text)),
        ),
        [
            {
                "code": code,
                "channel": channel,
                "subject": subject,
                "body": body,
                "variables": ["name", "link", *variables],
            }
            for code, channel, subject, body, variables in TEMPLATES
        ],
    )


def downgrade() -> None:
    codes = ", ".join(f"'{code}'" for code in {t[0] for t in TEMPLATES})
    op.execute(f"DELETE FROM message_templates WHERE code IN ({codes})")
    op.drop_constraint("fk_team_openings_venture_id_ventures", "team_openings", type_="foreignkey")
    op.drop_index("idx_teams_venture", table_name="teams")
    op.drop_constraint("fk_teams_venture_id_ventures", "teams", type_="foreignkey")
    op.drop_index("idx_projects_venture", table_name="projects")
    op.drop_constraint("fk_projects_venture_id_ventures", "projects", type_="foreignkey")
    op.drop_table("team_invitations")
    op.drop_table("venture_metrics")
    op.drop_table("venture_stage_changes")
    op.execute("DROP TRIGGER IF EXISTS trg_ventures_updated ON ventures")
    op.drop_table("ventures")
