"""مدل‌های Pydantic برای پرسش‌وپاسخ درس — FR-EDU-07، ADR-0024 برش ج.

طول‌ها را سرویس با پیام فارسی می‌سنجد (`domain.qa`)؛ اینجا فقط سقف درشتی
هست تا بدنهٔ عظیم تا لایهٔ سرویس نرسد.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from silp.schemas.idea import AuthorOut

ThreadFilter = Literal["all", "unanswered", "unresolved", "mine"]
_GUARD = 8000


class ThreadIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Annotated[str, Field(max_length=_GUARD)]
    body: Annotated[str, Field(max_length=_GUARD)]
    #: شمارهٔ هفته؛ خالی یعنی پرسش عمومیِ درس.
    week_number: Annotated[int | None, Field(ge=1, le=52)] = None
    is_anonymous: bool = False


class ReplyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body: Annotated[str, Field(max_length=_GUARD)]


class ResolveIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_resolved: bool


class ReplyOut(BaseModel):
    id: uuid.UUID
    thread_id: uuid.UUID
    body: str
    author: AuthorOut
    #: پاسخ را خودِ استاد نوشته.
    is_official: bool
    helpful_count: int
    voted_by_me: bool
    #: استاد این پاسخ را تأیید کرده.
    is_endorsed: bool
    endorsed_at: datetime | None
    is_mine: bool
    can_vote: bool
    #: استاد می‌تواند تأیید بگذارد یا بردارد.
    can_endorse: bool
    can_delete: bool
    created_at: datetime


class ThreadSummaryOut(BaseModel):
    id: uuid.UUID
    offering_id: uuid.UUID
    week_number: int | None
    title: str
    excerpt: str
    #: برای پرسش ناشناسِ دیگران `None`.
    author: AuthorOut | None
    is_anonymous: bool
    is_resolved: bool
    reply_count: int
    #: پاسخ استاد یا پاسخِ تأییدشدهٔ استاد دارد.
    has_official_answer: bool
    is_mine: bool
    created_at: datetime


class ThreadDetailOut(ThreadSummaryOut):
    body: str
    replies: list[ReplyOut]
    can_resolve: bool
    can_delete: bool
    #: کاربر استادِ ارائه است (پاسخش رسمی می‌شود و تأیید می‌کند).
    is_manager: bool
