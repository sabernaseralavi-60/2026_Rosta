"""0011 — تحویل پروژه: مرحله، تحویل‌دادنی، وظیفه، گفتگو، فعالیت، بازتاب، گواهی

مرجع: PRD §4.6 و §4.7 (`team_openings`).
وظیفهٔ نقشهٔ راه: M2-01.

این مهاجرت نیمهٔ دوم هستهٔ پروژه است؛ نیمهٔ اول در ۰۱۰ ساخته شد. جدایی
به این دلیل است که جدول‌های اینجا مستقیم یا غیرمستقیم به `files` وابسته‌اند
و `files` در ۰۰۰۵ ساخته می‌شود.

دو ستون ارجاع رو به جلو دارند و **قیدشان اینجا افزوده نمی‌شود** — همان
الگوی ۰۱۰ و ADR-0004:

| ستون | قید در مهاجرت |
|------|----------------|
| `team_openings.venture_id` | ۰۰۹ کسب‌وکار |
| `team_openings.idea_id` | ۰۰۸ ایده |

دو ستون بیرون از §4.6 افزوده شده‌اند (ADR-0006):

* `deliverables.is_late` — §7.6 ضریب تأخیر ۰.۷ را از «دیر بودن تحویل»
  می‌گیرد. اگر به‌جای ذخیره، هر بار از `submitted_at > milestone.due_on`
  محاسبه شود، جابه‌جا کردن مهلت پس از تحویل گذشته را بازنویسی می‌کند.
  عکسِ لحظهٔ ارسال گرفته می‌شود، مثل `match_score` در ۰۱۰.
* `milestones.approved_at` — لحظهٔ تأیید مرحله؛ بدون آن «تحویل به‌موقع»
  در شاخص سلامت (§7.4) قابل محاسبه نیست.

Revision ID: 0011
Revises: 0005
Create Date: 2026-09-22
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID_PK = sa.text("uuidv7()")
NOW = sa.text("now()")
TRUE = sa.text("true")
FALSE = sa.text("false")
ONE = sa.text("1")
ZERO = sa.text("0")
EMPTY_JSONB_ARRAY = sa.text("'[]'::jsonb")
EMPTY_TEXT_ARRAY = sa.text("'{}'::text[]")
EMPTY_UUID_ARRAY = sa.text("'{}'::uuid[]")
EMPTY_JSONB = sa.text("'{}'::jsonb")

MILESTONE_STATUSES = ("PENDING", "IN_PROGRESS", "SUBMITTED", "APPROVED", "OVERDUE")
OUTPUT_KINDS = ("DOCUMENT", "CODE", "DATA", "MEDIA", "SALES", "MIXED")
DELIVERABLE_STATUSES = (
    "SUBMITTED",
    "UNDER_REVIEW",
    "APPROVED",
    "CHANGES_REQUESTED",
    "REJECTED",
)
TASK_STATUSES = ("TODO", "DOING", "DONE")
CERTIFICATE_KINDS = ("PROJECT", "COURSE", "RESEARCH_LEVEL")
OPENING_STATUSES = ("OPEN", "FILLED", "EXPIRED")


def _in_list(column: str, values: tuple[str, ...]) -> str:
    joined = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({joined})"


def upgrade() -> None:
    # ── مراحل — §7.6 ───────────────────────────────────────────────────
    op.create_table(
        "milestones",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=UUID_PK, nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title_fa", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default=ZERO, nullable=False),
        sa.Column("due_on", sa.Date(), nullable=True),
        sa.Column("points", sa.Numeric(6, 2), server_default=ZERO, nullable=False),
        sa.Column("is_required", sa.Boolean(), server_default=TRUE, nullable=False),
        sa.Column("output_kind", sa.Text(), nullable=True),
        sa.Column(
            "checklist", postgresql.JSONB(), server_default=EMPTY_JSONB_ARRAY, nullable=False
        ),
        sa.Column("status", sa.Text(), server_default=sa.text("'PENDING'"), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_milestones"),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_milestones_project_id_projects",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            _in_list("status", MILESTONE_STATUSES), name="ck_milestones_status_valid"
        ),
        sa.CheckConstraint(
            f"output_kind IS NULL OR {_in_list('output_kind', OUTPUT_KINDS)}",
            name="ck_milestones_output_kind_valid",
        ),
        sa.CheckConstraint("points >= 0", name="ck_milestones_points_not_negative"),
        sa.CheckConstraint(
            "jsonb_typeof(checklist) = 'array'", name="ck_milestones_checklist_is_array"
        ),
        sa.CheckConstraint(
            "(status = 'APPROVED') = (approved_at IS NOT NULL)",
            name="ck_milestones_approved_at_matches_status",
        ),
    )
    op.create_index("idx_milestones_project", "milestones", ["project_id", "sort_order"])
    op.create_index(
        "idx_milestones_due",
        "milestones",
        ["due_on"],
        postgresql_where=sa.text("status IN ('PENDING', 'IN_PROGRESS')"),
    )
    op.execute("SELECT attach_updated_at('milestones')")

    # ── تحویل‌دادنی ────────────────────────────────────────────────────
    op.create_table(
        "deliverables",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=UUID_PK, nullable=False),
        sa.Column("milestone_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("submitter_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), server_default=ONE, nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column(
            "links", postgresql.ARRAY(sa.Text()), server_default=EMPTY_TEXT_ARRAY, nullable=False
        ),
        sa.Column("status", sa.Text(), server_default=sa.text("'SUBMITTED'"), nullable=False),
        sa.Column("is_late", sa.Boolean(), server_default=FALSE, nullable=False),
        sa.Column("score", sa.Numeric(6, 2), nullable=True),
        sa.Column("feedback", sa.Text(), nullable=True),
        sa.Column("rubric_scores", postgresql.JSONB(), nullable=True),
        sa.Column("reviewed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_deliverables"),
        sa.UniqueConstraint(
            "milestone_id", "submitter_id", "version", name="uq_deliverables_version"
        ),
        sa.ForeignKeyConstraint(
            ["milestone_id"],
            ["milestones.id"],
            name="fk_deliverables_milestone_id_milestones",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["submitter_id"], ["users.id"], name="fk_deliverables_submitter_id_users"
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by"], ["users.id"], name="fk_deliverables_reviewed_by_users"
        ),
        sa.CheckConstraint(
            _in_list("status", DELIVERABLE_STATUSES), name="ck_deliverables_status_valid"
        ),
        sa.CheckConstraint("version >= 1", name="ck_deliverables_version_positive"),
        sa.CheckConstraint(
            "score IS NULL OR score >= 0", name="ck_deliverables_score_not_negative"
        ),
        # §7.6 — بازخورد برای «اصلاح کن» و «رد» اجباری است. اعتبارسنجی در
        # سرویس هم هست؛ این سد دوم برای نوشتن مستقیم SQL است.
        sa.CheckConstraint(
            "status NOT IN ('CHANGES_REQUESTED', 'REJECTED')"
            " OR (feedback IS NOT NULL AND length(btrim(feedback)) > 0)",
            name="ck_deliverables_feedback_required_on_rejection",
        ),
        sa.CheckConstraint(
            "(reviewed_at IS NULL) = (reviewed_by IS NULL)",
            name="ck_deliverables_review_fields_together",
        ),
        sa.CheckConstraint(
            "rubric_scores IS NULL OR jsonb_typeof(rubric_scores) = 'object'",
            name="ck_deliverables_rubric_is_object",
        ),
    )
    op.create_index(
        "idx_deliverables_review_queue",
        "deliverables",
        ["status", "submitted_at"],
        postgresql_where=sa.text("status IN ('SUBMITTED', 'UNDER_REVIEW')"),
    )
    op.create_index("idx_deliverables_milestone", "deliverables", ["milestone_id"])

    op.create_table(
        "deliverable_files",
        sa.Column("deliverable_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("file_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.PrimaryKeyConstraint("deliverable_id", "file_id", name="pk_deliverable_files"),
        sa.ForeignKeyConstraint(
            ["deliverable_id"],
            ["deliverables.id"],
            name="fk_deliverable_files_deliverable_id_deliverables",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["file_id"], ["files.id"], name="fk_deliverable_files_file_id_files"
        ),
    )

    # ── تخته وظایف — FR-PRJ-06 ─────────────────────────────────────────
    op.create_table(
        "project_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=UUID_PK, nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("milestone_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("assignee_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.Text(), server_default=sa.text("'TODO'"), nullable=False),
        sa.Column("due_on", sa.Date(), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default=ZERO, nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_project_tasks"),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_project_tasks_project_id_projects",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["milestone_id"],
            ["milestones.id"],
            name="fk_project_tasks_milestone_id_milestones",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["assignee_id"], ["users.id"], name="fk_project_tasks_assignee_id_users"
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name="fk_project_tasks_created_by_users"
        ),
        sa.CheckConstraint(_in_list("status", TASK_STATUSES), name="ck_project_tasks_status_valid"),
        sa.CheckConstraint("length(btrim(title)) > 0", name="ck_project_tasks_title_not_blank"),
    )
    op.create_index(
        "idx_tasks_project_status", "project_tasks", ["project_id", "status", "sort_order"]
    )
    op.create_index(
        "idx_tasks_assignee",
        "project_tasks",
        ["assignee_id"],
        postgresql_where=sa.text("assignee_id IS NOT NULL AND status <> 'DONE'"),
    )
    op.execute("SELECT attach_updated_at('project_tasks')")

    # ── گفتگوی تیمی — FR-PRJ-06 ────────────────────────────────────────
    op.create_table(
        "project_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=UUID_PK, nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("parent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("author_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("file_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_project_messages"),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_project_messages_project_id_projects",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["project_messages.id"],
            name="fk_project_messages_parent_id_project_messages",
        ),
        sa.ForeignKeyConstraint(
            ["author_id"], ["users.id"], name="fk_project_messages_author_id_users"
        ),
        sa.ForeignKeyConstraint(
            ["file_id"], ["files.id"], name="fk_project_messages_file_id_files"
        ),
        sa.CheckConstraint("length(btrim(body)) > 0", name="ck_project_messages_body_not_blank"),
        sa.CheckConstraint("id <> parent_id", name="ck_project_messages_no_self_parent"),
    )
    # نخ فقط یک سطح عمق دارد؛ عمق دوم در لایهٔ سرویس رد می‌شود (§4.6).
    op.create_index(
        "idx_project_messages",
        "project_messages",
        ["project_id", sa.text("created_at DESC")],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "idx_project_messages_thread",
        "project_messages",
        ["parent_id", "created_at"],
        postgresql_where=sa.text("parent_id IS NOT NULL"),
    )

    # ── جریان فعالیت — FR-PRJ-06 ───────────────────────────────────────
    op.create_table(
        "project_activities",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=UUID_PK, nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("entity_type", sa.Text(), nullable=True),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_project_activities"),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_project_activities_project_id_projects",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"], ["users.id"], name="fk_project_activities_actor_id_users"
        ),
    )
    op.create_index(
        "idx_project_activities", "project_activities", ["project_id", sa.text("created_at DESC")]
    )

    # ── بازتاب و ارزیابی همتا — FR-PRJ-08 ──────────────────────────────
    op.create_table(
        "project_reflections",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("learned", sa.Text(), nullable=False),
        sa.Column("challenges", sa.Text(), nullable=True),
        sa.Column("would_do_differently", sa.Text(), nullable=True),
        sa.Column("satisfaction", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("project_id", "user_id", name="pk_project_reflections"),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_project_reflections_project_id_projects",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_project_reflections_user_id_users"
        ),
        sa.CheckConstraint(
            "satisfaction IS NULL OR satisfaction BETWEEN 1 AND 5",
            name="ck_project_reflections_satisfaction_range",
        ),
        sa.CheckConstraint(
            "length(btrim(learned)) > 0", name="ck_project_reflections_learned_not_blank"
        ),
    )

    op.create_table(
        "peer_evaluations",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evaluator_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evaluatee_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("contribution", sa.Integer(), nullable=False),
        sa.Column("reliability", sa.Integer(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint(
            "project_id", "evaluator_id", "evaluatee_id", name="pk_peer_evaluations"
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_peer_evaluations_project_id_projects",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["evaluator_id"], ["users.id"], name="fk_peer_evaluations_evaluator_id_users"
        ),
        sa.ForeignKeyConstraint(
            ["evaluatee_id"], ["users.id"], name="fk_peer_evaluations_evaluatee_id_users"
        ),
        sa.CheckConstraint("evaluator_id <> evaluatee_id", name="ck_peer_evaluations_no_self"),
        sa.CheckConstraint(
            "contribution BETWEEN 1 AND 5", name="ck_peer_evaluations_contribution_range"
        ),
        sa.CheckConstraint(
            "reliability IS NULL OR reliability BETWEEN 1 AND 5",
            name="ck_peer_evaluations_reliability_range",
        ),
    )

    # ── گواهی — FR-PRJ-08، FR-PROF-03 ──────────────────────────────────
    op.create_table(
        "certificates",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=UUID_PK, nullable=False),
        sa.Column("public_code", sa.Text(), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("subject_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title_fa", sa.Text(), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("issued_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), server_default=EMPTY_JSONB, nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_certificates"),
        sa.UniqueConstraint("public_code", name="uq_certificates_public_code"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_certificates_user_id_users"),
        sa.ForeignKeyConstraint(
            ["issued_by"], ["users.id"], name="fk_certificates_issued_by_users"
        ),
        sa.CheckConstraint(_in_list("kind", CERTIFICATE_KINDS), name="ck_certificates_kind_valid"),
        sa.CheckConstraint(
            "jsonb_typeof(metadata) = 'object'", name="ck_certificates_metadata_is_object"
        ),
    )
    op.create_index("idx_certificates_user", "certificates", ["user_id", "kind"])

    # ── آگهی نیاز به هم‌تیمی — FR-TEAM-02 (M7-08) ──────────────────────
    # جدول اینجا ساخته می‌شود چون §4.10 آن را در همین مهاجرت گذاشته است؛
    # مسیرهایش در M7 می‌آیند. `venture_id` و `idea_id` ارجاع رو به جلو
    # دارند و قیدشان در ۰۰۹ و ۰۰۸ افزوده می‌شود.
    op.create_table(
        "team_openings",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=UUID_PK, nullable=False),
        sa.Column("poster_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("venture_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("idea_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "needed_skills",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            server_default=EMPTY_UUID_ARRAY,
            nullable=False,
        ),
        sa.Column("commitment_hpw", sa.Integer(), nullable=True),
        sa.Column("status", sa.Text(), server_default=sa.text("'OPEN'"), nullable=False),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now() + interval '30 days'"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_team_openings"),
        sa.ForeignKeyConstraint(
            ["poster_id"], ["users.id"], name="fk_team_openings_poster_id_users"
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_team_openings_project_id_projects",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            _in_list("status", OPENING_STATUSES), name="ck_team_openings_status_valid"
        ),
        sa.CheckConstraint(
            "commitment_hpw IS NULL OR commitment_hpw BETWEEN 1 AND 60",
            name="ck_team_openings_commitment_range",
        ),
    )
    op.create_index(
        "idx_team_openings_open",
        "team_openings",
        ["expires_at"],
        postgresql_where=sa.text("status = 'OPEN'"),
    )


def downgrade() -> None:
    op.drop_table("team_openings")
    op.drop_table("certificates")
    op.drop_table("peer_evaluations")
    op.drop_table("project_reflections")
    op.drop_table("project_activities")
    op.drop_table("project_messages")
    op.execute("DROP TRIGGER IF EXISTS trg_project_tasks_updated ON project_tasks")
    op.drop_table("project_tasks")
    op.drop_table("deliverable_files")
    op.drop_table("deliverables")
    op.execute("DROP TRIGGER IF EXISTS trg_milestones_updated ON milestones")
    op.drop_table("milestones")
