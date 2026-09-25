"""0021 — سهم دانشجو از فروش تأییدشده

مرجع: ADR-0025، FR-VEN-03، ADR-0007 (ستون‌های عکس‌برداری).

پس از ۰۰۲۰ اجرا می‌شود. دو ستون روی `venture_metrics`: درصد سهم پروژه و ریالِ
آن هنگام تأیید. `projects.rewards` قابل ویرایش است؛ بی عکس‌برداری، تغییر
درصد ماه‌های بسته را جابه‌جا می‌کرد.

Revision ID: 0021
Revises: 0020
Create Date: 2026-09-25
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "venture_metrics"

# ردیف‌های تأییدشدهٔ فروشِ پروژه را از درصد فعلی پروژه پر می‌کند؛ درصد غیرعددی
# یا بیرون از ۰ تا ۱۰۰ بی‌سهم می‌ماند (ADR-0025 بند ۲).
BACKFILL = """
UPDATE venture_metrics AS m
   SET share_percent = p.pct,
       share_rial = floor(m.value * p.pct / 100)
  FROM (
        SELECT id, (rewards ->> 'revenue_share_percent')::numeric AS pct
          FROM projects
         WHERE jsonb_typeof(rewards -> 'revenue_share_percent') = 'number'
           AND (rewards ->> 'revenue_share_percent')::numeric BETWEEN 0 AND 100
       ) AS p
 WHERE m.project_id = p.id
   AND m.metric = 'SALES_AMOUNT'
   AND m.status = 'VERIFIED'
"""


def upgrade() -> None:
    op.add_column(TABLE, sa.Column("share_percent", sa.Numeric(5, 2), nullable=True))
    op.add_column(TABLE, sa.Column("share_rial", sa.BigInteger(), nullable=True))
    op.execute(BACKFILL)
    op.create_check_constraint(
        "ck_venture_metrics_share_pair", TABLE, "(share_percent IS NULL) = (share_rial IS NULL)"
    )
    op.create_check_constraint(
        "ck_venture_metrics_share_percent_range",
        TABLE,
        "share_percent IS NULL OR share_percent BETWEEN 0 AND 100",
    )
    op.create_check_constraint(
        "ck_venture_metrics_share_rial_range",
        TABLE,
        "share_rial IS NULL OR (share_rial >= 0 AND share_rial <= value)",
    )
    op.create_check_constraint(
        "ck_venture_metrics_share_only_verified_project_sales",
        TABLE,
        "share_rial IS NULL OR "
        "(status = 'VERIFIED' AND metric = 'SALES_AMOUNT' AND project_id IS NOT NULL)",
    )


def downgrade() -> None:
    for name in (
        "ck_venture_metrics_share_only_verified_project_sales",
        "ck_venture_metrics_share_rial_range",
        "ck_venture_metrics_share_percent_range",
        "ck_venture_metrics_share_pair",
    ):
        op.drop_constraint(name, TABLE, type_="check")
    op.drop_column(TABLE, "share_rial")
    op.drop_column(TABLE, "share_percent")
