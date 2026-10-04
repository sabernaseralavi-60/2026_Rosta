"""مدل‌های گفت‌وگوی استاد–دانشجو — ADR-0036."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field


class ConversationOut(BaseModel):
    id: uuid.UUID
    kind: Literal["OFFERING", "DIRECT", "GROUP"]
    offering_id: uuid.UUID
    course_title: str
    title: str
    last_message_at: datetime | None
    last_preview: str | None
    unread: int
    can_write: bool


class MessageOut(BaseModel):
    id: uuid.UUID
    sender_id: uuid.UUID
    sender_name: str
    mine: bool
    from_staff: bool
    body: str
    reply_to_id: uuid.UUID | None
    created_at: datetime
    deleted: bool


class MessageIn(BaseModel):
    body: Annotated[str, Field(min_length=1, max_length=4000)]
    reply_to_id: uuid.UUID | None = None


class UnreadOut(BaseModel):
    unread: int


class ThreadOut(BaseModel):
    student_id: uuid.UUID | None
    name: str
    has_account: bool
    conversation_id: uuid.UUID | None
    last_preview: str | None
    last_message_at: datetime | None
    unread: int


class ConversationRefOut(BaseModel):
    id: uuid.UUID


class AudienceIn(BaseModel):
    audience: Literal["ALL", "SELECTED"]
    student_ids: list[uuid.UUID] = Field(default_factory=list, max_length=500)
    body: Annotated[str, Field(min_length=1, max_length=4000)]


class SendResultOut(BaseModel):
    sent: int
    skipped_no_account: int
