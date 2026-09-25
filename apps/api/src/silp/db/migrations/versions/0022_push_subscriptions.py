"""0022 — اشتراک Push وب

مرجع: ADR-0029، FR-MSG-02.

جدول `push_subscriptions` (هر مرورگر یک ردیف) و افزودن `PUSH` به قیدهای کانال
سه جدولِ اعلان. `endpoint` یکتاست تا مرورگرِ مشترک‌شده با دو حساب، دو بار
اعلان نگیرد.

Revision ID: 0022
Revises: 0021
Create Date: 2026-09-25
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_CHANNELS = ("IN_APP", "EMAIL", "SMS", "TELEGRAM", "EITAA", "WHATSAPP")
NEW_CHANNELS = ("IN_APP", "EMAIL", "SMS", "PUSH", "TELEGRAM", "EITAA", "WHATSAPP")
OLD_EXTERNAL = OLD_CHANNELS[1:]
NEW_EXTERNAL = NEW_CHANNELS[1:]


def _in_list(values: tuple[str, ...]) -> str:
    return "channel IN (" + ", ".join(f"'{v}'" for v in values) + ")"


def _array(values: tuple[str, ...]) -> str:
    return "channels <@ ARRAY[" + ", ".join(f"'{v}'" for v in values) + "]::text[]"


def _swap(channels: tuple[str, ...], external: tuple[str, ...]) -> None:
    for table, name, expression in (
        ("outbox_messages", "channel_valid", _in_list(external)),
        ("message_templates", "channel_valid", _in_list(channels)),
        ("notification_preferences", "channels_valid", _array(channels)),
    ):
        # نام کوتاه: قرارداد نام‌گذاری خودش `ck_<جدول>_` را پیش می‌گذارد.
        op.drop_constraint(name, table, type_="check")
        op.create_check_constraint(name, table, expression)


def upgrade() -> None:
    op.create_table(
        "push_subscriptions",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), server_default=sa.text("uuidv7()"), nullable=False
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("endpoint", sa.Text(), nullable=False),
        sa.Column("p256dh", sa.Text(), nullable=False),
        sa.Column("auth", sa.Text(), nullable=False),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_push_subscriptions"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_push_subscriptions_user_id_users",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("endpoint LIKE 'https://%'", name="endpoint_https"),
    )
    op.create_index(
        "idx_push_subscriptions_endpoint", "push_subscriptions", ["endpoint"], unique=True
    )
    op.create_index("idx_push_subscriptions_user", "push_subscriptions", ["user_id", "created_at"])
    _swap(NEW_CHANNELS, NEW_EXTERNAL)


def downgrade() -> None:
    # ردیف‌های PUSH قید قدیمی را می‌شکنند؛ پیش از برگرداندن قید حذف می‌شوند.
    op.execute("DELETE FROM outbox_messages WHERE channel = 'PUSH'")
    op.execute("DELETE FROM message_templates WHERE channel = 'PUSH'")
    op.execute(
        "UPDATE notification_preferences SET channels = array_remove(channels, 'PUSH')"
        " WHERE 'PUSH' = ANY(channels)"
    )
    _swap(OLD_CHANNELS, OLD_EXTERNAL)
    op.drop_table("push_subscriptions")
