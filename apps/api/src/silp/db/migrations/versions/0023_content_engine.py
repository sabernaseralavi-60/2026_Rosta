"""0023 — موتور محتوای Vault-محور و پیام مالک

مرجع: ADR-0030.

جدول `content_items` نمایهٔ یادداشت‌های Markdownِ پوشهٔ `12_Content` در Vault
شخصی مالک است (مقاله، خلاصهٔ کتاب، خلاصهٔ مقاله، مثال، Case Study). خودِ
فایل منبع حقیقت است؛ ردیف با `source_path` کلید می‌خورد و `content_sha256`
اجرای دوباره را بی‌اثر می‌کند.

نوع اعلان `OWNER_BROADCAST` (پیام مالک به مخاطبان) هم اینجا الگو می‌گیرد؛
پیامک ندارد (`allow_sms=False`).

Revision ID: 0023
Revises: 0022
Create Date: 2026-09-28
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID_PK = sa.text("uuidv7()")
NOW = sa.text("now()")

KINDS = ("ARTICLE", "BOOK_SUMMARY", "PAPER_SUMMARY", "EXAMPLE", "CASE_STUDY", "DATASET_NOTE")
ACCESS = ("PUBLIC", "REGISTERED", "STUDENT", "MEMBER", "PREMIUM")
STATUSES = ("DRAFT", "PUBLISHED", "ARCHIVED")

# (کد، کانال، عنوان، متن، متغیرها) — همان قالب مهاجرت‌های ۰۰۱۹ و ۰۰۲۰.
TEMPLATES: tuple[tuple[str, str, str | None, str, tuple[str, ...]], ...] = (
    ("OWNER_BROADCAST", "IN_APP", "{{title}}", "{{body}}", ("title", "body")),
    (
        "OWNER_BROADCAST",
        "EMAIL",
        "{{title}}",
        "سلام {{name}}،\n\n{{body}}\n\nداخل سامانه: {{link}}",
        ("title", "body"),
    ),
)


def _in_list(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def upgrade() -> None:
    op.create_table(
        "content_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=UUID_PK, nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), server_default=sa.text("'ARTICLE'"), nullable=False),
        sa.Column("title_fa", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("body_md", sa.Text(), nullable=False),
        sa.Column("cover", sa.Text(), nullable=True),
        sa.Column("access", sa.Text(), server_default=sa.text("'PUBLIC'"), nullable=False),
        sa.Column(
            "topics",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'::text[]"),
            nullable=False,
        ),
        sa.Column(
            "skills",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'::text[]"),
            nullable=False,
        ),
        sa.Column("course_slug", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), server_default=sa.text("'DRAFT'"), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reading_minutes", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("source_path", sa.Text(), nullable=True),
        sa.Column("content_sha256", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_content_items"),
        sa.UniqueConstraint("slug", name="uq_content_items_slug"),
        sa.UniqueConstraint("source_path", name="uq_content_items_source_path"),
        sa.CheckConstraint(_in_list("kind", KINDS), name="kind_valid"),
        sa.CheckConstraint(_in_list("access", ACCESS), name="access_valid"),
        sa.CheckConstraint(_in_list("status", STATUSES), name="status_valid"),
        sa.CheckConstraint("length(title_fa) BETWEEN 3 AND 200", name="title_length"),
        sa.CheckConstraint("reading_minutes >= 1", name="reading_minutes_positive"),
    )
    op.create_index(
        "idx_content_items_feed",
        "content_items",
        [sa.text("published_at DESC")],
        postgresql_where=sa.text("status = 'PUBLISHED'"),
    )
    op.create_index("idx_content_items_topics", "content_items", ["topics"], postgresql_using="gin")
    op.create_index("idx_content_items_kind", "content_items", ["kind", "published_at"])
    # به‌روزرسانی updated_at با تریگر مشترک (PRD §4.0)
    op.execute("SELECT attach_updated_at('content_items')")
    _seed_templates()


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
    op.execute(f"DELETE FROM outbox_messages WHERE template IN ({codes})")
    op.execute(f"DELETE FROM message_templates WHERE code IN ({codes})")
    op.execute(f"DELETE FROM notifications WHERE kind IN ({codes})")
    op.drop_table("content_items")
