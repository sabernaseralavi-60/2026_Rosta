"""0013 — اعلان: مرکز اعلان، ترجیحات، صف ارسال (Outbox) و الگوهای پیام

مرجع: PRD §4.9، §7.10، §14.7، FR-MSG-01/02/03.
وظیفهٔ نقشهٔ راه: M6-01.

D-08: هیچ فراخوانی خارجی داخل تراکنش دیتابیس نیست. اعلان و ردیف‌های صف
در **همان** تراکنشِ رویداد درج می‌شوند و کارگر پس از commit می‌فرستد.

انحراف‌ها از §4.9، همه در ADR-0013:

* `notifications.kind_group` — فیلتر مرکز اعلان بر اساس دسته بدون
  نگاشت کد در هر کوئری.
* `notifications.dedup_key` + ایندکس یکتای جزئی — §7.11: «اجرای دوبارهٔ
  یک کار نباید اعلان تکراری بسازد». یادآوری مهلت و خلاصهٔ هفتگی با این
  کلید بی‌اثر در تکرار می‌شوند.
* `notifications.archived_at` — §4.12 «خوانده‌شده، ۹۰ روز، سپس آرشیو».
* قید `action_url_internal` — نشانی اقدام فقط مسیر داخلی است؛ اعلان
  نباید بتواند کاربر را به دامنهٔ دیگری بفرستد.
* `outbox_messages.priority` و `user_id` — ساعت آرام در تلاش مجدد هم
  رعایت می‌شود، و مدیر صف را بر اساس کاربر می‌بیند.
* `SENDING` در ایندکس ارسال — پیام برداشته‌شده «اجاره» دارد
  (`next_attempt_at`)؛ اگر کارگر وسط ارسال بمیرد، پس از پایان اجاره
  دوباره برداشته می‌شود.
* جدول تازهٔ `user_channels` — تلگرام و ایتا نشانی‌ای ندارند که در
  `users` باشد؛ شناسهٔ گفت‌وگو پس از پیوند دادن حساب اینجا می‌نشیند.

Revision ID: 0013
Revises: 0012
Create Date: 2026-09-23
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID_PK = sa.text("uuidv7()")
NOW = sa.text("now()")
TRUE = sa.text("true")
ZERO = sa.text("0")

GROUPS = ("COURSE", "PROJECT", "SOCIAL", "SYSTEM")
PRIORITIES = ("LOW", "NORMAL", "IMPORTANT", "URGENT")
CHANNELS = ("IN_APP", "EMAIL", "SMS", "TELEGRAM", "EITAA", "WHATSAPP")
EXTERNAL_CHANNELS = ("EMAIL", "SMS", "TELEGRAM", "EITAA", "WHATSAPP")
LINKABLE_CHANNELS = ("TELEGRAM", "EITAA", "WHATSAPP")
OUTBOX_STATUSES = ("QUEUED", "SENDING", "SENT", "FAILED", "DEAD")


def _in_list(column: str, values: tuple[str, ...]) -> str:
    joined = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({joined})"


def _array(values: tuple[str, ...]) -> str:
    joined = ", ".join(f"'{v}'" for v in values)
    return f"ARRAY[{joined}]::text[]"


# ── دادهٔ اولیهٔ الگوها — §14.7 ─────────────────────────────────────────
# (کد، کانال، عنوان، متن، متغیرها)
#
# قواعد نگارش §14.7: لحن دوم‌شخص مفرد، پیامک ≤ ۷۰ نویسه (یک بخش فارسی)،
# و هر پیام یا یک اقدام دارد یا فقط خبر است. پیامک لینک ندارد؛ لینک
# پیام را دو بخشی و هزینه را دو برابر می‌کند. ایمیل، تلگرام و ایتا اگر
# الگوی اختصاصی نداشته باشند، از الگوی `IN_APP` به‌علاوهٔ لینک ساخته
# می‌شوند (`silp.services.outbox_service`).
#
# `name` و `link` در همهٔ الگوها مجازند. هم‌ترازی این جدول با
# `silp.domain.notifications.catalog` را تست
# `test_seeded_templates_match_catalog` می‌پاید.
TEMPLATES: tuple[tuple[str, str, str | None, str, tuple[str, ...]], ...] = (
    # ── دروس ───────────────────────────────────────────────────────────
    (
        "ENROLLMENT_REQUESTED",
        "IN_APP",
        "درخواست ثبت‌نام در «{{course}}»",
        "{{student}} می‌خواهد در درس «{{course}}» ثبت‌نام کند و منتظر تأیید توست.",
        ("student", "course"),
    ),
    (
        "ENROLLMENT_APPROVED",
        "IN_APP",
        "ثبت‌نامت تأیید شد",
        "ثبت‌نام تو در درس «{{course}}» تأیید شد. محتوای درس حالا باز است.",
        ("course",),
    ),
    ("ENROLLMENT_APPROVED", "SMS", None, "ثبت‌نامت در «{{course}}» تأیید شد.", ("course",)),
    (
        "ENROLLMENT_REJECTED",
        "IN_APP",
        "ثبت‌نامت تأیید نشد",
        "درخواست ثبت‌نام تو در درس «{{course}}» تأیید نشد. برای جزئیات با استاد درس در تماس باش.",
        ("course",),
    ),
    (
        "WEEK_PUBLISHED",
        "IN_APP",
        "هفتهٔ {{week}} «{{course}}» منتشر شد",
        "محتوای هفتهٔ {{week}} درس «{{course}}» منتشر شد: {{title}}",
        ("course", "week", "title"),
    ),
    (
        "QUIZ_OPENED",
        "IN_APP",
        "آزمون «{{quiz}}» باز شد",
        "آزمون «{{quiz}}» درس «{{course}}» باز شد. مهلت: {{closes_at}}",
        ("course", "quiz", "closes_at"),
    ),
    (
        "QUIZ_OPENED",
        "SMS",
        None,
        "آزمون «{{quiz}}» باز شد. مهلت: {{closes_at}}",
        ("course", "quiz", "closes_at"),
    ),
    (
        "QUIZ_CLOSING",
        "IN_APP",
        "{{days}} روز تا بسته شدن «{{quiz}}»",
        "هنوز در آزمون «{{quiz}}» درس «{{course}}» شرکت نکرده‌ای. مهلت: {{closes_at}}",
        ("course", "quiz", "days", "closes_at"),
    ),
    (
        "QUIZ_CLOSING",
        "SMS",
        None,
        "یادآوری: آزمون «{{quiz}}» تا {{days}} روز دیگر بسته می‌شود.",
        ("course", "quiz", "days", "closes_at"),
    ),
    (
        "QUIZ_RESULT",
        "IN_APP",
        "نتیجهٔ «{{quiz}}» آمد",
        "نتیجهٔ «{{quiz}}»: {{score}} از {{total}}",
        ("quiz", "score", "total"),
    ),
    (
        "APPEAL_RESOLVED",
        "IN_APP",
        "اعتراضت بررسی شد",
        "اعتراض تو به نمرهٔ «{{quiz}}» بررسی شد: {{outcome}}",
        ("quiz", "outcome"),
    ),
    (
        "ANNOUNCEMENT_POSTED",
        "IN_APP",
        "{{course}}: {{title}}",
        "{{excerpt}}",
        ("course", "title", "excerpt"),
    ),
    (
        "ANNOUNCEMENT_POSTED",
        "SMS",
        None,
        "اعلان «{{course}}»: {{title}}",
        ("course", "title", "excerpt"),
    ),
    # ── پروژه‌ها ────────────────────────────────────────────────────────
    (
        "APPLICATION_SUBMITTED",
        "IN_APP",
        "درخواست پیوستن تازه",
        "{{applicant}} می‌خواهد به پروژهٔ «{{project}}» بپیوندد.",
        ("project", "applicant"),
    ),
    (
        "APPLICATION_ACCEPTED",
        "IN_APP",
        "درخواستت پذیرفته شد",
        "تبریک! درخواست تو برای پروژهٔ «{{project}}» پذیرفته شد. فضای کاری تیم حالا باز است.",
        ("project",),
    ),
    (
        "APPLICATION_ACCEPTED",
        "SMS",
        None,
        "تبریک! درخواستت برای «{{project}}» پذیرفته شد.",
        ("project",),
    ),
    (
        "APPLICATION_REJECTED",
        "IN_APP",
        "درخواستت پذیرفته نشد",
        "درخواست تو برای «{{project}}» پذیرفته نشد. {{reason}}",
        ("project", "reason"),
    ),
    (
        "APPLICATION_WAITLISTED",
        "IN_APP",
        "در فهرست انتظار هستی",
        "درخواست تو برای «{{project}}» در فهرست انتظار است."
        " اگر جایی در تیم باز شود، خبرت می‌کنیم.",
        ("project",),
    ),
    (
        "DELIVERABLE_SUBMITTED",
        "IN_APP",
        "تحویل تازه در «{{project}}»",
        "{{submitter}} تحویل مرحلهٔ «{{milestone}}» را فرستاد و منتظر بررسی توست.",
        ("project", "milestone", "submitter"),
    ),
    (
        "DELIVERABLE_APPROVED",
        "IN_APP",
        "تحویل «{{milestone}}» تأیید شد",
        "تحویل «{{milestone}}» در پروژهٔ «{{project}}» تأیید شد و {{points}} امتیاز گرفتی.",
        ("project", "milestone", "points"),
    ),
    (
        "DELIVERABLE_APPROVED",
        "SMS",
        None,
        "تحویل «{{milestone}}» تأیید شد و {{points}} امتیاز گرفتی.",
        ("project", "milestone", "points"),
    ),
    (
        "DELIVERABLE_CHANGES",
        "IN_APP",
        "«{{milestone}}» اصلاح لازم دارد",
        "برای «{{milestone}}» اصلاحاتی لازم است: {{feedback}}",
        ("project", "milestone", "feedback"),
    ),
    (
        "DELIVERABLE_CHANGES",
        "SMS",
        None,
        "«{{milestone}}» اصلاح لازم دارد. بازخورد را در سابِر ببین.",
        ("project", "milestone", "feedback"),
    ),
    (
        "DELIVERABLE_REJECTED",
        "IN_APP",
        "تحویل «{{milestone}}» رد شد",
        "تحویل «{{milestone}}» در پروژهٔ «{{project}}» رد شد: {{feedback}}",
        ("project", "milestone", "feedback"),
    ),
    (
        "DELIVERABLE_REJECTED",
        "SMS",
        None,
        "تحویل «{{milestone}}» رد شد. بازخورد را در سابِر ببین.",
        ("project", "milestone", "feedback"),
    ),
    (
        "DEADLINE_REMINDER",
        "IN_APP",
        "{{days}} روز تا مهلت «{{milestone}}»",
        "یادآوری: مهلت «{{milestone}}» در پروژهٔ «{{project}}» تا {{days}} روز دیگر"
        " ({{due_on}}) است.",
        ("project", "milestone", "days", "due_on"),
    ),
    (
        "DEADLINE_REMINDER",
        "SMS",
        None,
        "یادآوری: مهلت «{{milestone}}» تا {{days}} روز دیگر.",
        ("project", "milestone", "days", "due_on"),
    ),
    (
        "PROJECT_STALLED",
        "IN_APP",
        "«{{project}}» بی‌تحرک مانده",
        "پروژهٔ «{{project}}» {{days}} روز است بی‌تحرک مانده.",
        ("project", "days"),
    ),
    # ── نشان ───────────────────────────────────────────────────────────
    ("BADGE_AWARDED", "IN_APP", "نشان تازه!", "نشان «{{badge}}» را گرفتی!", ("badge",)),
    # ── حساب و سامانه ──────────────────────────────────────────────────
    (
        "WELCOME",
        "IN_APP",
        "به سابِر خوش آمدی",
        "به سامانهٔ سابِر خوش آمدی! نیمرخت را تکمیل کن تا پروژه‌های مناسبت را ببینی.",
        (),
    ),
    (
        "SESSIONS_REVOKED",
        "IN_APP",
        "همهٔ نشست‌هایت بسته شد",
        "یک نشست قدیمی دوباره به کار رفت و برای امنیت، همهٔ نشست‌های تو بسته شد."
        " اگر این کار تو نبود، به پشتیبانی خبر بده.",
        (),
    ),
    (
        "SESSIONS_REVOKED",
        "SMS",
        None,
        "سابِر: به دلیل فعالیت مشکوک همهٔ نشست‌هایت بسته شد.",
        (),
    ),
    (
        "CHANNEL_LINKED",
        "IN_APP",
        "{{channel}} وصل شد",
        "از این پس اعلان‌های سابِر را در {{channel}} هم می‌گیری. هر وقت خواستی از تنظیمات قطعش کن.",
        ("channel",),
    ),
    (
        "WEEKLY_DIGEST",
        "IN_APP",
        "خلاصهٔ هفتهٔ تو",
        "این هفته {{points}} امتیاز گرفتی. {{deadlines}} مهلت در هفتهٔ پیش رو داری"
        " و {{unread}} اعلان خوانده‌نشده.",
        ("points", "deadlines", "unread"),
    ),
    (
        "WEEKLY_DIGEST",
        "EMAIL",
        "خلاصهٔ هفتهٔ تو در سابِر",
        "سلام {{name}}،\n\n"
        "امتیاز این هفته: {{points}}\n"
        "مهلت‌های هفتهٔ پیش رو: {{deadlines}}\n"
        "اعلان‌های خوانده‌نشده: {{unread}}\n\n"
        "داشبوردت: {{link}}\n\n"
        "— سامانهٔ سابِر",
        ("points", "deadlines", "unread"),
    ),
    (
        "WEEKLY_DIGEST_TEACHER",
        "IN_APP",
        "خلاصهٔ هفتهٔ کلاس‌ها",
        "{{reviews}} مورد منتظر بررسی توست، {{enrollments}} درخواست ثبت‌نام در انتظار تأیید"
        " و {{at_risk}} پروژهٔ در خطر.",
        ("reviews", "enrollments", "at_risk"),
    ),
    (
        "OUTBOX_DEAD",
        "IN_APP",
        "پیام‌هایی ارسال نشدند",
        "{{count}} پیام پس از ۵ بار تلاش ارسال نشد. صف ارسال را بررسی کن.",
        ("count",),
    ),
    # ── الگوی مستقیم (بدون اعلان) ─────────────────────────────────────
    ("CHANNEL_VERIFY", "EITAA", None, "کد اتصال ایتا به سابِر: {{code}}", ("code",)),
)


def upgrade() -> None:
    _create_notifications()
    _create_preferences()
    _create_user_channels()
    _create_outbox()
    _create_templates()


def _create_notifications() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=UUID_PK, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        # فراتر از §4.9 — ADR-0013.
        sa.Column("kind_group", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("action_url", sa.Text(), nullable=True),
        sa.Column("priority", sa.Text(), server_default=sa.text("'NORMAL'"), nullable=False),
        sa.Column(
            "data",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        # فراتر از §4.9 — ADR-0013. کلید بی‌اثری کارهای زمان‌بندی‌شده.
        sa.Column("dedup_key", sa.Text(), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        # فراتر از §4.9 — §4.12 «۹۰ روز، سپس آرشیو».
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_notifications"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_notifications_user_id_users", ondelete="CASCADE"
        ),
        sa.CheckConstraint(_in_list("priority", PRIORITIES), name="priority_valid"),
        sa.CheckConstraint(_in_list("kind_group", GROUPS), name="kind_group_valid"),
        sa.CheckConstraint("jsonb_typeof(data) = 'object'", name="data_is_object"),
        # فقط مسیر داخلی: `/projects/…`، نه `https://…` و نه `//evil.example`.
        sa.CheckConstraint(
            "action_url IS NULL OR (action_url LIKE '/%' AND action_url NOT LIKE '//%')",
            name="action_url_internal",
        ),
        sa.CheckConstraint("length(btrim(title)) > 0", name="title_not_blank"),
    )
    # §4.9 — شمارندهٔ زنگوله.
    op.create_index(
        "idx_notifications_unread",
        "notifications",
        ["user_id", sa.text("created_at DESC")],
        postgresql_where=sa.text("read_at IS NULL AND archived_at IS NULL"),
    )
    # فهرست کرسری مرکز اعلان — uuidv7 به ترتیب زمان است.
    op.create_index(
        "idx_notifications_feed",
        "notifications",
        ["user_id", sa.text("id DESC")],
        postgresql_where=sa.text("archived_at IS NULL"),
    )
    op.create_index(
        "idx_notifications_dedup",
        "notifications",
        ["user_id", "dedup_key"],
        unique=True,
        postgresql_where=sa.text("dedup_key IS NOT NULL"),
    )


def _create_preferences() -> None:
    op.create_table(
        "notification_preferences",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind_group", sa.Text(), nullable=False),
        sa.Column(
            "channels",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{IN_APP}'"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("user_id", "kind_group", name="pk_notification_preferences"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_notification_preferences_user_id_users",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(_in_list("kind_group", GROUPS), name="kind_group_valid"),
        sa.CheckConstraint(f"channels <@ {_array(CHANNELS)}", name="channels_valid"),
        # مرکز اعلان خاموش‌شدنی نیست — `catalog.normalize_channels`.
        sa.CheckConstraint("'IN_APP' = ANY(channels)", name="in_app_always"),
    )
    op.execute(
        "CREATE TRIGGER trg_notification_preferences_updated BEFORE UPDATE"
        " ON notification_preferences FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )


def _create_user_channels() -> None:
    op.create_table(
        "user_channels",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel", sa.Text(), nullable=False),
        # شناسهٔ گفت‌وگو در پیام‌رسان. تا پیش از تأیید ممکن است خالی باشد.
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        # کد پیوند فقط به‌صورت چکیده نگه داشته می‌شود — مثل OTP.
        sa.Column("link_code_hash", sa.Text(), nullable=True),
        sa.Column("link_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("link_attempts", sa.SmallInteger(), server_default=ZERO, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("user_id", "channel", name="pk_user_channels"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_user_channels_user_id_users", ondelete="CASCADE"
        ),
        sa.CheckConstraint(_in_list("channel", LINKABLE_CHANNELS), name="channel_valid"),
        sa.CheckConstraint(
            "verified_at IS NULL OR address IS NOT NULL", name="verified_has_address"
        ),
        sa.CheckConstraint(
            "(link_code_hash IS NULL) = (link_expires_at IS NULL)", name="link_code_complete"
        ),
    )
    # یک حساب تلگرام به دو کاربر وصل نمی‌شود — وگرنه اعلان‌های یکی به دیگری می‌رسد.
    op.create_index(
        "idx_user_channels_address",
        "user_channels",
        ["channel", "address"],
        unique=True,
        postgresql_where=sa.text("verified_at IS NOT NULL"),
    )
    op.create_index(
        "idx_user_channels_link_code",
        "user_channels",
        ["link_code_hash"],
        unique=True,
        postgresql_where=sa.text("link_code_hash IS NOT NULL"),
    )
    op.execute(
        "CREATE TRIGGER trg_user_channels_updated BEFORE UPDATE ON user_channels"
        " FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )


def _create_outbox() -> None:
    op.create_table(
        "outbox_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=UUID_PK, nullable=False),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("recipient", sa.Text(), nullable=False),
        sa.Column("template", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("notification_id", postgresql.UUID(as_uuid=True), nullable=True),
        # فراتر از §4.9 — ADR-0013.
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("priority", sa.Text(), server_default=sa.text("'NORMAL'"), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'QUEUED'"), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default=ZERO, nullable=False),
        sa.Column(
            "next_attempt_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False
        ),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("provider_message_id", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_outbox_messages"),
        sa.ForeignKeyConstraint(
            ["notification_id"],
            ["notifications.id"],
            name="fk_outbox_messages_notification_id_notifications",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_outbox_messages_user_id_users", ondelete="CASCADE"
        ),
        sa.CheckConstraint(_in_list("channel", EXTERNAL_CHANNELS), name="channel_valid"),
        sa.CheckConstraint(_in_list("status", OUTBOX_STATUSES), name="status_valid"),
        sa.CheckConstraint(_in_list("priority", PRIORITIES), name="priority_valid"),
        sa.CheckConstraint("attempts >= 0", name="attempts_not_negative"),
        sa.CheckConstraint("jsonb_typeof(payload) = 'object'", name="payload_is_object"),
        sa.CheckConstraint("(status = 'SENT') = (sent_at IS NOT NULL)", name="sent_at_matches"),
    )
    # §7.10 — کارگر فقط این‌ها را می‌خواند. `SENDING` با اجارهٔ منقضی هم.
    op.create_index(
        "idx_outbox_dispatch",
        "outbox_messages",
        ["next_attempt_at"],
        postgresql_where=sa.text("status IN ('QUEUED','FAILED','SENDING')"),
    )
    op.create_index("idx_outbox_status", "outbox_messages", ["status", sa.text("created_at DESC")])
    op.create_index("idx_outbox_notification", "outbox_messages", ["notification_id"])


def _create_templates() -> None:
    op.create_table(
        "message_templates",
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("subject", sa.Text(), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "variables",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), server_default=TRUE, nullable=False),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("code", "channel", name="pk_message_templates"),
        sa.ForeignKeyConstraint(
            ["updated_by"], ["users.id"], name="fk_message_templates_updated_by_users"
        ),
        sa.CheckConstraint(_in_list("channel", CHANNELS), name="channel_valid"),
        sa.CheckConstraint("length(btrim(body)) > 0", name="body_not_blank"),
    )
    op.execute(
        "CREATE TRIGGER trg_message_templates_updated BEFORE UPDATE ON message_templates"
        " FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
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
                "variables": ["name", "link", *variables]
                if code != "CHANNEL_VERIFY"
                else list(variables),
            }
            for code, channel, subject, body, variables in TEMPLATES
        ],
    )


def downgrade() -> None:
    op.drop_table("message_templates")
    op.drop_table("outbox_messages")
    op.drop_table("user_channels")
    op.drop_table("notification_preferences")
    op.drop_table("notifications")
