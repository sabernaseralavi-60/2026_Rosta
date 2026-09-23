"""0016 — مدیریت: لاگ حسابرسی فقط‌افزودنی، و ابطال گواهی

مرجع: PRD §4.9، FR-ADM-01/02، FR-PRJ-08، FR-PROF-03، §6.5.
وظیفهٔ نقشهٔ راه: M7-11 و M7-12.

پس از ۰۰۱۵ اجرا می‌شود. همه در ADR-0017:

* جدول `audit_logs` — «فقط افزودنی؛ حتی مدیر نمی‌تواند تغییرش دهد». `REVOKE`
  §4.9 مالک جدول را محدود نمی‌کند و اپ با همان مالک وصل می‌شود، پس تریگر
  `audit_logs_append_only` هر `UPDATE` و `DELETE` را رد می‌کند. کنشگر کلید
  خارجی ندارد: لاگ هفت سال می‌ماند (§4.12) و نباید به ردیفی گره بخورد که
  فرایند رسمی حذف ممکن است پاکش کند.
* ابطال گواهی با کنشگر و دلیل (`revoked_by`، `revoke_reason`)، و یکتایی
  «یک گواهی معتبر برای هر موضوع» — صدور از شنوندهٔ رویداد بی‌اثر می‌شود.
* چهار الگوی اعلان تازه.

`app_settings` و `qa_threads`/`qa_replies` که §4.10 در همین مهاجرت گذاشته،
با ماژول‌هایشان می‌آیند (FR-ADM-03 و FR-EDU-07)؛ جدول بی‌مصرف ساخته نمی‌شود.

Revision ID: 0016
Revises: 0015
Create Date: 2026-09-23
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID_PK = sa.text("uuidv7()")
NOW = sa.text("now()")

# (کد، کانال، عنوان، متن، متغیرها) — قواعد نگارش §14.7، مانند ۰۰۱۵.
TEMPLATES: tuple[tuple[str, str, str | None, str, tuple[str, ...]], ...] = (
    (
        "CERTIFICATE_ISSUED",
        "IN_APP",
        "گواهی تازه: {{title}}",
        "گواهی «{{title}}» به نامت صادر شد. پیوند راستی‌آزمایی‌اش را می‌توانی در" " رزومه بگذاری.",
        ("title",),
    ),
    (
        "CERTIFICATE_REVOKED",
        "IN_APP",
        "گواهی «{{title}}» باطل شد",
        "گواهی «{{title}}» باطل شد: {{reason}}. اگر فکر می‌کنی اشتباه شده، با"
        " پشتیبانی تماس بگیر.",
        ("title", "reason"),
    ),
    (
        "ROLE_GRANTED",
        "IN_APP",
        "نقش تازه: {{role}}",
        "نقش «{{role}}» به حسابت داده شد. بخش‌های تازه در منوی سامانه دیده می‌شوند.",
        ("role",),
    ),
    (
        "ACCOUNT_VIEWED_BY_SUPPORT",
        "IN_APP",
        "پشتیبانی حساب شما را بررسی کرد",
        "{{agent}} برای رسیدگی به درخواست پشتیبانی، حساب شما را فقط در حالت مشاهده"
        " بررسی کرد. هیچ تغییری در حساب داده نشد.",
        ("agent",),
    ),
)


def upgrade() -> None:
    _create_audit_logs()
    _extend_certificates()
    _seed_templates()


def _create_audit_logs() -> None:
    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=UUID_PK, nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("impersonated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("entity_type", sa.Text(), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("before", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("after", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("ip_address", postgresql.INET(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_audit_logs"),
        sa.CheckConstraint("action ~ '^[A-Z][A-Z_]*$'", name="ck_audit_logs_action_code"),
    )
    op.create_index(
        "idx_audit_entity",
        "audit_logs",
        ["entity_type", "entity_id", sa.text("created_at DESC")],
    )
    op.create_index("idx_audit_actor", "audit_logs", ["actor_id", sa.text("created_at DESC")])
    op.create_index("idx_audit_created", "audit_logs", [sa.text("created_at DESC")])
    op.create_index("idx_audit_action", "audit_logs", ["action", sa.text("created_at DESC")])
    op.create_index(
        "idx_audit_impersonator",
        "audit_logs",
        ["impersonated_by", sa.text("created_at DESC")],
        postgresql_where=sa.text("impersonated_by IS NOT NULL"),
    )
    op.execute("REVOKE UPDATE, DELETE ON audit_logs FROM PUBLIC")
    op.execute(
        """
        CREATE FUNCTION audit_logs_append_only() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
          RAISE EXCEPTION 'audit_logs is append-only (FR-ADM-02)'
            USING ERRCODE = 'insufficient_privilege';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER audit_logs_append_only
          BEFORE UPDATE OR DELETE ON audit_logs
          FOR EACH ROW EXECUTE FUNCTION audit_logs_append_only()
        """
    )


def _extend_certificates() -> None:
    op.add_column(
        "certificates", sa.Column("revoked_by", postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.add_column("certificates", sa.Column("revoke_reason", sa.Text(), nullable=True))
    op.create_foreign_key(
        "fk_certificates_revoked_by_users", "certificates", "users", ["revoked_by"], ["id"]
    )
    op.create_check_constraint(
        "ck_certificates_revoke_has_reason",
        "certificates",
        "revoked_at IS NULL OR revoke_reason IS NOT NULL",
    )
    op.create_check_constraint(
        "ck_certificates_public_code_format",
        "certificates",
        "public_code ~ '^[0-9A-Z]{4}-[0-9A-Z]{4}$'",
    )
    op.create_index(
        "uq_certificates_subject",
        "certificates",
        ["user_id", "kind", "subject_id"],
        unique=True,
        postgresql_where=sa.text("revoked_at IS NULL"),
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

    op.drop_index("uq_certificates_subject", table_name="certificates")
    op.drop_constraint("ck_certificates_public_code_format", "certificates", type_="check")
    op.drop_constraint("ck_certificates_revoke_has_reason", "certificates", type_="check")
    op.drop_constraint("fk_certificates_revoked_by_users", "certificates", type_="foreignkey")
    op.drop_column("certificates", "revoke_reason")
    op.drop_column("certificates", "revoked_by")

    op.execute("DROP TRIGGER audit_logs_append_only ON audit_logs")
    op.execute("DROP FUNCTION audit_logs_append_only()")
    op.drop_table("audit_logs")
