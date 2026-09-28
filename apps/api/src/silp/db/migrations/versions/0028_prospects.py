"""0028 — کد شخصی برای مشتریِ بی‌حساب (`prospects`)

مرجع: ADR-0034، ADR-0030 «منفی / ریسک باقی‌مانده».

مشتریِ بی‌حساب تا اکنون فقط کد پیگیری داشت. حالا اولین درخواستش یک «شخصِ بی‌حساب»
می‌سازد با کد `P-…` از همان دنبالهٔ `person_code_seq` که کاربران دارند؛ پس دو
جدول هرگز کد تکراری نمی‌دهند. وقتی صاحب شمارهٔ (یا ایمیل) همین شخص با OTP وارد شود،
ردیف `user_id` می‌گیرد و کد قدیمی به‌صورت **نام دوم** کاربر می‌ماند؛ کد خود کاربر
عوض نمی‌شود (در Vault و گزارش‌ها آمده است).

Revision ID: 0028
Revises: 0027
Create Date: 2026-09-28
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0028"
down_revision: str | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID_PK = sa.text("uuidv7()")
NOW = sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "prospects",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=UUID_PK, nullable=False),
        sa.Column(
            "person_code", sa.Text(), server_default=sa.text("next_person_code()"), nullable=False
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("mobile", sa.Text(), nullable=True),
        sa.Column("email", postgresql.CITEXT(), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_prospects"),
        sa.UniqueConstraint("person_code", name="uq_prospects_person_code"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_prospects_user_id_users", ondelete="SET NULL"
        ),
        sa.CheckConstraint("person_code ~ '^P-[0-9]{5,}$'", name="person_code_format"),
        sa.CheckConstraint("mobile IS NOT NULL OR email IS NOT NULL", name="contact_required"),
        sa.CheckConstraint(r"mobile IS NULL OR mobile ~ '^09\d{9}$'", name="mobile_format"),
    )
    # یک راه تماس، یک شخص: بی‌این قید، دو درخواستِ هم‌زمان دو کد می‌ساختند.
    op.create_index(
        "uq_prospects_mobile",
        "prospects",
        ["mobile"],
        unique=True,
        postgresql_where=sa.text("mobile IS NOT NULL"),
    )
    op.create_index(
        "uq_prospects_email",
        "prospects",
        ["email"],
        unique=True,
        postgresql_where=sa.text("email IS NOT NULL"),
    )
    op.create_index("idx_prospects_user", "prospects", ["user_id"])
    op.execute("SELECT attach_updated_at('prospects')")

    op.add_column(
        "intake_requests", sa.Column("prospect_id", postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.create_foreign_key(
        "fk_intake_requests_prospect_id_prospects",
        "intake_requests",
        "prospects",
        ["prospect_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("idx_intake_requests_prospect", "intake_requests", ["prospect_id"])

    # درخواست‌های پیشین: برای هر راه تماسِ بی‌کاربر یک شخص بساز. ترتیب زمانی ثبت،
    # ترتیب کد را می‌دهد. موبایل کلید است؛ درخواستِ فقط‌ایمیلی با ایمیل کلید می‌خورد.
    op.execute(
        """
        WITH first_seen AS (
          SELECT DISTINCT ON (contact_mobile)
                 contact_mobile AS mobile, contact_name AS name, created_at, id
            FROM intake_requests
           WHERE user_id IS NULL AND contact_mobile IS NOT NULL
           ORDER BY contact_mobile, created_at, id
        )
        INSERT INTO prospects (mobile, name)
        SELECT f.mobile, f.name FROM first_seen f ORDER BY f.created_at, f.id
        """
    )
    op.execute(
        """
        INSERT INTO prospects (email, name)
        SELECT DISTINCT ON (r.contact_email) r.contact_email, r.contact_name
          FROM intake_requests r
         WHERE r.user_id IS NULL AND r.contact_mobile IS NULL AND r.contact_email IS NOT NULL
           AND NOT EXISTS (SELECT 1 FROM prospects p WHERE p.email = r.contact_email)
         ORDER BY r.contact_email, r.created_at, r.id
        """
    )
    op.execute(
        """
        UPDATE intake_requests r
           SET prospect_id = p.id
          FROM prospects p
         WHERE r.user_id IS NULL
           AND (p.mobile = r.contact_mobile
                OR (r.contact_mobile IS NULL AND p.email = r.contact_email))
        """
    )
    # کسی که از زمان ثبت درخواست، همان راه تماس را تأیید کرده، همین حالا صاحبش است.
    op.execute(
        """
        UPDATE prospects p
           SET user_id = u.id, claimed_at = now()
          FROM users u
         WHERE p.user_id IS NULL AND u.deleted_at IS NULL
           AND ((p.mobile = u.mobile AND u.mobile_verified_at IS NOT NULL)
                OR (p.email = u.email AND u.email_verified_at IS NOT NULL))
        """
    )


def downgrade() -> None:
    op.drop_index("idx_intake_requests_prospect", table_name="intake_requests")
    op.drop_constraint(
        "fk_intake_requests_prospect_id_prospects", "intake_requests", type_="foreignkey"
    )
    op.drop_column("intake_requests", "prospect_id")
    op.drop_table("prospects")
