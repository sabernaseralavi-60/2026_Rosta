"""0029 — فهرست دانشجویان هر ارائه و ادعای هویت

مرجع: ADR-0035.

* `roster_entries` — دانشجویان یک ارائه (نام، ایمیل ثبت‌شده، **HMAC** شمارهٔ دانشجویی).
  متن خام شمارهٔ دانشجویی هرگز ذخیره نمی‌شود.
* `roster_claims` — یک تلاش برای گرفتن حساب با موبایل + شمارهٔ دانشجویی؛ کد ایمیلی
  هش‌شده، با سقف تلاش و ارسال.

Revision ID: 0029
Revises: 0028
Create Date: 2026-09-28
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0029"
down_revision: str | None = "0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID_PK = sa.text("uuidv7()")
NOW = sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "roster_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=UUID_PK, nullable=False),
        sa.Column("offering_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("first_name", sa.Text(), nullable=False),
        sa.Column("last_name", sa.Text(), nullable=False),
        sa.Column("student_no_hash", sa.Text(), nullable=False),
        sa.Column("email", postgresql.CITEXT(), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_roster_entries"),
        sa.ForeignKeyConstraint(
            ["offering_id"],
            ["course_offerings.id"],
            name="fk_roster_entries_offering_id_course_offerings",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_roster_entries_user_id_users", ondelete="SET NULL"
        ),
        sa.CheckConstraint("student_no_hash ~ '^[0-9a-f]{64}$'", name="hash_format"),
    )
    op.create_index(
        "uq_roster_entries_offering_no",
        "roster_entries",
        ["offering_id", "student_no_hash"],
        unique=True,
    )
    op.create_index("idx_roster_entries_hash", "roster_entries", ["student_no_hash"])
    op.create_index("idx_roster_entries_user", "roster_entries", ["user_id"])

    op.create_table(
        "roster_claims",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=UUID_PK, nullable=False),
        sa.Column("student_no_hash", sa.Text(), nullable=False),
        sa.Column("mobile", sa.Text(), nullable=False),
        sa.Column("email", postgresql.CITEXT(), nullable=True),
        sa.Column(
            "status", sa.Text(), server_default=sa.text("'AWAITING_CONFIRM'"), nullable=False
        ),
        sa.Column("code_hash", sa.Text(), nullable=True),
        sa.Column("code_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("code_attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("code_sends", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("ip_address", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_roster_claims"),
        sa.CheckConstraint(
            "status IN ('AWAITING_CONFIRM', 'AWAITING_CODE', 'DONE', 'CANCELLED')",
            name="status_valid",
        ),
        sa.CheckConstraint(r"mobile ~ '^09\d{9}$'", name="mobile_format"),
    )
    op.create_index(
        "idx_roster_claims_hash_created",
        "roster_claims",
        ["student_no_hash", sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.drop_table("roster_claims")
    op.drop_table("roster_entries")
