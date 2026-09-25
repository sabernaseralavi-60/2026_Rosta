"""0019 — اعلان درخواست بازتاب پایان پروژه

مرجع: ADR-0024 (برش الف)، FR-PRJ-08، §7.13 «درخواست بازتاب از اعضا».

پس از ۰۰۱۸ اجرا می‌شود. فقط یک الگوی پیام؛ جدول `project_reflections` از ۰۰۱۱
هست. بی این اعلان، عضوی که پروژه‌اش بسته شد از وجود فرم بازتاب خبردار نمی‌شود.

Revision ID: 0019
Revises: 0018
Create Date: 2026-09-24
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (کد، کانال، عنوان، متن، متغیرها) — قواعد نگارش §14.7، مانند ۰۰۱۸.
TEMPLATES: tuple[tuple[str, str, str | None, str, tuple[str, ...]], ...] = (
    (
        "REFLECTION_REQUESTED",
        "IN_APP",
        "پروژهٔ «{{project}}» بسته شد؛ بازتابت را بنویس",
        "پروژهٔ «{{project}}» بسته شد. چند جمله بنویس که چه آموختی و چه چیزش سخت"
        " بود. بازتاب فقط خودت می‌بینی. {{reward}}",
        ("project", "reward"),
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
