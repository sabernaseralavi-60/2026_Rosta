"""مدل‌های طبقه‌بندی — PRD §4.3.

جداول: universities, skills, assets, interests.
مهاجرت متناظر: 0003_taxonomy.

این‌ها جدول مرجع‌اند: محتوایشان با مهاجرت درج می‌شود و مدیر می‌تواند مورد
تازه بیفزاید بدون استقرار مجدد (FR-PROF-02). هیچ کدی نباید فهرست مهارت را
به‌صورت ثابت در خود داشته باشد — همیشه از این جداول خوانده می‌شود.
"""

from __future__ import annotations

from sqlalchemy import Boolean, CheckConstraint, Index, Integer, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from silp.db.base import Base, UUIDPrimaryKeyMixin

SKILL_CATEGORIES = ("SOFTWARE", "ANALYSIS", "DOMAIN", "SOFT", "LANGUAGE")
ASSET_CATEGORIES = ("COMPUTING", "VEHICLE", "EQUIPMENT", "CONNECTIVITY", "SPACE")
UNIVERSITY_TYPES = ("STATE", "AZAD", "PAYAMNOOR", "NONPROFIT", "APPLIED", "OTHER")

# §14.1 — متن هر سطح مهارت. سرور این متن‌ها را می‌فرستد تا تعریف سطح در
# فرم، در توضیح توصیه‌گر، و در نیمرخ عمومی یکی باشد (FR-PROF-01).
SKILL_LEVEL_LABELS: dict[int, str] = {
    1: "نمی‌دانم",
    2: "آشنایی مقدماتی دارم",
    3: "با کمک می‌توانم کار کنم",
    4: "مستقل کار می‌کنم",
    5: "می‌توانم به دیگران آموزش دهم",
}

# §14.3 — مقیاس علاقه همان ۱ تا ۵ است ولی معنایش فرق دارد.
INTEREST_LEVEL_LABELS: dict[int, str] = {
    1: "اصلاً",
    2: "کم",
    3: "متوسط",
    4: "زیاد",
    5: "خیلی زیاد",
}

MIN_LEVEL = 1
MAX_LEVEL = 5


def _in_list(column: str, values: tuple[str, ...]) -> str:
    joined = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({joined})"


class University(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "universities"

    title_fa: Mapped[str] = mapped_column(Text, nullable=False)
    title_en: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(Text)
    province: Mapped[str | None] = mapped_column(Text)
    type: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    __table_args__ = (
        CheckConstraint(f"type IS NULL OR {_in_list('type', UNIVERSITY_TYPES)}", name="type_valid"),
        # جستجوی دانشگاه با نام فارسی — §5.4. ایندکس روی خروجی تابع است،
        # نه روی ستون، پس با `text()` نوشته می‌شود.
        Index(
            "idx_universities_search",
            text("fa_normalize(title_fa) gin_trgm_ops"),
            postgresql_using="gin",
        ),
    )


class Skill(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "skills"

    code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    title_fa: Mapped[str] = mapped_column(Text, nullable=False)
    title_en: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    icon: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    # گام ۱ نیمرخ فقط مهارت‌های هسته را نشان می‌دهد تا زیر ۹۰ ثانیه بماند.
    is_core: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    __table_args__ = (
        CheckConstraint(_in_list("category", SKILL_CATEGORIES), name="category_valid"),
    )


class Asset(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "assets"

    code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    title_fa: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    icon: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    __table_args__ = (
        CheckConstraint(_in_list("category", ASSET_CATEGORIES), name="category_valid"),
    )


class Interest(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "interests"

    code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    title_fa: Mapped[str] = mapped_column(Text, nullable=False)
    icon: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))


__all__ = [
    "INTEREST_LEVEL_LABELS",
    "MAX_LEVEL",
    "MIN_LEVEL",
    "SKILL_LEVEL_LABELS",
    "Asset",
    "Interest",
    "Skill",
    "University",
]
