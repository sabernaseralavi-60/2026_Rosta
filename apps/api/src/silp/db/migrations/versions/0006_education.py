"""0006 — آموزش: نیم‌سال، درس، ارائه، ثبت‌نام، هفته، منبع، حضور، اعلان

مرجع: PRD §4.4.
وظیفهٔ نقشهٔ راه: M3-01.

علاوه بر جدول‌های §4.4، پنج جدول افزوده می‌شود:

| جدول | چرا | ADR |
|------|-----|-----|
| `course_materials` | کتابخانهٔ ماندگار درس، همگام با پوشهٔ `Courses/` | ۰۰۰۸ |
| `week_materials` | پیوند هفته ← مادهٔ کتابخانه | ۰۰۰۸ |
| `subscription_plans` | طرح اشتراک ماهانه | ۰۰۰۹ |
| `subscriptions` | اشتراک فعال کاربر (رسید، نه تراکنش) | ۰۰۰۹ |
| `material_access_events` | رویداد `resource_accessed` — FR-EDU-03 | ۰۰۰۹ |

و دو قید ارجاع رو به جلو که §4.10 به همین مهاجرت سپرده بود:

* `projects.offering_id` → `course_offerings(id)`
* `announcements.project_id` → `projects(id)` — اینجا مستقیم در
  `create_table` می‌آید، چون `projects` از ۰۱۰ موجود است.

Revision ID: 0006
Revises: 0011
Create Date: 2026-09-22
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID_PK = sa.text("uuidv7()")
NOW = sa.text("now()")
TRUE = sa.text("true")
FALSE = sa.text("false")
ZERO = sa.text("0")
EMPTY_JSONB = sa.text("'{}'::jsonb")
EMPTY_TEXT_ARRAY = sa.text("'{}'::text[]")

DEGREE_LEVELS = ("BACHELOR", "MASTER", "PHD", "PUBLIC")
OFFERING_STATUSES = ("DRAFT", "OPEN", "IN_PROGRESS", "CLOSED", "ARCHIVED")
ENROLLMENT_STATUSES = ("PENDING", "ACTIVE", "DROPPED", "COMPLETED", "REJECTED")
WEEK_STATUSES = ("DRAFT", "PUBLISHED", "ARCHIVED")
RESOURCE_KINDS = ("PDF", "VIDEO", "LINK", "SLIDE", "DATASET", "CODE", "OTHER")
PROGRESS_STATUSES = ("NOT_STARTED", "IN_PROGRESS", "COMPLETED")
ATTENDANCE_STATUSES = ("PRESENT", "ABSENT", "LATE", "EXCUSED")
ANNOUNCEMENT_PRIORITIES = ("NORMAL", "IMPORTANT", "URGENT")
MATERIAL_KINDS = (
    "BOOK",
    "NOTE",
    "SLIDE",
    "VIDEO",
    "PODCAST",
    "DATASET",
    "CODE",
    "QUESTION_BANK",
    "LINK",
    "OTHER",
)
MATERIAL_STATUSES = ("DRAFT", "PUBLISHED", "ARCHIVED")
ACCESS_TIERS = ("PUBLIC", "SUBSCRIBER", "ENROLLED")
PLAN_SCOPES = ("ALL_COURSES", "SINGLE_COURSE")
SUBSCRIPTION_STATUSES = ("PENDING", "ACTIVE", "EXPIRED", "CANCELLED")

MAX_WEEK_NUMBER = 17


def _in_list(column: str, values: tuple[str, ...]) -> str:
    joined = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({joined})"


def upgrade() -> None:
    _create_terms()
    _create_courses()
    _create_offerings()
    _create_enrollments()
    _create_weeks_and_resources()
    _create_attendance_and_announcements()
    _create_library()
    _create_subscriptions()
    _attach_forward_references()


# ── نیم‌سال ────────────────────────────────────────────────────────────
def _create_terms() -> None:
    op.create_table(
        "terms",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=UUID_PK, nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("title_fa", sa.Text(), nullable=False),
        sa.Column("starts_on", sa.Date(), nullable=False),
        sa.Column("ends_on", sa.Date(), nullable=False),
        sa.Column("is_current", sa.Boolean(), server_default=FALSE, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_terms"),
        sa.UniqueConstraint("code", name="uq_terms_code"),
        sa.CheckConstraint("ends_on > starts_on", name="ck_terms_date_order"),
    )
    # حداکثر یک نیم‌سال جاری — قید در ایندکس است، نه در اپلیکیشن.
    op.create_index(
        "idx_terms_single_current",
        "terms",
        ["is_current"],
        unique=True,
        postgresql_where=sa.text("is_current"),
    )


# ── درس ────────────────────────────────────────────────────────────────
def _create_courses() -> None:
    op.create_table(
        "courses",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=UUID_PK, nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("title_fa", sa.Text(), nullable=False),
        sa.Column("title_en", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("degree_level", sa.Text(), nullable=True),
        sa.Column("credits", sa.Integer(), nullable=True),
        sa.Column("cover_key", sa.Text(), nullable=True),
        sa.Column("is_public", sa.Boolean(), server_default=FALSE, nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=TRUE, nullable=False),
        # ── ADR-0008 و ADR-0009 ────────────────────────────────────────
        sa.Column("source_dir", sa.Text(), nullable=True),
        sa.Column(
            "default_access_tier",
            sa.Text(),
            server_default=sa.text("'SUBSCRIBER'"),
            nullable=False,
        ),
        sa.Column(
            "topics", postgresql.ARRAY(sa.Text()), server_default=EMPTY_TEXT_ARRAY, nullable=False
        ),
        sa.Column(
            "title_norm",
            sa.Text(),
            sa.Computed("fa_normalize(title_fa)", persisted=True),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_courses"),
        sa.UniqueConstraint("code", name="uq_courses_code"),
        sa.UniqueConstraint("slug", name="uq_courses_slug"),
        sa.CheckConstraint(
            f"degree_level IS NULL OR {_in_list('degree_level', DEGREE_LEVELS)}",
            name="ck_courses_degree_level_valid",
        ),
        sa.CheckConstraint(
            _in_list("default_access_tier", ACCESS_TIERS),
            name="ck_courses_default_access_tier_valid",
        ),
        sa.CheckConstraint(
            "credits IS NULL OR credits BETWEEN 1 AND 12", name="ck_courses_credits_range"
        ),
    )
    op.execute("CREATE INDEX idx_courses_search ON courses USING GIN (title_norm gin_trgm_ops)")
    # یک پوشه، یک درس — همگام‌سازی نباید بتواند دو درس به یک پوشه ببندد.
    op.create_index(
        "idx_courses_source_dir",
        "courses",
        ["source_dir"],
        unique=True,
        postgresql_where=sa.text("source_dir IS NOT NULL"),
    )
    op.execute("SELECT attach_updated_at('courses')")


# ── ارائه ──────────────────────────────────────────────────────────────
def _create_offerings() -> None:
    op.create_table(
        "course_offerings",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=UUID_PK, nullable=False),
        sa.Column("course_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("term_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("instructor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("capacity", sa.Integer(), nullable=True),
        sa.Column("enrollment_code", sa.Text(), nullable=True),
        sa.Column("requires_approval", sa.Boolean(), server_default=FALSE, nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'DRAFT'"), nullable=False),
        sa.Column("grading_policy", postgresql.JSONB(), server_default=EMPTY_JSONB, nullable=False),
        sa.Column("syllabus_key", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_course_offerings"),
        sa.UniqueConstraint(
            "course_id",
            "term_id",
            "instructor_id",
            name="uq_course_offerings_course_term_instructor",
        ),
        sa.ForeignKeyConstraint(
            ["course_id"], ["courses.id"], name="fk_course_offerings_course_id_courses"
        ),
        sa.ForeignKeyConstraint(
            ["term_id"], ["terms.id"], name="fk_course_offerings_term_id_terms"
        ),
        sa.ForeignKeyConstraint(
            ["instructor_id"], ["users.id"], name="fk_course_offerings_instructor_id_users"
        ),
        sa.CheckConstraint(
            _in_list("status", OFFERING_STATUSES), name="ck_course_offerings_status_valid"
        ),
        sa.CheckConstraint(
            "capacity IS NULL OR capacity > 0", name="ck_course_offerings_capacity_positive"
        ),
        sa.CheckConstraint(
            "jsonb_typeof(grading_policy) = 'object'",
            name="ck_course_offerings_grading_policy_is_object",
        ),
    )
    op.create_index("idx_offerings_instructor", "course_offerings", ["instructor_id", "status"])
    op.create_index("idx_offerings_term", "course_offerings", ["term_id", "status"])
    op.create_index("idx_offerings_course", "course_offerings", ["course_id"])
    op.execute("SELECT attach_updated_at('course_offerings')")


# ── ثبت‌نام ────────────────────────────────────────────────────────────
def _create_enrollments() -> None:
    op.create_table(
        "enrollments",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=UUID_PK, nullable=False),
        sa.Column("offering_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("student_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'PENDING'"), nullable=False),
        sa.Column("final_grade", sa.Numeric(5, 2), nullable=True),
        sa.Column("enrolled_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_enrollments"),
        sa.UniqueConstraint("offering_id", "student_id", name="uq_enrollments_offering_student"),
        sa.ForeignKeyConstraint(
            ["offering_id"],
            ["course_offerings.id"],
            name="fk_enrollments_offering_id_course_offerings",
        ),
        sa.ForeignKeyConstraint(
            ["student_id"], ["users.id"], name="fk_enrollments_student_id_users"
        ),
        sa.ForeignKeyConstraint(
            ["decided_by"], ["users.id"], name="fk_enrollments_decided_by_users"
        ),
        sa.CheckConstraint(
            _in_list("status", ENROLLMENT_STATUSES), name="ck_enrollments_status_valid"
        ),
        sa.CheckConstraint(
            "final_grade IS NULL OR final_grade BETWEEN 0 AND 20",
            name="ck_enrollments_final_grade_range",
        ),
    )
    op.create_index("idx_enrollments_student", "enrollments", ["student_id", "status"])
    op.create_index("idx_enrollments_offering", "enrollments", ["offering_id", "status"])


# ── هفته و منبع ────────────────────────────────────────────────────────
def _create_weeks_and_resources() -> None:
    op.create_table(
        "course_weeks",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=UUID_PK, nullable=False),
        sa.Column("offering_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("week_number", sa.Integer(), nullable=False),
        sa.Column("title_fa", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("objectives", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("status", sa.Text(), server_default=sa.text("'DRAFT'"), nullable=False),
        sa.Column("publish_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_course_weeks"),
        sa.UniqueConstraint("offering_id", "week_number", name="uq_course_weeks_offering_week"),
        sa.ForeignKeyConstraint(
            ["offering_id"],
            ["course_offerings.id"],
            name="fk_course_weeks_offering_id_course_offerings",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            f"week_number BETWEEN 1 AND {MAX_WEEK_NUMBER}", name="ck_course_weeks_week_number_range"
        ),
        sa.CheckConstraint(_in_list("status", WEEK_STATUSES), name="ck_course_weeks_status_valid"),
    )
    # صف کار پس‌زمینهٔ انتشار — FR-EDU-02.
    op.create_index(
        "idx_weeks_publish_queue",
        "course_weeks",
        ["publish_at"],
        postgresql_where=sa.text("status = 'DRAFT' AND publish_at IS NOT NULL"),
    )
    op.execute("SELECT attach_updated_at('course_weeks')")

    op.create_table(
        "resources",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=UUID_PK, nullable=False),
        sa.Column("week_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("title_fa", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("file_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("external_url", sa.Text(), nullable=True),
        sa.Column("duration_sec", sa.Integer(), nullable=True),
        sa.Column("is_downloadable", sa.Boolean(), server_default=TRUE, nullable=False),
        sa.Column("is_required", sa.Boolean(), server_default=TRUE, nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=ZERO, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_resources"),
        sa.ForeignKeyConstraint(
            ["week_id"],
            ["course_weeks.id"],
            name="fk_resources_week_id_course_weeks",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["file_id"], ["files.id"], name="fk_resources_file_id_files"),
        sa.CheckConstraint(_in_list("kind", RESOURCE_KINDS), name="ck_resources_kind_valid"),
        sa.CheckConstraint(
            "file_id IS NOT NULL OR external_url IS NOT NULL",
            name="ck_resources_source_required",
        ),
    )
    op.create_index("idx_resources_week", "resources", ["week_id", "sort_order"])

    op.create_table(
        "resource_progress",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'NOT_STARTED'"), nullable=False),
        sa.Column("position_sec", sa.Integer(), nullable=True),
        sa.Column("percent", sa.Numeric(5, 2), server_default=ZERO, nullable=True),
        sa.Column("first_opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("user_id", "resource_id", name="pk_resource_progress"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_resource_progress_user_id_users", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["resource_id"],
            ["resources.id"],
            name="fk_resource_progress_resource_id_resources",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            _in_list("status", PROGRESS_STATUSES), name="ck_resource_progress_status_valid"
        ),
        sa.CheckConstraint("percent BETWEEN 0 AND 100", name="ck_resource_progress_percent_range"),
    )
    op.execute("SELECT attach_updated_at('resource_progress')")


# ── حضور و اعلان ───────────────────────────────────────────────────────
def _create_attendance_and_announcements() -> None:
    op.create_table(
        "class_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=UUID_PK, nullable=False),
        sa.Column("offering_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("week_number", sa.Integer(), nullable=True),
        sa.Column("held_on", sa.Date(), nullable=False),
        sa.Column("topic", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_class_sessions"),
        sa.UniqueConstraint("offering_id", "held_on", name="uq_class_sessions_offering_held_on"),
        sa.ForeignKeyConstraint(
            ["offering_id"],
            ["course_offerings.id"],
            name="fk_class_sessions_offering_id_course_offerings",
            ondelete="CASCADE",
        ),
    )

    op.create_table(
        "attendance_records",
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("student_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("recorded_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("session_id", "student_id", name="pk_attendance_records"),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["class_sessions.id"],
            name="fk_attendance_records_session_id_class_sessions",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["student_id"], ["users.id"], name="fk_attendance_records_student_id_users"
        ),
        sa.ForeignKeyConstraint(
            ["recorded_by"], ["users.id"], name="fk_attendance_records_recorded_by_users"
        ),
        sa.CheckConstraint(
            _in_list("status", ATTENDANCE_STATUSES), name="ck_attendance_records_status_valid"
        ),
    )

    op.create_table(
        "announcements",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=UUID_PK, nullable=False),
        sa.Column("offering_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("author_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("priority", sa.Text(), server_default=sa.text("'NORMAL'"), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_announcements"),
        sa.ForeignKeyConstraint(
            ["offering_id"],
            ["course_offerings.id"],
            name="fk_announcements_offering_id_course_offerings",
            ondelete="CASCADE",
        ),
        # §4.10 این قید را به همین مهاجرت سپرده بود.
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_announcements_project_id_projects",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["author_id"], ["users.id"], name="fk_announcements_author_id_users"
        ),
        sa.CheckConstraint(
            "(offering_id IS NOT NULL)::int + (project_id IS NOT NULL)::int = 1",
            name="ck_announcements_target",
        ),
        sa.CheckConstraint(
            _in_list("priority", ANNOUNCEMENT_PRIORITIES), name="ck_announcements_priority_valid"
        ),
    )
    op.create_index(
        "idx_announcements_offering", "announcements", ["offering_id", sa.text("published_at DESC")]
    )
    op.create_index(
        "idx_announcements_project", "announcements", ["project_id", sa.text("published_at DESC")]
    )


# ── کتابخانهٔ درس — ADR-0008 ───────────────────────────────────────────
def _create_library() -> None:
    op.create_table(
        "course_materials",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=UUID_PK, nullable=False),
        sa.Column("course_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("title_fa", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "authors", postgresql.ARRAY(sa.Text()), server_default=EMPTY_TEXT_ARRAY, nullable=False
        ),
        sa.Column("edition", sa.Text(), nullable=True),
        sa.Column("language", sa.Text(), server_default=sa.text("'fa'"), nullable=False),
        # مسیر نسبی داخل `Courses/` — کلید همگام‌سازی پوشه.
        sa.Column("source_path", sa.Text(), nullable=True),
        sa.Column("content_sha256", sa.Text(), nullable=True),
        sa.Column("file_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("external_url", sa.Text(), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("duration_sec", sa.Integer(), nullable=True),
        sa.Column("access_tier", sa.Text(), server_default=sa.text("'SUBSCRIBER'"), nullable=False),
        sa.Column("is_downloadable", sa.Boolean(), server_default=TRUE, nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'PUBLISHED'"), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=ZERO, nullable=False),
        sa.Column("added_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "title_norm",
            sa.Text(),
            sa.Computed("fa_normalize(title_fa)", persisted=True),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_course_materials"),
        sa.ForeignKeyConstraint(
            ["course_id"],
            ["courses.id"],
            name="fk_course_materials_course_id_courses",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["file_id"], ["files.id"], name="fk_course_materials_file_id_files"
        ),
        sa.ForeignKeyConstraint(
            ["added_by"], ["users.id"], name="fk_course_materials_added_by_users"
        ),
        sa.CheckConstraint(_in_list("kind", MATERIAL_KINDS), name="ck_course_materials_kind_valid"),
        sa.CheckConstraint(
            _in_list("access_tier", ACCESS_TIERS), name="ck_course_materials_access_tier_valid"
        ),
        sa.CheckConstraint(
            _in_list("status", MATERIAL_STATUSES), name="ck_course_materials_status_valid"
        ),
        sa.CheckConstraint(
            "file_id IS NOT NULL OR external_url IS NOT NULL",
            name="ck_course_materials_source_required",
        ),
    )
    op.create_index(
        "idx_course_materials_source",
        "course_materials",
        ["course_id", "source_path"],
        unique=True,
        postgresql_where=sa.text("source_path IS NOT NULL AND deleted_at IS NULL"),
    )
    op.create_index("idx_course_materials_course", "course_materials", ["course_id", "sort_order"])
    op.execute(
        "CREATE INDEX idx_course_materials_search"
        " ON course_materials USING GIN (title_norm gin_trgm_ops)"
    )
    op.execute("SELECT attach_updated_at('course_materials')")

    op.create_table(
        "week_materials",
        sa.Column("week_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("material_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("section", sa.Text(), nullable=True),
        sa.Column("is_required", sa.Boolean(), server_default=TRUE, nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=ZERO, nullable=False),
        sa.PrimaryKeyConstraint("week_id", "material_id", name="pk_week_materials"),
        sa.ForeignKeyConstraint(
            ["week_id"],
            ["course_weeks.id"],
            name="fk_week_materials_week_id_course_weeks",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["material_id"],
            ["course_materials.id"],
            name="fk_week_materials_material_id_course_materials",
            ondelete="CASCADE",
        ),
    )
    op.create_index("idx_week_materials_material", "week_materials", ["material_id"])


# ── اشتراک — ADR-0009 ──────────────────────────────────────────────────
def _create_subscriptions() -> None:
    op.create_table(
        "subscription_plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=UUID_PK, nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("title_fa", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("duration_days", sa.Integer(), nullable=False),
        # ریال، عدد صحیح. اعشار پول در پایگاه‌داده جای اشتباه است.
        sa.Column("price_irr", sa.BigInteger(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=TRUE, nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=ZERO, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_subscription_plans"),
        sa.UniqueConstraint("code", name="uq_subscription_plans_code"),
        sa.CheckConstraint(
            _in_list("scope", PLAN_SCOPES), name="ck_subscription_plans_scope_valid"
        ),
        sa.CheckConstraint(
            "duration_days BETWEEN 1 AND 3650", name="ck_subscription_plans_duration_range"
        ),
        sa.CheckConstraint("price_irr >= 0", name="ck_subscription_plans_price_non_negative"),
    )
    op.execute("SELECT attach_updated_at('subscription_plans')")

    op.create_table(
        "subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=UUID_PK, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("course_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.Text(), server_default=sa.text("'PENDING'"), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payment_ref", sa.Text(), nullable=True),
        sa.Column("amount_irr", sa.BigInteger(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("granted_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_subscriptions"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_subscriptions_user_id_users", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["plan_id"],
            ["subscription_plans.id"],
            name="fk_subscriptions_plan_id_subscription_plans",
        ),
        sa.ForeignKeyConstraint(
            ["course_id"],
            ["courses.id"],
            name="fk_subscriptions_course_id_courses",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["granted_by"], ["users.id"], name="fk_subscriptions_granted_by_users"
        ),
        sa.CheckConstraint(
            _in_list("status", SUBSCRIPTION_STATUSES), name="ck_subscriptions_status_valid"
        ),
        sa.CheckConstraint("ends_at > starts_at", name="ck_subscriptions_date_order"),
        sa.CheckConstraint(
            "(status = 'CANCELLED') = (cancelled_at IS NOT NULL)",
            name="ck_subscriptions_cancelled_at_matches_status",
        ),
    )
    op.create_index(
        "idx_subscriptions_active",
        "subscriptions",
        ["user_id", "ends_at"],
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )
    op.create_index(
        "idx_subscriptions_course",
        "subscriptions",
        ["course_id"],
        postgresql_where=sa.text("course_id IS NOT NULL"),
    )
    op.execute("SELECT attach_updated_at('subscriptions')")

    op.create_table(
        "material_access_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=UUID_PK, nullable=False),
        sa.Column("material_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("granted_by_reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_material_access_events"),
        sa.ForeignKeyConstraint(
            ["material_id"],
            ["course_materials.id"],
            name="fk_material_access_events_material_id_course_materials",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_material_access_events_user_id_users",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "idx_material_access_material",
        "material_access_events",
        ["material_id", sa.text("created_at DESC")],
    )
    op.create_index(
        "idx_material_access_user",
        "material_access_events",
        ["user_id", sa.text("created_at DESC")],
    )


# ── قید ارجاع رو به جلوی ۰۱۰ ───────────────────────────────────────────
def _attach_forward_references() -> None:
    """`projects.offering_id` → `course_offerings` — §4.10 و ADR-0004.

    ستون از ۰۱۰ بدون قید مانده بود چون جدول مقصد وجود نداشت. حالا دارد.
    """
    op.create_foreign_key(
        "fk_projects_offering_id_course_offerings",
        "projects",
        "course_offerings",
        ["offering_id"],
        ["id"],
    )
    op.create_index(
        "idx_projects_offering",
        "projects",
        ["offering_id"],
        postgresql_where=sa.text("offering_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("idx_projects_offering", table_name="projects")
    op.drop_constraint("fk_projects_offering_id_course_offerings", "projects", type_="foreignkey")

    op.drop_table("material_access_events")
    op.execute("DROP TRIGGER IF EXISTS trg_subscriptions_updated ON subscriptions")
    op.drop_table("subscriptions")
    op.execute("DROP TRIGGER IF EXISTS trg_subscription_plans_updated ON subscription_plans")
    op.drop_table("subscription_plans")

    op.drop_table("week_materials")
    op.execute("DROP TRIGGER IF EXISTS trg_course_materials_updated ON course_materials")
    op.drop_table("course_materials")

    op.drop_table("announcements")
    op.drop_table("attendance_records")
    op.drop_table("class_sessions")

    op.execute("DROP TRIGGER IF EXISTS trg_resource_progress_updated ON resource_progress")
    op.drop_table("resource_progress")
    op.drop_table("resources")
    op.execute("DROP TRIGGER IF EXISTS trg_course_weeks_updated ON course_weeks")
    op.drop_table("course_weeks")

    op.drop_table("enrollments")
    op.execute("DROP TRIGGER IF EXISTS trg_course_offerings_updated ON course_offerings")
    op.drop_table("course_offerings")
    op.execute("DROP TRIGGER IF EXISTS trg_courses_updated ON courses")
    op.drop_table("courses")
    op.drop_table("terms")
