"""0014 — پژوهش و تیم: مسیر چهارسطحی، خروجی، بانک موضوع، آگهی هم‌تیمی

مرجع: PRD §4.7، FR-RES-01/02/03، FR-TEAM-02/03، §7.11.
وظیفهٔ نقشهٔ راه: M7-05 تا M7-08.

پس از ۰۰۰۹ اجرا می‌شود (ADR-0004: ترتیب را `down_revision` تعیین می‌کند).
انحراف‌ها از §4.7، همه در ADR-0015:

* `research_tracks.deliverable_id` حذف شد و جدول تازهٔ
  `research_submissions` جایش آمد — تحویل‌دادنی به مرحلهٔ پروژه بسته است
  (`milestone_id NOT NULL`) و مسیر پژوهش پروژه ندارد.
* `research_outputs` ستون‌های راستی‌آزمایی گرفت (`verified_stage`،
  `verified_quartile`، `review_*`) — امتیاز `OUTPUT_*` از ادعای نویسنده
  نمی‌آید، همان اصل ADR-0014 برای شاخص فروش.
* `research_topics` وضعیت `PROPOSED` (پیشنهاد دانشجو، منبع امتیاز
  `TOPIC_PROPOSED`)، ستون `last_activity_at` (ساعت بی‌تحرکی رزرو) و
  ایندکس یکتای «یک رزرو باز برای هر نفر» گرفت.
* `team_openings`: «منقضی» دیگر وضعیت ذخیره‌شده نیست (همان استدلال دعوت در
  ADR-0014)؛ `CLOSED` جایش آمد. `role_id`، `filled_at`، `updated_at` و قید
  «دقیقاً یکی از پروژه و کسب‌وکار» افزوده شد.
* جدول تازهٔ `opening_applications` — FR-TEAM-03 «درخواست پیوستن از
  آگهی» جدولی نداشت و `project_applications` مال پروژه است.

Revision ID: 0014
Revises: 0009
Create Date: 2026-09-23
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID_PK = sa.text("uuidv7()")
NOW = sa.text("now()")
EMPTY_TEXT_ARRAY = sa.text("'{}'::text[]")
EMPTY_JSONB = sa.text("'{}'::jsonb")

TRACK_STATUSES = ("IN_PROGRESS", "SUBMITTED", "APPROVED")
SUBMISSION_STATUSES = ("SUBMITTED", "APPROVED", "CHANGES_REQUESTED")
OUTPUT_KINDS = ("JOURNAL", "CONFERENCE", "THESIS", "REPORT", "PREPRINT")
OUTPUT_STATUSES = (
    "DRAFT",
    "SUBMITTED",
    "UNDER_REVIEW",
    "REVISION",
    "ACCEPTED",
    "PUBLISHED",
    "REJECTED",
)
OUTPUT_STAGES = ("SUBMITTED", "ACCEPTED", "PUBLISHED")
QUARTILES = ("Q1", "Q2", "Q3", "Q4", "NA")
REVIEW_STATUSES = ("NONE", "PENDING", "VERIFIED", "REJECTED")
TOPIC_STATUSES = ("PROPOSED", "OPEN", "RESERVED", "TAKEN", "CLOSED")
OPENING_STATUSES = ("OPEN", "FILLED", "CLOSED")
OLD_OPENING_STATUSES = ("OPEN", "FILLED", "EXPIRED")
OPENING_APPLICATION_STATUSES = ("PENDING", "ACCEPTED", "DECLINED", "WITHDRAWN")

# (کد، کانال، عنوان، متن، متغیرها) — قواعد نگارش §14.7، مانند ۰۰۰۹.
# هم‌ترازی با `silp.domain.notifications.catalog` را
# `test_seeded_templates_match_catalog` می‌پاید.
TEMPLATES: tuple[tuple[str, str, str | None, str, tuple[str, ...]], ...] = (
    (
        "RESEARCH_SUBMITTED",
        "IN_APP",
        "تحویل تازهٔ پژوهش از {{student}}",
        "{{student}} تحویل سطح {{level}} مسیر پژوهش را برای بررسی فرستاد.",
        ("student", "level"),
    ),
    (
        "RESEARCH_REVIEWED",
        "IN_APP",
        "سطح {{level}} پژوهشت {{decision}}",
        "تحویل سطح {{level}} مسیر پژوهشت {{decision}}. {{detail}}",
        ("level", "decision", "detail"),
    ),
    (
        "RESEARCH_REVIEWED",
        "SMS",
        None,
        "تحویل سطح {{level}} پژوهشت {{decision}}.",
        ("level", "decision", "detail"),
    ),
    (
        "TOPIC_REVIEWED",
        "IN_APP",
        "پیشنهاد موضوع «{{topic}}» {{decision}}",
        "پیشنهاد موضوع پژوهشی «{{topic}}» {{decision}}. {{detail}}",
        ("topic", "decision", "detail"),
    ),
    (
        "TOPIC_RELEASE_WARNING",
        "IN_APP",
        "رزرو «{{topic}}» به‌زودی آزاد می‌شود",
        "رزرو موضوع «{{topic}}» تا {{days}} روز دیگر آزاد می‌شود. اگر هنوز رویش کار"
        " می‌کنی، تحویل سطح بعدی مسیر پژوهشت را بفرست.",
        ("topic", "days"),
    ),
    (
        "TOPIC_RELEASED",
        "IN_APP",
        "رزرو «{{topic}}» آزاد شد",
        "موضوع «{{topic}}» پس از {{days}} روز بی‌تحرکی آزاد شد و دیگران می‌توانند" " رزروش کنند.",
        ("topic", "days"),
    ),
    (
        "OUTPUT_REVIEWED",
        "IN_APP",
        "«{{title}}» {{decision}}",
        "وضعیت خروجی پژوهشی «{{title}}» {{decision}}. {{detail}}",
        ("title", "decision", "detail"),
    ),
    (
        "OPENING_MATCH",
        "IN_APP",
        "«{{team}}» دنبال {{opening}} است",
        "تیم «{{team}}» برای «{{opening}}» هم‌تیمی می‌خواهد و به مهارت {{skills}} تو" " نیاز دارد.",
        ("opening", "team", "skills"),
    ),
    (
        "OPENING_APPLIED",
        "IN_APP",
        "درخواست تازه برای «{{opening}}»",
        "{{applicant}} برای آگهی «{{opening}}» درخواست پیوستن فرستاد.",
        ("applicant", "opening"),
    ),
    (
        "OPENING_DECIDED",
        "IN_APP",
        "درخواستت برای «{{opening}}» {{decision}}",
        "درخواستت برای «{{opening}}» در تیم «{{team}}» {{decision}}. {{detail}}",
        ("opening", "team", "decision", "detail"),
    ),
    (
        "OPENING_DECIDED",
        "SMS",
        None,
        "درخواستت برای «{{opening}}» {{decision}}.",
        ("opening", "team", "decision", "detail"),
    ),
    (
        "OPENING_EXPIRED",
        "IN_APP",
        "آگهی «{{opening}}» منقضی شد",
        "مهلت آگهی «{{opening}}» تمام شد. اگر هنوز هم‌تیمی لازم داری، تمدیدش کن.",
        ("opening",),
    ),
)


def _in_list(column: str, values: tuple[str, ...]) -> str:
    joined = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({joined})"


def upgrade() -> None:
    _create_topics()
    _create_tracks()
    _create_submissions()
    _create_outputs()
    _reshape_openings()
    _create_opening_applications()
    _seed_templates()


def _create_topics() -> None:
    op.create_table(
        "research_topics",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=UUID_PK, nullable=False),
        sa.Column("proposer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("prerequisites", sa.Text(), nullable=True),
        sa.Column("level", sa.Integer(), nullable=True),
        sa.Column("status", sa.Text(), server_default=sa.text("'OPEN'"), nullable=False),
        sa.Column("reserved_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reserved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column(
            "search_norm",
            sa.Text(),
            sa.Computed("fa_normalize(title || ' ' || description)", persisted=True),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_research_topics"),
        sa.ForeignKeyConstraint(
            ["proposer_id"], ["users.id"], name="fk_research_topics_proposer_id_users"
        ),
        sa.ForeignKeyConstraint(
            ["reserved_by"], ["users.id"], name="fk_research_topics_reserved_by_users"
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by"], ["users.id"], name="fk_research_topics_reviewed_by_users"
        ),
        sa.CheckConstraint(
            _in_list("status", TOPIC_STATUSES), name="ck_research_topics_status_valid"
        ),
        sa.CheckConstraint(
            "level IS NULL OR level BETWEEN 1 AND 4", name="ck_research_topics_level_range"
        ),
        sa.CheckConstraint(
            "length(title) BETWEEN 5 AND 200", name="ck_research_topics_title_length"
        ),
        sa.CheckConstraint(
            "length(description) BETWEEN 20 AND 4000",
            name="ck_research_topics_description_length",
        ),
        sa.CheckConstraint(
            "prerequisites IS NULL OR length(prerequisites) <= 1000",
            name="ck_research_topics_prerequisites_length",
        ),
        sa.CheckConstraint(
            "(status IN ('RESERVED', 'TAKEN')) = (reserved_by IS NOT NULL)",
            name="ck_research_topics_reservation_matches_status",
        ),
        sa.CheckConstraint(
            "(reserved_by IS NULL) = (reserved_at IS NULL)"
            " AND (reserved_by IS NULL) = (last_activity_at IS NULL)",
            name="ck_research_topics_reservation_fields_together",
        ),
    )
    op.execute(
        "CREATE INDEX idx_topics_search ON research_topics USING GIN (search_norm gin_trgm_ops)"
    )
    op.create_index("idx_topics_status", "research_topics", ["status", sa.text("created_at DESC")])
    op.create_index(
        "idx_topics_reservation_expiry",
        "research_topics",
        ["last_activity_at"],
        postgresql_where=sa.text("status = 'RESERVED'"),
    )
    op.create_index(
        "idx_topics_one_reservation",
        "research_topics",
        ["reserved_by"],
        unique=True,
        postgresql_where=sa.text("status = 'RESERVED'"),
    )
    op.execute("SELECT attach_updated_at('research_topics')")


def _create_tracks() -> None:
    op.create_table(
        "research_tracks",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'IN_PROGRESS'"), nullable=False),
        sa.Column("mentor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.PrimaryKeyConstraint("user_id", "level", name="pk_research_tracks"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_research_tracks_user_id_users",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["mentor_id"], ["users.id"], name="fk_research_tracks_mentor_id_users"
        ),
        sa.ForeignKeyConstraint(
            ["approved_by"], ["users.id"], name="fk_research_tracks_approved_by_users"
        ),
        sa.CheckConstraint("level BETWEEN 1 AND 4", name="ck_research_tracks_level_range"),
        sa.CheckConstraint(
            _in_list("status", TRACK_STATUSES), name="ck_research_tracks_status_valid"
        ),
        sa.CheckConstraint(
            "(status = 'APPROVED') = (approved_at IS NOT NULL)",
            name="ck_research_tracks_approved_matches_status",
        ),
        sa.CheckConstraint(
            "(approved_at IS NULL) = (approved_by IS NULL)",
            name="ck_research_tracks_approval_fields_together",
        ),
    )


def _create_submissions() -> None:
    op.create_table(
        "research_submissions",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=UUID_PK, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("topic_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column(
            "links", postgresql.ARRAY(sa.Text()), server_default=EMPTY_TEXT_ARRAY, nullable=False
        ),
        sa.Column("evidence", postgresql.JSONB(), server_default=EMPTY_JSONB, nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'SUBMITTED'"), nullable=False),
        sa.Column("feedback", sa.Text(), nullable=True),
        sa.Column("reviewed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_research_submissions"),
        sa.ForeignKeyConstraint(
            ["user_id", "level"],
            ["research_tracks.user_id", "research_tracks.level"],
            name="fk_research_submissions_track",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["topic_id"],
            ["research_topics.id"],
            name="fk_research_submissions_topic_id_research_topics",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by"], ["users.id"], name="fk_research_submissions_reviewed_by_users"
        ),
        sa.UniqueConstraint("user_id", "level", "version", name="uq_research_submissions_version"),
        sa.CheckConstraint(
            _in_list("status", SUBMISSION_STATUSES), name="ck_research_submissions_status_valid"
        ),
        sa.CheckConstraint("version >= 1", name="ck_research_submissions_version_positive"),
        sa.CheckConstraint(
            "length(summary) BETWEEN 30 AND 4000", name="ck_research_submissions_summary_length"
        ),
        sa.CheckConstraint("cardinality(links) <= 10", name="ck_research_submissions_links_count"),
        sa.CheckConstraint(
            "jsonb_typeof(evidence) = 'object'", name="ck_research_submissions_evidence_is_object"
        ),
        sa.CheckConstraint(
            "status <> 'CHANGES_REQUESTED' OR length(btrim(coalesce(feedback, ''))) > 0",
            name="ck_research_submissions_feedback_required",
        ),
        sa.CheckConstraint(
            "(status = 'SUBMITTED') = (reviewed_at IS NULL)",
            name="ck_research_submissions_reviewed_matches_status",
        ),
        sa.CheckConstraint(
            "(reviewed_at IS NULL) = (reviewed_by IS NULL)",
            name="ck_research_submissions_review_fields_together",
        ),
        sa.CheckConstraint(
            "reviewed_by IS NULL OR reviewed_by <> user_id",
            name="ck_research_submissions_not_self_reviewed",
        ),
    )
    op.create_index(
        "idx_research_submissions_open",
        "research_submissions",
        ["user_id", "level"],
        unique=True,
        postgresql_where=sa.text("status = 'SUBMITTED'"),
    )
    op.create_index(
        "idx_research_submissions_queue",
        "research_submissions",
        ["submitted_at"],
        postgresql_where=sa.text("status = 'SUBMITTED'"),
    )

    op.create_table(
        "research_submission_files",
        sa.Column("submission_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("file_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.PrimaryKeyConstraint("submission_id", "file_id", name="pk_research_submission_files"),
        sa.ForeignKeyConstraint(
            ["submission_id"],
            ["research_submissions.id"],
            name="fk_research_submission_files_submission_id_research_submissions",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["file_id"], ["files.id"], name="fk_research_submission_files_file_id_files"
        ),
    )


def _create_outputs() -> None:
    op.create_table(
        "research_outputs",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=UUID_PK, nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("authors", sa.Text(), nullable=False),
        sa.Column("venue", sa.Text(), nullable=True),
        sa.Column("quartile", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), server_default=sa.text("'DRAFT'"), nullable=False),
        sa.Column("doi", sa.Text(), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("file_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("submitted_on", sa.Date(), nullable=True),
        sa.Column("published_on", sa.Date(), nullable=True),
        sa.Column("verified_stage", sa.Text(), nullable=True),
        sa.Column("verified_quartile", sa.Text(), nullable=True),
        sa.Column("review_status", sa.Text(), server_default=sa.text("'NONE'"), nullable=False),
        sa.Column("reviewed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_research_outputs"),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["users.id"], name="fk_research_outputs_owner_id_users"
        ),
        sa.ForeignKeyConstraint(
            ["file_id"], ["files.id"], name="fk_research_outputs_file_id_files"
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_research_outputs_project_id_projects",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by"], ["users.id"], name="fk_research_outputs_reviewed_by_users"
        ),
        sa.CheckConstraint(_in_list("kind", OUTPUT_KINDS), name="ck_research_outputs_kind_valid"),
        sa.CheckConstraint(
            _in_list("status", OUTPUT_STATUSES), name="ck_research_outputs_status_valid"
        ),
        sa.CheckConstraint(
            f"quartile IS NULL OR {_in_list('quartile', QUARTILES)}",
            name="ck_research_outputs_quartile_valid",
        ),
        sa.CheckConstraint(
            f"verified_stage IS NULL OR {_in_list('verified_stage', OUTPUT_STAGES)}",
            name="ck_research_outputs_verified_stage_valid",
        ),
        sa.CheckConstraint(
            f"verified_quartile IS NULL OR {_in_list('verified_quartile', QUARTILES)}",
            name="ck_research_outputs_verified_quartile_valid",
        ),
        sa.CheckConstraint(
            _in_list("review_status", REVIEW_STATUSES),
            name="ck_research_outputs_review_status_valid",
        ),
        sa.CheckConstraint(
            "length(title) BETWEEN 3 AND 300", name="ck_research_outputs_title_length"
        ),
        sa.CheckConstraint(
            "length(authors) BETWEEN 2 AND 500", name="ck_research_outputs_authors_length"
        ),
        sa.CheckConstraint(
            "url IS NULL OR length(url) <= 500", name="ck_research_outputs_url_length"
        ),
        sa.CheckConstraint(
            r"doi IS NULL OR doi ~ '^10\.\d{4,9}/\S+$'", name="ck_research_outputs_doi_format"
        ),
        sa.CheckConstraint(
            "review_status <> 'REJECTED' OR length(btrim(coalesce(review_note, ''))) > 0",
            name="ck_research_outputs_rejection_has_note",
        ),
        sa.CheckConstraint(
            "reviewed_by IS NULL OR reviewed_by <> owner_id",
            name="ck_research_outputs_not_self_reviewed",
        ),
    )
    op.create_index(
        "idx_research_outputs_owner", "research_outputs", ["owner_id", sa.text("created_at DESC")]
    )
    op.create_index(
        "idx_research_outputs_pending",
        "research_outputs",
        ["updated_at"],
        postgresql_where=sa.text("review_status = 'PENDING'"),
    )
    op.execute("SELECT attach_updated_at('research_outputs')")


def _reshape_openings() -> None:
    """`team_openings` از ۰۰۱۱ — هنوز مسیری نداشت، پس ردیفی هم ندارد."""
    op.execute("UPDATE team_openings SET status = 'CLOSED' WHERE status = 'EXPIRED'")
    op.drop_constraint("ck_team_openings_status_valid", "team_openings", type_="check")
    op.create_check_constraint(
        "ck_team_openings_status_valid", "team_openings", _in_list("status", OPENING_STATUSES)
    )
    op.add_column(
        "team_openings", sa.Column("role_id", postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.add_column(
        "team_openings", sa.Column("filled_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "team_openings",
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
    )
    op.create_foreign_key(
        "fk_team_openings_role_id_project_roles",
        "team_openings",
        "project_roles",
        ["role_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        "ck_team_openings_owner",
        "team_openings",
        "(project_id IS NOT NULL)::int + (venture_id IS NOT NULL)::int = 1",
    )
    op.create_check_constraint(
        "ck_team_openings_filled_matches_status",
        "team_openings",
        "(status = 'FILLED') = (filled_at IS NOT NULL)",
    )
    op.create_check_constraint(
        "ck_team_openings_title_length", "team_openings", "length(title) BETWEEN 3 AND 120"
    )
    op.create_check_constraint(
        "ck_team_openings_description_length",
        "team_openings",
        "length(description) BETWEEN 10 AND 2000",
    )
    op.create_check_constraint(
        "ck_team_openings_needed_skills_count", "team_openings", "cardinality(needed_skills) <= 10"
    )
    op.create_index(
        "idx_team_openings_project",
        "team_openings",
        ["project_id"],
        postgresql_where=sa.text("project_id IS NOT NULL"),
    )
    op.create_index(
        "idx_team_openings_venture",
        "team_openings",
        ["venture_id"],
        postgresql_where=sa.text("venture_id IS NOT NULL"),
    )
    op.execute("SELECT attach_updated_at('team_openings')")


def _create_opening_applications() -> None:
    op.create_table(
        "opening_applications",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=UUID_PK, nullable=False),
        sa.Column("opening_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("applicant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'PENDING'"), nullable=False),
        sa.Column("decided_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_opening_applications"),
        sa.ForeignKeyConstraint(
            ["opening_id"],
            ["team_openings.id"],
            name="fk_opening_applications_opening_id_team_openings",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["applicant_id"], ["users.id"], name="fk_opening_applications_applicant_id_users"
        ),
        sa.ForeignKeyConstraint(
            ["decided_by"], ["users.id"], name="fk_opening_applications_decided_by_users"
        ),
        sa.UniqueConstraint("opening_id", "applicant_id", name="uq_opening_applications_applicant"),
        sa.CheckConstraint(
            _in_list("status", OPENING_APPLICATION_STATUSES),
            name="ck_opening_applications_status_valid",
        ),
        sa.CheckConstraint(
            "length(btrim(message)) BETWEEN 1 AND 500",
            name="ck_opening_applications_message_length",
        ),
        sa.CheckConstraint(
            "(status = 'PENDING') = (decided_at IS NULL)",
            name="ck_opening_applications_decided_matches_status",
        ),
    )
    op.create_index(
        "idx_opening_applications_pending",
        "opening_applications",
        ["opening_id"],
        postgresql_where=sa.text("status = 'PENDING'"),
    )
    op.create_index(
        "idx_opening_applications_user", "opening_applications", ["applicant_id", "status"]
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

    op.drop_table("opening_applications")

    op.execute("DROP TRIGGER IF EXISTS trg_team_openings_updated ON team_openings")
    op.drop_index("idx_team_openings_venture", table_name="team_openings")
    op.drop_index("idx_team_openings_project", table_name="team_openings")
    for name in (
        "ck_team_openings_needed_skills_count",
        "ck_team_openings_description_length",
        "ck_team_openings_title_length",
        "ck_team_openings_filled_matches_status",
        "ck_team_openings_owner",
    ):
        op.drop_constraint(name, "team_openings", type_="check")
    op.drop_constraint(
        "fk_team_openings_role_id_project_roles", "team_openings", type_="foreignkey"
    )
    op.drop_column("team_openings", "updated_at")
    op.drop_column("team_openings", "filled_at")
    op.drop_column("team_openings", "role_id")
    op.drop_constraint("ck_team_openings_status_valid", "team_openings", type_="check")
    op.execute("UPDATE team_openings SET status = 'EXPIRED' WHERE status = 'CLOSED'")
    op.create_check_constraint(
        "ck_team_openings_status_valid", "team_openings", _in_list("status", OLD_OPENING_STATUSES)
    )

    op.execute("DROP TRIGGER IF EXISTS trg_research_outputs_updated ON research_outputs")
    op.drop_table("research_outputs")
    op.drop_table("research_submission_files")
    op.drop_table("research_submissions")
    op.drop_table("research_tracks")
    op.execute("DROP TRIGGER IF EXISTS trg_research_topics_updated ON research_topics")
    op.drop_table("research_topics")
