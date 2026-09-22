"""سیاست آپلود — FR-EDU-03، §5.9، §11.1.

منطق خالص است و دیتابیس یا S3 نمی‌خواهد؛ همهٔ این‌ها بدون داکر اجرا
می‌شوند.
"""

from __future__ import annotations

import pytest

from silp.domain.files import policy
from silp.domain.files.policy import MB, Category, FilePurpose


# ── نوع مجاز ───────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    ("purpose", "content_type", "allowed"),
    [
        (FilePurpose.DELIVERABLE, "application/pdf", True),
        (FilePurpose.DELIVERABLE, "video/mp4", True),
        # تصویر نیمرخ فقط تصویر است؛ وگرنه انبار رایگان می‌شود.
        (FilePurpose.AVATAR, "image/png", True),
        (FilePurpose.AVATAR, "video/mp4", False),
        (FilePurpose.AVATAR, "application/pdf", False),
        (FilePurpose.PROJECT_COVER, "image/jpeg", True),
        (FilePurpose.PROJECT_COVER, "application/zip", False),
        # نوع ناشناخته هیچ‌جا مجاز نیست.
        (FilePurpose.DELIVERABLE, "application/x-msdownload", False),
        (FilePurpose.DELIVERABLE, "text/html", False),
    ],
)
def test_purpose_limits_content_type(
    purpose: FilePurpose, content_type: str, allowed: bool
) -> None:
    assert policy.is_allowed(purpose, content_type) is allowed


def test_content_type_parameters_are_ignored() -> None:
    """`text/csv; charset=utf-8` همان `text/csv` است."""
    assert policy.is_allowed(FilePurpose.DELIVERABLE, "text/csv; charset=utf-8")
    assert policy.spec_for("APPLICATION/PDF") is not None


# ── سقف حجم ────────────────────────────────────────────────────────────
def test_size_caps_follow_the_spec() -> None:
    """FR-EDU-03 — PDF ۵۰، ویدئو ۵۰۰، دیتاست ۲۰۰ مگابایت."""
    assert policy.max_bytes_for("application/pdf") == 50 * MB
    assert policy.max_bytes_for("video/mp4") == 500 * MB
    assert policy.max_bytes_for("text/csv") == 200 * MB


def test_overrides_never_exceed_the_absolute_cap() -> None:
    """§11.8 — سقف مطلق ۵۰۰MB است، حتی اگر پیکربندی بیشتر بخواهد."""
    huge = {Category.DOCUMENT: 5_000 * MB}
    assert policy.max_bytes_for("application/pdf", huge) == policy.ABSOLUTE_MAX_BYTES


def test_unknown_type_gets_the_strictest_cap() -> None:
    assert policy.max_bytes_for("application/octet-stream") == 50 * MB


# ── Magic Number — §11.1 ───────────────────────────────────────────────
def test_pdf_signature_is_checked() -> None:
    assert policy.matches_signature("application/pdf", b"%PDF-1.7\n%...")
    assert not policy.matches_signature("application/pdf", b"MZ\x90\x00 not a pdf")


def test_png_signature_is_checked() -> None:
    assert policy.matches_signature("image/png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 8)
    assert not policy.matches_signature("image/png", b"GIF89a")


def test_webp_signature_needs_both_offsets() -> None:
    """RIFF تنها کافی نیست؛ WEBP در آفست ۸ هم باید باشد."""
    assert policy.matches_signature("image/webp", b"RIFF\x00\x00\x00\x00WEBPVP8 ")
    assert not policy.matches_signature("image/webp", b"RIFF\x00\x00\x00\x00WAVEfmt ")


def test_mp4_signature_sits_at_offset_four() -> None:
    assert policy.matches_signature("video/mp4", b"\x00\x00\x00\x20ftypisom")
    assert not policy.matches_signature("video/mp4", b"ftyp\x00\x00\x00\x20isom")


def test_office_formats_are_zip_containers() -> None:
    docx = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    assert policy.matches_signature(docx, b"PK\x03\x04\x14\x00")
    assert not policy.matches_signature(docx, b"%PDF-1.7")


def test_plain_formats_have_no_signature_to_check() -> None:
    """CSV و متن امضای ثابت ندارند؛ رد کردنشان یعنی رد کردن همهٔ CSVها."""
    assert policy.matches_signature("text/csv", b"id,name\n1,a\n")
    assert policy.matches_signature("text/plain", b"")


def test_unknown_type_never_matches() -> None:
    assert not policy.matches_signature("application/x-msdownload", b"MZ")


def test_probe_length_covers_every_signature() -> None:
    """هر امضا باید داخل بایت‌هایی که می‌خوانیم جا شود."""
    longest = max(
        offset + len(part)
        for spec in policy.CONTENT_SPECS
        for alternative in spec.signatures
        for offset, part in alternative
    )
    assert longest <= policy.SIGNATURE_PROBE_BYTES


# ── کلید ذخیره‌سازی ────────────────────────────────────────────────────
def test_storage_key_is_built_from_the_id_not_the_name() -> None:
    key = policy.storage_key(
        purpose=FilePurpose.DELIVERABLE,
        file_id="018f0000-0000-7000-8000-000000000001",
        original_name="گزارش نهایی.pdf",
    )
    assert key == "deliverable/018f0000-0000-7000-8000-000000000001.pdf"


@pytest.mark.parametrize(
    "name",
    [
        "../../etc/passwd",
        "report.pdf/../../secret",
        "report.p df",
        "بدون‌پسوند",
        "trailing.",
    ],
)
def test_hostile_names_never_reach_the_key(name: str) -> None:
    key = policy.storage_key(
        purpose=FilePurpose.RESOURCE, file_id="018f0000-0000-7000-8000-000000000002", original_name=name
    )
    assert key.startswith("resource/018f0000-0000-7000-8000-000000000002")
    assert ".." not in key
    assert key.count("/") == 1
