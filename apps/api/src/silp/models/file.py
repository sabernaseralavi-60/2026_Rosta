"""مدل فایل — PRD §4.9.

مهاجرت متناظر: 0005_files.

فایل از سرور اپلیکیشن عبور نمی‌کند (FR-EDU-03): کلاینت با Presigned URL
مستقیم روی S3 می‌نویسد. بنابراین یک ردیف `files` دو عمر دارد:

۱. **رزروشده** — `uploaded_at IS NULL`. فقط جا گرفته است؛ هیچ جای دیگری
   نباید به آن استناد کند.
۲. **تکمیل‌شده** — پس از `POST /files/{id}/complete` که حجم و Magic Number
   را راستی‌آزمایی می‌کند.

ردیف رزروشده‌ای که هرگز تکمیل نشود، زباله است و کار پاک‌سازی آن را
برمی‌دارد؛ این بهتر از ساختن ردیف پس از آپلود است، چون بدون شناسهٔ از
پیش‌ساخته نمی‌توان کلید ذخیره‌سازی قطعی تولید کرد.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, Text, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from silp.db.base import Base, SoftDeleteMixin, UUIDPrimaryKeyMixin

SCAN_STATUSES = ("PENDING", "CLEAN", "INFECTED", "SKIPPED")

# §5.9 — هدف آپلود سقف حجم و نوع مجاز را تعیین می‌کند.
FILE_PURPOSES = (
    "DELIVERABLE",
    "RESOURCE",
    "PROJECT_COVER",
    "AVATAR",
    "MESSAGE",
)


class File(UUIDPrimaryKeyMixin, SoftDeleteMixin, Base):
    __tablename__ = "files"

    storage_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    bucket: Mapped[str] = mapped_column(Text, nullable=False)
    original_name: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    checksum_sha256: Mapped[str | None] = mapped_column(Text)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    scan_status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'PENDING'"))
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    uploaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint("size_bytes > 0", name="size_positive"),
        CheckConstraint(
            "scan_status IN ('PENDING', 'CLEAN', 'INFECTED', 'SKIPPED')", name="scan_status_valid"
        ),
        Index("idx_files_uploader", "uploaded_by", text("created_at DESC")),
        Index(
            "idx_files_scan_queue",
            "created_at",
            postgresql_where=text("scan_status = 'PENDING' AND uploaded_at IS NOT NULL"),
        ),
    )

    @property
    def is_complete(self) -> bool:
        return self.uploaded_at is not None and self.deleted_at is None

    @property
    def is_attachable(self) -> bool:
        """آیا می‌توان این فایل را به تحویل‌دادنی یا پیام چسباند؟

        فایل آلوده هرگز؛ فایل در انتظار اسکن بله. ClamAV در فاز ۱ نصب
        نیست (§11.1) و اگر انتظار اسکن مانع پیوست شود، هیچ فایلی پیوست
        نمی‌شود. دانلود است که پیش از پاک بودن مسدود می‌گردد.
        """
        return self.is_complete and self.scan_status != "INFECTED"


__all__ = ["FILE_PURPOSES", "SCAN_STATUSES", "File"]
