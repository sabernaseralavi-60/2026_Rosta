"""قواعد خالص کارآفرینی — PRD §7.7، §9.2 `STARTUP`. بدون I/O.

## معیار خروج هر مرحله (§7.7)

| از | به | معیار |
|----|-----|-------|
| `IDEA` | `VALIDATION` | شرح، مسئله، بازار هدف و مدل درآمد پر شده |
| `VALIDATION` | `MVP` | ≥ ۱۰ جلسه یا سرنخ **تأییدشده** |
| `MVP` | `FIRST_REVENUE` | ≥ ۱ تحویل‌دادنی تأییدشدهٔ `CODE` یا `MEDIA` در پروژه‌های کسب‌وکار |
| `FIRST_REVENUE` | `GROWTH` | مجموع فروش تأییدشده > آستانهٔ تنظیمات |

«تأییدشده» عمدی است (ADR-0014): ارتقای مرحله امتیاز `50 × مرحله` دارد، و
معیاری که با خوداظهاری پر شود، امتیاز بدون خلق ارزش است — که §09 آن را
باگ می‌داند.

سرویس «واقعیت‌ها» را از دیتابیس می‌سازد و این ماژول فقط داوری می‌کند؛
پس هر معیار بدون دیتابیس تست می‌شود و همان داوری هم پیشرفت («۶ از ۱۰»)
را برای رابط کاربری برمی‌گرداند، هم فهرست کمبودها را برای خطای ۴۰۹.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from silp.domain.text import format_number_fa, to_persian_digits
from silp.models.venture import GROWTH_STAGES, STAGE_TITLE_FA

VALIDATION_CONTACTS_REQUIRED = 10
MVP_DELIVERABLES_REQUIRED = 1
MVP_OUTPUT_KINDS = ("CODE", "MEDIA")
#: پیش‌فرض آستانهٔ رشد — ۵۰ میلیون تومان. قابل تنظیم با
#: `VENTURE_GROWTH_THRESHOLD_RIAL` تا پنل تنظیمات (M7-12) بیاید.
DEFAULT_GROWTH_THRESHOLD_RIAL = 500_000_000

PROFILE_FIELDS: tuple[tuple[str, str], ...] = (
    ("description", "شرح کسب‌وکار"),
    ("problem", "مسئله‌ای که حل می‌کند"),
    ("target_market", "بازار هدف"),
    ("revenue_model", "مدل درآمد"),
)

# ── شاخص‌ها و امتیاز — §9.2 `STARTUP` ───────────────────────────────────
METRIC_RULES: dict[str, str] = {
    "CALLS": "METRIC_CALLS",
    "MEETINGS": "METRIC_MEETINGS",
    "LEADS": "METRIC_LEADS",
    "SALES_COUNT": "METRIC_SALES_COUNT",
    "SALES_AMOUNT": "METRIC_SALES_AMOUNT",
    "CONTENT_PIECES": "METRIC_CONTENT",
    "CUSTOMERS": "CUSTOMER_RETAINED",
}
#: §9.2 — «به‌ازای هر ۵۰۰ هزار تومان فروش ۱ امتیاز، سقف ۲۰۰ در هر تراکنش».
SALES_RIAL_PER_POINT = 5_000_000
SALES_MAX_MULTIPLIER = Decimal(200)
#: شمارشی که سقف روزانه ندارد هم بی‌کران نیست — یک ردیف ۱۰۰۰۰ سرنخی
#: غلط تایپی است، نه دستاورد.
UNCAPPED_COUNT_LIMIT = 100
MULTIPLIER_QUANTUM = Decimal("0.0001")


@dataclass(frozen=True, slots=True)
class VentureFacts:
    filled_fields: frozenset[str] = frozenset()
    verified_contacts: int = 0
    approved_mvp_deliverables: int = 0
    verified_sales_rial: int = 0
    growth_threshold_rial: int = DEFAULT_GROWTH_THRESHOLD_RIAL


@dataclass(frozen=True, slots=True)
class Criterion:
    code: str
    text: str
    met: bool
    current: int
    target: int


@dataclass(frozen=True, slots=True)
class Readiness:
    """آمادگی برای رفتن به مرحلهٔ بعد."""

    next_stage: str | None
    criteria: tuple[Criterion, ...] = field(default_factory=tuple)

    @property
    def ready(self) -> bool:
        return self.next_stage is not None and all(c.met for c in self.criteria)

    @property
    def missing(self) -> list[str]:
        return [c.text for c in self.criteria if not c.met]


def next_growth_stage(stage: str) -> str | None:
    if stage not in GROWTH_STAGES:
        return None
    index = GROWTH_STAGES.index(stage)
    return GROWTH_STAGES[index + 1] if index + 1 < len(GROWTH_STAGES) else None


def stage_number(stage: str) -> int:
    """ضریب `VENTURE_STAGE_UP`: VALIDATION=۱ … GROWTH=۴ — §9.2 «۵۰ × مرحله»."""
    return GROWTH_STAGES.index(stage)


def readiness(stage: str, facts: VentureFacts) -> Readiness:
    target = next_growth_stage(stage)
    if target is None:
        return Readiness(next_stage=None)
    return Readiness(next_stage=target, criteria=tuple(_criteria_for(stage, facts)))


def _criteria_for(stage: str, facts: VentureFacts) -> list[Criterion]:
    match stage:
        case "IDEA":
            return [
                Criterion(
                    code=f"FIELD_{name.upper()}",
                    text=f"«{title}» را بنویس",
                    met=name in facts.filled_fields,
                    current=int(name in facts.filled_fields),
                    target=1,
                )
                for name, title in PROFILE_FIELDS
            ]
        case "VALIDATION":
            return [
                Criterion(
                    code="VALIDATION_CONTACTS",
                    text=(
                        f"دست‌کم {to_persian_digits(VALIDATION_CONTACTS_REQUIRED)}"
                        " جلسه یا سرنخ مشتری ثبت و تأیید شود"
                    ),
                    met=facts.verified_contacts >= VALIDATION_CONTACTS_REQUIRED,
                    current=min(facts.verified_contacts, VALIDATION_CONTACTS_REQUIRED),
                    target=VALIDATION_CONTACTS_REQUIRED,
                )
            ]
        case "MVP":
            return [
                Criterion(
                    code="MVP_DELIVERABLE",
                    text="یک تحویل‌دادنی کد یا محتوا در پروژه‌های این کسب‌وکار تأیید شود",
                    met=facts.approved_mvp_deliverables >= MVP_DELIVERABLES_REQUIRED,
                    current=min(facts.approved_mvp_deliverables, MVP_DELIVERABLES_REQUIRED),
                    target=MVP_DELIVERABLES_REQUIRED,
                )
            ]
        case "FIRST_REVENUE":
            threshold = facts.growth_threshold_rial
            return [
                Criterion(
                    code="GROWTH_REVENUE",
                    text=f"مجموع فروش تأییدشده از {format_number_fa(threshold // 10)} تومان بگذرد",
                    met=facts.verified_sales_rial > threshold,
                    current=min(facts.verified_sales_rial, threshold),
                    target=threshold,
                )
            ]
    return []


def metric_multiplier(metric: str, value: int, *, per_row_cap: int | None) -> Decimal:
    """ضریب امتیاز یک ردیف شاخص تأییدشده.

    * `SALES_AMOUNT`: `min(200, ریال ÷ 5,000,000)`.
    * شمارش‌های سقف‌دار (تماس، جلسه، محتوا): `min(مقدار، سقف روزانهٔ قاعده)`.
      سقف §9.2 «۲۰ / روز» برای تماس است؛ یک ردیف «۵۰ تماس» ۲۰ حساب
      می‌شود، نه ۵۰ (ADR-0014).
    * بقیه: خود مقدار، تا `UNCAPPED_COUNT_LIMIT`.
    """
    if value <= 0:
        return Decimal(0)
    if metric == "SALES_AMOUNT":
        raw = Decimal(value) / Decimal(SALES_RIAL_PER_POINT)
        return min(raw, SALES_MAX_MULTIPLIER).quantize(MULTIPLIER_QUANTUM, rounding=ROUND_HALF_UP)
    limit = per_row_cap if per_row_cap is not None else UNCAPPED_COUNT_LIMIT
    return Decimal(min(value, limit))


def stage_title(stage: str) -> str:
    return STAGE_TITLE_FA.get(stage, stage)


__all__ = [
    "DEFAULT_GROWTH_THRESHOLD_RIAL",
    "METRIC_RULES",
    "MVP_OUTPUT_KINDS",
    "PROFILE_FIELDS",
    "VALIDATION_CONTACTS_REQUIRED",
    "Criterion",
    "Readiness",
    "VentureFacts",
    "metric_multiplier",
    "next_growth_stage",
    "readiness",
    "stage_number",
    "stage_title",
]
