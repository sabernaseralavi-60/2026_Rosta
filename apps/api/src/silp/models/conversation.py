"""گفت‌وگوی استاد–دانشجو — ADR-0036، مهاجرت ۰۰۳۰."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Text, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from silp.db.base import Base, UUIDPrimaryKeyMixin

CONVERSATION_KINDS = ("OFFERING", "DIRECT", "GROUP")
MEMBER_ROLES = ("STAFF", "STUDENT")


class Conversation(UUIDPrimaryKeyMixin, Base):
    """`OFFERING` = کانال درس (فقط کادر می‌نویسد)، `DIRECT` = استاد↔یک دانشجو."""

    __tablename__ = "conversations"

    kind: Mapped[str] = mapped_column(Text, nullable=False)
    offering_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("course_offerings.id", ondelete="CASCADE"), nullable=False
    )
    student_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id")
    )
    title: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("kind IN ('OFFERING', 'DIRECT', 'GROUP')", name="kind_valid"),
        CheckConstraint("(kind = 'DIRECT') = (student_id IS NOT NULL)", name="student_for_direct"),
        Index(
            "uq_conversations_offering_channel",
            "offering_id",
            unique=True,
            postgresql_where=text("kind = 'OFFERING'"),
        ),
        Index(
            "uq_conversations_direct",
            "offering_id",
            "student_id",
            unique=True,
            postgresql_where=text("kind = 'DIRECT'"),
        ),
    )


class ConversationMember(Base):
    __tablename__ = "conversation_members"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[str] = mapped_column(Text, nullable=False)
    last_read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint("role IN ('STAFF', 'STUDENT')", name="role_valid"),
        Index("idx_conversation_members_user", "user_id"),
    )


class Message(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "messages"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    sender_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    reply_to_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("messages.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("length(body) BETWEEN 1 AND 4000", name="body_length"),
        Index("idx_messages_conversation", "conversation_id", "id"),
    )
