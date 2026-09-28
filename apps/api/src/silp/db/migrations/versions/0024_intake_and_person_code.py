"""0024 — کد شخصی (Person Code) و درخواست‌های ورودی (مسئله / همکاری)

مرجع: ADR-0030، فایل مشخصات فاز ۰ بندهای ۳، ۲۰ و ۲۳.

۱. `users.person_code` — کد دائمی و یکتای هر فرد (`P-00128`). با تغییر نقش
   (دانشجو ← فارغ‌التحصیل ← مشتری…) عوض نمی‌شود. کاربران موجود به ترتیب
   ثبت‌نام شماره می‌گیرند؛ تازه‌ها از دنبالهٔ `person_code_seq`.
   تابع `next_person_code()` پس از `P-99999` بریده نمی‌شود (`lpad` رقم اضافه را
   می‌برید و کد تکراری می‌ساخت).

۲. `intake_requests` — «مسئله / نیاز» (INTAKE) و «درخواست همکاری»
   (COLLABORATION) از بازدیدکنندهٔ بی‌حساب. اگر شمارهٔ تماس با کاربری یکی
   باشد، به همان فرد وصل می‌شود؛ وگرنه `user_id` تهی می‌ماند و بعداً وصل
   می‌شود. کد پیگیری از دنبالهٔ `intake_code_seq` می‌آید.

Revision ID: 0024
Revises: 0023
Create Date: 2026-09-28
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID_PK = sa.text("uuidv7()")
NOW = sa.text("now()")

KINDS = ("INTAKE", "COLLABORATION")
STATUSES = ("NEW", "IN_REVIEW", "ACCEPTED", "DECLINED", "ARCHIVED")

NEXT_PERSON_CODE = """
CREATE OR REPLACE FUNCTION next_person_code() RETURNS text AS $$
DECLARE n bigint := nextval('person_code_seq');
BEGIN
  RETURN 'P-' || CASE WHEN n < 100000 THEN lpad(n::text, 5, '0') ELSE n::text END;
END;
$$ LANGUAGE plpgsql;
"""


def _in_list(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def upgrade() -> None:
    _person_code()
    _intake_requests()


def _person_code() -> None:
    op.execute("CREATE SEQUENCE person_code_seq START 1")
    op.execute(NEXT_PERSON_CODE)
    op.add_column("users", sa.Column("person_code", sa.Text(), nullable=True))
    op.execute(
        """
        WITH ranked AS (
          SELECT id, row_number() OVER (ORDER BY created_at, id) AS rn FROM users
        )
        UPDATE users u
           SET person_code = 'P-' || CASE WHEN r.rn < 100000
                                          THEN lpad(r.rn::text, 5, '0') ELSE r.rn::text END
          FROM ranked r
         WHERE u.id = r.id
        """
    )
    op.execute("SELECT setval('person_code_seq', (SELECT count(*) FROM users) + 1, false)")
    op.execute("ALTER TABLE users ALTER COLUMN person_code SET DEFAULT next_person_code()")
    op.alter_column("users", "person_code", nullable=False)
    op.create_unique_constraint("uq_users_person_code", "users", ["person_code"])
    op.create_check_constraint("person_code_format", "users", "person_code ~ '^P-[0-9]{5,}$'")


def _intake_requests() -> None:
    op.execute("CREATE SEQUENCE intake_code_seq START 1001")
    op.create_table(
        "intake_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=UUID_PK, nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("tracking_code", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'NEW'"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("contact_name", sa.Text(), nullable=False),
        sa.Column("contact_mobile", sa.Text(), nullable=True),
        sa.Column("contact_email", postgresql.CITEXT(), nullable=True),
        sa.Column("organization", sa.Text(), nullable=True),
        sa.Column("need_type", sa.Text(), nullable=True),
        sa.Column(
            "services",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'::text[]"),
            nullable=False,
        ),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_intake_requests"),
        sa.UniqueConstraint("tracking_code", name="uq_intake_requests_tracking_code"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_intake_requests_user_id_users",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(_in_list("kind", KINDS), name="kind_valid"),
        sa.CheckConstraint(_in_list("status", STATUSES), name="status_valid"),
        sa.CheckConstraint(
            "contact_mobile IS NOT NULL OR contact_email IS NOT NULL",
            name="contact_required",
        ),
        sa.CheckConstraint(
            r"contact_mobile IS NULL OR contact_mobile ~ '^09\d{9}$'",
            name="mobile_format",
        ),
        sa.CheckConstraint("length(summary) BETWEEN 5 AND 4000", name="summary_length"),
    )
    op.create_index(
        "idx_intake_requests_inbox",
        "intake_requests",
        ["kind", "status", sa.text("created_at DESC")],
    )
    op.create_index("idx_intake_requests_user", "intake_requests", ["user_id"])
    op.create_index("idx_intake_requests_mobile", "intake_requests", ["contact_mobile"])
    op.execute("SELECT attach_updated_at('intake_requests')")


def downgrade() -> None:
    op.drop_table("intake_requests")
    op.execute("DROP SEQUENCE IF EXISTS intake_code_seq")
    # نام کوتاه: قرارداد نام‌گذاری `ck_users_` را خودش پیش می‌گذارد.
    op.drop_constraint("person_code_format", "users", type_="check")
    op.drop_constraint("uq_users_person_code", "users", type_="unique")
    op.drop_column("users", "person_code")
    op.execute("DROP FUNCTION IF EXISTS next_person_code()")
    op.execute("DROP SEQUENCE IF EXISTS person_code_seq")
