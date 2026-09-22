"""0003 — طبقه‌بندی‌ها: universities, skills, assets, interests

مرجع: PRD §4.3 و دادهٔ مرجع §14.1 تا §14.3.
وظیفهٔ نقشهٔ راه: M1-01 و M1-02.

پس از ۰۰۲ (هویت) می‌آید.

دادهٔ ۱۷ مهارت، ۹ امکان و ۱۲ حوزهٔ علاقه اینجا درج می‌شود، نه در
`015_seed_reference_data` — با همان استدلال نقش‌ها در مهاجرت ۰۰۲:
فرم ارزیابی نیمرخ بدون آن رندر نمی‌شود و `project_required_skills` بدون
آن کلید خارجی معتبر ندارد. این دادهٔ نمونه نیست، بخشی از اسکیماست.
دلیل کامل در docs/adr/0004.

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-22
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID_PK = sa.text("uuidv7()")
TRUE = sa.text("true")
FALSE = sa.text("false")
ZERO = sa.text("0")

SKILL_CATEGORIES = ("SOFTWARE", "ANALYSIS", "DOMAIN", "SOFT", "LANGUAGE")
ASSET_CATEGORIES = ("COMPUTING", "VEHICLE", "EQUIPMENT", "CONNECTIVITY", "SPACE")
UNIVERSITY_TYPES = ("STATE", "AZAD", "PAYAMNOOR", "NONPROFIT", "APPLIED", "OTHER")

# §14.1 — (کد، فارسی، انگلیسی، دسته، هسته)
# «هسته» یعنی در گام ۱ نیمرخ پیش‌فرض دیده می‌شود. دقیقاً ده مورد، تا گام ۱
# زیر ۹۰ ثانیه بماند؛ قید «حداکثر ۱۰» در تست دادهٔ مرجع بررسی می‌شود.
SKILLS: tuple[tuple[str, str, str, str, bool], ...] = (
    ("EXCEL", "اکسل", "Excel", "SOFTWARE", True),
    ("PYTHON", "پایتون", "Python", "SOFTWARE", True),
    ("R", "آر", "R", "SOFTWARE", True),
    ("GIS", "سامانه اطلاعات مکانی", "GIS", "SOFTWARE", True),
    ("STATISTICS", "آمار و تحلیل داده", "Statistics", "ANALYSIS", True),
    ("WRITING", "نگارش علمی", "Academic Writing", "SOFT", True),
    ("MARKETING_SKILL", "بازاریابی و فروش", "Marketing & Sales", "SOFT", True),
    ("GRAPHIC_DESIGN", "طراحی گرافیک", "Graphic Design", "SOFTWARE", True),
    ("AI_TOOLS", "ابزارهای هوش مصنوعی", "AI Tools", "SOFTWARE", True),
    ("ENGLISH", "زبان انگلیسی", "English", "LANGUAGE", True),
    ("SUMO", "شبیه‌سازی SUMO", "SUMO", "SOFTWARE", False),
    ("AIMSUN", "ایمسان", "Aimsun", "SOFTWARE", False),
    ("AUTOCAD", "اتوکد", "AutoCAD", "SOFTWARE", False),
    ("POWERBI", "پاور بی‌آی", "Power BI", "SOFTWARE", False),
    ("WEB_DEV", "برنامه‌نویسی وب", "Web Development", "SOFTWARE", False),
    ("MODELING", "مدل‌سازی حمل‌ونقل", "Transport Modeling", "DOMAIN", False),
    ("PRESENTATION", "ارائه و سخنرانی", "Presentation", "SOFT", False),
)

# §14.2 — (کد، فارسی، دسته)
ASSETS: tuple[tuple[str, str, str], ...] = (
    ("LAPTOP", "لپ‌تاپ", "COMPUTING"),
    ("POWERFUL_PC", "کامپیوتر قوی", "COMPUTING"),
    ("SERVER", "سرور", "COMPUTING"),
    ("FAST_INTERNET", "اینترنت پرسرعت", "CONNECTIVITY"),
    ("CAR", "خودرو", "VEHICLE"),
    ("PICKUP", "وانت", "VEHICLE"),
    ("MOTORCYCLE", "موتورسیکلت", "VEHICLE"),
    ("CAMERA", "دوربین", "EQUIPMENT"),
    ("WORKSPACE", "فضای کاری", "SPACE"),
)

# §14.3 — (کد، فارسی)
INTERESTS: tuple[tuple[str, str], ...] = (
    ("RESEARCH", "پژوهش"),
    ("PROGRAMMING", "برنامه‌نویسی"),
    ("MARKETING", "بازاریابی"),
    ("SALES", "فروش"),
    ("GRAPHIC", "طراحی گرافیک"),
    ("CONTENT", "تولید محتوا"),
    ("PROJECT_MGMT", "مدیریت پروژه"),
    ("DATA_ANALYSIS", "تحلیل داده"),
    ("TRANSPORT", "حمل‌ونقل"),
    ("AGRICULTURE", "کشاورزی"),
    ("COMMERCE", "تجارت"),
    ("URBAN", "شهرسازی و شهر هوشمند"),
)

# دانشگاه‌های اولیه. فهرست کامل نیست و نباید باشد — کاربر دانشگاهش را
# جستجو می‌کند و مدیر موارد تازه را اضافه می‌کند (FR-PROF-02).
UNIVERSITIES: tuple[tuple[str, str | None, str, str, str], ...] = (
    ("دانشگاه شهید باهنر کرمان", "Shahid Bahonar University of Kerman", "کرمان", "کرمان", "STATE"),
    ("دانشگاه تحصیلات تکمیلی صنعتی کرمان", None, "کرمان", "کرمان", "STATE"),
    ("دانشگاه آزاد اسلامی واحد کرمان", None, "کرمان", "کرمان", "AZAD"),
    ("دانشگاه پیام نور کرمان", None, "کرمان", "کرمان", "PAYAMNOOR"),
    ("دانشگاه صنعتی سیرجان", None, "سیرجان", "کرمان", "STATE"),
    ("دانشگاه ولی‌عصر رفسنجان", None, "رفسنجان", "کرمان", "STATE"),
    ("دانشگاه تهران", "University of Tehran", "تهران", "تهران", "STATE"),
    ("دانشگاه صنعتی شریف", "Sharif University of Technology", "تهران", "تهران", "STATE"),
    (
        "دانشگاه علم و صنعت ایران",
        "Iran University of Science and Technology",
        "تهران",
        "تهران",
        "STATE",
    ),
    ("دانشگاه صنعتی امیرکبیر", "Amirkabir University of Technology", "تهران", "تهران", "STATE"),
    ("دانشگاه تربیت مدرس", "Tarbiat Modares University", "تهران", "تهران", "STATE"),
    ("دانشگاه فردوسی مشهد", "Ferdowsi University of Mashhad", "مشهد", "خراسان رضوی", "STATE"),
    ("دانشگاه شیراز", "Shiraz University", "شیراز", "فارس", "STATE"),
    ("دانشگاه اصفهان", "University of Isfahan", "اصفهان", "اصفهان", "STATE"),
    ("دانشگاه تبریز", "University of Tabriz", "تبریز", "آذربایجان شرقی", "STATE"),
    ("سایر", None, "", "", "OTHER"),
)


def _in_list(column: str, values: tuple[str, ...]) -> str:
    joined = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({joined})"


def upgrade() -> None:
    # ── universities ───────────────────────────────────────────────────
    op.create_table(
        "universities",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=UUID_PK, nullable=False),
        sa.Column("title_fa", sa.Text(), nullable=False),
        sa.Column("title_en", sa.Text(), nullable=True),
        sa.Column("city", sa.Text(), nullable=True),
        sa.Column("province", sa.Text(), nullable=True),
        sa.Column("type", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=TRUE, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_universities"),
        sa.CheckConstraint(
            f"type IS NULL OR {_in_list('type', UNIVERSITY_TYPES)}",
            name="ck_universities_type_valid",
        ),
    )
    # جستجوی دانشگاه با نام فارسی — §5.4 `GET /taxonomy/universities?q=`
    op.execute(
        "CREATE INDEX idx_universities_search ON universities"
        " USING GIN (fa_normalize(title_fa) gin_trgm_ops)"
    )

    # ── skills ─────────────────────────────────────────────────────────
    op.create_table(
        "skills",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=UUID_PK, nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("title_fa", sa.Text(), nullable=False),
        sa.Column("title_en", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("icon", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default=ZERO, nullable=False),
        sa.Column("is_core", sa.Boolean(), server_default=FALSE, nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=TRUE, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_skills"),
        sa.UniqueConstraint("code", name="uq_skills_code"),
        sa.CheckConstraint(_in_list("category", SKILL_CATEGORIES), name="ck_skills_category_valid"),
    )

    # ── assets ─────────────────────────────────────────────────────────
    op.create_table(
        "assets",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=UUID_PK, nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("title_fa", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("icon", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default=ZERO, nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=TRUE, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_assets"),
        sa.UniqueConstraint("code", name="uq_assets_code"),
        sa.CheckConstraint(_in_list("category", ASSET_CATEGORIES), name="ck_assets_category_valid"),
    )

    # ── interests ──────────────────────────────────────────────────────
    op.create_table(
        "interests",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=UUID_PK, nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("title_fa", sa.Text(), nullable=False),
        sa.Column("icon", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default=ZERO, nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=TRUE, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_interests"),
        sa.UniqueConstraint("code", name="uq_interests_code"),
    )

    # ── دادهٔ مرجع §14.1 تا §14.3 ───────────────────────────────────────
    op.bulk_insert(
        sa.table(
            "skills",
            sa.column("code", sa.Text),
            sa.column("title_fa", sa.Text),
            sa.column("title_en", sa.Text),
            sa.column("category", sa.Text),
            sa.column("is_core", sa.Boolean),
            sa.column("sort_order", sa.Integer),
        ),
        [
            {
                "code": code,
                "title_fa": fa,
                "title_en": en,
                "category": category,
                "is_core": is_core,
                # ترتیب سند = ترتیب نمایش. هسته‌ای‌ها اول‌اند.
                "sort_order": (index + 1) * 10,
            }
            for index, (code, fa, en, category, is_core) in enumerate(SKILLS)
        ],
    )
    op.bulk_insert(
        sa.table(
            "assets",
            sa.column("code", sa.Text),
            sa.column("title_fa", sa.Text),
            sa.column("category", sa.Text),
            sa.column("sort_order", sa.Integer),
        ),
        [
            {"code": code, "title_fa": fa, "category": category, "sort_order": (i + 1) * 10}
            for i, (code, fa, category) in enumerate(ASSETS)
        ],
    )
    op.bulk_insert(
        sa.table(
            "interests",
            sa.column("code", sa.Text),
            sa.column("title_fa", sa.Text),
            sa.column("sort_order", sa.Integer),
        ),
        [
            {"code": code, "title_fa": fa, "sort_order": (i + 1) * 10}
            for i, (code, fa) in enumerate(INTERESTS)
        ],
    )
    op.bulk_insert(
        sa.table(
            "universities",
            sa.column("title_fa", sa.Text),
            sa.column("title_en", sa.Text),
            sa.column("city", sa.Text),
            sa.column("province", sa.Text),
            sa.column("type", sa.Text),
        ),
        [
            {
                "title_fa": fa,
                "title_en": en,
                "city": city or None,
                "province": province or None,
                "type": kind,
            }
            for fa, en, city, province, kind in UNIVERSITIES
        ],
    )


def downgrade() -> None:
    op.drop_table("interests")
    op.drop_table("assets")
    op.drop_table("skills")
    op.execute("DROP INDEX IF EXISTS idx_universities_search")
    op.drop_table("universities")
