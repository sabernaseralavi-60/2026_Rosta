"""0018 — اعلان سپردن ارائه، و ویرایش اعلان درس

مرجع: ADR-0020 («هنوز باز»)، ADR-0021، FR-EDU-06، FR-MSG-03.

پس از ۰۰۱۷ اجرا می‌شود. دو کار کوچک:

* دو الگوی پیام: استادی که مدیر آموزشی ارائه‌ای به او سپرده بود تا امروز
  خبری نمی‌گرفت، و استاد قبلی ارائهٔ جابه‌جاشده فقط یک ۴۰۳ می‌دید.
* `announcements.edited_at`: اعلانی که پس از انتشار ویرایش شده باید همین را
  به دانشجو بگوید — «امتحان به شنبه افتاد» با تاریخ انتشار قدیمی گمراه‌کننده است.

Revision ID: 0018
Revises: 0017
Create Date: 2026-09-24
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (کد، کانال، عنوان، متن، متغیرها) — قواعد نگارش §14.7، مانند ۰۰۱۷.
TEMPLATES: tuple[tuple[str, str, str | None, str, tuple[str, ...]], ...] = (
    (
        "OFFERING_ASSIGNED",
        "IN_APP",
        "ارائهٔ «{{course}}» به تو سپرده شد",
        "ارائهٔ «{{course}}» در {{term}} به تو سپرده شد. تنظیمات، هفته‌ها و کد"
        " ثبت‌نام را در بخش «تدریس» ببین؛ اگر پیوندش در منو نیست، یک بار خارج و"
        " دوباره وارد شو.",
        ("course", "term"),
    ),
    (
        "OFFERING_REASSIGNED",
        "IN_APP",
        "ارائهٔ «{{course}}» به استاد دیگری سپرده شد",
        "مدیر آموزشی ارائهٔ «{{course}}» در {{term}} را به {{instructor}} سپرد و"
        " دسترسی تو به آن بسته شد. آزمون‌ها، نمره‌ها و حضور سر جایشان می‌مانند.",
        ("course", "term", "instructor"),
    ),
)


def upgrade() -> None:
    op.add_column(
        "announcements", sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True)
    )
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
    op.drop_column("announcements", "edited_at")
