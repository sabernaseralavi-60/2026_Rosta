"""0012 — گیمیفیکیشن: قواعد امتیاز، دفتر کل، نمای تجمیعی، نشان

مرجع: PRD §4.8 و §9.
وظیفه‌های نقشهٔ راه: M5-01 (اسکیما)، M5-02 (دادهٔ اولیهٔ قواعد و ۲۱ نشان).

دفتر کل تغییرناپذیر است (D-09): اصلاح امتیاز فقط با **رکورد معکوس**
انجام می‌شود، نه با ویرایش یا حذف. این قاعده اینجا در دیتابیس اعمال
می‌شود، نه فقط در سرویس:

| قاعده | ابزار |
|-------|-------|
| هیچ ردیفی ویرایش نمی‌شود | تریگر `forbid_point_entry_update` |
| یک رویداد، یک امتیاز | ایندکس یکتای جزئی `idx_point_idempotency` |
| هر ردیف حداکثر یک بار معکوس می‌شود | ایندکس یکتای جزئی `idx_point_single_reversal` |
| اصلی مثبت، معکوس منفی | قید `ck_point_entries_sign_matches_kind` |

سه انحراف از §4.8، هر سه در ADR-0012:

* `point_entries.revision` — کلید بی‌اثری §4.8 روی
  `(user, rule, source_type, source_id)` است و ردیف اصلی پس از معکوس شدن
  هم در ایندکس می‌ماند. پس «معکوس کن و دوباره ثبت کن» — که هم §7.12
  (بهترین تلاش آزمون) و هم §9.9 (بازمحاسبه) می‌خواهند — روی همان منبع با
  تصادم ایندکس شکست می‌خورد. شمارهٔ بازنگری جزئی از کلید می‌شود.
* `point_entries.multiplier` — عکس ضریب لحظهٔ اعطا (ADR-0007). بازمحاسبه
  با قاعدهٔ جدید بدون آن ممکن نیست: `۲۴ امتیاز` نمی‌گوید «۳۰ × ۰٫۸» بوده.
* سقف‌ها **تعداد اعطا** هستند، نه امتیاز (`INTEGER`)، و `weekly_cap`
  افزوده شد. جدول §9.2 با خوانش «امتیاز» خودش را نقض می‌کند: `IDEA_SUBMITTED`
  پنج امتیاز دارد و سقف «۳ در روز» — با خوانش امتیاز، هیچ ایده‌ای هرگز
  امتیاز نمی‌گرفت.

Revision ID: 0012
Revises: 0007
Create Date: 2026-09-23
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID_PK = sa.text("uuidv7()")
NOW = sa.text("now()")
TRUE = sa.text("true")
ZERO = sa.text("0")
ONE = sa.text("1")

CATEGORIES = ("LEARNING", "RESEARCH", "STARTUP", "COMMUNITY")
BADGE_TIERS = ("BRONZE", "SILVER", "GOLD", "PLATINUM")


def _in_list(column: str, values: tuple[str, ...]) -> str:
    joined = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({joined})"


# ── دادهٔ مرجع: قواعد امتیاز — §9.2 ─────────────────────────────────────
# (کد، عنوان، دسته، امتیاز پایه، فرمول، سقف روزانه، سقف هفتگی)
#
# قواعد پروژه‌ای (`MILESTONE_APPROVED`، `PROJECT_COMPLETED`) دستهٔ ثابت
# ندارند و از نوع پروژه می‌گیرند (§9.2 «نگاشت نوع پروژه به دسته»). دستهٔ
# ثبت‌شده اینجا فقط پیش‌فرض است؛ سرویس هنگام اعطا آن را بازنویسی می‌کند.
POINT_RULES: tuple[tuple[str, str, str, str, str | None, int | None, int | None], ...] = (
    # LEARNING
    ("RESOURCE_COMPLETED", "تکمیل منبع درسی", "LEARNING", "2", None, 20, None),
    ("QUIZ_ATTEMPTED", "شرکت در آزمون", "LEARNING", "5", "یک‌بار برای هر آزمون", None, None),
    (
        "QUIZ_SCORE",
        "نمرهٔ آزمون",
        "LEARNING",
        "30",
        "30 × (نمره ÷ کل) — فقط بهترین تلاش",
        None,
        None,
    ),
    ("QUIZ_PERFECT", "نمرهٔ کامل آزمون", "LEARNING", "15", "نمره = کل", None, None),
    ("QUIZ_FIRST_TRY", "قبولی در تلاش اول", "LEARNING", "10", "اولین تلاش معتبر، قبول", None, None),
    ("ATTENDANCE_PRESENT", "حضور در جلسه", "LEARNING", "3", None, None, None),
    ("ATTENDANCE_STREAK", "حضور کامل ماه", "LEARNING", "20", "۴ جلسهٔ متوالی بدون غیبت", None, None),
    (
        "WEEK_COMPLETED",
        "تکمیل کامل یک هفته",
        "LEARNING",
        "15",
        "همهٔ منابع الزامی + آزمون هفته",
        None,
        None,
    ),
    ("COURSE_COMPLETED", "اتمام درس", "LEARNING", "100", None, None, None),
    ("REFLECTION_SUBMITTED", "ثبت بازتاب پایانی", "LEARNING", "15", None, None, None),
    # RESEARCH
    ("RESEARCH_L1_APPROVED", "تأیید سطح ۱ پژوهش (مرور ادبیات)", "RESEARCH", "80", None, None, None),
    ("RESEARCH_L2_APPROVED", "تأیید سطح ۲ پژوهش (تحلیل داده)", "RESEARCH", "150", None, None, None),
    (
        "RESEARCH_L3_APPROVED",
        "تأیید سطح ۳ پژوهش (مقالهٔ کنفرانس)",
        "RESEARCH",
        "300",
        None,
        None,
        None,
    ),
    ("RESEARCH_L4_APPROVED", "تأیید سطح ۴ پژوهش (مقالهٔ Q1)", "RESEARCH", "600", None, None, None),
    ("OUTPUT_SUBMITTED", "ارسال مقاله", "RESEARCH", "50", None, None, None),
    (
        "OUTPUT_ACCEPTED",
        "پذیرش مقاله",
        "RESEARCH",
        "200",
        "ضریب چارک: Q1=۲، Q2=۱٫۵، Q3=۱٫۲، Q4=۱",
        None,
        None,
    ),
    ("OUTPUT_PUBLISHED", "انتشار مقاله", "RESEARCH", "100", None, None, None),
    ("TOPIC_PROPOSED", "پیشنهاد موضوع پژوهشی پذیرفته‌شده", "RESEARCH", "30", None, None, None),
    # STARTUP
    ("VENTURE_CREATED", "ثبت کسب‌وکار", "STARTUP", "20", None, None, None),
    ("VENTURE_STAGE_UP", "ارتقای مرحلهٔ بلوغ", "STARTUP", "50", "50 × شمارهٔ مرحله", None, None),
    ("METRIC_CALLS", "تماس فروش تأییدشده", "STARTUP", "1", None, 20, None),
    ("METRIC_MEETINGS", "جلسهٔ تأییدشده", "STARTUP", "5", None, 5, None),
    ("METRIC_LEADS", "سرنخ واجد شرایط", "STARTUP", "3", None, None, None),
    ("METRIC_SALES_COUNT", "فروش انجام‌شده", "STARTUP", "15", None, None, None),
    ("METRIC_SALES_AMOUNT", "مبلغ فروش", "STARTUP", "1", "min(200, ریال ÷ 5,000,000)", None, None),
    ("METRIC_CONTENT", "محتوای منتشرشده", "STARTUP", "8", None, 3, None),
    ("CUSTOMER_RETAINED", "مشتری تکرارشونده", "STARTUP", "25", None, None, None),
    # COMMUNITY
    ("QA_ANSWER_HELPFUL", "پاسخ مفید در پرسش‌وپاسخ", "COMMUNITY", "10", None, None, None),
    ("QA_ANSWER_OFFICIAL_MATCH", "پاسخ تأییدشده توسط استاد", "COMMUNITY", "20", None, None, None),
    ("IDEA_SUBMITTED", "ثبت ایده", "COMMUNITY", "5", None, 3, None),
    ("IDEA_VOTES_10", "ایده به ۱۰ رأی رسید", "COMMUNITY", "25", None, None, None),
    ("IDEA_VOTES_50", "ایده به ۵۰ رأی رسید", "COMMUNITY", "75", None, None, None),
    ("IDEA_PROMOTED", "ارتقای ایده به پروژه یا کسب‌وکار", "COMMUNITY", "100", None, None, None),
    ("TEAM_FORMED", "تشکیل تیم از آگهی", "COMMUNITY", "15", None, None, None),
    ("MENTORED_DELIVERABLE", "بازبینی تحویل‌دادنی به‌عنوان منتور", "COMMUNITY", "10", None, None, 50),
    ("PEER_EVAL_COMPLETED", "تکمیل ارزیابی همتا", "COMMUNITY", "5", None, None, None),
    ("PROFILE_COMPLETED", "تکمیل کامل نیمرخ", "COMMUNITY", "20", None, None, None),
    # پروژه — دسته از نوع پروژه
    ("APPLICATION_ACCEPTED", "پذیرش در پروژه", "COMMUNITY", "10", None, None, None),
    (
        "MILESTONE_APPROVED",
        "تأیید مرحلهٔ پروژه",
        "LEARNING",
        "1",
        "امتیاز مرحله × ضرایب تعدیل §9.3",
        None,
        None,
    ),
    (
        "PROJECT_COMPLETED",
        "تکمیل پروژه",
        "LEARNING",
        "150",
        "150 × (0.7 + 0.15 × دشواری)؛ نوع D نصف",
        None,
        None,
    ),
)


# ── دادهٔ مرجع: نشان‌ها — §9.5 ───────────────────────────────────────────
# (کد، عنوان، شرح شرط، آیکن، رده، معیار)
#
# `icon` نام آیکن در کتابخانهٔ lucide است. معیارها ساختار §9.5 را دارند و
# ارزیاب `silp.domain.gamification.badges` تنها خوانندهٔ آن‌هاست.
def _count(entity: str, n: int, **extra: Any) -> dict[str, Any]:
    return {"type": "COUNT", "entity": entity, "n": n, **extra}


BADGES: tuple[tuple[str, str, str, str, str, dict[str, Any]], ...] = (
    (
        "FIRST_STEP",
        "قدم اول",
        "نیمرخت را کامل کن.",
        "footprints",
        "BRONZE",
        _count("PROFILE_COMPLETED", 1),
    ),
    (
        "QUICK_START",
        "شروع سریع",
        "ظرف ۷ روز از ثبت‌نام، برای اولین پروژه درخواست بده.",
        "zap",
        "BRONZE",
        {"type": "WITHIN_DAYS", "entity": "APPLICATION_SUBMITTED", "days": 7},
    ),
    (
        "PERFECT_QUIZ",
        "بی‌نقص",
        "در یک آزمون نمرهٔ کامل بگیر.",
        "target",
        "BRONZE",
        _count("QUIZ_PERFECT", 1),
    ),
    (
        "SHARP_MIND",
        "ذهن تیز",
        "در ۵ آزمون نمرهٔ کامل بگیر.",
        "brain",
        "SILVER",
        _count("QUIZ_PERFECT", 5),
    ),
    (
        "CONSISTENT",
        "پایدار",
        "۸ هفتهٔ پشت‌سرهم فعالیت امتیازدار داشته باش.",
        "calendar-check",
        "SILVER",
        {"type": "STREAK", "entity": "WEEKLY_ACTIVITY", "n": 8},
    ),
    (
        "FIRST_DELIVERY",
        "اولین تحویل",
        "اولین تحویل‌دادنی‌ات تأیید شود.",
        "package-check",
        "BRONZE",
        _count("DELIVERABLE_APPROVED", 1),
    ),
    (
        "BUILDER",
        "سازنده",
        "۳ پروژه را تا پایان همراهی کن.",
        "hammer",
        "SILVER",
        _count("PROJECT_COMPLETED", 3),
    ),
    (
        "MASTER_BUILDER",
        "معمار",
        "۱۰ پروژه را تا پایان همراهی کن.",
        "building-2",
        "GOLD",
        _count("PROJECT_COMPLETED", 10),
    ),
    (
        "FIRST_SALE",
        "اولین فروش",
        "اولین فروش تأییدشده‌ات را ثبت کن.",
        "badge-dollar-sign",
        "SILVER",
        {"type": "FIRST", "entity": "SALES_AMOUNT", "min_value": 1},
    ),
    (
        "RAINMAKER",
        "باران‌ساز",
        "مجموع فروش تأییدشده‌ات از ۱۰۰ میلیون ریال بگذرد.",
        "cloud-rain",
        "GOLD",
        {"type": "SUM", "entity": "SALES_AMOUNT", "min_value": 100_000_001},
    ),
    (
        "SCHOLAR",
        "پژوهشگر",
        "سطح ۲ مسیر پژوهش (تحلیل داده) را تأیید بگیر.",
        "microscope",
        "SILVER",
        _count("RESEARCH_L2_APPROVED", 1),
    ),
    (
        "PUBLISHED",
        "منتشرشده",
        "یک مقاله‌ات پذیرفته شود.",
        "file-text",
        "GOLD",
        _count("OUTPUT_ACCEPTED", 1),
    ),
    (
        "Q1_AUTHOR",
        "نویسندهٔ Q1",
        "یک مقاله در مجلهٔ Q1 پذیرفته شود.",
        "award",
        "PLATINUM",
        _count("OUTPUT_ACCEPTED", 1, quartile="Q1"),
    ),
    (
        "IDEA_MACHINE",
        "کارخانهٔ ایده",
        "۱۰ ایده ثبت کن.",
        "lightbulb",
        "SILVER",
        _count("IDEA_SUBMITTED", 10),
    ),
    (
        "VISIONARY",
        "آینده‌نگر",
        "ایده‌ات به پروژه یا کسب‌وکار ارتقا یابد.",
        "telescope",
        "GOLD",
        _count("IDEA_PROMOTED", 1),
    ),
    (
        "HELPER",
        "یاریگر",
        "۵ پاسخ مفید در پرسش‌وپاسخ بده.",
        "hand-helping",
        "BRONZE",
        _count("QA_ANSWER_HELPFUL", 5),
    ),
    (
        "MENTOR_BADGE",
        "راهنما",
        "۲۰ تحویل‌دادنی را به‌عنوان منتور بازبینی کن.",
        "compass",
        "GOLD",
        _count("MENTORED_DELIVERABLE", 20),
    ),
    ("TEAM_PLAYER", "هم‌تیمی", "عضو ۳ تیم متفاوت باش.", "users", "SILVER", _count("TEAM_JOINED", 3)),
    (
        "POLYMATH",
        "همه‌فن‌حریف",
        "از هر چهار نوع پروژه دست‌کم یکی را تمام کن.",
        "shapes",
        "PLATINUM",
        {
            "type": "COMPOSITE",
            "all_of": [
                _count("PROJECT_COMPLETED", 1, kind=kind)
                for kind in ("A_VENTURE", "B_RESEARCH", "C_PROBLEM", "D_PERSONAL")
            ],
        },
    ),
    (
        "CITY_BUILDER",
        "شهرساز",
        "گردش‌کار ۸ مرحله‌ای شهر هوشمند را کامل کن.",
        "map",
        "PLATINUM",
        _count("CITY_WORKFLOW_COMPLETED", 1),
    ),
    (
        "NIGHT_OWL",
        "شب‌زنده‌دار",
        "۲۰ فعالیت امتیازدار بین ساعت ۲۳ تا ۴ بامداد.",
        "moon",
        "BRONZE",
        _count("NIGHT_ACTIVITY", 20),
    ),
)


# نام قیدهای CHECK کوتاه داده می‌شود: قرارداد نام‌گذاری `metadata` خودش
# پیشوند `ck_<جدول>_` را می‌افزاید (`db/base.py`)، و نام کامل یعنی
# `ck_point_entries_ck_point_entries_…` در دیتابیس.
def upgrade() -> None:
    _create_point_rules()
    _create_point_entries()
    _create_totals_view()
    _create_badges()
    _create_user_badges()


# ── قواعد ──────────────────────────────────────────────────────────────
def _create_point_rules() -> None:
    op.create_table(
        "point_rules",
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("title_fa", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("base_points", sa.Numeric(6, 2), nullable=False),
        sa.Column("formula", sa.Text(), nullable=True),
        # تعداد اعطا در پنجره، نه امتیاز — ADR-0012.
        sa.Column("daily_cap", sa.Integer(), nullable=True),
        sa.Column("weekly_cap", sa.Integer(), nullable=True),
        sa.Column("term_cap", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=TRUE, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("code", name="pk_point_rules"),
        sa.CheckConstraint(_in_list("category", CATEGORIES), name="category_valid"),
        sa.CheckConstraint("base_points >= 0", name="base_points_not_negative"),
        sa.CheckConstraint(
            "(daily_cap IS NULL OR daily_cap > 0)"
            " AND (weekly_cap IS NULL OR weekly_cap > 0)"
            " AND (term_cap IS NULL OR term_cap > 0)",
            name="caps_positive",
        ),
    )
    op.execute(
        "CREATE TRIGGER trg_point_rules_updated BEFORE UPDATE ON point_rules"
        " FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    op.bulk_insert(
        sa.table(
            "point_rules",
            sa.column("code", sa.Text),
            sa.column("title_fa", sa.Text),
            sa.column("category", sa.Text),
            sa.column("base_points", sa.Numeric),
            sa.column("formula", sa.Text),
            sa.column("daily_cap", sa.Integer),
            sa.column("weekly_cap", sa.Integer),
        ),
        [
            {
                "code": code,
                "title_fa": title,
                "category": category,
                "base_points": base,
                "formula": formula,
                "daily_cap": daily,
                "weekly_cap": weekly,
            }
            for code, title, category, base, formula, daily, weekly in POINT_RULES
        ],
    )


# ── دفتر کل ────────────────────────────────────────────────────────────
def _create_point_entries() -> None:
    op.create_table(
        "point_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=UUID_PK, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("rule_code", sa.Text(), nullable=False),
        # می‌تواند منفی باشد — فقط در رکورد معکوس.
        sa.Column("amount", sa.Numeric(6, 2), nullable=False),
        # فراتر از §4.8 — ADR-0012. عکس ضریب لحظهٔ اعطا.
        sa.Column("multiplier", sa.Numeric(10, 4), server_default=ONE, nullable=False),
        sa.Column("source_type", sa.Text(), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=True),
        # فراتر از §4.8 — ADR-0012. بخشی از کلید بی‌اثری.
        sa.Column("revision", sa.SmallInteger(), server_default=ZERO, nullable=False),
        sa.Column("term_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("offering_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("reverses_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_point_entries"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_point_entries_user_id_users", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["rule_code"], ["point_rules.code"], name="fk_point_entries_rule_code_point_rules"
        ),
        sa.ForeignKeyConstraint(["term_id"], ["terms.id"], name="fk_point_entries_term_id_terms"),
        sa.ForeignKeyConstraint(
            ["offering_id"],
            ["course_offerings.id"],
            name="fk_point_entries_offering_id_course_offerings",
        ),
        sa.ForeignKeyConstraint(
            ["reverses_id"],
            ["point_entries.id"],
            name="fk_point_entries_reverses_id_point_entries",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(_in_list("category", CATEGORIES), name="category_valid"),
        # اصلی همیشه مثبت است و معکوس همیشه منفی. «امتیاز صفر» ثبت نمی‌شود
        # (§9.9) و «امتیاز منفیِ اصلی» یعنی جریمه، که در §9 وجود ندارد.
        sa.CheckConstraint(
            "(reverses_id IS NULL AND amount > 0) OR (reverses_id IS NOT NULL AND amount < 0)",
            name="sign_matches_kind",
        ),
        sa.CheckConstraint("multiplier > 0", name="multiplier_positive"),
        sa.CheckConstraint("revision >= 0", name="revision_not_negative"),
        sa.CheckConstraint("length(btrim(source_type)) > 0", name="source_type_not_blank"),
    )
    # FR-GAM-01 — یک رویداد، یک امتیاز. `revision` اجازه می‌دهد پس از
    # معکوس شدن، همان منبع دوباره امتیاز بگیرد (ADR-0012).
    op.create_index(
        "idx_point_idempotency",
        "point_entries",
        ["user_id", "rule_code", "source_type", "source_id", "revision"],
        unique=True,
        postgresql_where=sa.text("reverses_id IS NULL AND source_id IS NOT NULL"),
    )
    # دو معکوسِ هم‌زمان یک ردیف، امتیاز را دو بار کم نکنند.
    op.create_index(
        "idx_point_single_reversal",
        "point_entries",
        ["reverses_id"],
        unique=True,
        postgresql_where=sa.text("reverses_id IS NOT NULL"),
    )
    op.create_index("idx_points_user_term", "point_entries", ["user_id", "term_id", "category"])
    op.create_index("idx_points_created", "point_entries", [sa.text("created_at DESC")])
    # سقف روزانه/هفتگی و «امتیازهای اخیر» هر دو از این می‌خوانند.
    op.create_index(
        "idx_points_user_rule_created", "point_entries", ["user_id", "rule_code", "created_at"]
    )
    op.create_index(
        "idx_points_offering",
        "point_entries",
        ["offering_id", "user_id"],
        postgresql_where=sa.text("offering_id IS NOT NULL"),
    )

    # D-09 — دفتر کل تغییرناپذیر. حذف مجاز می‌ماند: `ON DELETE CASCADE` از
    # `users` در اجرای خط‌مشی نگهداری (§4.12) باید کار کند.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION forbid_point_entry_update() RETURNS TRIGGER AS $$
        BEGIN
          RAISE EXCEPTION 'point_entries is append-only; write a reversal instead (D-09)'
            USING ERRCODE = 'restrict_violation';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        "CREATE TRIGGER trg_point_entries_immutable BEFORE UPDATE ON point_entries"
        " FOR EACH ROW EXECUTE FUNCTION forbid_point_entry_update()"
    )


def _create_totals_view() -> None:
    # §4.8 — تجمیع برای جدول رتبه‌بندی. هر ۱۵ دقیقه تازه می‌شود (§7.11)؛
    # مجموع شخصی کاربر از خود دفتر کل خوانده می‌شود، نه از این نما.
    op.execute(
        """
        CREATE MATERIALIZED VIEW user_point_totals AS
        SELECT user_id, term_id, category, SUM(amount) AS total
        FROM point_entries
        GROUP BY user_id, term_id, category
        """
    )
    # `NULLS NOT DISTINCT`: ردیف‌های بدون نیم‌سال هم یکتا بمانند — شرط
    # `REFRESH ... CONCURRENTLY`.
    op.execute(
        "CREATE UNIQUE INDEX idx_user_point_totals_key ON user_point_totals"
        " (user_id, term_id, category) NULLS NOT DISTINCT"
    )
    op.execute("CREATE INDEX idx_user_point_totals_term ON user_point_totals (term_id, category)")


# ── نشان ───────────────────────────────────────────────────────────────
def _create_badges() -> None:
    op.create_table(
        "badges",
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("title_fa", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("icon", sa.Text(), nullable=False),
        sa.Column("tier", sa.Text(), nullable=False),
        sa.Column("criteria", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=TRUE, nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=ZERO, nullable=False),
        sa.PrimaryKeyConstraint("code", name="pk_badges"),
        sa.CheckConstraint(_in_list("tier", BADGE_TIERS), name="tier_valid"),
        sa.CheckConstraint("jsonb_typeof(criteria) = 'object'", name="criteria_is_object"),
    )
    badges = sa.table(
        "badges",
        sa.column("code", sa.Text),
        sa.column("title_fa", sa.Text),
        sa.column("description", sa.Text),
        sa.column("icon", sa.Text),
        sa.column("tier", sa.Text),
        sa.column("criteria", postgresql.JSONB),
        sa.column("sort_order", sa.Integer),
    )
    op.bulk_insert(
        badges,
        [
            {
                "code": code,
                "title_fa": title,
                "description": description,
                "icon": icon,
                "tier": tier,
                "criteria": criteria,
                "sort_order": (index + 1) * 10,
            }
            for index, (code, title, description, icon, tier, criteria) in enumerate(BADGES)
        ],
    )


def _create_user_badges() -> None:
    op.create_table(
        "user_badges",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("badge_code", sa.Text(), nullable=False),
        sa.Column("awarded_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("context", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        # فراتر از §4.8 — لحظه‌ای که کاربر جشن نشان را دید (§9.10). بدون آن،
        # مودال جشن یا هرگز نمایش داده نمی‌شود یا در هر بار ورود تکرار می‌شود.
        sa.Column("seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("user_id", "badge_code", name="pk_user_badges"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_user_badges_user_id_users", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["badge_code"], ["badges.code"], name="fk_user_badges_badge_code_badges"
        ),
        sa.CheckConstraint(
            "context IS NULL OR jsonb_typeof(context) = 'object'",
            name="context_is_object",
        ),
    )
    op.create_index(
        "idx_user_badges_unseen",
        "user_badges",
        ["user_id"],
        postgresql_where=sa.text("seen_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_table("user_badges")
    op.drop_table("badges")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS user_point_totals")
    op.execute("DROP TRIGGER IF EXISTS trg_point_entries_immutable ON point_entries")
    op.drop_table("point_entries")
    op.execute("DROP FUNCTION IF EXISTS forbid_point_entry_update()")
    op.execute("DROP TRIGGER IF EXISTS trg_point_rules_updated ON point_rules")
    op.drop_table("point_rules")
