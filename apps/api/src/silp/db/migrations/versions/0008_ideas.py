"""0008 — بانک ایده: ایده، رأی، نظر

مرجع: PRD §4.7، §7.8، §7.12 «شمارنده‌های غیرنرمال»، FR-IDEA-01/02/03.
وظیفهٔ نقشهٔ راه: M7-01، M7-02.

شمارهٔ فایل ۰۰۰۸ است چون §4.10 این جدول‌ها را آنجا گذاشته؛ ولی پس از ۰۰۱۳
اجرا می‌شود — همان قاعدهٔ ADR-0004: «ترتیب اجرا را `down_revision` تعیین
می‌کند، نه شمارهٔ فایل».

## شمارنده‌ها

`vote_count` و `comment_count` با تریگر **افزایشی** نگه داشته می‌شوند
(§7.12). بازشماری (`SELECT count(*)`) در READ COMMITTED رأی تراکنش
هم‌زمانِ commit‌نشده را نمی‌بیند و دو رأی هم‌زمان یکی می‌شدند؛
`UPDATE … SET vote_count = vote_count + 1` ردیف ایده را قفل می‌کند و دومی
مقدار تازه را می‌خواند.

نظر حذف نرم دارد، پس تریگر نظر به `UPDATE OF deleted_at` هم گوش می‌دهد.

## ارجاع‌های رو به جلو

`projects.origin_idea_id` (از ۰۰۱۰) و `team_openings.idea_id` (از ۰۰۱۱) تا
امروز بی‌قید بودند. اینجا قیدشان افزوده می‌شود.

## هم‌ترازی مدل و مهاجرت

دو ناهمخوانی قدیمی که `alembic check` را قرمز نگه داشته بود، اینجا بسته
می‌شوند: `resource_progress.percent` در ۰۰۰۶ نال‌پذیر ساخته شده بود ولی
مدل و منطق آن را همیشه عدد می‌دانند؛ و قید `projects.offering_id` در مدل
اعلام نشده بود.

Revision ID: 0008
Revises: 0013
Create Date: 2026-09-23
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID_PK = sa.text("uuidv7()")
NOW = sa.text("now()")
FALSE = sa.text("false")
ZERO = sa.text("0")
EMPTY_TEXT_ARRAY = sa.text("'{}'::text[]")

IDEA_STATUSES = ("OPEN", "PROMOTED", "ARCHIVED")
PROMOTION_TARGETS = ("PROJECT", "VENTURE")
IDEA_CATEGORIES = (
    "TRANSPORT",
    "AGRICULTURE",
    "COMMERCE",
    "EDUCATION",
    "TECHNOLOGY",
    "ENVIRONMENT",
    "SOCIAL",
    "OTHER",
)

# (کد، کانال، عنوان، متن، متغیرها) — قواعد نگارش §14.7، مانند ۰۰۱۳.
# هم‌ترازی با `silp.domain.notifications.catalog` را
# `test_seeded_templates_match_catalog` می‌پاید.
TEMPLATES: tuple[tuple[str, str, str | None, str, tuple[str, ...]], ...] = (
    (
        "IDEA_COMMENTED",
        "IN_APP",
        "نظر تازه روی «{{idea}}»",
        "{{commenter}} روی ایده‌ات نظر داد: {{excerpt}}",
        ("idea", "commenter", "excerpt"),
    ),
    (
        "IDEA_PROMOTED",
        "IN_APP",
        "ایده‌ات ارتقا یافت",
        "ایدهٔ «{{idea}}» به {{target}} تبدیل شد: «{{title}}». {{next_step}}",
        ("idea", "target", "title", "next_step"),
    ),
)


def _in_list(column: str, values: tuple[str, ...]) -> str:
    joined = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({joined})"


def upgrade() -> None:
    _create_ideas()
    _create_votes()
    _create_comments()
    _create_counter_triggers()
    _attach_forward_references()
    _align_old_drift()
    _seed_templates()


def _create_ideas() -> None:
    op.create_table(
        "ideas",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=UUID_PK, nullable=False),
        sa.Column("author_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("problem", sa.Text(), nullable=True),
        sa.Column("category", sa.Text(), nullable=True),
        sa.Column(
            "tags", postgresql.ARRAY(sa.Text()), server_default=EMPTY_TEXT_ARRAY, nullable=False
        ),
        sa.Column("is_anonymous", sa.Boolean(), server_default=FALSE, nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'OPEN'"), nullable=False),
        sa.Column("vote_count", sa.Integer(), server_default=ZERO, nullable=False),
        sa.Column("comment_count", sa.Integer(), server_default=ZERO, nullable=False),
        sa.Column("promoted_to_type", sa.Text(), nullable=True),
        sa.Column("promoted_to_id", postgresql.UUID(as_uuid=True), nullable=True),
        # فراتر از §4.7: چه کسی و کِی ارتقا داد — اعتبار ایده (FR-IDEA-03)
        # بدون این دو قابل پیگیری نیست.
        sa.Column("promoted_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("promoted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "search_norm",
            sa.Text(),
            sa.Computed("fa_normalize(title || ' ' || body)", persisted=True),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ideas"),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"], name="fk_ideas_author_id_users"),
        sa.ForeignKeyConstraint(["promoted_by"], ["users.id"], name="fk_ideas_promoted_by_users"),
        sa.CheckConstraint(_in_list("status", IDEA_STATUSES), name="ck_ideas_status_valid"),
        sa.CheckConstraint(
            f"category IS NULL OR {_in_list('category', IDEA_CATEGORIES)}",
            name="ck_ideas_category_valid",
        ),
        sa.CheckConstraint("length(title) BETWEEN 3 AND 120", name="ck_ideas_title_length"),
        sa.CheckConstraint("length(body) BETWEEN 10 AND 4000", name="ck_ideas_body_length"),
        sa.CheckConstraint(
            "problem IS NULL OR length(problem) <= 1000", name="ck_ideas_problem_length"
        ),
        sa.CheckConstraint("cardinality(tags) <= 8", name="ck_ideas_tags_count"),
        sa.CheckConstraint(
            "vote_count >= 0 AND comment_count >= 0", name="ck_ideas_counters_not_negative"
        ),
        sa.CheckConstraint(
            "promoted_to_type IS NULL OR " + _in_list("promoted_to_type", PROMOTION_TARGETS),
            name="ck_ideas_promoted_to_type_valid",
        ),
        sa.CheckConstraint(
            "(status = 'PROMOTED') = (promoted_to_id IS NOT NULL)"
            " AND (promoted_to_id IS NULL) = (promoted_to_type IS NULL)",
            name="ck_ideas_promotion_consistent",
        ),
    )
    op.execute("CREATE INDEX idx_ideas_search ON ideas USING GIN (search_norm gin_trgm_ops)")
    op.create_index(
        "idx_ideas_ranking",
        "ideas",
        [sa.text("vote_count DESC"), sa.text("created_at DESC")],
        postgresql_where=sa.text("status = 'OPEN' AND deleted_at IS NULL"),
    )
    op.create_index("idx_ideas_author", "ideas", ["author_id", sa.text("created_at DESC")])
    op.create_index("idx_ideas_tags", "ideas", ["tags"], postgresql_using="gin")
    op.execute("SELECT attach_updated_at('ideas')")


def _create_votes() -> None:
    op.create_table(
        "idea_votes",
        sa.Column("idea_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("idea_id", "user_id", name="pk_idea_votes"),
        sa.ForeignKeyConstraint(
            ["idea_id"], ["ideas.id"], name="fk_idea_votes_idea_id_ideas", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_idea_votes_user_id_users", ondelete="CASCADE"
        ),
    )
    op.create_index("idx_idea_votes_user", "idea_votes", ["user_id"])


def _create_comments() -> None:
    op.create_table(
        "idea_comments",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=UUID_PK, nullable=False),
        sa.Column("idea_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("author_id", postgresql.UUID(as_uuid=True), nullable=False),
        # فراتر از §4.7: «نخ یک‌سطحی» (FR-IDEA-02) بدون ارجاع به نظر والد
        # قابل ساختن نیست.
        sa.Column("parent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_idea_comments"),
        sa.ForeignKeyConstraint(
            ["idea_id"], ["ideas.id"], name="fk_idea_comments_idea_id_ideas", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["author_id"], ["users.id"], name="fk_idea_comments_author_id_users"
        ),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["idea_comments.id"],
            name="fk_idea_comments_parent_id_idea_comments",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("length(body) BETWEEN 1 AND 1000", name="ck_idea_comments_body_length"),
        sa.CheckConstraint(
            "parent_id IS NULL OR parent_id <> id", name="ck_idea_comments_not_own_parent"
        ),
    )
    op.create_index("idx_idea_comments_idea", "idea_comments", ["idea_id", "created_at"])


def _create_counter_triggers() -> None:
    """§7.12 — شمارنده‌های غیرنرمال ایده با تریگر افزایشی."""
    op.execute(
        """
        CREATE OR REPLACE FUNCTION bump_idea_votes() RETURNS TRIGGER AS $$
        BEGIN
          IF TG_OP = 'INSERT' THEN
            UPDATE ideas SET vote_count = vote_count + 1 WHERE id = NEW.idea_id;
          ELSIF TG_OP = 'DELETE' THEN
            UPDATE ideas SET vote_count = GREATEST(0, vote_count - 1) WHERE id = OLD.idea_id;
          END IF;
          RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_idea_votes_count
        AFTER INSERT OR DELETE ON idea_votes
        FOR EACH ROW EXECUTE FUNCTION bump_idea_votes();
        """
    )
    # نظر «زنده» یعنی `deleted_at IS NULL`. حذف نرم یک UPDATE است و حذف
    # سخت (آبشاری با حذف ایده) یک DELETE؛ هر دو شمرده می‌شوند، ولی فقط
    # وقتی نظر پیش از آن زنده بوده.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION bump_idea_comments() RETURNS TRIGGER AS $$
        BEGIN
          IF TG_OP = 'INSERT' AND NEW.deleted_at IS NULL THEN
            UPDATE ideas SET comment_count = comment_count + 1 WHERE id = NEW.idea_id;
          ELSIF TG_OP = 'DELETE' AND OLD.deleted_at IS NULL THEN
            UPDATE ideas SET comment_count = GREATEST(0, comment_count - 1)
             WHERE id = OLD.idea_id;
          ELSIF TG_OP = 'UPDATE' THEN
            IF OLD.deleted_at IS NULL AND NEW.deleted_at IS NOT NULL THEN
              UPDATE ideas SET comment_count = GREATEST(0, comment_count - 1)
               WHERE id = NEW.idea_id;
            ELSIF OLD.deleted_at IS NOT NULL AND NEW.deleted_at IS NULL THEN
              UPDATE ideas SET comment_count = comment_count + 1 WHERE id = NEW.idea_id;
            END IF;
          END IF;
          RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_idea_comments_count
        AFTER INSERT OR DELETE OR UPDATE OF deleted_at ON idea_comments
        FOR EACH ROW EXECUTE FUNCTION bump_idea_comments();
        """
    )


