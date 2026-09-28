"""0025 — توکن دسترسی برنامه‌ای (PAT) برای ابزارهای بی‌آدم

مرجع: ADR-0031.

`vault push` روی رایانهٔ مالک نمی‌تواند OTP بزند. توکن بلندمدت، قابل ابطال و
دامنه‌دار (`vault:publish`) جایگزین است؛ فقط `sha256` آن ذخیره می‌شود.

Revision ID: 0025
Revises: 0024
Create Date: 2026-09-28
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID_PK = sa.text("uuidv7()")
NOW = sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "api_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=UUID_PK, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("token_hint", sa.Text(), nullable=False),
        sa.Column(
            "scopes",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'::text[]"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_api_tokens"),
        sa.UniqueConstraint("token_hash", name="uq_api_tokens_token_hash"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_api_tokens_user_id_users", ondelete="CASCADE"
        ),
        sa.CheckConstraint("length(name) BETWEEN 1 AND 80", name="name_length"),
        sa.CheckConstraint("cardinality(scopes) >= 1", name="scopes_required"),
    )
    op.create_index("idx_api_tokens_user", "api_tokens", ["user_id"])
    op.execute("SELECT attach_updated_at('api_tokens')")


def downgrade() -> None:
    op.drop_table("api_tokens")
