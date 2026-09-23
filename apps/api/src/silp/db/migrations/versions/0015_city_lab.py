"""0015 — آزمایشگاه شهر هوشمند: الگوی گردش‌کار، مسئول مرحله، شاهد، نسخهٔ فایل مدل

مرجع: PRD §7.9، FR-CITY-01، §9.5 (`CITY_BUILDER`).
وظیفهٔ نقشهٔ راه: M7-09.

پس از ۰۰۱۴ اجرا می‌شود. همه در ADR-0016:

* `projects.workflow` و `workflow_completed_at` — الگوی ثابت هشت‌مرحله‌ای
  فقط برای پروژهٔ نوع C؛ زمان کامل شدنش منبع واقعیت نشان «شهرساز» است.
* `milestones.workflow_stage` و `owner_id` — شمارهٔ مرحله در الگو و
  «مسئول» هر مرحله (FR-CITY-01). مرحلهٔ الگو همیشه مسئول دارد.
* `deliverables.evidence` — شاهد ساختاریافتهٔ مرحله (محدوده، جدول
  راستی‌آزمایی، سناریوها، …).
* جدول تازهٔ `project_artifact_versions` — نسخه‌بندی `.osm`، `.net.xml` و
  `.rou.xml` در کتابخانهٔ پروژه.

Revision ID: 0015
Revises: 0014
Create Date: 2026-09-23
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID_PK = sa.text("uuidv7()")
NOW = sa.text("now()")

ARTIFACT_KINDS = ("OSM", "SUMO_NET", "SUMO_ROUTES")

# (کد، کانال، عنوان، متن، متغیرها) — قواعد نگارش §14.7، مانند ۰۰۱۴.
# هم‌ترازی با `silp.domain.notifications.catalog` را
# `test_seeded_templates_match_catalog` می‌پاید.
TEMPLATES: tuple[tuple[str, str, str | None, str, tuple[str, ...]], ...] = (
    (
        "MILESTONE_OWNER_ASSIGNED",
        "IN_APP",
        "مسئول «{{milestone}}» شدی",
        "{{assigner}} تو را مسئول مرحلهٔ «{{milestone}}» در پروژهٔ «{{project}}» کرد.",
        ("project", "milestone", "assigner"),
    ),
    (
        "CITY_STAGE_UNLOCKED",
        "IN_APP",
        "مرحلهٔ {{number}} «{{project}}» باز شد",
        "مرحلهٔ قبل تأیید شد و «{{milestone}}» اکنون تحویل می‌پذیرد. مسئول این" " مرحله تویی.",
        ("project", "milestone", "number"),
    ),
    (
        "CITY_WORKFLOW_COMPLETED",
        "IN_APP",
        "گردش‌کار «{{project}}» کامل شد",
        "هر هشت مرحلهٔ گردش‌کار شهر هوشمند «{{project}}» تأیید شد. حالا می‌توانید" " پروژه را ببندید.",
        ("project",),
    ),
)


def _in_list(column: str, values: tuple[str, ...]) -> str:
    joined = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({joined})"


def upgrade() -> None:
    _extend_projects()
    _extend_milestones()
    _extend_deliverables()
    _create_artifact_versions()
    _seed_templates()


def _extend_projects() -> None:
    op.add_column("projects", sa.Column("workflow", sa.Text(), nullable=True))
    op.add_column(
        "projects", sa.Column("workflow_completed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_check_constraint(
        "ck_projects_workflow_valid", "projects", "workflow IS NULL OR workflow IN ('CITY')"
    )
    op.create_check_constraint(
        "ck_projects_workflow_kind", "projects", "workflow IS NULL OR kind = 'C_PROBLEM'"
    )
    op.create_check_constraint(
        "ck_projects_workflow_completed_needs_workflow",
        "projects",
        "workflow_completed_at IS NULL OR workflow IS NOT NULL",
    )
    op.create_index(
        "idx_projects_workflow",
        "projects",
        ["workflow"],
        postgresql_where=sa.text("workflow IS NOT NULL"),
    )


def _extend_milestones() -> None:
    op.add_column("milestones", sa.Column("workflow_stage", sa.Integer(), nullable=True))
    op.add_column("milestones", sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_milestones_owner_id_users", "milestones", "users", ["owner_id"], ["id"]
    )
    op.create_check_constraint(
        "ck_milestones_workflow_stage_range",
        "milestones",
        "workflow_stage IS NULL OR workflow_stage BETWEEN 1 AND 8",
    )
    op.create_check_constraint(
        "ck_milestones_workflow_stage_has_owner",
        "milestones",
        "workflow_stage IS NULL OR owner_id IS NOT NULL",
    )
    op.create_index(
        "idx_milestones_workflow_stage",
        "milestones",
        ["project_id", "workflow_stage"],
        unique=True,
        postgresql_where=sa.text("workflow_stage IS NOT NULL"),
    )
    op.create_index(
        "idx_milestones_owner",
        "milestones",
        ["owner_id"],
        postgresql_where=sa.text("owner_id IS NOT NULL"),
    )


def _extend_deliverables() -> None:
    op.add_column(
        "deliverables",
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_check_constraint(
        "ck_deliverables_evidence_is_object",
        "deliverables",
        "evidence IS NULL OR jsonb_typeof(evidence) = 'object'",
    )


def _create_artifact_versions() -> None:
    op.create_table(
        "project_artifact_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=UUID_PK, nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("artifact", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("file_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("deliverable_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_project_artifact_versions"),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_project_artifact_versions_project_id_projects",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["file_id"], ["files.id"], name="fk_project_artifact_versions_file_id_files"
        ),
        sa.ForeignKeyConstraint(
            ["deliverable_id"],
            ["deliverables.id"],
            name="fk_project_artifact_versions_deliverable_id_deliverables",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name="fk_project_artifact_versions_created_by_users"
        ),
        sa.UniqueConstraint(
            "project_id", "artifact", "version", name="uq_project_artifact_versions_version"
        ),
        sa.UniqueConstraint(
            "deliverable_id", "artifact", name="uq_project_artifact_versions_deliverable"
        ),
        sa.CheckConstraint(
            _in_list("artifact", ARTIFACT_KINDS),
            name="ck_project_artifact_versions_artifact_valid",
        ),
        sa.CheckConstraint("version >= 1", name="ck_project_artifact_versions_version_positive"),
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
    codes = ", ".join(f"'{code}'" for code in sorted({t[0] for t in TEMPLATES}))
    op.execute(f"DELETE FROM message_templates WHERE code IN ({codes})")
    op.execute(f"DELETE FROM notifications WHERE kind IN ({codes})")

    op.drop_table("project_artifact_versions")

    op.drop_constraint("ck_deliverables_evidence_is_object", "deliverables", type_="check")
    op.drop_column("deliverables", "evidence")

    op.drop_index("idx_milestones_owner", table_name="milestones")
    op.drop_index("idx_milestones_workflow_stage", table_name="milestones")
    op.drop_constraint("ck_milestones_workflow_stage_has_owner", "milestones", type_="check")
    op.drop_constraint("ck_milestones_workflow_stage_range", "milestones", type_="check")
    op.drop_constraint("fk_milestones_owner_id_users", "milestones", type_="foreignkey")
    op.drop_column("milestones", "owner_id")
    op.drop_column("milestones", "workflow_stage")

    op.drop_index("idx_projects_workflow", table_name="projects")
    op.drop_constraint("ck_projects_workflow_completed_needs_workflow", "projects", type_="check")
    op.drop_constraint("ck_projects_workflow_kind", "projects", type_="check")
    op.drop_constraint("ck_projects_workflow_valid", "projects", type_="check")
    op.drop_column("projects", "workflow_completed_at")
    op.drop_column("projects", "workflow")
