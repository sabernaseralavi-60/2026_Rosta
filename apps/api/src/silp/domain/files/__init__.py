"""منطق خالص فایل — سیاست نوع، حجم و راستی‌آزمایی Magic Number."""

from silp.domain.files.policy import (
    MAX_FILES_PER_DELIVERABLE,
    SIGNATURE_PROBE_BYTES,
    Category,
    FilePurpose,
    is_allowed,
    matches_signature,
    max_bytes_for,
    spec_for,
    storage_key,
)

__all__ = [
    "MAX_FILES_PER_DELIVERABLE",
    "SIGNATURE_PROBE_BYTES",
    "Category",
    "FilePurpose",
    "is_allowed",
    "matches_signature",
    "max_bytes_for",
    "spec_for",
    "storage_key",
]
