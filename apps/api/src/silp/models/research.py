"""مدل‌های پژوهش — PRD §4.7، FR-RES-01/02/03، ADR-0015. مهاجرت متناظر: 0014_research.

| جدول | نقش |
|------|-----|
| `research_tracks` | یک ردیف به‌ازای هر (دانشجو، سطح) — وضعیت سطح |
| `research_submissions` | نسخه‌های تحویل یک سطح، با بازخورد بازبین |
| `research_submission_files` | پیوست فایل تحویل |
| `research_outputs` | مقاله، پایان‌نامه و گزارش — با راستی‌آزمایی (FR-RES-02) |
| `research_topics` | بانک موضوع با پیشنهاد، رزرو و آزادسازی (FR-RES-03) |

§4.7 ستون `research_tracks.deliverable_id` را به `deliverables` داده بود؛
ولی تحویل‌دادنی به **مرحلهٔ پروژه** بسته است (`milestone_id NOT NULL`) و
مسیر پژوهش پروژه ندارد. پس تحویل سطح جدول خودش را دارد — با همان الگوی
نسخه‌بندی §7.6: نسخهٔ «اصلاح کن» پاک نمی‌شود.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from silp.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from silp.domain.research import (
    OUTPUT_KINDS,
    OUTPUT_STAGES,
    OUTPUT_STATUSES,
    QUARTILES,
    REVIEW_STATUSES,
    TOPIC_STATUSES,
)

TRACK_STATUSES = ("IN_PROGRESS", "SUBMITTED", "APPROVED")
SUBMISSION_STATUSES = ("SUBMITTED", "APPROVED", "CHANGES_REQUESTED")

SUBMISSION_STATUS_TITLE_FA: dict[str, str] = {
    "SUBMITTED": "در انتظار بررسی",
    "APPROVED": "تأیید شده",
    "CHANGES_REQUESTED": "نیازمند اصلاح",
}
REVIEW_STATUS_TITLE_FA: dict[str, str] = {
    "NONE": "بدون نیاز به راستی‌آزمایی",
    "PENDING": "در انتظار راستی‌آزمایی",
    "VERIFIED": "راستی‌آزمایی شده",
    "REJECTED": "راستی‌آزمایی نشد",
}

TOPIC_TITLE_MAX = 200
TOPIC_DESCRIPTION_MAX = 4000
PREREQUISITES_MAX = 1000
OUTPUT_TITLE_MAX = 300
AUTHORS_MAX = 500
NOTE_MAX = 1000


def _in_list(column: str, values: tuple[str, ...]) -> str:
    joined = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({joined})"


class ResearchTrack(Base):
    """یک سطح از مسیر یک دانشجو. ردیف سطح بعد با تأیید همین سطح ساخته می‌شود."""

    __tablename__ = "research_tracks"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    level: Mapped[int] = mapped_column(Integer, primary_key=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'IN_PROGRESS'"))
    #: نخستین بازبینی که این سطح را بررسی کرد — تحویل بعدی به او خبر داده می‌شود.
    mentor_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id")
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id")
    )

    __table_args__ = (
        CheckConstraint("level BETWEEN 1 AND 4", name="level_range"),
        CheckConstraint(_in_list("status", TRACK_STATUSES), name="status_valid"),
        CheckConstraint(
            "(status = 'APPROVED') = (approved_at IS NOT NULL)", name="approved_matches_status"
        ),
        CheckConstraint(
            "(approved_at IS NULL) = (approved_by IS NULL)", name="approval_fields_together"
        ),
    )


class ResearchSubmission(UUIDPrimaryKeyMixin, Base):
    """یک نسخه از تحویل یک سطح."""

    __tablename__ = "research_submissions"

    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    #: موضوع رزروشدهٔ دانشجو در لحظهٔ تحویل — تحویل، «تحرک» رزرو است.
    topic_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("research_topics.id", ondelete="SET NULL")
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    links: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'::text[]")
    )
    #: شاهدهای ساختاریافتهٔ سطح (`silp.domain.research.LEVEL_SPECS`).
    evidence: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'SUBMITTED'"))
    feedback: Mapped[str | None] = mapped_column(Text)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    files: Mapped[list[ResearchSubmissionFile]] = relationship(
        back_populates="submission", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id", "level"],
            ["research_tracks.user_id", "research_tracks.level"],
            name="fk_research_submissions_track",
            ondelete="CASCADE",
        ),
        UniqueConstraint("user_id", "level", "version", name="uq_research_submissions_version"),
        CheckConstraint(_in_list("status", SUBMISSION_STATUSES), name="status_valid"),
        CheckConstraint("version >= 1", name="version_positive"),
        CheckConstraint("length(summary) BETWEEN 30 AND 4000", name="summary_length"),
        CheckConstraint("cardinality(links) <= 10", name="links_count"),
        CheckConstraint("jsonb_typeof(evidence) = 'object'", name="evidence_is_object"),
        CheckConstraint(
            "status <> 'CHANGES_REQUESTED' OR length(btrim(coalesce(feedback, ''))) > 0",
            name="feedback_required",
        ),
        CheckConstraint(
            "(status = 'SUBMITTED') = (reviewed_at IS NULL)", name="reviewed_matches_status"
        ),
        CheckConstraint(
            "(reviewed_at IS NULL) = (reviewed_by IS NULL)", name="review_fields_together"
        ),
        # تأیید تحویل خود، تأیید نیست.
        CheckConstraint("reviewed_by IS NULL OR reviewed_by <> user_id", name="not_self_reviewed"),
        # یک تحویل باز به‌ازای هر سطح.
        Index(
            "idx_research_submissions_open",
            "user_id",
            "level",
            unique=True,
            postgresql_where=text("status = 'SUBMITTED'"),
        ),
        Index(
            "idx_research_submissions_queue",
            "submitted_at",
            postgresql_where=text("status = 'SUBMITTED'"),
        ),
    )


class ResearchSubmissionFile(Base):
    __tablename__ = "research_submission_files"

    submission_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("research_submissions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    file_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("files.id"), primary_key=True
    )

    submission: Mapped[ResearchSubmission] = relationship(back_populates="files")


class ResearchOutput(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """خروجی پژوهشی — FR-RES-02.

    `status` ادعای نویسنده است؛ `verified_stage` و `verified_quartile`
    چیزی است که بازبین دیده. امتیاز فقط از دومی می‌آید (ADR-0015).
    """

    __tablename__ = "research_outputs"

    owner_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    authors: Mapped[str] = mapped_column(Text, nullable=False)
    venue: Mapped[str | None] = mapped_column(Text)
    quartile: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'DRAFT'"))
    doi: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text)
    file_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("files.id"))
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL")
    )
    submitted_on: Mapped[date | None] = mapped_column(Date)
    published_on: Mapped[date | None] = mapped_column(Date)

    verified_stage: Mapped[str | None] = mapped_column(Text)
    verified_quartile: Mapped[str | None] = mapped_column(Text)
    review_status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'NONE'"))
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_note: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint(_in_list("kind", OUTPUT_KINDS), name="kind_valid"),
        CheckConstraint(_in_list("status", OUTPUT_STATUSES), name="status_valid"),
        CheckConstraint(
            f"quartile IS NULL OR {_in_list('quartile', QUARTILES)}", name="quartile_valid"
        ),
        CheckConstraint(
            f"verified_stage IS NULL OR {_in_list('verified_stage', OUTPUT_STAGES)}",
            name="verified_stage_valid",
        ),
        CheckConstraint(
            f"verified_quartile IS NULL OR {_in_list('verified_quartile', QUARTILES)}",
            name="verified_quartile_valid",
        ),
        CheckConstraint(_in_list("review_status", REVIEW_STATUSES), name="review_status_valid"),
        CheckConstraint(f"length(title) BETWEEN 3 AND {OUTPUT_TITLE_MAX}", name="title_length"),
        CheckConstraint(f"length(authors) BETWEEN 2 AND {AUTHORS_MAX}", name="authors_length"),
        CheckConstraint("url IS NULL OR length(url) <= 500", name="url_length"),
        CheckConstraint(r"doi IS NULL OR doi ~ '^10\.\d{4,9}/\S+$'", name="doi_format"),
        CheckConstraint(
            "review_status <> 'REJECTED' OR length(btrim(coalesce(review_note, ''))) > 0",
            name="rejection_has_note",
        ),
        CheckConstraint("reviewed_by IS NULL OR reviewed_by <> owner_id", name="not_self_reviewed"),
        Index("idx_research_outputs_owner", "owner_id", text("created_at DESC")),
        Index(
            "idx_research_outputs_pending",
            "updated_at",
            postgresql_where=text("review_status = 'PENDING'"),
        ),
    )


class ResearchTopic(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """موضوع پژوهشی — FR-RES-03.

    `last_activity_at` ساعت بی‌تحرکی رزرو است: رزرو، تحویل سطح با این
    موضوع، و بازخورد بازبین آن را جلو می‌برند. سی روز بی‌تحرکی ⇒ آزاد.
    """

    __tablename__ = "research_topics"

    proposer_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    prerequisites: Mapped[str | None] = mapped_column(Text)
    level: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'OPEN'"))
    reserved_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id")
    )
    reserved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_activity_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_note: Mapped[str | None] = mapped_column(Text)

    search_norm: Mapped[str | None] = mapped_column(
        Text, Computed("fa_normalize(title || ' ' || description)", persisted=True)
    )

    __table_args__ = (
        CheckConstraint(_in_list("status", TOPIC_STATUSES), name="status_valid"),
        CheckConstraint("level IS NULL OR level BETWEEN 1 AND 4", name="level_range"),
        CheckConstraint(f"length(title) BETWEEN 5 AND {TOPIC_TITLE_MAX}", name="title_length"),
        CheckConstraint(
            f"length(description) BETWEEN 20 AND {TOPIC_DESCRIPTION_MAX}",
            name="description_length",
        ),
        CheckConstraint(
            f"prerequisites IS NULL OR length(prerequisites) <= {PREREQUISITES_MAX}",
            name="prerequisites_length",
        ),
        CheckConstraint(
            "(status IN ('RESERVED', 'TAKEN')) = (reserved_by IS NOT NULL)",
            name="reservation_matches_status",
        ),
        CheckConstraint(
            "(reserved_by IS NULL) = (reserved_at IS NULL)"
            " AND (reserved_by IS NULL) = (last_activity_at IS NULL)",
            name="reservation_fields_together",
        ),
        Index("idx_topics_search", text("search_norm gin_trgm_ops"), postgresql_using="gin"),
        Index("idx_topics_status", "status", text("created_at DESC")),
        Index(
            "idx_topics_reservation_expiry",
            "last_activity_at",
            postgresql_where=text("status = 'RESERVED'"),
        ),
        # یک رزرو باز برای هر نفر — ADR-0015.
        Index(
            "idx_topics_one_reservation",
            "reserved_by",
            unique=True,
            postgresql_where=text("status = 'RESERVED'"),
        ),
    )


__all__ = [
    "NOTE_MAX",
    "REVIEW_STATUS_TITLE_FA",
    "SUBMISSION_STATUSES",
    "SUBMISSION_STATUS_TITLE_FA",
    "TRACK_STATUSES",
    "ResearchOutput",
    "ResearchSubmission",
    "ResearchSubmissionFile",
    "ResearchTopic",
    "ResearchTrack",
]
