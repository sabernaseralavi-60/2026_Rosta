"""مدل‌های موتور محتوا — ADR-0030."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class ContentCardOut(BaseModel):
    slug: str
    kind: str
    kind_fa: str
    title_fa: str
    summary: str
    cover: str | None
    access: str
    access_fa: str
    topics: list[str]
    reading_minutes: int
    published_at: datetime | None
    #: برای بیننده‌ای که این محتوا را نمی‌تواند بخواند `true` است؛ متنش هرگز نمی‌آید.
    locked: bool


class FacetOut(BaseModel):
    value: str
    label: str
    count: int


class ContentListOut(BaseModel):
    items: list[ContentCardOut]
    total: int
    kinds: list[FacetOut]
    topics: list[FacetOut]


class ContentDetailOut(ContentCardOut):
    skills: list[str]
    course_slug: str | None
    #: `null` وقتی `locked` است.
    body_md: str | None
    related: list[ContentCardOut]
