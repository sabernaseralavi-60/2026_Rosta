"""آپلود و دانلود فایل — FR-EDU-03، §5.9، M2-08.

جریان سه‌مرحله‌ای است و هر مرحله عمداً کوچک است:

۱. `reserve()` — ردیف `files` با `uploaded_at IS NULL` ساخته و URL امضاشده
   برگردانده می‌شود. اینجا فقط **ادعای** کاربر بررسی می‌شود.
۲. کلاینت خودش روی S3 می‌نویسد؛ سرور در این مرحله اصلاً درگیر نیست.
۳. `complete()` — حجم واقعی و Magic Number بررسی و ردیف تکمیل می‌شود.

اگر مرحلهٔ سوم هرگز نیاید، یک ردیف رزروشده باقی می‌ماند که هیچ‌جا قابل
استناد نیست. این بدترین حالت است و بی‌ضرر — برعکسِ حالتی که فایل بدون
راستی‌آزمایی به تحویل‌دادنی بچسبد.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from silp.core.config import Settings
from silp.core.exceptions import (
    Conflict,
    ContentTypeNotAllowed,
    FileScanPending,
    FileTooLarge,
    NotFound,
    PermissionDenied,
    UploadIncomplete,
    ValidationFailed,
)
from silp.core.logging import get_logger
from silp.core.permissions import CurrentUser, Role
from silp.domain.files import policy
from silp.integrations.storage import ObjectMissing, StorageBackend, UploadTicket
from silp.models.delivery import DeliverableFile
from silp.models.file import File
from silp.models.research import ResearchSubmissionFile

log = get_logger("silp.files")

MAX_ORIGINAL_NAME_LENGTH = 255


@dataclass(frozen=True, slots=True)
class ReservedUpload:
    file_id: uuid.UUID
    ticket: UploadTicket
    max_bytes: int


class FileService:
    def __init__(self, session: AsyncSession, settings: Settings, storage: StorageBackend) -> None:
        self.session = session
        self.settings = settings
        self.storage = storage

    def _limits(self) -> dict[policy.Category, int]:
        raw = self.settings.upload_limit_overrides
        return {policy.Category(name): value for name, value in raw.items()}

    # ── مرحلهٔ ۱ ───────────────────────────────────────────────────────
    async def reserve(
        self,
        *,
        user_id: uuid.UUID,
        purpose: policy.FilePurpose,
        original_name: str,
        content_type: str,
        size_bytes: int,
    ) -> ReservedUpload:
        """ساخت ردیف رزرو و URL آپلود — §5.9."""
        name = original_name.strip()
        if not name or len(name) > MAX_ORIGINAL_NAME_LENGTH:
            raise ValidationFailed("نام فایل معتبر نیست.")
        if not policy.is_allowed(purpose, content_type):
            raise ContentTypeNotAllowed

        max_bytes = policy.max_bytes_for(content_type, self._limits())
        if size_bytes > max_bytes:
            raise FileTooLarge(max_bytes=max_bytes)

        spec = policy.spec_for(content_type)
        # `is_allowed` قبلاً None بودن را رد کرده؛ این فقط برای تایپ است.
        normalized_type = spec.content_type if spec else content_type

        file = File(
            storage_key="",
            bucket=self.storage.bucket,
            original_name=name,
            content_type=normalized_type,
            size_bytes=size_bytes,
            uploaded_by=user_id,
            purpose=purpose.value,
        )
        self.session.add(file)
        # شناسه در دیتابیس ساخته می‌شود (uuidv7)، پس کلید ذخیره‌سازی تا
        # پیش از flush وجود ندارد.
        await self.session.flush()
        file.storage_key = policy.storage_key(
            purpose=purpose, file_id=str(file.id), original_name=name
        )
        await self.session.commit()

        ticket = await self.storage.upload_ticket(
            file.storage_key,
            content_type=normalized_type,
            max_bytes=max_bytes,
            expires_in=self.settings.upload_url_ttl_seconds,
        )
        log.info("upload_reserved", file_id=str(file.id), purpose=purpose.value, size=size_bytes)
        return ReservedUpload(file_id=file.id, ticket=ticket, max_bytes=max_bytes)

    # ── مرحلهٔ ۳ ───────────────────────────────────────────────────────
    async def complete(self, *, file_id: uuid.UUID, user_id: uuid.UUID) -> File:
        """راستی‌آزمایی حجم و Magic Number، سپس تکمیل ردیف — §11.1."""
        file = await self.session.get(File, file_id)
        if file is None or file.deleted_at is not None:
            raise NotFound("فایل پیدا نشد.")
        if file.uploaded_by != user_id:
            # §6.4 قاعدهٔ ۴ — فایل کس دیگر برای این کاربر وجود ندارد.
            raise NotFound("فایل پیدا نشد.")
        if file.uploaded_at is not None:
            return file  # بی‌اثر در تکرار: دو بار کلیک، یک نتیجه.

        try:
            info = await self.storage.stat(file.storage_key)
        except ObjectMissing as exc:
            raise UploadIncomplete from exc

        max_bytes = policy.max_bytes_for(file.content_type, self._limits())
        if info.size_bytes > max_bytes:
            await self.storage.delete(file.storage_key)
            raise FileTooLarge(max_bytes=max_bytes)

        head = await self.storage.read_head(file.storage_key, policy.SIGNATURE_PROBE_BYTES)
        if not policy.matches_signature(file.content_type, head):
            # محتوای فایل با نوع ادعاشده نمی‌خواند: دور انداخته می‌شود،
            # نه اینکه با نوع «واقعی» پذیرفته شود.
            await self.storage.delete(file.storage_key)
            log.warning(
                "upload_signature_mismatch",
                file_id=str(file.id),
                claimed=file.content_type,
            )
            raise ContentTypeNotAllowed("محتوای فایل با نوع اعلام‌شده نمی‌خواند.")

        file.size_bytes = info.size_bytes
        file.uploaded_at = _now()
        # ClamAV در فاز ۱ مستقر نیست (§11.1)؛ تا آن زمان وضعیت صریحاً
        # «بررسی نشد» است، نه «پاک» — تا بعداً به‌جای اعتماد کاذب، یک
        # کار پس‌زمینه بتواند همین‌ها را بازبینی کند.
        file.scan_status = "SKIPPED"
        await self.session.commit()
        log.info("upload_completed", file_id=str(file.id), size=info.size_bytes)
        return file

    # ── دانلود ─────────────────────────────────────────────────────────
    async def download_url(self, *, file: File) -> str:
        """URL موقت دانلود — §5.9. همیشه با `Content-Disposition: attachment`."""
        if not file.is_complete:
            raise UploadIncomplete
        if file.scan_status == "INFECTED":
            raise FileScanPending("این فایل در بررسی امنیتی رد شد.")
        return await self.storage.download_url(
            file.storage_key,
            filename=file.original_name,
            expires_in=self.settings.download_url_ttl_seconds,
        )

    async def soft_delete(self, *, file_id: uuid.UUID, actor: CurrentUser) -> None:
        file = await self.session.get(File, file_id)
        if file is None or file.deleted_at is not None:
            raise NotFound("فایل پیدا نشد.")
        if file.uploaded_by != actor.id and not actor.has_role(Role.ADMIN):
            raise PermissionDenied("فقط آپلودکننده می‌تواند فایل را حذف کند.")
        # §7.6 «نسخه‌ها هرگز پاک نمی‌شوند» — پیوست یک تحویل بخشی از همان
        # نسخه است، و نسخهٔ فایل مدل شهری به آن ارجاع می‌دهد (ADR-0016).
        attached = await self.session.scalar(
            select(DeliverableFile.file_id).where(DeliverableFile.file_id == file.id).limit(1)
        )
        if attached is None:
            attached = await self.session.scalar(
                select(ResearchSubmissionFile.file_id)
                .where(ResearchSubmissionFile.file_id == file.id)
                .limit(1)
            )
        if attached is not None:
            raise Conflict("این فایل پیوست یک تحویل است و حذف نمی‌شود.")
        file.deleted_at = _now()
        await self.session.commit()

    # ── پیوست ──────────────────────────────────────────────────────────
    async def load_attachable(
        self, file_ids: list[uuid.UUID], *, owner_id: uuid.UUID
    ) -> list[File]:
        """فایل‌هایی که می‌توان به تحویل‌دادنی یا پیام چسباند.

        شرط‌ها با هم: مال همین کاربر، تکمیل‌شده، حذف‌نشده، آلوده‌نبوده.
        هر شناسهٔ نامعتبر خطا می‌دهد؛ پیوست بی‌صدای ۲ فایل از ۳ فایل،
        بدترین نوع شکست است.
        """
        if not file_ids:
            return []
        unique = list(dict.fromkeys(file_ids))
        if len(unique) > policy.MAX_FILES_PER_DELIVERABLE:
            raise ValidationFailed(
                f"حداکثر {policy.MAX_FILES_PER_DELIVERABLE} فایل در هر تحویل‌دادنی."
            )
        rows = (await self.session.scalars(select(File).where(File.id.in_(unique)))).all()
        by_id = {f.id: f for f in rows}
        result: list[File] = []
        for fid in unique:
            file = by_id.get(fid)
            if file is None or file.uploaded_by != owner_id or file.deleted_at is not None:
                raise NotFound("یکی از فایل‌ها پیدا نشد.")
            if not file.is_complete:
                raise UploadIncomplete
            if file.scan_status == "INFECTED":
                raise FileScanPending("یکی از فایل‌ها در بررسی امنیتی رد شد.")
            result.append(file)
        return result


def _now() -> datetime:
    return datetime.now(UTC)


__all__ = ["FileService", "ReservedUpload"]
