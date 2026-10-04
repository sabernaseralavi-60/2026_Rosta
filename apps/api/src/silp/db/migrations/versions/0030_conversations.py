"""0030 — گفت‌وگوی استاد–دانشجو (جایگزین تلگرام)

مرجع: ADR-0036 §۲.۴.

* `conversations` — `OFFERING` (کانال درس: فقط کادر آموزشی می‌نویسد) و `DIRECT`
  (استاد↔یک دانشجو). نوع `GROUP` در قید مجاز است ولی هنوز ساخته نمی‌شود.
* `conversation_members` — عضویت صریح و نشانهٔ «تا کجا خوانده». دانشجوی کانال درس
  عضو ضمنی است (ثبت‌نام فعال)؛ ردیفش با اولین خواندن ساخته می‌شود.
* `messages` — حذف نرم؛ متن در همین سامانه می‌ماند و فقط یک اعلان کوتاه به
  پیام‌رسان بیرونی می‌رود.
* الگوی اعلان `MESSAGE_RECEIVED`.

Revision ID: 0030
Revises: 0029
Create Date: 2026-10-04
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0030"
down_revision: str | None = "0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID_PK = sa.text("uuidv7()")
NOW = sa.text("now()")
UUID = postgresql.UUID(as_uuid=True)

TEMPLATES: tuple[tuple[str, str, str | None, str, tuple[str, ...]], ...] = (
    (
        "MESSAGE_RECEIVED",
        "IN_APP",
        "{{sender}} · {{course}}",
        "{{preview}}",
        ("sender", "course", "preview"),
    ),
)


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("id", UUID, server_default=UUID_PK, nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("offering_id", UUID, nullable=False),
        sa.Column("student_id", UUID, nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("created_by", UUID, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_conversations"),
        sa.ForeignKeyConstraint(
            ["offering_id"],
            ["course_offerings.id"],
            name="fk_conversations_offering_id_course_offerings",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["student_id"], ["users.id"], name="fk_conversations_student_id_users"
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name="fk_conversations_created_by_users"
        ),
        sa.CheckConstraint("kind IN ('OFFERING', 'DIRECT', 'GROUP')", name="kind_valid"),
        sa.CheckConstraint(
            "(kind = 'DIRECT') = (student_id IS NOT NULL)", name="student_for_direct"
        ),
    )
    op.create_index(
        "uq_conversations_offering_channel",
        "conversations",
        ["offering_id"],
        unique=True,
        postgresql_where=sa.text("kind = 'OFFERING'"),
    )
    op.create_index(
        "uq_conversations_direct",
        "conversations",
        ["offering_id", "student_id"],
        unique=True,
        postgresql_where=sa.text("kind = 'DIRECT'"),
    )

    op.create_table(
        "conversation_members",
        sa.Column("conversation_id", UUID, nullable=False),
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("last_read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("joined_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("conversation_id", "user_id", name="pk_conversation_members"),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name="fk_conversation_members_conversation_id_conversations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_conversation_members_user_id_users",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("role IN ('STAFF', 'STUDENT')", name="role_valid"),
    )
    op.create_index("idx_conversation_members_user", "conversation_members", ["user_id"])

    op.create_table(
        "messages",
        sa.Column("id", UUID, server_default=UUID_PK, nullable=False),
        sa.Column("conversation_id", UUID, nullable=False),
        sa.Column("sender_id", UUID, nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("reply_to_id", UUID, nullable=True),
        # clock_timestamp، نه now(): ترتیب «خوانده/نخوانده» نباید به آغاز تراکنش گره بخورد.
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_messages"),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name="fk_messages_conversation_id_conversations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["sender_id"], ["users.id"], name="fk_messages_sender_id_users"),
        sa.ForeignKeyConstraint(
            ["reply_to_id"],
            ["messages.id"],
            name="fk_messages_reply_to_id_messages",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint("length(body) BETWEEN 1 AND 4000", name="body_length"),
    )
    op.create_index("idx_messages_conversation", "messages", ["conversation_id", "id"])

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
    op.execute("DELETE FROM message_templates WHERE code = 'MESSAGE_RECEIVED'")
    op.execute("DELETE FROM notifications WHERE kind = 'MESSAGE_RECEIVED'")
    op.drop_table("messages")
    op.drop_table("conversation_members")
    op.drop_table("conversations")
