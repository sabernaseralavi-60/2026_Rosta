"""0017 — اعلان فعال شدن و رد اشتراک

مرجع: ADR-0009، ADR-0019، FR-MSG-03.
وظیفهٔ نقشهٔ راه: §13.6 (ناحیهٔ استاد و فعال‌سازی اشتراک در پنل).

پس از ۰۰۱۶ اجرا می‌شود. فقط سه الگوی پیام: کاربری که پول داده تا امروز
هیچ خبری از فعال شدن اشتراکش نمی‌گرفت، و درخواست ردشده بی‌صدا «لغو شده»
می‌شد. جدولی عوض نمی‌شود — دلیل رد در `audit_logs` می‌نشیند (ADR-0019).

Revision ID: 0017
Revises: 0016
Create Date: 2026-09-24
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (کد، کانال، عنوان، متن، متغیرها) — قواعد نگارش §14.7، مانند ۰۰۱۶.
TEMPLATES: tuple[tuple[str, str, str | None, str, tuple[str, ...]], ...] = (
    (
        "SUBSCRIPTION_ACTIVATED",
        "IN_APP",
        "اشتراک «{{plan}}» فعال شد",
        "پرداختت تأیید شد و اشتراک «{{plan}}» تا {{ends_on}} فعال است. محتوای"
        " قفل کتابخانه حالا باز است.",
        ("plan", "ends_on"),
    ),
    (
        "SUBSCRIPTION_ACTIVATED",
        "SMS",
        None,
        "اشتراک «{{plan}}» سیلپ تا {{ends_on}} فعال شد.",
        ("plan", "ends_on"),
    ),
    (
        "SUBSCRIPTION_REJECTED",
        "IN_APP",
        "درخواست اشتراک «{{plan}}» تأیید نشد",
        "درخواست اشتراک «{{plan}}» تأیید نشد: {{reason}}. اگر پرداخت کرده‌ای،"
        " کد پیگیری را برای پشتیبانی بفرست.",
        ("plan", "reason"),
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
