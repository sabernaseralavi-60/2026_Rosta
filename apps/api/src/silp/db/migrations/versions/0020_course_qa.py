"""0020 — پرسش‌وپاسخ درس: پرسش، پاسخ، رأی «مفید»، تأیید استاد

مرجع: ADR-0024 (برش ج)، PRD §4.10، §7.12 «شمارنده‌های غیرنرمال»، FR-EDU-07.

پس از ۰۰۱۹ اجرا می‌شود. ۰۰۱۶ این دو جدول را صریحاً به «زمان ماژولشان»
سپرده بود؛ اینجا با ماژولشان می‌آیند — به‌اضافهٔ سه چیزی که §4.10 نداشت:

* `deleted_at` روی هر دو (نظارت؛ D-15) — پاسخ حذف‌شده امتیازش برمی‌گردد.
* `qa_replies.endorsed_by/endorsed_at` — «تأیید استاد» بر پاسخِ دانشجو.
  `is_official` یعنی پاسخ را خودِ استاد نوشته و مفهوم دیگری است.
* `qa_reply_votes` — جدول رأی، برای اینکه `helpful_count` روی چیزی بنشیند.

`helpful_count` را تریگر افزایشی نگه می‌دارد (همان دلیل `ideas.vote_count`):
بازشماری در READ COMMITTED رأی تراکنش هم‌زمان را نمی‌دید.

Revision ID: 0020
Revises: 0019
Create Date: 2026-09-25
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID_PK = sa.text("uuidv7()")
NOW = sa.text("now()")
FALSE = sa.text("false")
ZERO = sa.text("0")

# (کد، کانال، عنوان، متن، متغیرها) — قواعد نگارش §14.7، مانند ۰۰۱۹.
TEMPLATES: tuple[tuple[str, str, str | None, str, tuple[str, ...]], ...] = (
    (
        "QA_REPLY_POSTED",
        "IN_APP",
        "پاسخ تازه به «{{thread}}»",
        "{{replier}} در درس {{course}} به پرسشت پاسخ داد: {{excerpt}}",
        ("course", "thread", "replier", "excerpt"),
    ),
    (
        "QA_REPLY_ENDORSED",
        "IN_APP",
        "استاد پاسخت را تأیید کرد",
        "پاسخ تو به «{{thread}}» در درس {{course}} را استاد تأیید کرد. {{reward}}",
        ("course", "thread", "reward"),
    ),
)


def upgrade() -> None:
    _create_threads()
    _create_replies()
    _create_votes()
    _create_counter_trigger()
    _seed_templates()


def _create_threads() -> None:
    op.create_table(
        "qa_threads",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=UUID_PK, nullable=False),
        sa.Column("week_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("offering_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("author_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("is_anonymous", sa.Boolean(), server_default=FALSE, nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("is_resolved", sa.Boolean(), server_default=FALSE, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_qa_threads"),
        sa.ForeignKeyConstraint(
            ["week_id"],
            ["course_weeks.id"],
            name="fk_qa_threads_week_id_course_weeks",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["offering_id"],
            ["course_offerings.id"],
            name="fk_qa_threads_offering_id_course_offerings",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"], name="fk_qa_threads_author_id_users"),
        sa.CheckConstraint("length(title) BETWEEN 5 AND 150", name="ck_qa_threads_title_length"),
        sa.CheckConstraint("length(body) BETWEEN 10 AND 4000", name="ck_qa_threads_body_length"),
    )
    op.create_index(
        "idx_qa_threads_offering", "qa_threads", ["offering_id", sa.text("created_at DESC")]
    )
    op.create_index("idx_qa_threads_week", "qa_threads", ["week_id"])
    op.create_index("idx_qa_threads_author", "qa_threads", ["author_id"])


def _create_replies() -> None:
    op.create_table(
        "qa_replies",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=UUID_PK, nullable=False),
        sa.Column("thread_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("author_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("is_official", sa.Boolean(), server_default=FALSE, nullable=False),
        sa.Column("helpful_count", sa.Integer(), server_default=ZERO, nullable=False),
        sa.Column("endorsed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("endorsed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_qa_replies"),
        sa.ForeignKeyConstraint(
            ["thread_id"],
            ["qa_threads.id"],
            name="fk_qa_replies_thread_id_qa_threads",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"], name="fk_qa_replies_author_id_users"),
        sa.ForeignKeyConstraint(
            ["endorsed_by"], ["users.id"], name="fk_qa_replies_endorsed_by_users"
        ),
        sa.CheckConstraint("length(body) BETWEEN 3 AND 4000", name="ck_qa_replies_body_length"),
        sa.CheckConstraint("helpful_count >= 0", name="ck_qa_replies_helpful_not_negative"),
        sa.CheckConstraint(
            "(endorsed_by IS NULL) = (endorsed_at IS NULL)", name="ck_qa_replies_endorsement_pair"
        ),
        sa.CheckConstraint(
            "NOT (is_official AND endorsed_by IS NOT NULL)",
            name="ck_qa_replies_official_not_endorsed",
        ),
    )
    op.create_index("idx_qa_replies_thread", "qa_replies", ["thread_id", "created_at"])
    op.create_index("idx_qa_replies_author", "qa_replies", ["author_id"])


def _create_votes() -> None:
    op.create_table(
        "qa_reply_votes",
        sa.Column("reply_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("reply_id", "user_id", name="pk_qa_reply_votes"),
        sa.ForeignKeyConstraint(
            ["reply_id"],
            ["qa_replies.id"],
            name="fk_qa_reply_votes_reply_id_qa_replies",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_qa_reply_votes_user_id_users",
            ondelete="CASCADE",
        ),
    )
    op.create_index("idx_qa_reply_votes_user", "qa_reply_votes", ["user_id"])


def _create_counter_trigger() -> None:
    """§7.12 — `helpful_count` با تریگر افزایشی، مثل `bump_idea_votes`."""
    op.execute(
        """
        CREATE OR REPLACE FUNCTION bump_qa_reply_votes() RETURNS TRIGGER AS $$
        BEGIN
          IF TG_OP = 'INSERT' THEN
            UPDATE qa_replies SET helpful_count = helpful_count + 1 WHERE id = NEW.reply_id;
          ELSIF TG_OP = 'DELETE' THEN
            UPDATE qa_replies SET helpful_count = GREATEST(0, helpful_count - 1)
             WHERE id = OLD.reply_id;
          END IF;
          RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_qa_reply_votes_count
        AFTER INSERT OR DELETE ON qa_reply_votes
        FOR EACH ROW EXECUTE FUNCTION bump_qa_reply_votes();
        """
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
    op.execute("DROP TRIGGER IF EXISTS trg_qa_reply_votes_count ON qa_reply_votes")
    op.execute("DROP FUNCTION IF EXISTS bump_qa_reply_votes()")
    op.drop_table("qa_reply_votes")
    op.drop_table("qa_replies")
    op.drop_table("qa_threads")
