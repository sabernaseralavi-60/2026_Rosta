"""مسیر /files — §5.9، M2-08.

فایل از سرور اپلیکیشن عبور نمی‌کند. این مسیرها فقط اجازه می‌دهند،
راستی‌آزمایی می‌کنند و آدرس موقت می‌سازند.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, status

from silp.core.exceptions import NotFound
from silp.domain.files import policy
from silp.models.file import File
from silp.routers.deps import CurrentUserDep, FileServiceDep, SessionDep, SettingsDep
from silp.schemas.common import ErrorResponse
from silp.schemas.file import DownloadUrlOut, FileOut, UploadUrlIn, UploadUrlOut

router = APIRouter(prefix="/files", tags=["files"])


@router.post(
    "/upload-url",
    response_model=UploadUrlOut,
    summary="دریافت URL آپلود مستقیم",
    responses={
        413: {"model": ErrorResponse, "description": "FILE_TOO_LARGE"},
        415: {"model": ErrorResponse, "description": "CONTENT_TYPE_NOT_ALLOWED"},
    },
)
async def upload_url(
    payload: UploadUrlIn,
    current: CurrentUserDep,
    files: FileServiceDep,
) -> UploadUrlOut:
    """§5.9 — کلاینت با این آدرس مستقیم روی S3 می‌نویسد."""
    reserved = await files.reserve(
        user_id=current.id,
        purpose=policy.FilePurpose(payload.purpose),
        original_name=payload.original_name,
        content_type=payload.content_type,
        size_bytes=payload.size_bytes,
    )
    return UploadUrlOut(
        file_id=reserved.file_id,
        upload_url=reserved.ticket.url,
        method=reserved.ticket.method,
        headers=reserved.ticket.headers,
        expires_in=reserved.ticket.expires_in,
        max_bytes=reserved.max_bytes,
    )


@router.post(
    "/{file_id}/complete",
    response_model=FileOut,
    summary="اعلام پایان آپلود",
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
async def complete_upload(
    file_id: uuid.UUID,
    current: CurrentUserDep,
    files: FileServiceDep,
) -> FileOut:
    """حجم واقعی و Magic Number اینجا بررسی می‌شوند — §11.1."""
    file = await files.complete(file_id=file_id, user_id=current.id)
    return FileOut.model_validate(file)


@router.get(
    "/{file_id}/download-url",
    response_model=DownloadUrlOut,
    summary="URL دانلود موقت",
    responses={404: {"model": ErrorResponse}},
)
async def download_url(
    file_id: uuid.UUID,
    current: CurrentUserDep,
    files: FileServiceDep,
    session: SessionDep,
    settings: SettingsDep,
) -> DownloadUrlOut:
    """آدرس کوتاه‌عمر با `Content-Disposition: attachment`.

    در M2 فقط آپلودکننده دانلود می‌کند. دسترسی هم‌تیمی‌ها به کتابخانهٔ
    فایل پروژه از راه `GET /projects/{id}/files` می‌آید؛ تا آن زمان
    نشتی وجود ندارد.
    """
    file = await session.get(File, file_id)
    if file is None or file.deleted_at is not None or file.uploaded_by != current.id:
        raise NotFound("فایل پیدا نشد.")
    url = await files.download_url(file=file)
    return DownloadUrlOut(
        download_url=url,
        expires_in=settings.download_url_ttl_seconds,
        original_name=file.original_name,
    )


@router.delete(
    "/{file_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="حذف نرم فایل",
    responses={404: {"model": ErrorResponse}},
)
async def delete_file(
    file_id: uuid.UUID,
    current: CurrentUserDep,
    files: FileServiceDep,
) -> None:
    await files.soft_delete(file_id=file_id, actor=current)


__all__ = ["router"]
