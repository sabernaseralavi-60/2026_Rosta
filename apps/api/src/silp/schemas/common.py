"""مدل‌های مشترک پاسخ — §5.1."""

from __future__ import annotations

from typing import Annotated, Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")

MAX_PAGE_SIZE = 100
DEFAULT_PAGE_SIZE = 20


class Page(BaseModel, Generic[T]):
    """قالب فهرست صفحه‌بندی‌شده — §5.1."""

    items: list[T]
    total: int
    page: int
    page_size: int
    has_next: bool

    @classmethod
    def of(cls, items: list[T], *, total: int, page: int, page_size: int) -> Page[T]:
        return cls(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            has_next=page * page_size < total,
        )


class Cursor(BaseModel, Generic[T]):
    """مکان‌نمای کرسری برای فهرست‌های پرترافیک — §5.1."""

    items: list[T]
    next_cursor: str | None = None


class PageParams(BaseModel):
    page: Annotated[int, Field(ge=1)] = 1
    page_size: Annotated[int, Field(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    trace_id: str


class ErrorResponse(BaseModel):
    """قالب ثابت خطا — §5.1. فقط برای مستندسازی OpenAPI."""

    error: ErrorDetail


class HealthOut(BaseModel):
    status: str
    environment: str
    version: str
    checks: dict[str, str] = Field(default_factory=dict)
