"""آداپتور ذخیره‌سازی شیء — رابط مشترک، S3/MinIO و پیاده‌سازی حافظه‌ای.

مرجع: §5.9، §11.7 («هر وابستگی پشت یک رابط»).

فایل هرگز از سرور اپلیکیشن عبور نمی‌کند (FR-EDU-03): کلاینت با URL امضاشده
مستقیم روی S3 می‌نویسد و مستقیم می‌خواند. سرور فقط سه کار می‌کند — امضا
کردن، پرسیدن «چقدر شد؟» و خواندن چند بایت اول برای Magic Number.

boto3 همگام است. تماس‌ها کوتاه‌اند ولی روی شبکه‌اند، پس در thread اجرا
می‌شوند تا حلقهٔ رویداد بند نیاید.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

from silp.core.config import Settings
from silp.core.logging import get_logger

if TYPE_CHECKING:  # pragma: no cover — فقط برای تایپ
    from mypy_boto3_s3.client import S3Client

log = get_logger("silp.storage")


@dataclass(frozen=True, slots=True)
class UploadTicket:
    """آنچه کلاینت برای آپلود مستقیم لازم دارد — §5.9."""

    url: str
    method: str
    headers: dict[str, str]
    expires_in: int


@dataclass(frozen=True, slots=True)
class ObjectInfo:
    size_bytes: int
    content_type: str
    etag: str | None = None


class ObjectMissing(Exception):
    """شیء در فضای ذخیره‌سازی نیست — کلاینت آپلود را تمام نکرده است."""


class StorageBackend(Protocol):
    """قرارداد ذخیره‌سازی شیء."""

    @property
    def bucket(self) -> str: ...

    async def upload_ticket(
        self, key: str, *, content_type: str, max_bytes: int, expires_in: int
    ) -> UploadTicket: ...

    async def download_url(self, key: str, *, filename: str, expires_in: int) -> str: ...

    async def stat(self, key: str) -> ObjectInfo: ...

    async def read_head(self, key: str, length: int) -> bytes: ...

    async def delete(self, key: str) -> None: ...


class S3Storage:
    """MinIO در توسعه، ابر آروان در تولید — هر دو با همین کلاینت (§12.3)."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._bucket = settings.s3_bucket
        self._client: S3Client | None = None

    @property
    def bucket(self) -> str:
        return self._bucket

    def _get_client(self) -> S3Client:
        if self._client is None:
            import boto3
            from botocore.config import Config

            self._client = boto3.client(
                "s3",
                endpoint_url=self._settings.s3_endpoint,
                aws_access_key_id=self._settings.s3_access_key,
                aws_secret_access_key=self._settings.s3_secret_key,
                region_name=self._settings.s3_region,
                # MinIO فقط sigv4 را می‌فهمد و آدرس مسیری می‌خواهد.
                config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
            )
        return self._client

    async def _call(self, name: str, **kwargs: Any) -> Any:
        client = self._get_client()
        return await asyncio.to_thread(getattr(client, name), **kwargs)

    async def upload_ticket(
        self, key: str, *, content_type: str, max_bytes: int, expires_in: int
    ) -> UploadTicket:
        url = await asyncio.to_thread(
            self._get_client().generate_presigned_url,
            "put_object",
            Params={"Bucket": self._bucket, "Key": key, "ContentType": content_type},
            ExpiresIn=expires_in,
        )
        # `max_bytes` در URL امضاشدهٔ PUT قابل اعمال نیست (آن کار POST
        # policy است). سقف واقعی هنگام `complete` با `stat` بررسی می‌شود
        # و فایل بزرگ‌تر پذیرفته نمی‌شود؛ این مقدار فقط به کلاینت
        # می‌گوید پیش از آپلود چه چیزی را رد کند.
        return UploadTicket(
            url=str(url),
            method="PUT",
            headers={"Content-Type": content_type},
            expires_in=expires_in,
        )

    async def download_url(self, key: str, *, filename: str, expires_in: int) -> str:
        # §11.1 — همیشه پیوست، هرگز نمایش درون‌خطی: HTML آپلودشده نباید
        # روی دامنهٔ ذخیره‌سازی اجرا شود.
        disposition = f'attachment; filename="{_ascii_fallback(filename)}"'
        if filename != _ascii_fallback(filename):
            disposition += f"; filename*=UTF-8''{_percent_encode(filename)}"
        url = await asyncio.to_thread(
            self._get_client().generate_presigned_url,
            "get_object",
            Params={
                "Bucket": self._bucket,
                "Key": key,
                "ResponseContentDisposition": disposition,
            },
            ExpiresIn=expires_in,
        )
        return str(url)

    async def stat(self, key: str) -> ObjectInfo:
        try:
            head = await self._call("head_object", Bucket=self._bucket, Key=key)
        except Exception as exc:
            raise ObjectMissing(key) from exc
        return ObjectInfo(
            size_bytes=int(head["ContentLength"]),
            content_type=str(head.get("ContentType", "application/octet-stream")),
            etag=str(head.get("ETag", "")).strip('"') or None,
        )

    async def read_head(self, key: str, length: int) -> bytes:
        try:
            obj = await self._call(
                "get_object", Bucket=self._bucket, Key=key, Range=f"bytes=0-{length - 1}"
            )
            return bytes(await asyncio.to_thread(obj["Body"].read))
        except Exception as exc:
            raise ObjectMissing(key) from exc

    async def delete(self, key: str) -> None:
        await self._call("delete_object", Bucket=self._bucket, Key=key)


