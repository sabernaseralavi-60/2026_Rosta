"""مدل‌های Pydantic برای /ideas — قرارداد §5.8، FR-IDEA-01/02/03."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

IdeaStatus = Literal["OPEN", "PROMOTED", "ARCHIVED"]
IdeaSort = Literal["hot", "new", "top"]
IdeaCategory = Literal[
    "TRANSPORT",
    "AGRICULTURE",
    "COMMERCE",
    "EDUCATION",
    "TECHNOLOGY",
    "ENVIRONMENT",
    "SOCIAL",
    "OTHER",
]
PromotionTarget = Literal["PROJECT", "VENTURE"]


class IdeaIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Annotated[str, Field(min_length=3, max_length=120)]
    body: Annotated[str, Field(min_length=10, max_length=4000)]
    problem: Annotated[str | None, Field(max_length=1000)] = None
    category: IdeaCategory | None = None
    tags: Annotated[list[str], Field(max_length=8)] = Field(default_factory=list)
    is_anonymous: bool = False


class AuthorOut(BaseModel):
    """نویسنده — برای ایدهٔ ناشناس `None` است، مگر برای خودش."""

    id: uuid.UUID
    name: str | None
    username: str | None


class IdeaSummaryOut(BaseModel):
    id: uuid.UUID
    title: str
    excerpt: str
    category: IdeaCategory | None = None
    category_fa: str | None = None
    tags: list[str] = Field(default_factory=list)
    status: IdeaStatus
    is_anonymous: bool
    author: AuthorOut | None = None
    vote_count: int
    comment_count: int
    voted_by_me: bool = False
    is_mine: bool = False
    promoted_to_type: PromotionTarget | None = None
    promoted_to_id: uuid.UUID | None = None
    created_at: datetime


class CommentOut(BaseModel):
    id: uuid.UUID
    parent_id: uuid.UUID | None = None
    body: str | None
    author: AuthorOut | None
    is_deleted: bool = False
    is_mine: bool = False
    can_delete: bool = False
    created_at: datetime


class IdeaDetailOut(IdeaSummaryOut):
    body: str
    problem: str | None = None
    archived_reason: str | None = None
    promoted_at: datetime | None = None
    comments: list[CommentOut] = Field(default_factory=list)
    can_edit: bool = False
    can_promote: bool = False
    can_moderate: bool = False


class VoteOut(BaseModel):
    idea_id: uuid.UUID
    vote_count: int
    voted_by_me: bool


class CommentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body: Annotated[str, Field(min_length=1, max_length=1000)]
    parent_id: uuid.UUID | None = None


class ArchiveIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: Annotated[str, Field(min_length=1, max_length=500)]


class PromoteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target: PromotionTarget
    project_kind: Literal["A_VENTURE", "B_RESEARCH", "C_PROBLEM", "D_PERSONAL"] = "C_PROBLEM"
    expected_output: Annotated[str | None, Field(max_length=500)] = None


class PromotionOut(BaseModel):
    target_type: PromotionTarget
    target_id: uuid.UUID
    href: str


class CategoryOut(BaseModel):
    code: IdeaCategory
    title_fa: str
