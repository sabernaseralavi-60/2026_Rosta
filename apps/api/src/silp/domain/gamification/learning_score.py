"""نمرهٔ یادگیری (Learning Score) — PRD §9.6، M5-06. منطق خالص.

```
LS = 100 × ( 0.40 × Q + 0.25 × S + 0.20 × P + 0.15 × A )
```

| نماد | مؤلفه | ورودی |
|------|-------|-------|
| `Q` | آزمون | `Σ نمره / Σ کل` آزمون‌های در شمار (میانگین وزنی به بارم) |
| `S` | مطالعه | منابع الزامی تکمیل‌شده / منابع الزامی هفته‌های منتشرشده |
| `P` | پروژه | مراحل الزامی تأییدشده / مراحل الزامی پروژه‌های متصل به ارائه |
| `A` | حضور | `(PRESENT + 0.5×LATE + EXCUSED) / کل جلسات` |

دو قاعدهٔ انصاف §9.6 اینجا اعمال می‌شوند، نه در سرویس:

* **مخرج فقط محتوای منتشرشده است** — سرویس فقط همان را می‌شمارد و این
  ماژول کسری با مخرج صفر را «مؤلفهٔ غایب» می‌داند، نه «صفر».
* **مؤلفهٔ غایب وزنش صفر می‌شود و بقیه بازنرمال می‌شوند.** درسی بدون
  حضور و غیاب، نمرهٔ دانشجو را به‌خاطر نبودِ حضور پایین نمی‌آورد.

## وزن‌ها و `grading_policy`

`course_offerings.grading_policy` کلیدهای `quiz`، `project`، `attendance`
و `participation` دارد (§4.4، جمع ۱۰۰). `participation` وزن **مطالعه** (`S`)
است — تنها مشارکتی که سامانه تا این مرحله می‌سنجد، مطالعهٔ منابع است
(ADR-0012). سیاست خالی یعنی وزن‌های پیش‌فرض §9.6.

این عدد **پیشنهاد است، نه نمره** (§9.6): هرگز خودکار در
`enrollments.final_grade` نوشته نمی‌شود.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

COMPONENTS = ("quiz", "study", "project", "attendance")

COMPONENT_TITLE_FA: dict[str, str] = {
    "quiz": "آزمون",
    "study": "مطالعه",
    "project": "پروژه",
    "attendance": "حضور",
}

DEFAULT_WEIGHTS: dict[str, Decimal] = {
    "quiz": Decimal("40"),
    "study": Decimal("25"),
    "project": Decimal("20"),
    "attendance": Decimal("15"),
}

#: کلید `grading_policy` ← مؤلفه. `participation` همان مطالعه است (ADR-0012).
POLICY_KEY_TO_COMPONENT: dict[str, str] = {
    "quiz": "quiz",
    "participation": "study",
    "project": "project",
    "attendance": "attendance",
}

#: `LS × 0.2` — «اعمال به‌عنوان نمرهٔ پیشنهادی» روی مقیاس ۲۰ (§9.6).
FINAL_GRADE_SCALE = Decimal("0.2")

SCORE_QUANTUM = Decimal("0.1")
RATIO_QUANTUM = Decimal("0.0001")


@dataclass(frozen=True, slots=True)
class Fraction:
    """یک مؤلفه به‌صورت صورت/مخرج. مخرج صفر یعنی مؤلفه در این ارائه نیست."""

    earned: Decimal
    possible: Decimal

    @property
    def is_present(self) -> bool:
        return self.possible > 0

    @property
    def ratio(self) -> Decimal:
        if not self.is_present:
            return Decimal(0)
        value = min(max(self.earned / self.possible, Decimal(0)), Decimal(1))
        return value.quantize(RATIO_QUANTUM, rounding=ROUND_HALF_UP)


@dataclass(frozen=True, slots=True)
class LearningInputs:
    quiz: Fraction
    study: Fraction
    project: Fraction
    attendance: Fraction

    def get(self, component: str) -> Fraction:
        value: Fraction = getattr(self, component)
        return value


@dataclass(frozen=True, slots=True)
class ComponentScore:
    key: str
    title_fa: str
    ratio: Decimal | None
    weight: Decimal
    """وزن مؤثر پس از بازنرمال‌سازی، از ۱۰۰. مؤلفهٔ غایب صفر است."""


@dataclass(frozen=True, slots=True)
class LearningScore:
    score: Decimal | None
    """۰ تا ۱۰۰، یا `None` وقتی هیچ مؤلفه‌ای هنوز وجود ندارد."""
    components: tuple[ComponentScore, ...]

    @property
    def suggested_grade(self) -> Decimal | None:
        """نمرهٔ پیشنهادی از ۲۰ — فقط پیشنهاد؛ استاد تأیید می‌کند."""
        if self.score is None:
            return None
        return (self.score * FINAL_GRADE_SCALE).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def weights_from_policy(policy: Mapping[str, object] | None) -> dict[str, Decimal]:
    """وزن هر مؤلفه از `grading_policy`. سیاست خالی یا نامعتبر ⇒ پیش‌فرض."""
    if not policy:
        return dict(DEFAULT_WEIGHTS)
    weights = {component: Decimal(0) for component in COMPONENTS}
    for key, value in policy.items():
        component = POLICY_KEY_TO_COMPONENT.get(key)
        if component is None or isinstance(value, bool) or not isinstance(value, int | float):
            continue
        weights[component] = max(Decimal(str(value)), Decimal(0))
    if sum(weights.values()) <= 0:
        return dict(DEFAULT_WEIGHTS)
    return weights


def compute(inputs: LearningInputs, weights: Mapping[str, Decimal]) -> LearningScore:
    active = {
        c: weights.get(c, Decimal(0))
        for c in COMPONENTS
        if inputs.get(c).is_present and weights.get(c, Decimal(0)) > 0
    }
    total_weight = sum(active.values(), Decimal(0))

    components = tuple(
        ComponentScore(
            key=c,
            title_fa=COMPONENT_TITLE_FA[c],
            ratio=inputs.get(c).ratio if inputs.get(c).is_present else None,
            weight=(
                (active[c] * 100 / total_weight).quantize(SCORE_QUANTUM, rounding=ROUND_HALF_UP)
                if c in active
                else Decimal(0)
            ),
        )
        for c in COMPONENTS
    )
    if total_weight <= 0:
        return LearningScore(score=None, components=components)

    weighted = sum((inputs.get(c).ratio * w for c, w in active.items()), Decimal(0))
    score = (weighted * 100 / total_weight).quantize(SCORE_QUANTUM, rounding=ROUND_HALF_UP)
    return LearningScore(score=score, components=components)


__all__ = [
    "COMPONENTS",
    "COMPONENT_TITLE_FA",
    "DEFAULT_WEIGHTS",
    "ComponentScore",
    "Fraction",
    "LearningInputs",
    "LearningScore",
    "compute",
    "weights_from_policy",
]
