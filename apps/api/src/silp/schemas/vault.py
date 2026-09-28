"""مدل‌های آپلود Vault — ADR-0031."""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

#: سقف‌ها: یک Vault شخصی چند صد یادداشت دارد، نه چند هزار. بزرگ‌تر از این ۴۲۲
#: می‌گیرد (حافظهٔ کارگر پر نشود). پشت nginx `client_max_body_size` هم باید هم‌اندازه باشد.
MAX_NOTES = 500
MAX_NOTE_CHARS = 300_000

RelPath = Annotated[
    str,
    StringConstraints(min_length=1, max_length=300, pattern=r"^12_Content/[^\\\x00]+\.md$"),
]


class VaultNoteIn(BaseModel):
    """یک فایل، خام. تحلیل و اعتبارسنجی سمت سرور است، نه از دستِ ابزار."""

    path: RelPath
    #: متن کامل فایل (UTF-8) — `sha256` همین متن ملاک «تغییر کرده؟» است.
    raw: Annotated[str, Field(max_length=MAX_NOTE_CHARS)]


class VaultPublishIn(BaseModel):
    notes: Annotated[list[VaultNoteIn], Field(max_length=MAX_NOTES)]
    #: پیش‌فرض ایمن: پیش‌نمایش. نوشتن واقعی صریح است.
    apply: bool = False
    #: «این فهرست کل Vault است.» فقط آن‌وقت فایل‌های ناپدیدشده آرشیو می‌شوند؛
    #: فهرست ناقص هرگز آرشیو نمی‌کند.
    complete: bool = False
    #: فایل‌هایی که خودِ ابزار نتوانست بخواند (مثلاً UTF-8 نبود) — آرشیو نشوند.
    client_errors: dict[str, str] = Field(default_factory=dict, max_length=MAX_NOTES)


class VaultPublishOut(BaseModel):
    applied: bool
    created: list[str]
    updated: list[str]
    unchanged: list[str]
    archived: list[str]
    errors: dict[str, str]
    warnings: dict[str, list[str]]
    ok: bool