def _attach_forward_references() -> None:
    """`projects.origin_idea_id` و `team_openings.idea_id` → `ideas` — §4.10."""
    op.create_foreign_key(
        "fk_projects_origin_idea_id_ideas", "projects", "ideas", ["origin_idea_id"], ["id"]
    )
    op.create_foreign_key(
        "fk_team_openings_idea_id_ideas",
        "team_openings",
        "ideas",
        ["idea_id"],
        ["id"],
        ondelete="CASCADE",
    )


def _align_old_drift() -> None:
    op.execute("UPDATE resource_progress SET percent = 0 WHERE percent IS NULL")
    op.alter_column("resource_progress", "percent", nullable=False)


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
    op.alter_column("resource_progress", "percent", nullable=True)
    op.drop_constraint("fk_team_openings_idea_id_ideas", "team_openings", type_="foreignkey")
    op.drop_constraint("fk_projects_origin_idea_id_ideas", "projects", type_="foreignkey")
    op.execute("DROP TRIGGER IF EXISTS trg_idea_comments_count ON idea_comments")
    op.execute("DROP FUNCTION IF EXISTS bump_idea_comments()")
    op.drop_table("idea_comments")
    op.execute("DROP TRIGGER IF EXISTS trg_idea_votes_count ON idea_votes")
    op.execute("DROP FUNCTION IF EXISTS bump_idea_votes()")
    op.drop_table("idea_votes")
    op.execute("DROP TRIGGER IF EXISTS trg_ideas_updated ON ideas")
    op.drop_table("ideas")
