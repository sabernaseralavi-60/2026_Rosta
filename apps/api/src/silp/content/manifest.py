"""مانیفست پوشهٔ درس — ADR-0008.

هر پوشه در `Courses/` یک درس است. اگر کنارش `course.yml` باشد، همان
حرف آخر را می‌زند؛ اگر نباشد، از نام پوشه و نام فایل‌ها یکی ساخته
می‌شود و روی دیسک نوشته می‌شود تا دفعهٔ بعد قابل ویرایش باشد.

**اصل حاکم: فایلِ نامنتظره حذف نمی‌شود، حدس زده می‌شود.**
اگر کسی فردا یک PDF تازه در پوشه بیندازد و هیچ‌جا ثبتش نکند، باید
دیده شود. مانیفست برای *بهتر کردن* حدس است، نه برای *اجازه دادن*؛
وگرنه «ماژولار» یعنی «هر بار یک فایل YAML هم ویرایش کن».

نمونهٔ کامل `course.yml`::

    code: TRAFFIC-ENG
    slug: traffic-engineering
    title_fa: مهندسی ترابری
    title_en: Traffic Engineering
    degree_level: MASTER
    credits: 3
    is_public: true
    default_access_tier: SUBSCRIBER
    description: |
      ...
    topics: [جریان ترافیک, شبیه‌سازی]

    materials:
      - file: SUMO.docx
        kind: BOOK
        title_fa: مهندسی شبیه‌سازی ترافیک با SUMO
        authors: [مؤلف, اکرم مظاهری]
        access_tier: SUBSCRIBER
        weeks: [3, 4]
        section: فصل ۱ تا ۴

    syllabus:
      - week: 1
        title_fa: مقدمه
        objectives: [آشنایی با دامنه]
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

MANIFEST_NAME = "course.yml"
# نام‌های جایگزین که کاربر ممکن است به‌کار ببرد.
MANIFEST_ALIASES = ("course.yml", "course.yaml", "درس.yml")

# فایل‌هایی که هرگز محتوای درس نیستند.
IGNORED_NAMES = frozenset(
    {MANIFEST_NAME, "course.yaml", "درس.yml", ".gitkeep", "Thumbs.db", ".DS_Store"}
)
IGNORED_PREFIXES = ("~$", ".")

DEFAULT_ACCESS_TIER = "SUBSCRIBER"

# پسوند ← (نوع محتوا برای S3، نوع پیش‌فرض ماده)
EXTENSION_MAP: dict[str, tuple[str, str]] = {
    ".pdf": ("application/pdf", "NOTE"),
    ".docx": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "NOTE",
    ),
    ".pptx": (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "SLIDE",
    ),
    ".xlsx": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "DATASET"),
    ".csv": ("text/csv", "DATASET"),
    ".json": ("application/json", "DATASET"),
    ".geojson": ("application/geo+json", "DATASET"),
    ".mp4": ("video/mp4", "VIDEO"),
    ".m4v": ("video/mp4", "VIDEO"),
    ".png": ("image/png", "OTHER"),
    ".jpg": ("image/jpeg", "OTHER"),
    ".jpeg": ("image/jpeg", "OTHER"),
    ".zip": ("application/zip", "CODE"),
    ".txt": ("text/plain", "NOTE"),
    ".md": ("text/plain", "NOTE"),
}

# نشانه‌های فارسی و انگلیسی در نام فایل ← نوع ماده. ترتیب مهم است:
# اولین تطبیق برنده است، پس خاص‌ها بالاترند.
NAME_HINTS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("سوال", "سؤال", "چهارگزینه", "تست", "quiz", "question", "mcq"), "QUESTION_BANK"),
    (("پادکست", "podcast", "audio"), "PODCAST"),
    (("اسلاید", "slide", "presentation"), "SLIDE"),
    (("کتاب", "book", "essentials", "handbook", "textbook"), "BOOK"),
    (("جزوه", "note", "lecture"), "NOTE"),
    (("داده", "dataset", "data"), "DATASET"),
    (("کد", "code", "script", "notebook"), "CODE"),
    (("ویدئو", "ویدیو", "video", "film"), "VIDEO"),
)


class ManifestError(Exception):
    """مانیفست خوانده نشد یا شکل درستی نداشت."""


@dataclass(slots=True)
class MaterialEntry:
    """یک ماده در مانیفست — همیشه به یک فایل روی دیسک اشاره دارد."""

    file: str
    kind: str = "NOTE"
    title_fa: str = ""
    description: str | None = None
    authors: list[str] = field(default_factory=list)
    edition: str | None = None
    language: str = "fa"
    access_tier: str = DEFAULT_ACCESS_TIER
    is_downloadable: bool = True
    status: str = "PUBLISHED"
    sort_order: int = 0
    page_count: int | None = None
    duration_sec: int | None = None
    # هفته‌هایی که این ماده منبعشان است — `week_materials` از این ساخته می‌شود.
    weeks: list[int] = field(default_factory=list)
    section: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"file": self.file, "kind": self.kind, "title_fa": self.title_fa}
        if self.description:
            data["description"] = self.description
        if self.authors:
            data["authors"] = list(self.authors)
        if self.edition:
            data["edition"] = self.edition
        if self.language != "fa":
            data["language"] = self.language
        if self.access_tier != DEFAULT_ACCESS_TIER:
            data["access_tier"] = self.access_tier
        if not self.is_downloadable:
            data["is_downloadable"] = False
        if self.status != "PUBLISHED":
            data["status"] = self.status
        if self.sort_order:
            data["sort_order"] = self.sort_order
        if self.weeks:
            data["weeks"] = list(self.weeks)
        if self.section:
            data["section"] = self.section
        return data


@dataclass(slots=True)
class SyllabusWeek:
    """یک هفته از برنامهٔ درسی."""

    week: int
    title_fa: str
    description: str | None = None
    objectives: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"week": self.week, "title_fa": self.title_fa}
        if self.description:
            data["description"] = self.description
        if self.objectives:
            data["objectives"] = list(self.objectives)
        return data


@dataclass(slots=True)
class CourseManifest:
    """درس، همان‌طور که پوشه‌اش توصیفش می‌کند."""

    directory: Path
    code: str
    slug: str
    title_fa: str
    title_en: str | None = None
    description: str | None = None
    degree_level: str | None = None
    credits: int | None = None
    is_public: bool = True
    is_active: bool = True
    default_access_tier: str = DEFAULT_ACCESS_TIER
    topics: list[str] = field(default_factory=list)
    materials: list[MaterialEntry] = field(default_factory=list)
    syllabus: list[SyllabusWeek] = field(default_factory=list)

    @property
    def source_dir(self) -> str:
        """نام پوشه — کلید پایدار پیوند درس به پوشه."""
        return self.directory.name

    def material_for(self, filename: str) -> MaterialEntry | None:
        for entry in self.materials:
            if entry.file == filename:
                return entry
        return None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "code": self.code,
            "slug": self.slug,
            "title_fa": self.title_fa,
        }
        if self.title_en:
            data["title_en"] = self.title_en
        if self.degree_level:
            data["degree_level"] = self.degree_level
        if self.credits:
            data["credits"] = self.credits
        data["is_public"] = self.is_public
        data["default_access_tier"] = self.default_access_tier
        if self.description:
            data["description"] = self.description
        if self.topics:
            data["topics"] = list(self.topics)
        if self.materials:
            data["materials"] = [m.to_dict() for m in self.materials]
        if self.syllabus:
            data["syllabus"] = [w.to_dict() for w in self.syllabus]
        return data


# ── کشف و حدس ──────────────────────────────────────────────────────────
def discover_courses(root: Path) -> list[Path]:
    """پوشه‌های درس زیر `Courses/` — مرتب، بدون پوشهٔ مخفی."""
    if not root.is_dir():
        raise ManifestError(f"پوشهٔ دروس پیدا نشد: {root}")
    return sorted(
        p for p in root.iterdir() if p.is_dir() and not p.name.startswith(IGNORED_PREFIXES)
    )


def content_files(directory: Path) -> list[Path]:
    """فایل‌های محتوایی یک پوشه — بازگشتی، تا زیرپوشه هم کار کند."""
    result: list[Path] = []
    for path in sorted(directory.rglob("*")):
        if not path.is_file():
            continue
        if path.name in IGNORED_NAMES or path.name.startswith(IGNORED_PREFIXES):
            continue
        if path.suffix.lower() not in EXTENSION_MAP:
            continue
        result.append(path)
    return result


def content_type_of(path: Path) -> str:
    spec = EXTENSION_MAP.get(path.suffix.lower())
    return spec[0] if spec else "application/octet-stream"


# پسوندهایی که خودشان نوع را قطعی می‌کنند. یک `.pptx` اسلاید است حتی
# اگر «lecture» نامیده شده باشد.
DECISIVE_KINDS = frozenset({"SLIDE", "VIDEO", "DATASET", "CODE"})


def infer_kind(path: Path) -> str:
    """نوع ماده: پسوندِ قطعی، وگرنه نام فایل، وگرنه پیش‌فرض پسوند.

    نام فایل حرف کاربر است و اینجا عمداً به آن گوش داده می‌شود: کسی که
    فایلش را «پادکست کتاب ایمنی» نامیده، منظورش پادکست است، نه PDF.
    ولی این فقط جایی معنا دارد که پسوند مبهم باشد — `.pdf` و `.docx`
    هرچیزی می‌توانند باشند، `.mp4` نه.
    """
    spec = EXTENSION_MAP.get(path.suffix.lower())
    by_extension = spec[1] if spec else "OTHER"
    if by_extension in DECISIVE_KINDS:
        return by_extension

    haystack = path.stem.casefold()
    for needles, kind in NAME_HINTS:
        if any(needle in haystack for needle in needles):
            return kind
    return by_extension


_CLEAN_TITLE = re.compile(r"[_\-+]+")


def infer_title(path: Path) -> str:
    """عنوان خوانا از نام فایل — بدون پسوند، بدون `+++` و زیرخط."""
    title = _CLEAN_TITLE.sub(" ", path.stem)
    return " ".join(title.split()) or path.stem


def infer_material(
    path: Path, directory: Path, *, default_tier: str = DEFAULT_ACCESS_TIER
) -> MaterialEntry:
    """حدس یک ماده از روی فایل — وقتی مانیفست چیزی دربارهٔ آن نگفته."""
    return MaterialEntry(
        file=path.relative_to(directory).as_posix(),
        kind=infer_kind(path),
        title_fa=infer_title(path),
        access_tier=default_tier,
    )


_SLUG_SAFE = re.compile(r"[^a-z0-9]+")


def slugify_dir(name: str) -> str:
    """نشانی انگلیسی از نام پوشه. نام فارسی؟ به کد درس برمی‌گردیم."""
    slug = _SLUG_SAFE.sub("-", name.casefold()).strip("-")
    return slug


def default_manifest(directory: Path) -> CourseManifest:
    """مانیفست کمینه از روی نام پوشه — برای درسی که هنوز توصیف نشده."""
    slug = slugify_dir(directory.name) or "course"
    return CourseManifest(
        directory=directory,
        code=slug.upper().replace("-", "_"),
        slug=slug,
        title_fa=directory.name,
        title_en=directory.name,
    )


# ── خواندن و نوشتن ─────────────────────────────────────────────────────
def manifest_path(directory: Path) -> Path | None:
    for name in MANIFEST_ALIASES:
        candidate = directory / name
        if candidate.is_file():
            return candidate
    return None


def load_manifest(directory: Path) -> CourseManifest:
    """مانیفست پوشه، یا حدس پیش‌فرض اگر نبود.

    فایل‌های موجود در پوشه که در مانیفست نیامده‌اند، **افزوده** می‌شوند
    — همان چیزی که «یک فایل تازه بینداز و کار کند» یعنی.
    """
    path = manifest_path(directory)
    manifest = default_manifest(directory) if path is None else _parse(path, directory)

    known = {m.file for m in manifest.materials}
    for file_path in content_files(directory):
        relative = file_path.relative_to(directory).as_posix()
        if relative in known:
            continue
        manifest.materials.append(
            infer_material(file_path, directory, default_tier=manifest.default_access_tier)
        )
    return manifest


def _parse(path: Path, directory: Path) -> CourseManifest:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ManifestError(f"خواندن {path} ناموفق بود: {exc}") from exc
    if not isinstance(raw, dict):
        raise ManifestError(f"{path} باید یک نگاشت باشد، نه {type(raw).__name__}.")

    fallback = default_manifest(directory)
    materials = [_parse_material(item, path) for item in raw.get("materials") or []]
    syllabus = [_parse_week(item, path) for item in raw.get("syllabus") or []]

    return CourseManifest(
        directory=directory,
        code=str(raw.get("code") or fallback.code),
        slug=str(raw.get("slug") or fallback.slug),
        title_fa=str(raw.get("title_fa") or fallback.title_fa),
        title_en=_opt_str(raw.get("title_en")),
        description=_opt_str(raw.get("description")),
        degree_level=_opt_str(raw.get("degree_level")),
        credits=_opt_int(raw.get("credits")),
        is_public=bool(raw.get("is_public", True)),
        is_active=bool(raw.get("is_active", True)),
        default_access_tier=str(raw.get("default_access_tier") or DEFAULT_ACCESS_TIER),
        topics=[str(t) for t in raw.get("topics") or []],
        materials=materials,
        syllabus=sorted(syllabus, key=lambda w: w.week),
    )


def _parse_material(item: Any, path: Path) -> MaterialEntry:
    if not isinstance(item, dict) or not item.get("file"):
        raise ManifestError(f"{path}: هر ماده باید کلید `file` داشته باشد.")
    file_name = str(item["file"])
    return MaterialEntry(
        file=file_name,
        kind=str(item.get("kind") or infer_kind(Path(file_name))),
        title_fa=str(item.get("title_fa") or infer_title(Path(file_name))),
        description=_opt_str(item.get("description")),
        authors=[str(a) for a in item.get("authors") or []],
        edition=_opt_str(item.get("edition")),
        language=str(item.get("language") or "fa"),
        access_tier=str(item.get("access_tier") or DEFAULT_ACCESS_TIER),
        is_downloadable=bool(item.get("is_downloadable", True)),
        status=str(item.get("status") or "PUBLISHED"),
        sort_order=_opt_int(item.get("sort_order")) or 0,
        page_count=_opt_int(item.get("page_count")),
        duration_sec=_opt_int(item.get("duration_sec")),
        weeks=[int(w) for w in item.get("weeks") or []],
        section=_opt_str(item.get("section")),
    )


def _parse_week(item: Any, path: Path) -> SyllabusWeek:
    if not isinstance(item, dict) or item.get("week") is None:
        raise ManifestError(f"{path}: هر هفته باید کلید `week` داشته باشد.")
    return SyllabusWeek(
        week=int(item["week"]),
        title_fa=str(item.get("title_fa") or f"هفتهٔ {item['week']}"),
        description=_opt_str(item.get("description")),
        objectives=[str(o) for o in item.get("objectives") or []],
    )


def write_manifest(manifest: CourseManifest) -> Path:
    """نوشتن مانیفست روی دیسک — همیشه UTF-8، همیشه با فارسی خوانا."""
    path = manifest.directory / MANIFEST_NAME
    header = (
        "# مانیفست درس — SILP (ADR-0008)\n"
        "# این فایل را آزادانه ویرایش کنید. هر فایلی که در این پوشه\n"
        "# بگذارید و اینجا نامش نباشد، هنگام همگام‌سازی خودکار افزوده\n"
        "# می‌شود؛ ویرایش این فایل فقط حدسِ سامانه را دقیق‌تر می‌کند.\n"
        "#\n"
        "# access_tier: PUBLIC (برای همه) | SUBSCRIBER (دانشجوی درس رایگان،\n"
        "#              بقیه با اشتراک) | ENROLLED (فقط دانشجوی درس)\n\n"
    )
    body = yaml.safe_dump(
        manifest.to_dict(),
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
        width=88,
    )
    path.write_text(header + body, encoding="utf-8")
    return path


def _opt_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _opt_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


__all__ = [
    "DECISIVE_KINDS",
    "DEFAULT_ACCESS_TIER",
    "EXTENSION_MAP",
    "MANIFEST_NAME",
    "CourseManifest",
    "ManifestError",
    "MaterialEntry",
    "SyllabusWeek",
    "content_files",
    "content_type_of",
    "default_manifest",
    "discover_courses",
    "infer_kind",
    "infer_material",
    "infer_title",
    "load_manifest",
    "manifest_path",
    "slugify_dir",
    "write_manifest",
]