class MemoryStorage:
    """برای تست و توسعهٔ بدون MinIO — همان رابط، بدون شبکه.

    `upload_ticket` آدرسی می‌دهد که هیچ‌جا نمی‌رود؛ تست به‌جای PUT،
    مستقیم `put_object` را صدا می‌زند.
    """

    def __init__(self, bucket: str = "memory") -> None:
        self._bucket = bucket
        self.objects: dict[str, tuple[bytes, str]] = {}

    @property
    def bucket(self) -> str:
        return self._bucket

    def put_object(self, key: str, body: bytes, content_type: str) -> None:
        """شبیه‌سازی آپلود کلاینت — فقط در تست."""
        self.objects[key] = (body, content_type)

    async def upload_ticket(
        self, key: str, *, content_type: str, max_bytes: int, expires_in: int
    ) -> UploadTicket:
        return UploadTicket(
            url=f"memory://{self._bucket}/{key}",
            method="PUT",
            headers={"Content-Type": content_type},
            expires_in=expires_in,
        )

    async def download_url(self, key: str, *, filename: str, expires_in: int) -> str:
        if key not in self.objects:
            raise ObjectMissing(key)
        return f"memory://{self._bucket}/{key}?download={_percent_encode(filename)}"

    async def stat(self, key: str) -> ObjectInfo:
        if key not in self.objects:
            raise ObjectMissing(key)
        body, content_type = self.objects[key]
        return ObjectInfo(size_bytes=len(body), content_type=content_type)

    async def read_head(self, key: str, length: int) -> bytes:
        if key not in self.objects:
            raise ObjectMissing(key)
        return self.objects[key][0][:length]

    async def delete(self, key: str) -> None:
        self.objects.pop(key, None)


def _ascii_fallback(filename: str) -> str:
    """نام امن برای هدر: بدون نویسهٔ غیر ASCII، گیومه و جداکنندهٔ مسیر."""
    cleaned = "".join(c if c.isascii() and c not in '"\\/\r\n' else "_" for c in filename)
    return cleaned.strip() or "download"


def _percent_encode(value: str) -> str:
    from urllib.parse import quote

    return quote(value, safe="")


_memory_storage = MemoryStorage()


def get_storage(settings: Settings) -> StorageBackend:
    """انتخاب آداپتور بر اساس پیکربندی."""
    if settings.storage_provider == "memory":
        return _memory_storage
    return S3Storage(settings)


def get_memory_storage() -> MemoryStorage:
    """نمونهٔ مشترک حافظه‌ای — تست از همین می‌خواند."""
    return _memory_storage


__all__ = [
    "MemoryStorage",
    "ObjectInfo",
    "ObjectMissing",
    "S3Storage",
    "StorageBackend",
    "UploadTicket",
    "get_memory_storage",
    "get_storage",
]
