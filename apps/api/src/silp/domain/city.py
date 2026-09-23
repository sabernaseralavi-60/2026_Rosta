"""آزمایشگاه شهر هوشمند — FR-CITY-01، §7.9، ADR-0016. منطق خالص.

## الگوی ثابت هشت‌مرحله‌ای

پروژهٔ شهری (`projects.workflow = 'CITY'`) با هشت مرحلهٔ ثابت ساخته
می‌شود. مثل راهنمای مسیر پژوهش (ADR-0015)، الگو محتوای کد است نه داده:
برای همهٔ پروژه‌های شهری یکی است و با نسخهٔ کد عوض می‌شود.

هر مرحله سه چیز دارد که FR-CITY-01 خواسته: تحویل‌دادنی مشخص، چک‌لیست
کیفیت و مسئول (`milestones.owner_id`). مسئول در دیتابیس است؛ بقیه اینجا.

## شاهد ساختاریافته

هر تحویل علاوه بر خلاصه و پیوست، شاهد ساختاریافتهٔ مرحلهٔ خودش را دارد.
`validate_submission` هر آنچه ماشین می‌تواند بسنجد، می‌سنجد — بسته بودن
محدوده، مساحت، صفر بودن خطای `netconvert`، دو منبع برای هر مغایرت،
سناریوی پایه — و **همهٔ کمبودها را یک‌جا** برمی‌گرداند (همان قاعدهٔ §7.7).
بقیهٔ چک‌لیست تأیید تحویل‌دهنده است و داوری نهایی با بازبین.

## قاعدهٔ حیاتی مرحلهٔ ۳

«راستی‌آزمایی OSM بدون شواهد تصویری تأیید نمی‌شود» (§7.9): هر ردیف جدول
راستی‌آزمایی دست‌کم یک تصویر پیوست دارد، و کل جدول از دست‌کم دو منبع
مختلف آمده است.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from itertools import pairwise
from typing import Any, Literal

from silp.domain.text import to_persian_digits

WORKFLOW_CITY = "CITY"
WORKFLOWS = (WORKFLOW_CITY,)
#: §7.9 — «ساخت پروژهٔ نوع C با این الگو».
WORKFLOW_KIND = "C_PROBLEM"
STAGE_COUNT = 8

SUMMARY_MIN = 30
TEXT_FIELD_MAX = 3000

#: محدودهٔ مطالعه — از یک تقاطع و اطرافش تا یک منطقهٔ شهری. شبیه‌سازی
#: ریزنگر کل یک شهر، کار یک تیم دانشجویی در یک نیم‌سال نیست.
AREA_MIN_KM2 = 0.05
AREA_MAX_KM2 = 30.0
#: سقف رأس‌ها — محدودهٔ مطالعه دست‌کشیده است، نه مرز دقیق اداری.
AREA_MAX_VERTICES = 1000
EARTH_RADIUS_M = 6_378_137.0

MAX_CHECKS = 200
MAX_SCENARIOS = 20
MIN_SCENARIOS = 3
REPORT_MAX_PAGES = 20
EXECUTIVE_SUMMARY_MIN = 200
EXECUTIVE_SUMMARY_MAX = 3000

# ── منبع راستی‌آزمایی — FR-CITY-01 «Google/نشان/بلد/بازدید میدانی» ─────
SOURCE_TITLE_FA: dict[str, str] = {
    "GOOGLE": "نقشهٔ گوگل",
    "NESHAN": "نشان",
    "BALAD": "بلد",
    "FIELD": "بازدید میدانی",
}
SOURCES = tuple(SOURCE_TITLE_FA)
FIELD_SOURCE = "FIELD"

VERDICT_TITLE_FA: dict[str, str] = {"MATCH": "مطابق", "MISMATCH": "مغایر"}
SEVERITY_TITLE_FA: dict[str, str] = {"NORMAL": "عادی", "CRITICAL": "بحرانی"}

# ── فایل‌های مدل — FR-CITY-01 «نسخه‌بندی در کتابخانهٔ پروژه» ──────────
ARTIFACT_TITLE_FA: dict[str, str] = {
    "OSM": "دادهٔ خام OSM",
    "SUMO_NET": "شبکهٔ SUMO",
    "SUMO_ROUTES": "مسیرهای SUMO",
}
ARTIFACTS = tuple(ARTIFACT_TITLE_FA)
#: پسوند هر فایل مدل؛ ترتیب مهم است — `.osm.xml` پیش از `.xml` کلی.
ARTIFACT_SUFFIXES: tuple[tuple[str, str], ...] = (
    (".net.xml", "SUMO_NET"),
    (".rou.xml", "SUMO_ROUTES"),
    (".osm.xml", "OSM"),
    (".osm", "OSM"),
)
ARTIFACT_EXTENSION_FA: dict[str, str] = {
    "OSM": ".osm",
    "SUMO_NET": ".net.xml",
    "SUMO_ROUTES": ".rou.xml",
}
XML_TYPES = frozenset({"application/xml", "text/xml"})

FieldKind = Literal["int", "number", "text", "url", "date"]
Structured = Literal["AREA", "CHECKS", "SCENARIOS"]
#: کلید شاهد ساختاریافتهٔ هر نوع در `evidence`.
STRUCTURED_KEY: dict[str, str] = {"AREA": "area", "CHECKS": "checks", "SCENARIOS": "scenarios"}
FileKind = Literal["OSM", "SUMO_NET", "SUMO_ROUTES", "PDF", "DATASET"]


@dataclass(frozen=True, slots=True)
class EvidenceField:
    key: str
    label_fa: str
    kind: FieldKind
    hint_fa: str | None = None
    min_value: float | None = None
    max_value: float | None = None
    min_length: int | None = None
    max_length: int = TEXT_FIELD_MAX


@dataclass(frozen=True, slots=True)
class ChecklistItem:
    text: str
    #: سامانه خودش می‌سنجد؛ تحویل‌دهنده لازم نیست تیکش بزند.
    auto: bool = False


@dataclass(frozen=True, slots=True)
class FileRule:
    kind: FileKind
    label_fa: str
    #: دقیقاً یکی — نسخهٔ فایل مدل یکتا به هر تحویل بسته می‌شود.
    exactly_one: bool = False


@dataclass(frozen=True, slots=True)
class Stage:
    number: int
    code: str
    title_fa: str
    deliverable_fa: str
    output_kind: str
    points: int
    duration_days: int
    guide: tuple[str, ...]
    checklist: tuple[ChecklistItem, ...]
    evidence: tuple[EvidenceField, ...] = ()
    structured: Structured | None = None
    files: tuple[FileRule, ...] = ()
    #: کمینهٔ پیوست (فایل یا پیوند) جدا از فایل‌های معین.
    min_attachments: int = 0
    attachments_hint_fa: str | None = None

    @property
    def manual_items(self) -> tuple[int, ...]:
        return tuple(i for i, item in enumerate(self.checklist) if not item.auto)


STAGES: tuple[Stage, ...] = (
    Stage(
        number=1,
        code="AREA",
        title_fa="انتخاب محدوده",
        deliverable_fa="محدودهٔ GeoJSON و توجیه انتخاب",
        output_kind="DATA",
        points=30,
        duration_days=7,
        guide=(
            "مسئله را از شهرداری یا از داده بپرس: کجا صف، تصادف یا شکایت بیشتر است؟",
            "محدوده را روی geojson.io یا QGIS به‌صورت چندضلعی بکش — نه مستطیل دلخواه؛"
            " مرز را تا تقاطع‌های اثرگذار بالادست و پایین‌دست ببر.",
            "فایل GeoJSON را ذخیره کن و در فرم بارگذاری کن؛ سامانه مساحت و بسته بودنش"
            " را می‌سنجد و هم‌پوشانی با پروژه‌های فعال دیگر را نشان می‌دهد.",
            "در توجیه بنویس چرا این محدوده، و چه چیزی عمداً بیرون ماند.",
        ),
        checklist=(
            ChecklistItem("محدوده بسته است", auto=True),
            ChecklistItem(
                f"مساحت بین {to_persian_digits(AREA_MIN_KM2)} و"
                f" {to_persian_digits(int(AREA_MAX_KM2))} کیلومتر مربع است",
                auto=True,
            ),
            ChecklistItem("هم‌پوشانی با محدودهٔ پروژه‌های فعال بررسی شده است", auto=True),
        ),
        evidence=(
            EvidenceField(
                "justification",
                "توجیه انتخاب محدوده",
                "text",
                hint_fa="مسئله، ذی‌نفع، و مرز محدوده",
                min_length=50,
            ),
        ),
        structured="AREA",
    ),
    Stage(
        number=2,
        code="OSM",
        title_fa="استخراج OSM",
        deliverable_fa="فایل خام .osm و گزارش آمار شبکه",
        output_kind="DATA",
        points=40,
        duration_days=7,
        guide=(
            "دادهٔ OSM محدوده را از Overpass یا برش Geofabrik ایران بگیر؛ osmium برای"
            " برش فایل بزرگ کافی است.",
            "نسخه (تاریخ دادهٔ OSM) و تاریخ استخراج را یادداشت کن — بدون آن مدل"
            " بازتولیدپذیر نیست.",
            "تعداد گره‌ها و یال‌های شبکهٔ راه را بشمار و در خلاصه بنویس کدام"
            " کلاس‌های راه نگه داشته شد.",
        ),
        checklist=(
            ChecklistItem("تعداد گره و یال ثبت شده", auto=True),
            ChecklistItem("نسخهٔ OSM و تاریخ استخراج مشخص است", auto=True),
        ),
        evidence=(
            EvidenceField("node_count", "تعداد گره‌ها", "int", min_value=1),
            EvidenceField("edge_count", "تعداد یال‌ها", "int", min_value=1),
            EvidenceField(
                "osm_source",
                "منبع داده",
                "text",
                hint_fa="Overpass، Geofabrik یا …",
                min_length=3,
                max_length=200,
            ),
            EvidenceField("osm_data_date", "تاریخ نسخهٔ دادهٔ OSM", "date"),
            EvidenceField("extracted_on", "تاریخ استخراج", "date"),
        ),
        files=(FileRule("OSM", "فایل .osm", exactly_one=True),),
    ),
    Stage(
        number=3,
        code="VERIFY",
        title_fa="راستی‌آزمایی",
        deliverable_fa="جدول مغایرت با شواهد تصویری",
        output_kind="DATA",
        points=80,
        duration_days=14,
        guide=(
            "نقاط حساس را فهرست کن: تقاطع‌ها، جهت یک‌طرفه‌ها، تعداد خط، ممنوعیت گردش.",
            "هر نقطه را با دست‌کم دو منبع مستقل — گوگل، نشان، بلد، بازدید میدانی —"
            " مقایسه کن و از هر منبع تصویر بگیر.",
            "هر مغایرت بحرانی (جهت، اتصال، ممنوعیت) باید با بازدید میدانی تأیید شود.",
            "مغایرت‌ها را در دادهٔ OSM اصلاح کن و اصلاح را در همان ردیف بنویس.",
        ),
        checklist=(
            ChecklistItem("هر مغایرت با دست‌کم دو منبع مستقل بررسی شده", auto=True),
            ChecklistItem("برای موارد بحرانی بازدید میدانی انجام شده", auto=True),
            ChecklistItem("هر ردیف شاهد تصویری دارد", auto=True),
        ),
        structured="CHECKS",
    ),
    Stage(
        number=4,
        code="SUMO",
        title_fa="مدل SUMO",
        deliverable_fa="فایل‌های .net.xml و .rou.xml و گزارش خطا",
        output_kind="CODE",
        points=100,
        duration_days=21,
        guide=(
            "شبکه را با netconvert از OSM راستی‌آزمایی‌شده بساز و خروجی را کامل بخوان.",
            "هر خطا را رفع کن؛ هشدارهای باقی‌مانده را در گزارش توضیح بده.",
            "اتصال شبکه را در SUMO-GUI یا با ابزار netcheck بررسی کن — یال بی‌راه‌به‌در"
            " مدل را بی‌صدا خراب می‌کند.",
            "برنامهٔ زمان‌بندی چراغ‌ها را از میدان یا شهرداری بگیر و کدگذاری کن.",
        ),
        checklist=(
            ChecklistItem("netconvert بدون خطا اجرا شده", auto=True),
            ChecklistItem("اتصال شبکه بررسی شده"),
            ChecklistItem("چراغ‌ها کدگذاری شده‌اند"),
        ),
        evidence=(
            EvidenceField(
                "netconvert_errors",
                "تعداد خطای netconvert",
                "int",
                hint_fa="باید صفر باشد؛ هشدارها را در گزارش بنویس",
                min_value=0,
                max_value=0,
            ),
            EvidenceField(
                "traffic_lights",
                "تقاطع‌های چراغ‌دار کدگذاری‌شده",
                "int",
                min_value=0,
            ),
            EvidenceField(
                "sumo_version",
                "نسخهٔ SUMO",
                "text",
                hint_fa="مثلاً 1.20.0",
                min_length=3,
                max_length=40,
            ),
            EvidenceField(
                "error_report",
                "گزارش خطا و هشدار",
                "text",
                hint_fa="خلاصهٔ خروجی netconvert و آنچه رفع شد",
                min_length=20,
            ),
        ),
        files=(
            FileRule("SUMO_NET", "فایل .net.xml", exactly_one=True),
            FileRule("SUMO_ROUTES", "فایل .rou.xml", exactly_one=True),
        ),
    ),
    Stage(
        number=5,
        code="DEMAND",
        title_fa="تخمین تقاضا",
        deliverable_fa="ماتریس مبدأ-مقصد و روش‌شناسی",
        output_kind="DATA",
        points=60,
        duration_days=14,
        guide=(
            "منبع داده را مشخص کن: شمارش میدانی، دوربین، طرح جامع، یا دادهٔ شهرداری.",
            "روش تخمین را انتخاب و توجیه کن — od2trips، routeSampler یا مدل جاذبه.",
            "ماتریس را با شمارش‌های موجود مقایسه کن (مثلاً GEH) و نتیجه را بنویس.",
        ),
        checklist=(
            ChecklistItem("منبع داده مستند است", auto=True),
            ChecklistItem("روش تخمین توجیه شده است"),
            ChecklistItem("با شمارش موجود اعتبارسنجی شده"),
        ),
        evidence=(
            EvidenceField("data_source", "منبع داده", "text", min_length=10),
            EvidenceField(
                "method",
                "روش تخمین و توجیه آن",
                "text",
                min_length=30,
            ),
            EvidenceField(
                "count_sites",
                "تعداد مقطع شمارش برای اعتبارسنجی",
                "int",
                min_value=1,
            ),
            EvidenceField(
                "validation_result",
                "نتیجهٔ اعتبارسنجی",
                "text",
                hint_fa="مثلاً GEH کمتر از ۵ در ۸۵٪ مقاطع",
                min_length=10,
            ),
        ),
        files=(FileRule("DATASET", "ماتریس مبدأ-مقصد (CSV، Excel یا XML)"),),
    ),
    Stage(
        number=6,
        code="SCENARIOS",
        title_fa="سناریوسازی",
        deliverable_fa="دست‌کم سه سناریو با نتایج شبیه‌سازی",
        output_kind="DATA",
        points=80,
        duration_days=14,
        guide=(
            "سناریوی پایه همان وضع موجود است؛ بدون آن هیچ بهبودی قابل سنجش نیست.",
            "دست‌کم دو سناریوی بهبود بساز: زمان‌بندی چراغ، تغییر هندسه، ممنوعیت گردش.",
            "هر سناریو را چند بار با بذر تصادفی متفاوت اجرا کن و میانگین را گزارش کن.",
            "تأخیر، طول صف و انتشار را برای هر سناریو با یک واحد ثابت بنویس.",
        ),
        checklist=(
            ChecklistItem("سناریوی پایه دارد", auto=True),
            ChecklistItem("شاخص‌های تأخیر، صف و انتشار گزارش شده", auto=True),
        ),
        structured="SCENARIOS",
        min_attachments=1,
        attachments_hint_fa="نتایج شبیه‌سازی را به‌صورت فایل یا پیوند پیوست کن.",
    ),
    Stage(
        number=7,
        code="REPORT",
        title_fa="گزارش مدیریتی",
        deliverable_fa="گزارش PDF حداکثر ۲۰ صفحه، فارسی و بدون ژارگون",
        output_kind="DOCUMENT",
        points=60,
        duration_days=14,
        guide=(
            "خواننده مدیر شهری است، نه مدل‌ساز: از مسئله و توصیه شروع کن، نه از روش.",
            "خلاصهٔ اجرایی یک صفحه باشد و بدون خواندن بقیه قابل تصمیم‌گیری.",
            "هر توصیه را با هزینهٔ تقریبی و اثر مورد انتظار بنویس.",
        ),
        checklist=(
            ChecklistItem("خلاصهٔ اجرایی یک‌صفحه‌ای", auto=True),
            ChecklistItem("حداکثر ۲۰ صفحه", auto=True),
            ChecklistItem("برآورد هزینه دارد", auto=True),
            ChecklistItem("توصیهٔ عملی مشخص"),
            ChecklistItem("فارسی و بدون ژارگون"),
        ),
        evidence=(
            EvidenceField(
                "page_count",
                "تعداد صفحهٔ گزارش",
                "int",
                min_value=1,
                max_value=REPORT_MAX_PAGES,
            ),
            EvidenceField(
                "executive_summary",
                "خلاصهٔ اجرایی",
                "text",
                min_length=EXECUTIVE_SUMMARY_MIN,
                max_length=EXECUTIVE_SUMMARY_MAX,
            ),
            EvidenceField("recommendations", "توصیه‌های عملی", "text", min_length=50),
            EvidenceField(
                "cost_estimate_rial",
                "برآورد هزینه (ریال)",
                "int",
                min_value=1,
            ),
        ),
        files=(FileRule("PDF", "گزارش PDF"),),
    ),
    Stage(
        number=8,
        code="DASHBOARD",
        title_fa="داشبورد شهرداری",
        deliverable_fa="داشبورد تعاملی و راهنمای استفاده",
        output_kind="CODE",
        points=50,
        duration_days=21,
        guide=(
            "داشبورد برای کارشناس شهرداری است: سه پرسش اصلی او را پیدا کن و فقط"
            " همان‌ها را نشان بده.",
            "روی گوشی آزمایش کن — بیشتر مدیران گزارش را روی موبایل می‌بینند.",
            "راه به‌روزرسانی داده را مستند کن تا داشبورد پس از پایان پروژه نمیرد.",
        ),
        checklist=(
            ChecklistItem("روی موبایل کار می‌کند"),
            ChecklistItem("بدون آموزش قابل استفاده است"),
            ChecklistItem("داده قابل به‌روزرسانی است"),
        ),
        evidence=(
            EvidenceField("dashboard_url", "پیوند داشبورد", "url"),
            EvidenceField(
                "update_method",
                "روش به‌روزرسانی داده",
                "text",
                min_length=20,
            ),
        ),
        min_attachments=1,
        attachments_hint_fa="راهنمای استفاده را به‌صورت فایل یا پیوند پیوست کن.",
    ),
)

STAGE_BY_NUMBER: dict[int, Stage] = {stage.number: stage for stage in STAGES}
TOTAL_POINTS = sum(stage.points for stage in STAGES)
TOTAL_DAYS = sum(stage.duration_days for stage in STAGES)


def stage(number: int) -> Stage:
    spec = STAGE_BY_NUMBER.get(number)
    if spec is None:
        msg = f"مرحلهٔ شهری نامعتبر: {number}"
        raise ValueError(msg)
    return spec


def due_dates(starts_on: date | None) -> dict[int, date | None]:
    """مهلت هر مرحله از تاریخ شروع — مجموع مدت‌ها ۱۶ هفته، یک نیم‌سال."""
    if starts_on is None:
        return {s.number: None for s in STAGES}
    result: dict[int, date | None] = {}
    elapsed = 0
    for s in STAGES:
        elapsed += s.duration_days
        result[s.number] = starts_on + timedelta(days=elapsed)
    return result


# ── فایل‌ها ─────────────────────────────────────────────────────────────
@dataclass(frozen=True, slots=True)
class AttachedFile:
    id: str
    name: str
    content_type: str


def artifact_of(name: str) -> str | None:
    """نوع فایل مدل از روی نام — `.osm`، `.net.xml` یا `.rou.xml`."""
    lowered = name.strip().lower()
    for suffix, artifact in ARTIFACT_SUFFIXES:
        if lowered.endswith(suffix):
            return artifact
    return None


def _is_image(file: AttachedFile) -> bool:
    return file.content_type.startswith("image/")


def _matches(rule: FileKind, file: AttachedFile) -> bool:
    match rule:
        case "OSM" | "SUMO_NET" | "SUMO_ROUTES":
            return file.content_type in XML_TYPES and artifact_of(file.name) == rule
        case "PDF":
            return file.content_type == "application/pdf"
        case _:  # DATASET — ماتریس مبدأ-مقصد
            return file.content_type in {
                "text/csv",
                "application/json",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                *XML_TYPES,
            }


def artifacts_in(files: Sequence[AttachedFile]) -> dict[str, AttachedFile]:
    """فایل‌های مدلِ یک تحویل — هر نوع حداکثر یکی (قاعدهٔ مرحله تضمینش می‌کند)."""
    found: dict[str, AttachedFile] = {}
    for file in files:
        artifact = artifact_of(file.name)
        if artifact is not None and file.content_type in XML_TYPES:
            found.setdefault(artifact, file)
    return found


# ── محدوده — GeoJSON ────────────────────────────────────────────────────
Ring = list[tuple[float, float]]
Polygon = list[Ring]


def _geometries(value: Any) -> list[Any]:
    """Feature و FeatureCollection را به فهرست هندسه باز می‌کند."""
    if not isinstance(value, Mapping):
        return []
    kind = value.get("type")
    if kind == "FeatureCollection":
        features = value.get("features")
        if not isinstance(features, list):
            return []
        return [g for f in features for g in _geometries(f)]
    if kind == "Feature":
        return _geometries(value.get("geometry"))
    return [value]


def _ring(raw: Any) -> Ring | None:
    if not isinstance(raw, list):
        return None
    points: Ring = []
    for position in raw:
        if (
            not isinstance(position, list | tuple)
            or len(position) < 2
            or not all(isinstance(c, int | float) and not isinstance(c, bool) for c in position[:2])
        ):
            return None
        points.append((float(position[0]), float(position[1])))
    return points


def parse_area(value: Any) -> tuple[list[Polygon], list[str]]:
    """GeoJSON محدوده ← فهرست چندضلعی، یا فهرست کمبودها.

    Polygon، MultiPolygon، و Feature یا FeatureCollection از همین‌ها
    پذیرفته می‌شود. «محدوده بسته است» (§7.9) یعنی هر حلقه همان نقطه‌ای
    تمام شود که شروع شده.
    """
    geometries = _geometries(value)
    if not geometries:
        return [], ["محدوده باید GeoJSON از نوع Polygon یا MultiPolygon باشد"]

    polygons: list[Polygon] = []
    problems: list[str] = []
    for geometry in geometries:
        kind = geometry.get("type") if isinstance(geometry, Mapping) else None
        coordinates = geometry.get("coordinates") if isinstance(geometry, Mapping) else None
        if kind == "Polygon":
            raw_polygons = [coordinates]
        elif kind == "MultiPolygon" and isinstance(coordinates, list):
            raw_polygons = coordinates
        else:
            problems.append("محدوده فقط از چندضلعی ساخته می‌شود، نه نقطه یا خط")
            continue
        for raw_polygon in raw_polygons:
            if not isinstance(raw_polygon, list) or not raw_polygon:
                problems.append("یکی از چندضلعی‌ها مختصات ندارد")
                continue
            rings = [_ring(r) for r in raw_polygon]
            if any(r is None for r in rings):
                problems.append("مختصات محدوده عددی و به شکل [طول، عرض] نیست")
                continue
            polygons.append([r for r in rings if r is not None])

    if problems:
        return [], sorted(set(problems))

    vertices = sum(len(r) for p in polygons for r in p)
    if vertices > AREA_MAX_VERTICES:
        return [], [
            f"محدوده حداکثر {to_persian_digits(AREA_MAX_VERTICES)} رأس دارد؛" " مرز را ساده‌تر بکش"
        ]
    for polygon in polygons:
        for ring in polygon:
            if len(ring) < 4:
                problems.append("هر حلقهٔ محدوده دست‌کم چهار نقطه دارد")
            elif ring[0] != ring[-1]:
                problems.append("محدوده بسته نیست: آخرین نقطه باید همان نقطهٔ اول باشد")
            if any(not (-180 <= lon <= 180 and -90 <= lat <= 90) for lon, lat in ring):
                problems.append("مختصات بیرون از بازهٔ طول و عرض جغرافیایی است")
    return (polygons, []) if not problems else ([], sorted(set(problems)))


def _ring_area_m2(ring: Ring) -> float:
    """مساحت حلقه روی کره — Chamberlain و Duquette، همان فرمول turf.js."""
    total = 0.0
    for (lon1, lat1), (lon2, lat2) in pairwise(ring):
        total += math.radians(lon2 - lon1) * (
            2 + math.sin(math.radians(lat1)) + math.sin(math.radians(lat2))
        )
    return abs(total * EARTH_RADIUS_M * EARTH_RADIUS_M / 2)


def area_km2(polygons: Sequence[Polygon]) -> float:
    """مساحت کل — حلقهٔ اول بیرونی، بقیه سوراخ."""
    total = 0.0
    for polygon in polygons:
        outer, *holes = polygon
        total += _ring_area_m2(outer) - sum(_ring_area_m2(h) for h in holes)
    return max(total, 0.0) / 1_000_000


def bbox(polygons: Sequence[Polygon]) -> tuple[float, float, float, float]:
    lons = [lon for p in polygons for lon, _ in p[0]]
    lats = [lat for p in polygons for _, lat in p[0]]
    return (min(lons), min(lats), max(lons), max(lats))


def _boxes_touch(a: Sequence[float], b: Sequence[float]) -> bool:
    return a[0] <= b[2] and b[0] <= a[2] and a[1] <= b[3] and b[1] <= a[3]


def _orientation(p: tuple[float, float], q: tuple[float, float], r: tuple[float, float]) -> float:
    return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])


def _segments_cross(
    a1: tuple[float, float],
    a2: tuple[float, float],
    b1: tuple[float, float],
    b2: tuple[float, float],
) -> bool:
    d1 = _orientation(b1, b2, a1)
    d2 = _orientation(b1, b2, a2)
    d3 = _orientation(a1, a2, b1)
    d4 = _orientation(a1, a2, b2)
    return ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0)) and 0 not in (d1, d2, d3, d4)


def _inside(point: tuple[float, float], ring: Ring) -> bool:
    """پرتاب پرتو — نقطه درون حلقه است؟"""
    x, y = point
    inside = False
    for (x1, y1), (x2, y2) in pairwise(ring):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


Point = tuple[float, float]


def _edges_near(ring: Ring, box: Sequence[float]) -> list[tuple[Point, Point]]:
    edges: list[tuple[Point, Point]] = []
    for p, q in pairwise(ring):
        edge_box = (min(p[0], q[0]), min(p[1], q[1]), max(p[0], q[0]), max(p[1], q[1]))
        if _boxes_touch(edge_box, box):
            edges.append((p, q))
    return edges


def polygons_overlap(a: Sequence[Polygon], b: Sequence[Polygon]) -> bool:
    """آیا دو محدوده هم‌پوشانی دارند؟ فقط حلقه‌های بیرونی سنجیده می‌شوند.

    سوراخ‌ها نادیده گرفته می‌شوند — محدودهٔ مطالعه به‌ندرت سوراخ دارد و
    هم‌پوشانی فقط **هشدار** است (FR-CITY-02)، نه ممنوعیت. سنجش دقیق با
    PostGIS در FR-CITY-02 می‌آید.
    """
    if not a or not b or not _boxes_touch(bbox(a), bbox(b)):
        return False
    for pa in a:
        for pb in b:
            outer_a, outer_b = pa[0], pb[0]
            box_a, box_b = bbox([pa]), bbox([pb])
            if not _boxes_touch(box_a, box_b):
                continue
            edges_a = _edges_near(outer_a, box_b)
            edges_b = _edges_near(outer_b, box_a)
            if any(_segments_cross(p, q, r, s) for p, q in edges_a for r, s in edges_b):
                return True
            if _inside(outer_a[0], outer_b) or _inside(outer_b[0], outer_a):
                return True
    return False


def normalized_geometry(polygons: Sequence[Polygon]) -> dict[str, Any]:
    """شکل ذخیره‌شده — همیشه MultiPolygon، تا خواننده یک حالت داشته باشد."""
    return {
        "type": "MultiPolygon",
        "coordinates": [[[list(pt) for pt in ring] for ring in polygon] for polygon in polygons],
    }


def polygons_of(geometry: Any) -> list[Polygon]:
    """خواندن دوبارهٔ هندسهٔ ذخیره‌شده؛ دادهٔ خراب یعنی «بی‌محدوده»."""
    polygons, problems = parse_area(geometry)
    return [] if problems else polygons


# ── اعتبارسنجی تحویل ────────────────────────────────────────────────────
def is_url(value: str) -> bool:
    return (
        value.startswith(("http://", "https://"))
        and len(value) <= 500
        and " " not in value
        and len(value) > len("https://")
    )


def _row(index: int) -> str:
    return f"ردیف {to_persian_digits(index + 1)}"


def _field(field: EvidenceField, raw: Any, today: date) -> tuple[Any, str | None]:
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return None, f"«{field.label_fa}» را وارد کن"
    match field.kind:
        case "int" | "number":
            try:
                number: float = int(raw) if field.kind == "int" else float(raw)
            except (TypeError, ValueError):
                return None, f"«{field.label_fa}» باید عدد باشد"
            if isinstance(raw, bool) or (field.kind == "number" and not math.isfinite(number)):
                return None, f"«{field.label_fa}» باید عدد باشد"
            if field.min_value is not None and number < field.min_value:
                if field.max_value == field.min_value:
                    return (
                        None,
                        f"«{field.label_fa}» باید {to_persian_digits(int(field.min_value))} باشد",
                    )
                return None, f"«{field.label_fa}» دست‌کم {to_persian_digits(field.min_value)} است"
            if field.max_value is not None and number > field.max_value:
                if field.max_value == field.min_value:
                    return (
                        None,
                        f"«{field.label_fa}» باید {to_persian_digits(int(field.max_value))} باشد",
                    )
                return None, f"«{field.label_fa}» حداکثر {to_persian_digits(field.max_value)} است"
            return number, None
        case "url":
            text = str(raw).strip()
            return (text, None) if is_url(text) else (None, f"«{field.label_fa}» پیوند معتبری نیست")
        case "date":
            try:
                when = date.fromisoformat(str(raw))
            except ValueError:
                return None, f"«{field.label_fa}» تاریخ معتبری نیست"
            if when > today:
                return None, f"«{field.label_fa}» نمی‌تواند در آینده باشد"
            return when.isoformat(), None
        case _:  # text
            text = " ".join(str(raw).split())
            if field.min_length is not None and len(text) < field.min_length:
                return None, (
                    f"«{field.label_fa}» دست‌کم {to_persian_digits(field.min_length)} نویسه باشد"
                )
            if len(text) > field.max_length:
                return None, f"«{field.label_fa}» بیش از حد طولانی است"
            return text, None


def _clean_text(raw: Any) -> str:
    return " ".join(str(raw or "").split())


def _validate_checks(
    raw: Any, files: Sequence[AttachedFile]
) -> tuple[list[dict[str, Any]], list[str]]:
    """جدول راستی‌آزمایی — قاعدهٔ حیاتی مرحلهٔ ۳."""
    if not isinstance(raw, list) or not raw:
        return [], ["جدول راستی‌آزمایی دست‌کم یک ردیف دارد"]
    if len(raw) > MAX_CHECKS:
        return [], [f"جدول راستی‌آزمایی حداکثر {to_persian_digits(MAX_CHECKS)} ردیف دارد"]

    images = {f.id for f in files if _is_image(f)}
    attached = {f.id for f in files}
    problems: list[str] = []
    cleaned: list[dict[str, Any]] = []
    all_sources: set[str] = set()
    for i, item in enumerate(raw):
        if not isinstance(item, Mapping):
            problems.append(f"{_row(i)}: ساختار نادرست است")
            continue
        row = _row(i)
        location = _clean_text(item.get("location"))
        finding = _clean_text(item.get("finding"))
        verdict = item.get("verdict")
        severity = item.get("severity") or "NORMAL"
        raw_sources = item.get("sources")
        sources = (
            list(dict.fromkeys(s for s in raw_sources if isinstance(s, str)))
            if isinstance(raw_sources, list)
            else []
        )
        raw_images = item.get("image_file_ids")
        image_ids = (
            list(dict.fromkeys(str(x) for x in raw_images)) if isinstance(raw_images, list) else []
        )
        resolution = _clean_text(item.get("resolution"))

        if len(location) < 3:
            problems.append(f"{row}: موقعیت را بنویس")
        if len(finding) < 10:
            problems.append(f"{row}: یافته را دست‌کم در ده نویسه بنویس")
        if verdict not in VERDICT_TITLE_FA:
            problems.append(f"{row}: «مطابق» یا «مغایر» را انتخاب کن")
        if severity not in SEVERITY_TITLE_FA:
            problems.append(f"{row}: شدت نامعتبر است")
        unknown = [s for s in sources if s not in SOURCE_TITLE_FA]
        if unknown:
            problems.append(f"{row}: منبع ناشناخته")
        if not sources:
            problems.append(f"{row}: دست‌کم یک منبع را علامت بزن")
        elif verdict == "MISMATCH" and len(sources) < 2:
            problems.append(f"{row}: هر مغایرت با دست‌کم دو منبع مستقل بررسی می‌شود")
        if severity == "CRITICAL" and FIELD_SOURCE not in sources:
            problems.append(f"{row}: مورد بحرانی بازدید میدانی لازم دارد")
        if verdict == "MISMATCH" and len(resolution) < 5:
            problems.append(f"{row}: اصلاح انجام‌شده در داده را بنویس")
        if not image_ids:
            problems.append(f"{row}: شاهد تصویری ندارد")
        elif any(x not in attached for x in image_ids):
            problems.append(f"{row}: تصویری که به آن ارجاع شده، پیوست نشده است")
        elif any(x not in images for x in image_ids):
            problems.append(f"{row}: شاهد تصویری باید فایل تصویر باشد")

        all_sources.update(s for s in sources if s in SOURCE_TITLE_FA)
        cleaned.append(
            {
                "location": location,
                "finding": finding,
                "verdict": verdict,
                "severity": severity,
                "sources": [s for s in SOURCES if s in sources],
                "image_file_ids": image_ids,
                "resolution": resolution or None,
            }
        )
    if cleaned and len(all_sources) < 2:
        problems.append("شواهد باید دست‌کم از دو منبع مختلف باشد")
    return cleaned, problems


SCENARIO_KPIS: tuple[tuple[str, str], ...] = (
    ("delay_s", "میانگین تأخیر (ثانیه بر وسیله)"),
    ("queue_m", "بیشینهٔ طول صف (متر)"),
    ("emissions_kg", "انتشار CO₂ (کیلوگرم در ساعت اوج)"),
)


def _validate_scenarios(raw: Any) -> tuple[list[dict[str, Any]], list[str]]:
    if not isinstance(raw, list) or len(raw) < MIN_SCENARIOS:
        return [], [f"دست‌کم {to_persian_digits(MIN_SCENARIOS)} سناریو لازم است"]
    if len(raw) > MAX_SCENARIOS:
        return [], [f"حداکثر {to_persian_digits(MAX_SCENARIOS)} سناریو"]
    problems: list[str] = []
    cleaned: list[dict[str, Any]] = []
    names: set[str] = set()
    baselines = 0
    for i, item in enumerate(raw):
        label = f"سناریوی {to_persian_digits(i + 1)}"
        if not isinstance(item, Mapping):
            problems.append(f"{label}: ساختار نادرست است")
            continue
        name = _clean_text(item.get("name"))
        description = _clean_text(item.get("description"))
        is_baseline = item.get("is_baseline") is True
        baselines += int(is_baseline)
        if len(name) < 2:
            problems.append(f"{label}: نام را بنویس")
        elif name in names:
            problems.append(f"{label}: نام تکراری است")
        names.add(name)
        if len(description) < 10:
            problems.append(f"{label}: شرح را دست‌کم در ده نویسه بنویس")
        row: dict[str, Any] = {"name": name, "description": description, "is_baseline": is_baseline}
        for key, title in SCENARIO_KPIS:
            value = item.get(key)
            try:
                number = float(value)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                problems.append(f"{label}: «{title}» را وارد کن")
                continue
            if isinstance(value, bool) or not math.isfinite(number) or number < 0:
                problems.append(f"{label}: «{title}» عدد نامنفی است")
                continue
            row[key] = number
        cleaned.append(row)
    if baselines != 1:
        problems.append("دقیقاً یک سناریو باید «سناریوی پایه» (وضع موجود) باشد")
    return cleaned, problems


def validate_submission(
    number: int,
    *,
    body: str | None,
    links: Sequence[str],
    files: Sequence[AttachedFile],
    evidence: Mapping[str, Any],
    checklist_confirmed: Sequence[int],
    today: date,
) -> tuple[dict[str, Any], list[str]]:
    """شاهدهای تحویل یک مرحلهٔ شهری. خروجی: (شاهد پاک‌شده، فهرست کمبودها).

    هم‌پوشانی محدوده اینجا سنجیده نمی‌شود: به پروژه‌های دیگر نیاز دارد و
    سرویس پس از همین تابع اضافه‌اش می‌کند.
    """
    spec = stage(number)
    problems: list[str] = []
    cleaned: dict[str, Any] = {}

    if len((body or "").strip()) < SUMMARY_MIN:
        problems.append(f"خلاصهٔ تحویل دست‌کم {to_persian_digits(SUMMARY_MIN)} نویسه باشد")

    known = {f.key for f in spec.evidence}
    if spec.structured is not None:
        known.add(STRUCTURED_KEY[spec.structured])
    unknown = sorted(set(evidence) - known)
    if unknown:
        problems.append("شاهد ناشناخته: " + "، ".join(unknown))

    for field in spec.evidence:
        value, problem = _field(field, evidence.get(field.key), today)
        if problem:
            problems.append(problem)
        else:
            cleaned[field.key] = value

    match spec.structured:
        case "AREA":
            polygons, area_problems = parse_area(evidence.get("area"))
            if area_problems:
                problems.extend(area_problems)
            else:
                size = area_km2(polygons)
                if not AREA_MIN_KM2 <= size <= AREA_MAX_KM2:
                    problems.append(
                        f"مساحت محدوده {to_persian_digits(round(size, 2))} کیلومتر مربع است؛"
                        f" باید بین {to_persian_digits(AREA_MIN_KM2)} و"
                        f" {to_persian_digits(int(AREA_MAX_KM2))} باشد"
                    )
                cleaned["area"] = normalized_geometry(polygons)
                cleaned["area_km2"] = round(size, 3)
                cleaned["bbox"] = list(bbox(polygons))
        case "CHECKS":
            checks, check_problems = _validate_checks(evidence.get("checks"), files)
            problems.extend(check_problems)
            cleaned["checks"] = checks
        case "SCENARIOS":
            scenarios, scenario_problems = _validate_scenarios(evidence.get("scenarios"))
            problems.extend(scenario_problems)
            cleaned["scenarios"] = scenarios
        case _:
            pass

    for rule in spec.files:
        matching = [f for f in files if _matches(rule.kind, f)]
        if not matching:
            problems.append(f"{rule.label_fa} را پیوست کن")
        elif rule.exactly_one and len(matching) > 1:
            problems.append(f"فقط یک {rule.label_fa} در هر تحویل؛ نسخهٔ تازه را جدا بفرست")

    if len(files) + len(links) < spec.min_attachments:
        problems.append(spec.attachments_hint_fa or "پیوست لازم است")
    problems.extend(f"پیوند نامعتبر: {link}" for link in links if not is_url(link))

    confirmed = set(checklist_confirmed)
    missing_items = [spec.checklist[i].text for i in spec.manual_items if i not in confirmed]
    if missing_items:
        problems.append("این موارد چک‌لیست را تأیید کن: " + "، ".join(missing_items))
    cleaned["checklist_confirmed"] = sorted(i for i in confirmed if 0 <= i < len(spec.checklist))
    return cleaned, problems


def image_count(evidence: Mapping[str, Any] | None) -> int:
    """شمار تصویرهای جدول راستی‌آزمایی — نگهبان تأیید مرحلهٔ ۳."""
    if not evidence:
        return 0
    checks = evidence.get("checks")
    if not isinstance(checks, list):
        return 0
    return sum(len(c.get("image_file_ids") or []) for c in checks if isinstance(c, Mapping))


# ── وضعیت مراحل ─────────────────────────────────────────────────────────
def is_locked(number: int, statuses: Mapping[int, str]) -> bool:
    """مرحلهٔ n فقط پس از تأیید مرحلهٔ n−۱ تحویل می‌پذیرد."""
    return number > 1 and statuses.get(number - 1) != "APPROVED"


def current_stage(statuses: Mapping[int, str]) -> int | None:
    """اولین مرحلهٔ تأییدنشده؛ None یعنی گردش‌کار کامل شده است."""
    for s in STAGES:
        if statuses.get(s.number) != "APPROVED":
            return s.number
    return None


__all__ = [
    "AREA_MAX_KM2",
    "AREA_MAX_VERTICES",
    "AREA_MIN_KM2",
    "ARTIFACTS",
    "ARTIFACT_EXTENSION_FA",
    "ARTIFACT_TITLE_FA",
    "SCENARIO_KPIS",
    "SEVERITY_TITLE_FA",
    "SOURCES",
    "SOURCE_TITLE_FA",
    "STAGES",
    "STAGE_BY_NUMBER",
    "STAGE_COUNT",
    "TOTAL_DAYS",
    "TOTAL_POINTS",
    "VERDICT_TITLE_FA",
    "WORKFLOWS",
    "WORKFLOW_CITY",
    "WORKFLOW_KIND",
    "AttachedFile",
    "ChecklistItem",
    "EvidenceField",
    "FileRule",
    "Stage",
    "area_km2",
    "artifact_of",
    "artifacts_in",
    "bbox",
    "current_stage",
    "due_dates",
    "image_count",
    "is_locked",
    "is_url",
    "normalized_geometry",
    "parse_area",
    "polygons_of",
    "polygons_overlap",
    "stage",
    "validate_submission",
]
