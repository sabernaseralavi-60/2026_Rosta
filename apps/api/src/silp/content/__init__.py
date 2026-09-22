"""کتابخانهٔ محتوای درس از روی پوشه — ADR-0008.

`Courses/<نام درس>/` منبع حقیقتِ **محتوا**ست. هر فایلی که آنجا گذاشته
شود، پس از یک `make courses-sync` در سامانه دیده می‌شود؛ هیچ‌کس لازم
نیست کد عوض کند یا از رابط کاربری آپلود کند.
"""

from silp.content.manifest import (
    CourseManifest,
    ManifestError,
    MaterialEntry,
    SyllabusWeek,
    discover_courses,
    infer_material,
    load_manifest,
    write_manifest,
)

__all__ = [
    "CourseManifest",
    "ManifestError",
    "MaterialEntry",
    "SyllabusWeek",
    "discover_courses",
    "infer_material",
    "load_manifest",
    "write_manifest",
]
