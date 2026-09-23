"""مسیر پژوهش، خروجی پژوهشی و بانک موضوع — FR-RES-01/02/03، ADR-0015. منطق خالص.

## مسیر چهارسطحی

هر سطح یک تحویل‌دادنی دارد (FR-RES-01) و «راهنمای گام‌به‌گام و الگو».
این‌ها محتوای ثابت‌اند، نه داده: متن راهنما با نسخهٔ کد عوض می‌شود و
برای هر دانشجو یکی است. پس جدولی برایشان ساخته نشد.

تحویل هر سطح، علاوه بر خلاصه و پیوست، چند «شاهد» ساختاریافته دارد —
«≥۲۰ منبع» عددی است که بازبین باید ببیند، نه جمله‌ای در دل متن.
`validate_submission` شاهدها را پیش از رسیدن به بازبین می‌سنجد؛ تأیید
نهایی با انسان است.

## خروجی پژوهشی و امتیاز

وضعیت مقاله (`status`) ادعای نویسنده است. امتیاز `OUTPUT_*` فقط از
آنچه بازبین **راستی‌آزمایی** کرده (`verified_stage`) می‌آید — همان اصل
ADR-0014 برای شاخص فروش: «ثبت خود دانشجو ادعاست، تأیید دیگری واقعیت».
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Literal

LEVELS = (1, 2, 3, 4)
MAX_LEVEL = 4

SUMMARY_MIN = 30
SUMMARY_MAX = 4000
MAX_LINKS = 10
URL_MAX = 500
TEXT_FIELD_MAX = 1500

#: FR-RES-03 — «موضوعات رزروشده پس از ۳۰ روز بی‌تحرکی آزاد می‌شوند».
RESERVATION_IDLE_DAYS = 30
#: هشدار پیش از آزادسازی — کسی که واقعاً کار می‌کند، فرصت دارد تحویلی بفرستد.
RESERVATION_WARNING_DAYS = 25

FieldKind = Literal["int", "text", "url", "date"]


@dataclass(frozen=True, slots=True)
class EvidenceField:
    key: str
    label_fa: str
    kind: FieldKind
    hint_fa: str | None = None
    min_value: int | None = None
    min_length: int | None = None


@dataclass(frozen=True, slots=True)
class Level:
    number: int
    title_fa: str
    deliverable_fa: str
    rule_code: str
    steps: tuple[str, ...]
    checklist: tuple[str, ...]
    template_title_fa: str
    template_columns: tuple[str, ...]
    evidence: tuple[EvidenceField, ...]
    #: کمینهٔ پیوست (فایل یا پیوند) — ماتریس مرور، پیش‌نویس مقاله، …
    min_attachments: int = 0
    attachments_hint_fa: str | None = None


LEVEL_SPECS: dict[int, Level] = {
    1: Level(
        number=1,
        title_fa="مرور ادبیات",
        deliverable_fa="ماتریس مرور با دست‌کم ۲۰ منبع و خلاصهٔ شکاف پژوهشی",
        rule_code="RESEARCH_L1_APPROVED",
        steps=(
            "پرسش پژوهشی‌ات را در یک جمله بنویس؛ اگر موضوعی از بانک موضوع رزرو"
            " کرده‌ای، از شرح همان شروع کن.",
            "کلیدواژه‌ها را فهرست کن و در Scopus، Google Scholar و پایگاه‌های داخلی"
            " (SID، Magiran) جستجو کن.",
            "از میان نتایج، دست‌کم ۲۰ منبع مرتبط برگزین — ترجیحاً مقاله‌های پنج سال"
            " اخیر و چند منبع پایه‌ای.",
            "هر منبع را در یک سطر ماتریس مرور خلاصه کن: مسئله، روش، داده، یافته و محدودیت.",
            "ستون‌ها را کنار هم بخوان: چه چیزی تکرار شده و چه چیزی را هیچ‌کس"
            " نپرسیده؟ این شکاف پژوهشی توست.",
            "شکاف را در یک بند بنویس و ماتریس را پیوست کن.",
        ),
        checklist=(
            "دست‌کم ۲۰ منبع، همه با مشخصات کامل کتاب‌شناختی",
            "برای هر منبع روش و یافتهٔ اصلی ثبت شده است",
            "شکاف پژوهشی مشخص است و از خود ماتریس درمی‌آید، نه از حدس",
            "منابع فقط فارسی یا فقط انگلیسی نیستند",
        ),
        template_title_fa="ماتریس مرور ادبیات",
        template_columns=(
            "ردیف",
            "نویسندگان و سال",
            "عنوان",
            "مجله یا کنفرانس",
            "مسئلهٔ پژوهش",
            "روش",
            "داده و محدوده",
            "یافتهٔ اصلی",
            "محدودیت",
            "ارتباط با پژوهش من",
        ),
        evidence=(
            EvidenceField(
                "source_count",
                "تعداد منابع ماتریس",
                "int",
                hint_fa="دست‌کم ۲۰",
                min_value=20,
            ),
            EvidenceField(
                "gap_summary",
                "خلاصهٔ شکاف پژوهشی",
                "text",
                hint_fa="یک بند: چه چیزی در ادبیات نیست و چرا مهم است",
                min_length=80,
            ),
        ),
        min_attachments=1,
        attachments_hint_fa="ماتریس مرور را به‌صورت فایل (Excel یا CSV) یا پیوند پیوست کن.",
    ),
    2: Level(
        number=2,
        title_fa="تحلیل داده",
        deliverable_fa="دفترچهٔ تحلیل بازتولیدپذیر و مجموعه‌داده",
        rule_code="RESEARCH_L2_APPROVED",
        steps=(
            "از شکاف سطح ۱ یک فرضیه یا پرسش قابل آزمون بساز.",
            "داده را پیدا یا گردآوری کن و منبع و مجوز استفاده‌اش را ثبت کن.",
            "پاک‌سازی داده را در کد انجام بده، نه با دست — هر تغییر باید در دفترچه دیده شود.",
            "تحلیل را در یک دفترچهٔ R Markdown، Quarto یا Jupyter بنویس که از دادهٔ"
            " خام تا نمودار نهایی اجرا شود.",
            "دفترچه را در GitHub، OSF یا Colab بگذار و مجموعه‌داده را با شرح ستون‌ها منتشر کن.",
        ),
        checklist=(
            "دفترچه از ابتدا تا انتها بدون خطا اجرا می‌شود",
            "نسخهٔ بسته‌ها یا محیط اجرا ثبت شده است",
            "مجموعه‌داده شرح ستون‌ها (دیکشنری داده) دارد",
            "هر نمودار و جدول یک جملهٔ تفسیر دارد",
        ),
        template_title_fa="ساختار دفترچهٔ تحلیل",
        template_columns=(
            "پرسش و فرضیه",
            "منبع داده و مجوز",
            "پاک‌سازی و آماده‌سازی",
            "تحلیل توصیفی",
            "مدل یا آزمون",
            "نتایج و تفسیر",
            "محدودیت‌ها",
            "محیط اجرا و نسخه‌ها",
        ),
        evidence=(
            EvidenceField(
                "notebook_url",
                "پیوند دفترچهٔ تحلیل",
                "url",
                hint_fa="GitHub، OSF یا Colab",
            ),
            EvidenceField(
                "dataset_url",
                "پیوند مجموعه‌داده",
                "url",
                hint_fa="همراه با شرح ستون‌ها",
            ),
        ),
    ),
    3: Level(
        number=3,
        title_fa="مقالهٔ کنفرانس",
        deliverable_fa="پیش‌نویس کامل مقاله و گواهی ارسال به کنفرانس",
        rule_code="RESEARCH_L3_APPROVED",
        steps=(
            "کنفرانس مناسب را انتخاب کن و قالب و مهلت ارسالش را بخوان.",
            "مقاله را در ساختار IMRaD بنویس: مقدمه، روش، نتایج، بحث.",
            "یافته‌های سطح ۲ را با همان دفترچه بازتولید کن تا عدد متن و عدد کد یکی باشند.",
            "پیش‌نویس را پیش از ارسال به منتور بده و بازخوردش را اعمال کن.",
            "مقاله را ارسال کن و ایمیل یا صفحهٔ تأیید ارسال را نگه دار.",
        ),
        checklist=(
            "چکیده حداکثر ۲۵۰ واژه و پاسخ‌گوی «چه، چرا، چگونه، چه یافتیم»",
            "روش آن‌قدر دقیق است که دیگری بتواند تکرارش کند",
            "همهٔ منابع متن در فهرست منابع هستند و برعکس",
            "قالب کنفرانس رعایت شده است",
        ),
        template_title_fa="ساختار مقالهٔ کنفرانس (IMRaD)",
        template_columns=(
            "عنوان",
            "چکیده",
            "مقدمه و شکاف پژوهشی",
            "روش",
            "نتایج",
            "بحث",
            "نتیجه‌گیری",
            "منابع",
        ),
        evidence=(
            EvidenceField("venue", "نام کنفرانس", "text", min_length=3),
            EvidenceField("submitted_on", "تاریخ ارسال", "date"),
        ),
        min_attachments=1,
        attachments_hint_fa="پیش‌نویس کامل و گواهی یا ایمیل تأیید ارسال را پیوست کن.",
    ),
    4: Level(
        number=4,
        title_fa="مقالهٔ Q1",
        deliverable_fa="پیش‌نویس مقاله و شناسهٔ ارسال به مجلهٔ Q1",
        rule_code="RESEARCH_L4_APPROVED",
        steps=(
            "مجلهٔ هدف را با چارک Q1 در SJR یا JCR و دامنهٔ هم‌خوان با پژوهشت انتخاب کن.",
            "راهنمای نویسندگان مجله را بخوان و مقاله را با آن تطبیق بده.",
            "سهم نوآوری را در مقدمه و بحث روشن بنویس — داور Q1 اول همین را می‌پرسد.",
            "داده و کد را در مخزن عمومی بگذار و در متن به آن ارجاع بده.",
            "نامهٔ همراه (Cover Letter) بنویس، مقاله را ارسال کن و شناسهٔ ارسال را ثبت کن.",
        ),
        checklist=(
            "چارک مجله در سال جاری Q1 است",
            "نوآوری مقاله در یک جمله قابل بیان است",
            "داده و کد در دسترس داوران است",
            "نامهٔ همراه به دامنهٔ مجله اشاره می‌کند",
        ),
        template_title_fa="بستهٔ ارسال به مجله",
        template_columns=(
            "نامهٔ همراه",
            "صفحهٔ عنوان و نویسندگان",
            "متن اصلی بدون نام نویسندگان",
            "نکات برجسته (Highlights)",
            "بیانیهٔ دسترسی به داده",
            "بیانیهٔ تعارض منافع",
        ),
        evidence=(
            EvidenceField("journal", "نام مجله", "text", min_length=3),
            EvidenceField("manuscript_id", "شناسهٔ ارسال", "text", min_length=3),
            EvidenceField(
                "quartile_source_url",
                "پیوند صفحهٔ مجله در SJR یا JCR",
                "url",
                hint_fa="صفحه‌ای که چارک Q1 مجله را نشان می‌دهد",
            ),
        ),
        min_attachments=1,
        attachments_hint_fa="پیش‌نویس ارسال‌شده را پیوست کن.",
    ),
}


def level_spec(level: int) -> Level:
    spec = LEVEL_SPECS.get(level)
    if spec is None:
        msg = f"سطح پژوهش نامعتبر: {level}"
        raise ValueError(msg)
    return spec


def rule_for_level(level: int) -> str:
    return level_spec(level).rule_code


def is_url(value: str) -> bool:
    return (
        value.startswith(("http://", "https://"))
        and len(value) <= URL_MAX
        and " " not in value
        and len(value) > len("https://")
    )


def validate_submission(
    level: int,
    *,
    summary: str,
    links: Sequence[str],
    file_count: int,
    evidence: Mapping[str, Any],
    today: date,
) -> tuple[dict[str, Any], list[str]]:
    """شاهدهای یک تحویل را می‌سنجد. خروجی: (شاهد پاک‌شده، فهرست کمبودها).

    همهٔ کمبودها یک‌جا برمی‌گردند — همان قاعدهٔ §7.7 برای معیار خروج:
    دانشجو باید بداند دقیقاً چه چیزی لازم است، نه اینکه یکی‌یکی کشفش کند.
    """
    spec = level_spec(level)
    problems: list[str] = []
    cleaned: dict[str, Any] = {}

    if len(summary.strip()) < SUMMARY_MIN:
        problems.append(f"خلاصهٔ تحویل دست‌کم {SUMMARY_MIN} نویسه باشد")
    if len(links) > MAX_LINKS:
        problems.append(f"حداکثر {MAX_LINKS} پیوند")
    problems.extend(f"پیوند نامعتبر: {link}" for link in links if not is_url(link))
    if file_count + len(links) < spec.min_attachments:
        problems.append(spec.attachments_hint_fa or "پیوست لازم است")

    known = {f.key for f in spec.evidence}
    unknown = sorted(set(evidence) - known)
    if unknown:
        problems.append("شاهد ناشناخته: " + "، ".join(unknown))

    for field in spec.evidence:
        raw = evidence.get(field.key)
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            problems.append(f"«{field.label_fa}» را وارد کن")
            continue
        match field.kind:
            case "int":
                try:
                    number = int(raw)
                except (TypeError, ValueError):
                    problems.append(f"«{field.label_fa}» باید عدد باشد")
                    continue
                if field.min_value is not None and number < field.min_value:
                    problems.append(f"«{field.label_fa}» دست‌کم {field.min_value} است")
                    continue
                cleaned[field.key] = number
            case "url":
                text = str(raw).strip()
                if not is_url(text):
                    problems.append(f"«{field.label_fa}» پیوند معتبری نیست")
                    continue
                cleaned[field.key] = text
            case "date":
                try:
                    when = date.fromisoformat(str(raw))
                except ValueError:
                    problems.append(f"«{field.label_fa}» تاریخ معتبری نیست")
                    continue
                if when > today:
                    problems.append(f"«{field.label_fa}» نمی‌تواند در آینده باشد")
                    continue
                cleaned[field.key] = when.isoformat()
            case _:  # text
                text = " ".join(str(raw).split())
                if field.min_length is not None and len(text) < field.min_length:
                    problems.append(f"«{field.label_fa}» دست‌کم {field.min_length} نویسه باشد")
                    continue
                if len(text) > TEXT_FIELD_MAX:
                    problems.append(f"«{field.label_fa}» بیش از حد طولانی است")
                    continue
                cleaned[field.key] = text
    return cleaned, problems


# ── وضعیت هر سطح برای نمایش ────────────────────────────────────────────
LevelState = Literal["LOCKED", "AVAILABLE", "IN_PROGRESS", "SUBMITTED", "APPROVED"]

LEVEL_STATE_TITLE_FA: dict[str, str] = {
    "LOCKED": "قفل",
    "AVAILABLE": "آمادهٔ شروع",
    "IN_PROGRESS": "در جریان",
    "SUBMITTED": "در انتظار بررسی",
    "APPROVED": "تأیید شده",
}


def level_state(level: int, track_statuses: Mapping[int, str]) -> LevelState:
    """وضعیت سطح از روی ردیف‌های `research_tracks` کاربر.

    ردیف هر سطح وقتی ساخته می‌شود که سطح قبلی تأیید شود (سطح ۱ با اولین
    تحویل). پس سطح بی‌ردیف یا «آمادهٔ شروع» است یا «قفل».
    """
    status = track_statuses.get(level)
    if status is not None:
        return status  # type: ignore[return-value]
    if level == 1:
        return "AVAILABLE"
    return "AVAILABLE" if track_statuses.get(level - 1) == "APPROVED" else "LOCKED"


def current_level(track_statuses: Mapping[int, str]) -> int | None:
    """اولین سطحی که تأیید نشده؛ None یعنی هر چهار سطح تأیید شده‌اند."""
    for level in LEVELS:
        if track_statuses.get(level) != "APPROVED":
            return level
    return None


# ── خروجی پژوهشی — FR-RES-02 ───────────────────────────────────────────
OUTPUT_KIND_TITLE_FA: dict[str, str] = {
    "JOURNAL": "مقالهٔ مجله",
    "CONFERENCE": "مقالهٔ کنفرانس",
    "THESIS": "پایان‌نامه",
    "REPORT": "گزارش پژوهشی",
    "PREPRINT": "پیش‌انتشار",
}
OUTPUT_KINDS = tuple(OUTPUT_KIND_TITLE_FA)

OUTPUT_STATUS_TITLE_FA: dict[str, str] = {
    "DRAFT": "پیش‌نویس",
    "SUBMITTED": "ارسال‌شده",
    "UNDER_REVIEW": "در داوری",
    "REVISION": "در حال اصلاح",
    "ACCEPTED": "پذیرفته‌شده",
    "PUBLISHED": "منتشرشده",
    "REJECTED": "ردشده",
}
OUTPUT_STATUSES = tuple(OUTPUT_STATUS_TITLE_FA)
QUARTILES = ("Q1", "Q2", "Q3", "Q4", "NA")
REVIEW_STATUSES = ("NONE", "PENDING", "VERIFIED", "REJECTED")

#: فقط مقالهٔ مجله و کنفرانس «ارسال» و «پذیرش» دارند؛ پایان‌نامه، گزارش و
#: پیش‌انتشار در نیمرخ دیده می‌شوند ولی امتیاز `OUTPUT_*` ندارند.
SCORED_KINDS = frozenset({"JOURNAL", "CONFERENCE"})

#: مرحلهٔ امتیازی هر وضعیت. مقالهٔ ردشده هم ارسال شده بوده است.
OUTPUT_STAGES = ("SUBMITTED", "ACCEPTED", "PUBLISHED")
STAGE_OF_STATUS: dict[str, str | None] = {
    "DRAFT": None,
    "SUBMITTED": "SUBMITTED",
    "UNDER_REVIEW": "SUBMITTED",
    "REVISION": "SUBMITTED",
    "REJECTED": "SUBMITTED",
    "ACCEPTED": "ACCEPTED",
    "PUBLISHED": "PUBLISHED",
}
STAGE_RANK: dict[str | None, int] = {None: 0, "SUBMITTED": 1, "ACCEPTED": 2, "PUBLISHED": 3}

#: §9.2 `OUTPUT_ACCEPTED` — «ضریب چارک: Q1=۲.۰، Q2=۱.۵، Q3=۱.۲، Q4=۱.۰».
QUARTILE_FACTOR: dict[str, Decimal] = {
    "Q1": Decimal("2.0"),
    "Q2": Decimal("1.5"),
    "Q3": Decimal("1.2"),
    "Q4": Decimal("1.0"),
}

OUTPUT_RULES = ("OUTPUT_SUBMITTED", "OUTPUT_ACCEPTED", "OUTPUT_PUBLISHED")


def stage_of(status: str) -> str | None:
    return STAGE_OF_STATUS.get(status)


def effective_quartile(kind: str, quartile: str | None) -> str | None:
    """چارک فقط برای مجله معنا دارد."""
    if kind != "JOURNAL" or quartile in (None, "NA"):
        return None
    return quartile


def output_awards(kind: str, stage: str | None, quartile: str | None) -> list[tuple[str, Decimal]]:
    """امتیازهای مطلوب یک خروجی در یک مرحله — (قاعده، ضریب).

    پذیرش، ارسال را هم شامل می‌شود و انتشار، پذیرش را: مقاله‌ای که
    مستقیم با وضعیت «منتشرشده» ثبت شد، هر سه را گرفته است.
    """
    if kind not in SCORED_KINDS:
        return []
    rank = STAGE_RANK.get(stage, 0)
    awards: list[tuple[str, Decimal]] = []
    if rank >= 1:
        awards.append(("OUTPUT_SUBMITTED", Decimal(1)))
    if rank >= 2:
        q = effective_quartile(kind, quartile)
        awards.append(("OUTPUT_ACCEPTED", QUARTILE_FACTOR.get(q or "", Decimal(1))))
    if rank >= 3:
        awards.append(("OUTPUT_PUBLISHED", Decimal(1)))
    return awards


def needs_review(
    *,
    kind: str,
    status: str,
    quartile: str | None,
    verified_stage: str | None,
    verified_quartile: str | None,
) -> bool:
    """آیا ادعای فعلی امتیازی متفاوت از آنچه تأیید شده می‌سازد؟

    هر تفاوت — بالا یا پایین — بازبینی می‌خواهد: بالا رفتن امتیاز تازه
    می‌دهد، و پایین آمدن (مثلاً اصلاح اشتباه) امتیاز قبلی را پس می‌گیرد.
    ویرایشی که امتیاز را عوض نمی‌کند (DOI، پیوند، «در داوری» پس از
    «ارسال‌شده»)، صف بازبین را پر نمی‌کند.
    """
    claimed = output_awards(kind, stage_of(status), quartile)
    verified = output_awards(kind, verified_stage, verified_quartile)
    return claimed != verified


DOI_PATTERN = re.compile(r"^10\.\d{4,9}/\S+$")


def normalize_doi(raw: str | None) -> str | None:
    """`https://doi.org/10.1016/…` یا `doi:10.1016/…` ← `10.1016/…`."""
    if raw is None:
        return None
    text = raw.strip()
    for prefix in ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/", "doi:"):
        if text.lower().startswith(prefix):
            text = text[len(prefix) :]
            break
    return text or None


def is_doi(value: str) -> bool:
    return bool(DOI_PATTERN.match(value))


# ── بانک موضوع — FR-RES-03 ─────────────────────────────────────────────
TOPIC_STATUS_TITLE_FA: dict[str, str] = {
    "PROPOSED": "در انتظار تأیید",
    "OPEN": "باز",
    "RESERVED": "رزروشده",
    "TAKEN": "در حال انجام",
    "CLOSED": "بسته",
}
TOPIC_STATUSES = tuple(TOPIC_STATUS_TITLE_FA)
#: وضعیت‌هایی که همه می‌بینند؛ پیشنهاد تأییدنشده و موضوع بسته فقط برای
#: پیشنهاددهنده و کادر.
PUBLIC_TOPIC_STATUSES = ("OPEN", "RESERVED", "TAKEN")


__all__ = [
    "LEVELS",
    "LEVEL_SPECS",
    "LEVEL_STATE_TITLE_FA",
    "MAX_LEVEL",
    "OUTPUT_KINDS",
    "OUTPUT_KIND_TITLE_FA",
    "OUTPUT_RULES",
    "OUTPUT_STAGES",
    "OUTPUT_STATUSES",
    "OUTPUT_STATUS_TITLE_FA",
    "PUBLIC_TOPIC_STATUSES",
    "QUARTILES",
    "QUARTILE_FACTOR",
    "RESERVATION_IDLE_DAYS",
    "RESERVATION_WARNING_DAYS",
    "REVIEW_STATUSES",
    "SCORED_KINDS",
    "TOPIC_STATUSES",
    "TOPIC_STATUS_TITLE_FA",
    "EvidenceField",
    "Level",
    "LevelState",
    "current_level",
    "effective_quartile",
    "is_doi",
    "is_url",
    "level_spec",
    "level_state",
    "needs_review",
    "normalize_doi",
    "output_awards",
    "rule_for_level",
    "stage_of",
    "validate_submission",
]
