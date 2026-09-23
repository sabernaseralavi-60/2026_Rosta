"""سیاست آپلود: چه نوعی، چه حجمی، و چگونه راستی‌آزمایی می‌شود.

مرجع: FR-EDU-03، §5.9، §11.1، §11.8.

منطق خالص است و به S3 یا دیتابیس کاری ندارد؛ همین آن را مستقیم قابل
تست می‌کند.

**قاعدهٔ اصلی: پسوند و هدر `Content-Type` حرف کاربرند، نه حقیقت.**
حجم واقعی از `HEAD` روی شیء و نوع واقعی از چند بایت اول فایل خوانده
می‌شود. تا وقتی این دو با ادعای کاربر جور نباشد، فایل تکمیل نمی‌شود.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

MB = 1024 * 1024


class FilePurpose(StrEnum):
    """هدف آپلود — §5.9. سقف حجم و نوع مجاز از همین تعیین می‌شود."""

    DELIVERABLE = "DELIVERABLE"
    RESOURCE = "RESOURCE"
    PROJECT_COVER = "PROJECT_COVER"
    AVATAR = "AVATAR"
    MESSAGE = "MESSAGE"


PURPOSE_TITLE_FA: dict[FilePurpose, str] = {
    FilePurpose.DELIVERABLE: "تحویل‌دادنی",
    FilePurpose.RESOURCE: "منبع درس",
    FilePurpose.PROJECT_COVER: "تصویر پروژه",
    FilePurpose.AVATAR: "تصویر نیمرخ",
    FilePurpose.MESSAGE: "پیوست پیام",
}


class Category(StrEnum):
    """دستهٔ محتوا — سقف حجم روی دسته تعریف می‌شود، نه روی تک‌تک انواع."""

    DOCUMENT = "DOCUMENT"
    IMAGE = "IMAGE"
    VIDEO = "VIDEO"
    DATASET = "DATASET"
    ARCHIVE = "ARCHIVE"


# FR-EDU-03: «PDF ۵۰MB، ویدئو ۵۰۰MB، دیتاست ۲۰۰MB». سقف مطلق §11.8
# برابر ۵۰۰MB است و هیچ دسته‌ای از آن بالاتر نمی‌رود.
DEFAULT_MAX_BYTES: dict[Category, int] = {
    Category.DOCUMENT: 50 * MB,
    Category.IMAGE: 10 * MB,
    Category.VIDEO: 500 * MB,
    Category.DATASET: 200 * MB,
    Category.ARCHIVE: 200 * MB,
}

ABSOLUTE_MAX_BYTES = 500 * MB

# §11.8 — حداکثر فایل در هر تحویل‌دادنی.
MAX_FILES_PER_DELIVERABLE = 10


@dataclass(frozen=True, slots=True)
class ContentSpec:
    """یک نوع محتوای مجاز با امضای بایتی‌اش."""

    content_type: str
    category: Category
    extensions: tuple[str, ...]
    # فهرست **جایگزین‌ها**: فایل معتبر است اگر با دست‌کم یکی از آن‌ها
    # بخواند. هر جایگزین خودش چند تکه (آفست، بایت) دارد که **همه** باید
    # بخوانند — WebP هم `RIFF` در ۰ می‌خواهد و هم `WEBP` در ۸، وگرنه یک
    # فایل WAV از بررسی رد می‌شود.
    #
    # خالی یعنی این قالب امضای ثابت ندارد (متن ساده، CSV، JSON).
    signatures: tuple[tuple[tuple[int, bytes], ...], ...] = ()

    @property
    def has_signature(self) -> bool:
        return bool(self.signatures)


_ZIP_SIGNATURES = (((0, b"PK\x03\x04"),), ((0, b"PK\x05\x06"),), ((0, b"PK\x07\x08"),))
# XML — فایل‌های مدل شهری (`.osm`، `.net.xml`، `.rou.xml`، ADR-0016). بیشترشان
# با اعلان `<?xml` شروع می‌شوند؛ خروجی بعضی ابزارها مستقیم با ریشهٔ سند.
_XML_SIGNATURES = (
    ((0, b"<?xml"),),
    ((0, b"\xef\xbb\xbf<?xml"),),
    ((0, b"<osm"),),
    ((0, b"<net"),),
    ((0, b"<routes"),),
)
_OOXML = "application/vnd.openxmlformats-officedocument"

CONTENT_SPECS: tuple[ContentSpec, ...] = (
    ContentSpec("application/pdf", Category.DOCUMENT, (".pdf",), (((0, b"%PDF-"),),)),
    ContentSpec(
        f"{_OOXML}.wordprocessingml.document", Category.DOCUMENT, (".docx",), _ZIP_SIGNATURES
    ),
    ContentSpec(f"{_OOXML}.spreadsheetml.sheet", Category.DATASET, (".xlsx",), _ZIP_SIGNATURES),
    ContentSpec(
        f"{_OOXML}.presentationml.presentation",
        Category.DOCUMENT,
        (".pptx",),
        _ZIP_SIGNATURES,
    ),
    ContentSpec("image/png", Category.IMAGE, (".png",), (((0, b"\x89PNG\r\n\x1a\n"),),)),
    ContentSpec("image/jpeg", Category.IMAGE, (".jpg", ".jpeg"), (((0, b"\xff\xd8\xff"),),)),
    ContentSpec("image/webp", Category.IMAGE, (".webp",), (((0, b"RIFF"), (8, b"WEBP")),)),
    ContentSpec("video/mp4", Category.VIDEO, (".mp4", ".m4v"), (((4, b"ftyp"),),)),
    ContentSpec("application/zip", Category.ARCHIVE, (".zip",), _ZIP_SIGNATURES),
    ContentSpec("text/csv", Category.DATASET, (".csv",)),
    ContentSpec("text/plain", Category.DOCUMENT, (".txt", ".md")),
    ContentSpec("application/json", Category.DATASET, (".json", ".geojson")),
    ContentSpec("application/geo+json", Category.DATASET, (".geojson",)),
    ContentSpec("application/xml", Category.DATASET, (".xml", ".osm"), _XML_SIGNATURES),
    # مرورگرها `.xml` را اغلب با این نوع می‌فرستند؛ همان قاعده، نام دیگر.
    ContentSpec("text/xml", Category.DATASET, (".xml", ".osm"), _XML_SIGNATURES),
)

_BY_TYPE: dict[str, ContentSpec] = {spec.content_type: spec for spec in CONTENT_SPECS}

# چند بایت اول باید خوانده شود تا همهٔ امضاها قابل بررسی باشند.
SIGNATURE_PROBE_BYTES = 16

# §5.9 — هر هدف فقط دسته‌های معنادار خودش را می‌پذیرد. تصویر نیمرخ که
# بتواند ویدئوی ۵۰۰ مگابایتی باشد، یک انبار رایگان است، نه یک قابلیت.
PURPOSE_CATEGORIES: dict[FilePurpose, frozenset[Category]] = {
    FilePurpose.DELIVERABLE: frozenset(
        {Category.DOCUMENT, Category.IMAGE, Category.DATASET, Category.ARCHIVE, Category.VIDEO}
    ),
    FilePurpose.RESOURCE: frozenset(
        {Category.DOCUMENT, Category.IMAGE, Category.VIDEO, Category.DATASET}
    ),
    FilePurpose.PROJECT_COVER: frozenset({Category.IMAGE}),
    FilePurpose.AVATAR: frozenset({Category.IMAGE}),
    FilePurpose.MESSAGE: frozenset({Category.DOCUMENT, Category.IMAGE, Category.DATASET}),
}


def spec_for(content_type: str) -> ContentSpec | None:
    """مشخصات یک نوع محتوا، یا None اگر مجاز نباشد.

    پارامترهای پس از `;` (مثل `charset=utf-8`) حذف می‌شوند.
    """
    base = content_type.split(";", 1)[0].strip().lower()
    return _BY_TYPE.get(base)


def is_allowed(purpose: FilePurpose, content_type: str) -> bool:
    spec = spec_for(content_type)
    return spec is not None and spec.category in PURPOSE_CATEGORIES[purpose]


def max_bytes_for(content_type: str, overrides: dict[Category, int] | None = None) -> int:
    """سقف حجم این نوع محتوا. نوع ناشناخته سقف سخت‌گیرانهٔ سند می‌گیرد."""
    spec = spec_for(content_type)
    if spec is None:
        return DEFAULT_MAX_BYTES[Category.DOCUMENT]
    limits = {**DEFAULT_MAX_BYTES, **(overrides or {})}
    return min(limits[spec.category], ABSOLUTE_MAX_BYTES)


def matches_signature(content_type: str, head: bytes) -> bool:
    """آیا بایت‌های ابتدای فایل با نوع ادعاشده می‌خوانند؟ — §11.1.

    قالب‌های بدون امضای ثابت (CSV، متن، JSON) همیشه قبول می‌شوند؛ برای
    آن‌ها Magic Number وجود ندارد که بررسی شود. امنیتشان از راه دیگری
    می‌آید: سرو شدن با `Content-Disposition: attachment`.
    """
    spec = spec_for(content_type)
    if spec is None:
        return False
    if not spec.has_signature:
        return True
    return any(
        all(head[offset : offset + len(part)] == part for offset, part in alternative)
        for alternative in spec.signatures
    )


def extension_of(original_name: str) -> str:
    _, dot, ext = original_name.rpartition(".")
    return f".{ext.lower()}" if dot else ""


def storage_key(*, purpose: FilePurpose, file_id: str, original_name: str) -> str:
    """کلید ذخیره‌سازی قطعی — از شناسهٔ فایل ساخته می‌شود، نه از نام کاربر.

    نام اصلی فقط پسوند را می‌دهد. نام کاربر ممکن است `../`، فاصله،
    یا نویسهٔ کنترلی داشته باشد؛ هیچ‌کدام وارد کلید نمی‌شوند.
    """
    ext = extension_of(original_name)
    safe_ext = ext if ext.isascii() and ext[1:].isalnum() else ""
    return f"{purpose.value.lower()}/{file_id}{safe_ext}"


__all__ = [
    "ABSOLUTE_MAX_BYTES",
    "CONTENT_SPECS",
    "DEFAULT_MAX_BYTES",
    "MAX_FILES_PER_DELIVERABLE",
    "MB",
    "PURPOSE_CATEGORIES",
    "PURPOSE_TITLE_FA",
    "SIGNATURE_PROBE_BYTES",
    "Category",
    "ContentSpec",
    "FilePurpose",
    "extension_of",
    "is_allowed",
    "matches_signature",
    "max_bytes_for",
    "spec_for",
    "storage_key",
]
