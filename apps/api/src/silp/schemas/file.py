"""مدل‌های Pydantic برای /files — قرارداد §5.9."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

FilePurposeIn = Literal["DELIVERABLE", "RESOURCE", "PROJECT_COVER", "AVATAR", "MESSAGE"]
ScanStatus = Literal["PENDING", "CLEAN", "INFECTED", "SKIPPED"]

MAX_FILE_NAME = 255


class UploadUrlIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    original_name: Annotated[str, Field(min_length=1, max_length=MAX_FILE_NAME)]
    content_type: Annotated[str, Field(min_length=3, max_length=150)]
    # حجم ادعایی کلاینت. سقف واقعی هنگام `complete` روی خود شیء بررسی
    # می‌شود؛ این فقط جلوی شروع یک آپلود محکوم‌به‌شکست را می‌گیرد.
    size_bytes: Annotated[int, Field(gt=0)]
    purpose: FilePurposeIn


class UploadUrlOut(BaseModel):
    file_id: uuid.UUID
    upload_url: str
    method: str
    headers: dict[str, str]
    expires_in: int
    max_bytes: int


class FileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    original_name: str
    content_type: str
    size_bytes: int
    purpose: FilePurposeIn
    scan_status: ScanStatus
    uploaded_at: datetime | None = None


class DownloadUrlOut(BaseModel):
    download_url: str
    expires_in: int
    original_name: str


__all__ = ["DownloadUrlOut", "FileOut", "FilePurposeIn", "UploadUrlIn", "UploadUrlOut"]
