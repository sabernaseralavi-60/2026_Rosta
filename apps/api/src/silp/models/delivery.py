"""مدل‌های تحویل پروژه — PRD §4.6 و §4.7.

مهاجرت متناظر: 0011_project_delivery.

اینجا نیمهٔ دوم هستهٔ پروژه است: مرحله، تحویل‌دادنی، وظیفه، گفتگو،
جریان فعالیت، بازتاب، ارزیابی همتا، گواهی و آگهی هم‌تیمی. نیمهٔ اول
(پروژه، تیم، درخواست) در `models/project.py` است.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
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

MILESTONE_STATUSES = ("PENDING", "IN_PROGRESS", "SUBMITTED", "APPROVED", "OVERDUE")
OUTPUT_KINDS = ("DOCUMENT", "CODE", "DATA", "MEDIA", "SALES", "MIXED")
DELIVERABLE_STATUSES = (
    "SUBMITTED",
    "UNDER_REVIEW",
    "APPROVED",
    "CHANGES_REQUESTED",
    "REJECTED",
)
# §7.6 — این دو تصمیم بدون بازخورد متنی پذیرفته نمی‌شوند.
FEEDBACK_REQUIRED_STATUSES = ("CHANGES_REQUESTED", "REJECTED")
TASK_STATUSES = ("TODO", "DOING", "DONE")
CERTIFICATE_KINDS = ("PROJECT", "COURSE", "RESEARCH_LEVEL")
#: «منقضی» ذخیره نمی‌شود — آگهی باز با `expires_at` گذشته (ADR-0015، مثل دعوت).
OPENING_STATUSES = ("OPEN", "FILLED", "CLOSED")
OPENING_APPLICATION_STATUSES = ("PENDING", "ACCEPTED", "DECLINED", "WITHDRAWN")
OPENING_TITLE_MAX = 120
OPENING_DESCRIPTION_MAX = 2000
OPENING_MESSAGE_MAX = 500
MAX_OPENING_SKILLS = 10
#: فایل‌های مدل شهری که در کتابخانهٔ پروژه نسخه می‌خورند — FR-CITY-01.
ARTIFACT_KINDS = ("OSM", "SUMO_NET", "SUMO_ROUTES")

MILESTONE_STATUS_TITLE_FA: dict[str, str] = {
    "PENDING": "شروع نشده",
    "IN_PROGRESS": "در جریان",
    "SUBMITTED": "تحویل داده شده",
    "APPROVED": "تأیید شده",
    "OVERDUE": "از مهلت گذشته",
}

DELIVERABLE_STATUS_TITLE_FA: dict[str, str] = {
    "SUBMITTED": "در انتظار بررسی",
    "UNDER_REVIEW": "در حال بررسی",
    "APPROVED": "تأیید شده",
    "CHANGES_REQUESTED": "نیازمند اصلاح",
    "REJECTED": "رد شده",
}

OUTPUT_KIND_TITLE_FA: dict[str, str] = {
    "DOCUMENT": "سند یا گزارش",
    "CODE": "کد",
    "DATA": "داده",
    "MEDIA": "محتوای چندرسانه‌ای",
    "SALES": "نتیجهٔ فروش",
    "MIXED": "ترکیبی",
}

TASK_STATUS_TITLE_FA: dict[str, str] = {
    "TODO": "انجام نشده",
    "DOING": "در حال انجام",
    "DONE": "انجام شد",
}


def _in_list(column: str, values: tuple[str, ...]) -> str:
    joined = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({joined})"


class Milestone(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """یک گام قابل تحویل در پروژه — §7.6."""

    __tablename__ = "milestones"

    project_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    title_fa: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    due_on: Mapped[date | None] = mapped_column(Date)
    points: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False, server_default=text("0"))
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    output_kind: Mapped[str | None] = mapped_column(Text)
    # معیارهای کیفیت: آرایهٔ رشته، نه شیء — رابط کاربری آن را چک‌لیست می‌کند.
    checklist: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'PENDING'"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: شمارهٔ مرحله در الگوی گردش‌کار پروژه (ADR-0016)؛ تهی یعنی مرحلهٔ آزاد.
    workflow_stage: Mapped[int | None] = mapped_column(Integer)
    #: مسئول مرحله — FR-CITY-01 «هر مرحله: تحویل‌دادنی، چک‌لیست کیفیت، و مسئول».
    owner_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"))

    deliverables: Mapped[list[Deliverable]] = relationship(
        back_populates="milestone", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (
        CheckConstraint(_in_list("status", MILESTONE_STATUSES), name="status_valid"),
        CheckConstraint(
            f"output_kind IS NULL OR {_in_list('output_kind', OUTPUT_KINDS)}",
            name="output_kind_valid",
        ),
        CheckConstraint("points >= 0", name="points_not_negative"),
        CheckConstraint("jsonb_typeof(checklist) = 'array'", name="checklist_is_array"),
        CheckConstraint(
            "(status = 'APPROVED') = (approved_at IS NOT NULL)",
            name="approved_at_matches_status",
        ),
        CheckConstraint(
            "workflow_stage IS NULL OR workflow_stage BETWEEN 1 AND 8", name="workflow_stage_range"
        ),
        # مرحلهٔ الگو همیشه مسئول دارد — پیش‌فرض مدیر پروژه (ADR-0016).
        CheckConstraint(
            "workflow_stage IS NULL OR owner_id IS NOT NULL", name="workflow_stage_has_owner"
        ),
        Index("idx_milestones_project", "project_id", "sort_order"),
        Index(
            "idx_milestones_workflow_stage",
            "project_id",
            "workflow_stage",
            unique=True,
            postgresql_where=text("workflow_stage IS NOT NULL"),
        ),
        Index("idx_milestones_owner", "owner_id", postgresql_where=text("owner_id IS NOT NULL")),
        Index(
            "idx_milestones_due",
            "due_on",
            postgresql_where=text("status IN ('PENDING', 'IN_PROGRESS')"),
        ),
    )

    @property
    def accepts_submission(self) -> bool:
        """§7.6 — تأییدشده دیگر تحویل نمی‌پذیرد؛ از مهلت گذشته می‌پذیرد."""
        return self.status != "APPROVED"


class Deliverable(UUIDPrimaryKeyMixin, Base):
    """یک نسخه از تحویل یک عضو برای یک مرحله.

    نسخه‌ها هرگز پاک نمی‌شوند (§7.6): هر بار «اصلاح کن» بگیرد، نسخهٔ
    بعدی ساخته می‌شود و قبلی با بازخوردش در تاریخچه می‌ماند.
    """

    __tablename__ = "deliverables"

    milestone_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("milestones.id", ondelete="CASCADE"), nullable=False
    )
    submitter_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    body: Mapped[str | None] = mapped_column(Text)
    links: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'::text[]")
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'SUBMITTED'"))
    # عکس لحظهٔ ارسال — جابه‌جایی بعدی مهلت، گذشته را بازنویسی نکند.
    is_late: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    score: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    feedback: Mapped[str | None] = mapped_column(Text)
    rubric_scores: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    #: شاهد ساختاریافتهٔ مرحلهٔ الگو (ADR-0016) — محدوده، جدول راستی‌آزمایی، …
    evidence: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    milestone: Mapped[Milestone] = relationship(back_populates="deliverables")
    files: Mapped[list[DeliverableFile]] = relationship(
        back_populates="deliverable", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (
        UniqueConstraint("milestone_id", "submitter_id", "version", name="uq_deliverables_version"),
        CheckConstraint(_in_list("status", DELIVERABLE_STATUSES), name="status_valid"),
        CheckConstraint("version >= 1", name="version_positive"),
        CheckConstraint("score IS NULL OR score >= 0", name="score_not_negative"),
        CheckConstraint(
            "status NOT IN ('CHANGES_REQUESTED', 'REJECTED')"
            " OR (feedback IS NOT NULL AND length(btrim(feedback)) > 0)",
            name="feedback_required_on_rejection",
        ),
        CheckConstraint(
            "(reviewed_at IS NULL) = (reviewed_by IS NULL)", name="review_fields_together"
        ),
        CheckConstraint(
            "rubric_scores IS NULL OR jsonb_typeof(rubric_scores) = 'object'",
            name="rubric_is_object",
        ),
        CheckConstraint(
            "evidence IS NULL OR jsonb_typeof(evidence) = 'object'", name="evidence_is_object"
        ),
        Index(
            "idx_deliverables_review_queue",
            "status",
            "submitted_at",
            postgresql_where=text("status IN ('SUBMITTED', 'UNDER_REVIEW')"),
        ),
        Index("idx_deliverables_milestone", "milestone_id"),
    )

    @property
    def is_open_for_review(self) -> bool:
        return self.status in ("SUBMITTED", "UNDER_REVIEW")

    @property
    def allows_new_version(self) -> bool:
        return self.status == "CHANGES_REQUESTED"


class DeliverableFile(Base):
    __tablename__ = "deliverable_files"

    deliverable_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("deliverables.id", ondelete="CASCADE"), primary_key=True
    )
    file_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("files.id"), primary_key=True
    )

    deliverable: Mapped[Deliverable] = relationship(back_populates="files")


class ProjectArtifactVersion(UUIDPrimaryKeyMixin, Base):
    """نسخهٔ یک فایل مدل شهری در کتابخانهٔ پروژه — FR-CITY-01، ADR-0016.

    هر تحویل مرحلهٔ ۲ یا ۴ که فایل `.osm`، `.net.xml` یا `.rou.xml` دارد،
    نسخهٔ بعدی همان نوع را می‌سازد. شماره مال پروژه است، نه مال تحویل‌دهنده:
    «نسخهٔ ۳ شبکه» برای کل تیم یک معنا دارد. وضعیت نسخه از تحویلش خوانده
    می‌شود و «نسخهٔ جاری» آخرین نسخهٔ تأییدشده است.
    """

    __tablename__ = "project_artifact_versions"

    project_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    artifact: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    file_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("files.id"), nullable=False
    )
    deliverable_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("deliverables.id", ondelete="CASCADE"), nullable=False
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        UniqueConstraint(
            "project_id", "artifact", "version", name="uq_project_artifact_versions_version"
        ),
        UniqueConstraint(
            "deliverable_id", "artifact", name="uq_project_artifact_versions_deliverable"
        ),
        CheckConstraint(_in_list("artifact", ARTIFACT_KINDS), name="artifact_valid"),
        CheckConstraint("version >= 1", name="version_positive"),
    )


class ProjectTask(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """تختهٔ وظایف تیم — FR-PRJ-06. عمداً ساده: سه ستون، بدون جریان کاری."""

    __tablename__ = "project_tasks"

    project_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    milestone_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("milestones.id", ondelete="SET NULL")
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id")
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'TODO'"))
    due_on: Mapped[date | None] = mapped_column(Date)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    created_by: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )

    __table_args__ = (
        CheckConstraint(_in_list("status", TASK_STATUSES), name="status_valid"),
        CheckConstraint("length(btrim(title)) > 0", name="title_not_blank"),
        Index("idx_tasks_project_status", "project_id", "status", "sort_order"),
        Index(
            "idx_tasks_assignee",
            "assignee_id",
            postgresql_where=text("assignee_id IS NOT NULL AND status <> 'DONE'"),
        ),
    )


class ProjectMessage(UUIDPrimaryKeyMixin, SoftDeleteMixin, Base):
    """گفتگوی تیمی — FR-PRJ-06. نخ یک‌سطحی، نه چت بی‌درنگ."""

    __tablename__ = "project_messages"

    project_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("project_messages.id")
    )
    author_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    file_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("files.id"))
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint("length(btrim(body)) > 0", name="body_not_blank"),
        CheckConstraint("id <> parent_id", name="no_self_parent"),
        Index(
            "idx_project_messages",
            "project_id",
            text("created_at DESC"),
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "idx_project_messages_thread",
            "parent_id",
            "created_at",
            postgresql_where=text("parent_id IS NOT NULL"),
        ),
    )


class ProjectActivity(UUIDPrimaryKeyMixin, Base):
    """جریان فعالیت — FR-PRJ-06.

    `summary` متن فارسی آمادهٔ نمایش است، نه کلید ترجمه: یک رویداد پس از
    ثبت، تغییر نمی‌کند و بازنویسی متنش در آینده، تاریخ را عوض می‌کند.
    """

    __tablename__ = "project_activities"

    project_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"))
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str | None] = mapped_column(Text)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (Index("idx_project_activities", "project_id", text("created_at DESC")),)


class ProjectReflection(Base):
    """بازتاب پایان پروژه — FR-PRJ-08."""

    __tablename__ = "project_reflections"

    project_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), primary_key=True
    )
    learned: Mapped[str] = mapped_column(Text, nullable=False)
    challenges: Mapped[str | None] = mapped_column(Text)
    would_do_differently: Mapped[str | None] = mapped_column(Text)
    satisfaction: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint(
            "satisfaction IS NULL OR satisfaction BETWEEN 1 AND 5", name="satisfaction_range"
        ),
        CheckConstraint("length(btrim(learned)) > 0", name="learned_not_blank"),
    )


class PeerEvaluation(Base):
    """ارزیابی همتا — FR-PRJ-08. نتیجه فقط تجمیعی به مدیر پروژه نشان داده می‌شود."""

    __tablename__ = "peer_evaluations"

    project_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    evaluator_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), primary_key=True
    )
    evaluatee_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), primary_key=True
    )
    contribution: Mapped[int] = mapped_column(Integer, nullable=False)
    reliability: Mapped[int | None] = mapped_column(Integer)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint("evaluator_id <> evaluatee_id", name="no_self"),
        CheckConstraint("contribution BETWEEN 1 AND 5", name="contribution_range"),
        CheckConstraint(
            "reliability IS NULL OR reliability BETWEEN 1 AND 5", name="reliability_range"
        ),
    )


class Certificate(UUIDPrimaryKeyMixin, Base):
    """گواهی با صفحهٔ راستی‌آزمایی عمومی — FR-PRJ-08، FR-PROF-03 (M7-11)."""

    __tablename__ = "certificates"

    public_code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    subject_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    title_fa: Mapped[str] = mapped_column(Text, nullable=False)
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    issued_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id")
    )
    # `metadata` روی کلاس رزرو شده است، پس نام پایتونی فرق می‌کند.
    meta: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(_in_list("kind", CERTIFICATE_KINDS), name="kind_valid"),
        CheckConstraint("jsonb_typeof(metadata) = 'object'", name="metadata_is_object"),
        Index("idx_certificates_user", "user_id", "kind"),
    )


class TeamOpening(UUIDPrimaryKeyMixin, Base):
    """آگهی نیاز به هم‌تیمی — FR-TEAM-02، M7-08.

    آگهی مال **تیم** است — پروژه یا کسب‌وکار، دقیقاً یکی — چون پذیرش
    درخواست یعنی عضویت، و ایده تیمی ندارد که کسی به آن بپیوندد (ADR-0015).
    `idea_id` از §4.7 مانده ولی در فاز ۱ نوشته نمی‌شود.

    یک آگهی یک جای خالی است: پذیرش یک درخواست آن را `FILLED` می‌کند.
    """

    __tablename__ = "team_openings"

    poster_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE")
    )
    # ارجاع‌های رو به جلو — قیدشان در ۰۰۹ و ۰۰۸ افزوده شد.
    venture_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("ventures.id", ondelete="CASCADE")
    )
    idea_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("ideas.id", ondelete="CASCADE")
    )
    #: نقش پروژه — پذیرش، همان نقش را به عضو تازه می‌دهد (از ۰۰۱۴).
    role_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("project_roles.id", ondelete="SET NULL")
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    needed_skills: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(PGUUID(as_uuid=True)), nullable=False, server_default=text("'{}'::uuid[]")
    )
    commitment_hpw: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'OPEN'"))
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now() + interval '30 days'")
    )
    filled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint(_in_list("status", OPENING_STATUSES), name="status_valid"),
        CheckConstraint(
            "commitment_hpw IS NULL OR commitment_hpw BETWEEN 1 AND 60",
            name="commitment_range",
        ),
        CheckConstraint(
            "(project_id IS NOT NULL)::int + (venture_id IS NOT NULL)::int = 1", name="owner"
        ),
        CheckConstraint(
            "(status = 'FILLED') = (filled_at IS NOT NULL)", name="filled_matches_status"
        ),
        CheckConstraint(f"length(title) BETWEEN 3 AND {OPENING_TITLE_MAX}", name="title_length"),
        CheckConstraint(
            f"length(description) BETWEEN 10 AND {OPENING_DESCRIPTION_MAX}",
            name="description_length",
        ),
        CheckConstraint(
            f"cardinality(needed_skills) <= {MAX_OPENING_SKILLS}", name="needed_skills_count"
        ),
        Index("idx_team_openings_open", "expires_at", postgresql_where=text("status = 'OPEN'")),
        Index(
            "idx_team_openings_project",
            "project_id",
            postgresql_where=text("project_id IS NOT NULL"),
        ),
        Index(
            "idx_team_openings_venture",
            "venture_id",
            postgresql_where=text("venture_id IS NOT NULL"),
        ),
    )

    def is_open_at(self, now: datetime) -> bool:
        return self.status == "OPEN" and self.expires_at > now


class OpeningApplication(UUIDPrimaryKeyMixin, Base):
    """درخواست پیوستن از روی آگهی — FR-TEAM-03 «درخواست پیوستن از آگهی».

    جدا از `project_applications`: آن جدول مال پروژه است و کسب‌وکار
    درخواست پیوستن ندارد؛ آگهی هم می‌تواند پس از شروع کار پروژه باز شود،
    وقتی پروژه دیگر `OPEN` نیست.
    """

    __tablename__ = "opening_applications"

    opening_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("team_openings.id", ondelete="CASCADE"), nullable=False
    )
    applicant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'PENDING'"))
    decided_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id")
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        UniqueConstraint("opening_id", "applicant_id", name="uq_opening_applications_applicant"),
        CheckConstraint(_in_list("status", OPENING_APPLICATION_STATUSES), name="status_valid"),
        CheckConstraint(
            f"length(btrim(message)) BETWEEN 1 AND {OPENING_MESSAGE_MAX}", name="message_length"
        ),
        CheckConstraint(
            "(status = 'PENDING') = (decided_at IS NULL)", name="decided_matches_status"
        ),
        Index(
            "idx_opening_applications_pending",
            "opening_id",
            postgresql_where=text("status = 'PENDING'"),
        ),
        Index("idx_opening_applications_user", "applicant_id", "status"),
    )


__all__ = [
    "ARTIFACT_KINDS",
    "CERTIFICATE_KINDS",
    "DELIVERABLE_STATUSES",
    "DELIVERABLE_STATUS_TITLE_FA",
    "FEEDBACK_REQUIRED_STATUSES",
    "MILESTONE_STATUSES",
    "MILESTONE_STATUS_TITLE_FA",
    "MAX_OPENING_SKILLS",
    "OPENING_APPLICATION_STATUSES",
    "OPENING_DESCRIPTION_MAX",
    "OPENING_MESSAGE_MAX",
    "OPENING_STATUSES",
    "OPENING_TITLE_MAX",
    "OUTPUT_KINDS",
    "OUTPUT_KIND_TITLE_FA",
    "TASK_STATUSES",
    "TASK_STATUS_TITLE_FA",
    "Certificate",
    "Deliverable",
    "DeliverableFile",
    "Milestone",
    "OpeningApplication",
    "PeerEvaluation",
    "ProjectArtifactVersion",
    "ProjectActivity",
    "ProjectMessage",
    "ProjectReflection",
    "ProjectTask",
    "TeamOpening",
]
