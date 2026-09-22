"""مدل‌های آموزش — PRD §4.4.

جداول سند: terms، courses، course_offerings، enrollments، course_weeks،
resources، resource_progress، class_sessions، attendance_records،
announcements.
مهاجرت متناظر: 0006_education.

دو جدول بیرون از §4.4 افزوده شده‌اند (ADR-0008):

* `course_materials` — **کتابخانهٔ درس**. کتاب، جزوه، پادکست و بانک سؤالی
  که به خودِ درس تعلق دارد، نه به ارائهٔ یک نیم‌سال. منبعشان پوشهٔ
  `Courses/<نام درس>/` است و `silp.scripts.sync_courses` آن‌ها را همگام
  می‌کند. افزودن یک کتاب تازه نباید یعنی تکرار همان ردیف در هر ارائه.
* `week_materials` — پیوند هفته به مادهٔ کتابخانه. یک فصل می‌تواند منبع
  دو هفته باشد و یک ماده می‌تواند به هیچ هفته‌ای وصل نباشد و فقط در
  کتابخانه بماند.

`resources` (§4.4) حذف نشده و کار خودش را می‌کند: منبعِ **مخصوص همین
ارائه** — اسلاید امسال، ویدئوی همین جلسه. تفاوت در عمر است، نه در نوع:
ماده با درس می‌ماند، منبع با ارائه می‌رود.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from silp.db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin

DEGREE_LEVELS = ("BACHELOR", "MASTER", "PHD", "PUBLIC")
OFFERING_STATUSES = ("DRAFT", "OPEN", "IN_PROGRESS", "CLOSED", "ARCHIVED")
ENROLLMENT_STATUSES = ("PENDING", "ACTIVE", "DROPPED", "COMPLETED", "REJECTED")
WEEK_STATUSES = ("DRAFT", "PUBLISHED", "ARCHIVED")
RESOURCE_KINDS = ("PDF", "VIDEO", "LINK", "SLIDE", "DATASET", "CODE", "OTHER")
PROGRESS_STATUSES = ("NOT_STARTED", "IN_PROGRESS", "COMPLETED")
ATTENDANCE_STATUSES = ("PRESENT", "ABSENT", "LATE", "EXCUSED")
ANNOUNCEMENT_PRIORITIES = ("NORMAL", "IMPORTANT", "URGENT")

# ── کتابخانهٔ درس (ADR-0008) ────────────────────────────────────────────
MATERIAL_KINDS = (
    "BOOK",
    "NOTE",
    "SLIDE",
    "VIDEO",
    "PODCAST",
    "DATASET",
    "CODE",
    "QUESTION_BANK",
    "LINK",
    "OTHER",
)
MATERIAL_STATUSES = ("DRAFT", "PUBLISHED", "ARCHIVED")

# ── سطح دسترسی (ADR-0009) ──────────────────────────────────────────────
# سه سطح، و ترتیبشان از باز به بسته است:
#
#   PUBLIC     — برای همه، حتی مهمان. ویترین و نمونهٔ رایگان.
#   SUBSCRIBER — دانشجوی همین درس رایگان، بقیه با اشتراک ماهانه.
#   ENROLLED   — فقط دانشجوی ثبت‌نام‌شده. فروختنی نیست (کلید آزمون،
#                تکلیف نمره‌دار). اشتراک این را باز نمی‌کند.
ACCESS_TIERS = ("PUBLIC", "SUBSCRIBER", "ENROLLED")

ACCESS_TIER_TITLE_FA: dict[str, str] = {
    "PUBLIC": "رایگان برای همه",
    "SUBSCRIBER": "رایگان برای دانشجوی درس، با اشتراک برای بقیه",
    "ENROLLED": "فقط دانشجوی ثبت‌نام‌شدهٔ درس",
}

MATERIAL_KIND_TITLE_FA: dict[str, str] = {
    "BOOK": "کتاب",
    "NOTE": "جزوه",
    "SLIDE": "اسلاید",
    "VIDEO": "ویدئو",
    "PODCAST": "پادکست",
    "DATASET": "مجموعه‌داده",
    "CODE": "کد",
    "QUESTION_BANK": "بانک سؤال",
    "LINK": "پیوند",
    "OTHER": "سایر",
}

DEGREE_LEVEL_TITLE_FA: dict[str, str] = {
    "BACHELOR": "کارشناسی",
    "MASTER": "کارشناسی ارشد",
    "PHD": "دکتری",
    "PUBLIC": "عمومی",
}

MAX_WEEK_NUMBER = 17


def _in_list(column: str, values: tuple[str, ...]) -> str:
    joined = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({joined})"


class Term(UUIDPrimaryKeyMixin, Base):
    """نیم‌سال تحصیلی — §4.4."""

    __tablename__ = "terms"

    code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    title_fa: Mapped[str] = mapped_column(Text, nullable=False)
    starts_on: Mapped[date] = mapped_column(Date, nullable=False)
    ends_on: Mapped[date] = mapped_column(Date, nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))

    __table_args__ = (
        CheckConstraint("ends_on > starts_on", name="date_order"),
        # فقط یک نیم‌سال می‌تواند «جاری» باشد — ایندکس یکتای جزئی.
        Index(
            "idx_terms_single_current",
            "is_current",
            unique=True,
            postgresql_where=text("is_current"),
        ),
    )


class Course(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """الگوی درس — FR-EDU-01. مستقل از نیم‌سال و استاد."""

    __tablename__ = "courses"

    code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    slug: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    title_fa: Mapped[str] = mapped_column(Text, nullable=False)
    title_en: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    degree_level: Mapped[str | None] = mapped_column(Text)
    credits: Mapped[int | None] = mapped_column(Integer)
    cover_key: Mapped[str | None] = mapped_column(Text)
    is_public: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    # ── افزوده‌های ADR-0008 و ADR-0009 ─────────────────────────────────
    # نام پوشهٔ درس در `Courses/`. کلید همگام‌سازی کتابخانه است و در
    # سامانه هیچ معنای دیگری ندارد.
    source_dir: Mapped[str | None] = mapped_column(Text)
    # سطح دسترسی پیش‌فرض موادی که در مانیفست سطح صریح ندارند.
    default_access_tier: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'SUBSCRIBER'")
    )
    topics: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'::text[]")
    )

    title_norm: Mapped[str | None] = mapped_column(
        Text, Computed("fa_normalize(title_fa)", persisted=True)
    )

    materials: Mapped[list[CourseMaterial]] = relationship(
        back_populates="course", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (
        CheckConstraint(
            f"degree_level IS NULL OR {_in_list('degree_level', DEGREE_LEVELS)}",
            name="degree_level_valid",
        ),
        CheckConstraint(
            _in_list("default_access_tier", ACCESS_TIERS), name="default_access_tier_valid"
        ),
        CheckConstraint("credits IS NULL OR credits BETWEEN 1 AND 12", name="credits_range"),
        Index("idx_courses_search", text("title_norm gin_trgm_ops"), postgresql_using="gin"),
        Index(
            "idx_courses_source_dir",
            "source_dir",
            unique=True,
            postgresql_where=text("source_dir IS NOT NULL"),
        ),
    )


class CourseOffering(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """ارائهٔ یک درس در یک نیم‌سال توسط یک استاد — FR-EDU-01."""

    __tablename__ = "course_offerings"

    course_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("courses.id"), nullable=False
    )
    term_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("terms.id"), nullable=False
    )
    instructor_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    capacity: Mapped[int | None] = mapped_column(Integer)
    enrollment_code: Mapped[str | None] = mapped_column(Text)
    requires_approval: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'DRAFT'"))
    grading_policy: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    syllabus_key: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint(
            "course_id",
            "term_id",
            "instructor_id",
            name="uq_course_offerings_course_term_instructor",
        ),
        CheckConstraint(_in_list("status", OFFERING_STATUSES), name="status_valid"),
        CheckConstraint("capacity IS NULL OR capacity > 0", name="capacity_positive"),
        CheckConstraint("jsonb_typeof(grading_policy) = 'object'", name="grading_policy_is_object"),
        Index("idx_offerings_instructor", "instructor_id", "status"),
        Index("idx_offerings_term", "term_id", "status"),
        Index("idx_offerings_course", "course_id"),
    )

    @property
    def accepts_enrollment(self) -> bool:
        return self.status == "OPEN" and self.deleted_at is None


class Enrollment(UUIDPrimaryKeyMixin, Base):
    """ثبت‌نام دانشجو در یک ارائه — FR-AUTH-05، §7.2.

    `status = 'ACTIVE'` تنها چیزی است که «دانشجوی این درس» را می‌سازد؛
    سنجش دسترسی رایگان به کتابخانه هم از همین می‌خواند (ADR-0009).
    """

    __tablename__ = "enrollments"

    offering_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("course_offerings.id"), nullable=False
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'PENDING'"))
    final_grade: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    enrolled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id")
    )

    __table_args__ = (
        UniqueConstraint("offering_id", "student_id", name="uq_enrollments_offering_student"),
        CheckConstraint(_in_list("status", ENROLLMENT_STATUSES), name="status_valid"),
        CheckConstraint(
            "final_grade IS NULL OR final_grade BETWEEN 0 AND 20", name="final_grade_range"
        ),
        Index("idx_enrollments_student", "student_id", "status"),
        Index("idx_enrollments_offering", "offering_id", "status"),
    )

    @property
    def is_active(self) -> bool:
        """آیا این ثبت‌نام «دانشجوی درس» بودن را می‌سازد؟

        `COMPLETED` هم هست: دانشجویی که درس را تمام کرده، دسترسی
        رایگانش به جزوهٔ همان درس را از دست نمی‌دهد.
        """
        return self.status in ("ACTIVE", "COMPLETED")


class CourseWeek(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """یک هفته از ارائه — FR-EDU-02."""

    __tablename__ = "course_weeks"

    offering_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("course_offerings.id", ondelete="CASCADE"),
        nullable=False,
    )
    week_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title_fa: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    objectives: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'DRAFT'"))
    publish_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    resources: Mapped[list[Resource]] = relationship(
        back_populates="week", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (
        UniqueConstraint("offering_id", "week_number", name="uq_course_weeks_offering_week"),
        CheckConstraint(f"week_number BETWEEN 1 AND {MAX_WEEK_NUMBER}", name="week_number_range"),
        CheckConstraint(_in_list("status", WEEK_STATUSES), name="status_valid"),
        # صف انتشار زمان‌بندی‌شده — کار پس‌زمینه فقط همین ردیف‌ها را می‌خواند.
        Index(
            "idx_weeks_publish_queue",
            "publish_at",
            postgresql_where=text("status = 'DRAFT' AND publish_at IS NOT NULL"),
        ),
    )

    @property
    def is_visible_to_students(self) -> bool:
        return self.status == "PUBLISHED"


class Resource(UUIDPrimaryKeyMixin, Base):
    """منبع مخصوص یک هفته از یک ارائه — FR-EDU-03.

    برای محتوایی که با همین نیم‌سال می‌آید و می‌رود. محتوای ماندگار درس
    در `course_materials` است.
    """

    __tablename__ = "resources"

    week_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("course_weeks.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    title_fa: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    file_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("files.id"))
    external_url: Mapped[str | None] = mapped_column(Text)
    duration_sec: Mapped[int | None] = mapped_column(Integer)
    is_downloadable: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    week: Mapped[CourseWeek] = relationship(back_populates="resources")

    __table_args__ = (
        CheckConstraint(_in_list("kind", RESOURCE_KINDS), name="kind_valid"),
        CheckConstraint("file_id IS NOT NULL OR external_url IS NOT NULL", name="source_required"),
        Index("idx_resources_week", "week_id", "sort_order"),
    )


class ResourceProgress(Base):
    """پیشرفت مطالعهٔ یک منبع توسط یک کاربر — FR-EDU-04."""

    __tablename__ = "resource_progress"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    resource_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("resources.id", ondelete="CASCADE"), primary_key=True
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'NOT_STARTED'"))
    position_sec: Mapped[int | None] = mapped_column(Integer)
    percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), server_default=text("0"))
    first_opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint(_in_list("status", PROGRESS_STATUSES), name="status_valid"),
        CheckConstraint("percent BETWEEN 0 AND 100", name="percent_range"),
    )


class ClassSession(UUIDPrimaryKeyMixin, Base):
    """جلسهٔ کلاس — FR-EDU-05."""

    __tablename__ = "class_sessions"

    offering_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("course_offerings.id", ondelete="CASCADE"),
        nullable=False,
    )
    week_number: Mapped[int | None] = mapped_column(Integer)
    held_on: Mapped[date] = mapped_column(Date, nullable=False)
    topic: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint("offering_id", "held_on", name="uq_class_sessions_offering_held_on"),
    )


class AttendanceRecord(Base):
    """حضور یک دانشجو در یک جلسه — FR-EDU-05."""

    __tablename__ = "attendance_records"

    session_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("class_sessions.id", ondelete="CASCADE"), primary_key=True
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), primary_key=True
    )
    status: Mapped[str] = mapped_column(Text, nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    recorded_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id")
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint(_in_list("status", ATTENDANCE_STATUSES), name="status_valid"),
    )


class Announcement(UUIDPrimaryKeyMixin, Base):
    """اعلان درس یا پروژه — FR-EDU-06. دقیقاً یک مقصد دارد، نه دو."""

    __tablename__ = "announcements"

    offering_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("course_offerings.id", ondelete="CASCADE")
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE")
    )
    author_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'NORMAL'"))
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "(offering_id IS NOT NULL)::int + (project_id IS NOT NULL)::int = 1", name="target"
        ),
        CheckConstraint(_in_list("priority", ANNOUNCEMENT_PRIORITIES), name="priority_valid"),
        Index("idx_announcements_offering", "offering_id", text("published_at DESC")),
        Index("idx_announcements_project", "project_id", text("published_at DESC")),
    )


# ── کتابخانهٔ درس — ADR-0008 ───────────────────────────────────────────
class CourseMaterial(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """یک کتاب، جزوه، پادکست یا بانک سؤال که به **درس** تعلق دارد.

    `source_path` مسیر نسبی فایل داخل `Courses/` است و کلید همگام‌سازی:
    اجرای دوبارهٔ `sync_courses` همان ردیف را به‌روز می‌کند، نه اینکه
    نسخهٔ دوم بسازد. `content_sha256` می‌گوید فایل عوض شده یا نه، تا
    آپلود دوبارهٔ ۷ مگابایت بی‌دلیل تکرار نشود.

    مادهٔ دستی (که استاد از رابط کاربری می‌سازد) `source_path` ندارد و
    همگام‌سازی هرگز به آن دست نمی‌زند.
    """

    __tablename__ = "course_materials"

    course_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    title_fa: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    authors: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'::text[]")
    )
    edition: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'fa'"))

    source_path: Mapped[str | None] = mapped_column(Text)
    content_sha256: Mapped[str | None] = mapped_column(Text)
    file_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("files.id"))
    external_url: Mapped[str | None] = mapped_column(Text)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    page_count: Mapped[int | None] = mapped_column(Integer)
    duration_sec: Mapped[int | None] = mapped_column(Integer)

    access_tier: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'SUBSCRIBER'")
    )
    is_downloadable: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'PUBLISHED'"))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    added_by: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"))

    title_norm: Mapped[str | None] = mapped_column(
        Text, Computed("fa_normalize(title_fa)", persisted=True)
    )

    course: Mapped[Course] = relationship(back_populates="materials")

    __table_args__ = (
        CheckConstraint(_in_list("kind", MATERIAL_KINDS), name="kind_valid"),
        CheckConstraint(_in_list("access_tier", ACCESS_TIERS), name="access_tier_valid"),
        CheckConstraint(_in_list("status", MATERIAL_STATUSES), name="status_valid"),
        CheckConstraint("file_id IS NOT NULL OR external_url IS NOT NULL", name="source_required"),
        # یکتایی روی مسیر منبع — دو ردیف برای یک فایل معنا ندارد.
        Index(
            "idx_course_materials_source",
            "course_id",
            "source_path",
            unique=True,
            postgresql_where=text("source_path IS NOT NULL AND deleted_at IS NULL"),
        ),
        Index("idx_course_materials_course", "course_id", "sort_order"),
        Index(
            "idx_course_materials_search",
            text("title_norm gin_trgm_ops"),
            postgresql_using="gin",
        ),
    )

    @property
    def is_published(self) -> bool:
        return self.status == "PUBLISHED" and self.deleted_at is None


class WeekMaterial(Base):
    """پیوند هفته به مادهٔ کتابخانه — ADR-0008.

    دو طرف مستقل‌اند: مادهٔ بدون هفته در کتابخانه می‌ماند، و هفتهٔ بدون
    ماده فقط منابع مخصوص خودش را دارد.
    """

    __tablename__ = "week_materials"

    week_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("course_weeks.id", ondelete="CASCADE"), primary_key=True
    )
    material_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("course_materials.id", ondelete="CASCADE"),
        primary_key=True,
    )
    # «فصل ۳ تا ۵» — کدام تکه از کتاب به این هفته مربوط است.
    section: Mapped[str | None] = mapped_column(Text)
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    __table_args__ = (Index("idx_week_materials_material", "material_id"),)


__all__ = [
    "ACCESS_TIERS",
    "ACCESS_TIER_TITLE_FA",
    "ANNOUNCEMENT_PRIORITIES",
    "ATTENDANCE_STATUSES",
    "DEGREE_LEVELS",
    "DEGREE_LEVEL_TITLE_FA",
    "ENROLLMENT_STATUSES",
    "MATERIAL_KINDS",
    "MATERIAL_KIND_TITLE_FA",
    "MATERIAL_STATUSES",
    "MAX_WEEK_NUMBER",
    "OFFERING_STATUSES",
    "PROGRESS_STATUSES",
    "RESOURCE_KINDS",
    "WEEK_STATUSES",
    "Announcement",
    "AttendanceRecord",
    "ClassSession",
    "Course",
    "CourseMaterial",
    "CourseOffering",
    "CourseWeek",
    "Enrollment",
    "Resource",
    "ResourceProgress",
    "Term",
    "WeekMaterial",
]
