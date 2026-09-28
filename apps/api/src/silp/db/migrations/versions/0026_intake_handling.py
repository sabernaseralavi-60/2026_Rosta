"""0026 — رسیدگی مالک به درخواست‌های ورودی و پیگیری مشتری

مرجع: ADR-0032.

۱. `intake_requests.owner_note` — یادداشت **خصوصی** مالک؛ هرگز به مشتری نمی‌رود.
۲. `intake_events` — تاریخچهٔ افزودنیِ تغییر وضعیت. `public_note` تنها چیزی است که مشتری
   در داشبوردش می‌بیند. ردیف با حذف درخواست می‌رود (CASCADE)؛ کنشگر با حذف کاربر تهی می‌شود.

Revision ID: 0026
Revises: 0025
Create Date: 2026-09-28
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID_PK = sa.text("uuidv7()")
NOW = sa.text("now()")
STATUSES = ("NEW", "IN_REVIEW", "ACCEPTED", "DECLINED", "ARCHIVED")


def upgrade() -> None:
    op.add_column("intake_requests", sa.Column("owner_note", sa.Text(), nullable=True))
    op.create_check_constraint(
        "owner_note_length", "intake_requests", "owner_note IS NULL OR length(owner_note) <= 4000"
    )
    op.create_table(
        "intake_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=UUID_PK, nullable=False),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("from_status", sa.Text(), nullable=True),
        sa.Column("to_status", sa.Text(), nullable=False),
        sa.Column("public_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_intake_events"),
        sa.ForeignKeyConstraint(
            ["request_id"],
            ["intake_requests.id"],
            name="fk_intake_events_request_id_intake_requests",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            name="fk_intake_events_actor_id_users",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "to_status IN (" + ", ".join(repr(s) for s in STATUSES) + ")", name="to_status_valid"
        ),
        sa.CheckConstraint(
            "public_note IS NULL OR length(public_note) BETWEEN 1 AND 1000",
            name="public_note_length",
        ),
    )
    op.create_index("idx_intake_events_request", "intake_events", ["request_id", "id"])


def downgrade() -> None:
    op.drop_table("intake_events")
    # نام کوتاه: قرارداد نام‌گذاری `ck_intake_requests_` را خودش پیش می‌گذارد.
    op.drop_constraint("owner_note_length", "intake_requests", type_="check")
    op.drop_column("intake_requests", "owner_note")
