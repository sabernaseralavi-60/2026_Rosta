"""0027 — اعلان تغییر وضعیت و پیام درخواست ورودی به مشتریِ دارای حساب

مرجع: ADR-0013، ADR-0032 («پیامدها»)، ADR-0033.

پس از ۰۰۲۶ اجرا می‌شود. فقط دو الگوی پیام؛ جدولی عوض نمی‌شود. ایمیل و پیام‌رسان از
الگوی `IN_APP` ساخته می‌شوند و پیامکی نیست (`allow_sms` نیست).

Revision ID: 0027
Revises: 0026
Create Date: 2026-09-28
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0027"
down_revision: str | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (کد، کانال، عنوان، متن، متغیرها) — قواعد نگارش §14.7، مانند ۰۰۱۷.
TEMPLATES: tuple[tuple[str, str, str | None, str, tuple[str, ...]], ...] = (
    (
        "INTAKE_STATUS_CHANGED",
        "IN_APP",
        "وضعیت درخواست {{code}}: {{status}}",
        "وضعیت درخواستت با کد {{code}} به «{{status}}» تغییر کرد.{{note}}",
        ("code", "status", "note"),
    ),
    (
        "INTAKE_MESSAGE",
        "IN_APP",
        "پیام دربارهٔ درخواست {{code}}",
        "دربارهٔ درخواستت با کد {{code}} پیام تازه‌ای هست: «{{note}}»",
        ("code", "note"),
    ),
)


def upgrade() -> None:
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
