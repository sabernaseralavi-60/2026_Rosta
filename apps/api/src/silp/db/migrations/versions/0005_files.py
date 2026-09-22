"""0005 — فایل: جدول `files`

مرجع: PRD §4.9.
وظیفهٔ نقشهٔ راه: بخشی از M2-01 (پیش‌نیاز M2-08).

**پس از ۰۱۰ اجرا می‌شود، نه پیش از ۰۰۶.** §4.10 این جدول را پیش از
آموزش گذاشته بود، ولی چون ۰۱۰ جلو آمد (ADR-0004) زنجیره از ۰۱۰ ادامه
پیدا می‌کند. شمارهٔ فایل می‌گوید چه چیزی داخلش است، `down_revision`
می‌گوید کِی اجرا می‌شود.

هیچ جدولی در ۰۱۰ به `files` ارجاع نمی‌دهد، پس این ترتیب چیزی را
نمی‌شکند؛ `deliverable_files`، `project_messages.file_id` و منابع درس
همگی بعد از این می‌آیند.

Revision ID: 0005
Revises: 0010
Create Date: 2026-09-22
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID_PK = sa.text("uuidv7()")
NOW = sa.text("now()")

SCAN_STATUSES = ("PENDING", "CLEAN", "INFECTED", "SKIPPED")


def upgrade() -> None:
    op.create_table(
        "files",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=UUID_PK, nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("bucket", sa.Text(), nullable=False),
        sa.Column("original_name", sa.Text(), nullable=False),
        sa.Column("content_type", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("checksum_sha256", sa.Text(), nullable=True),
        sa.Column("uploaded_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("scan_status", sa.Text(), server_default=sa.text("'PENDING'"), nullable=False),
        # `purpose` در §4.9 نیامده ولی قرارداد §5.9 آن را می‌گیرد؛ بدون
        # ذخیره‌اش نمی‌توان هنگام `complete` سقف حجم درست را اعمال کرد.
        sa.Column("purpose", sa.Text(), nullable=False),
        # تا وقتی آپلود تمام نشده، فایل قابل استناد نیست (§5.9).
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_files"),
        sa.UniqueConstraint("storage_key", name="uq_files_storage_key"),
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"], name="fk_files_uploaded_by_users"),
        sa.CheckConstraint("size_bytes > 0", name="ck_files_size_positive"),
        sa.CheckConstraint(
            "scan_status IN ('PENDING', 'CLEAN', 'INFECTED', 'SKIPPED')",
            name="ck_files_scan_status_valid",
        ),
    )
    op.create_index("idx_files_uploader", "files", ["uploaded_by", sa.text("created_at DESC")])
    # صف اسکن: فایل‌های تکمیل‌شده‌ای که هنوز بررسی نشده‌اند.
    op.create_index(
        "idx_files_scan_queue",
        "files",
        ["created_at"],
        postgresql_where=sa.text("scan_status = 'PENDING' AND uploaded_at IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_table("files")
