"""ساختارهای دادهٔ آزمون — بدون رفتار، بدون I/O. PRD §4.5.

`payload` هر سؤال در دیتابیس `JSONB` است و شکلش به `kind` بستگی دارد.
این ماژول آن شکل‌ها را صریح می‌کند تا موتور تصحیح با `dict` خام کار
نکند: یک بار در مرز پارس می‌شود، بعد همه‌جا تایپ‌دار است.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum


class QuestionKind(StrEnum):
    """هفت نوع سؤال §4.5. با `CHECK` ستون `kind` یکسان است."""

    SINGLE_CHOICE = "SINGLE_CHOICE"
    MULTI_CHOICE = "MULTI_CHOICE"
    TRUE_FALSE = "TRUE_FALSE"
    SHORT_ANSWER = "SHORT_ANSWER"
    NUMERIC = "NUMERIC"
    ESSAY = "ESSAY"
    MATCHING = "MATCHING"


#: نوع‌هایی که سرور می‌تواند خودش تصحیح کند — FR-QUIZ-03.
AUTO_GRADED_KINDS: frozenset[QuestionKind] = frozenset(
    {
        QuestionKind.SINGLE_CHOICE,
        QuestionKind.MULTI_CHOICE,
        QuestionKind.TRUE_FALSE,
        QuestionKind.SHORT_ANSWER,
        QuestionKind.NUMERIC,
        QuestionKind.MATCHING,
    }
)

#: نوع‌هایی که گزینه دارند و ترتیب گزینه‌هایشان درهم می‌شود.
CHOICE_KINDS: frozenset[QuestionKind] = frozenset(
    {QuestionKind.SINGLE_CHOICE, QuestionKind.MULTI_CHOICE}
)

QUESTION_KIND_TITLE_FA: dict[QuestionKind, str] = {
    QuestionKind.SINGLE_CHOICE: "چندگزینه‌ای — یک پاسخ",
    QuestionKind.MULTI_CHOICE: "چندگزینه‌ای — چند پاسخ",
    QuestionKind.TRUE_FALSE: "درست/نادرست",
    QuestionKind.SHORT_ANSWER: "پاسخ کوتاه",
    QuestionKind.NUMERIC: "عددی",
    QuestionKind.ESSAY: "تشریحی",
    QuestionKind.MATCHING: "جورکردنی",
}

#: دقت ذخیره‌سازی نمره — `NUMERIC(5,2)` در §4.5.
SCORE_QUANTUM = Decimal("0.01")

ZERO = Decimal("0")


@dataclass(frozen=True, slots=True)
class Option:
    """یک گزینه از سؤال چندگزینه‌ای."""

    id: str
    text: str


@dataclass(frozen=True, slots=True)
class MatchPair:
    """یک جفت درست در سؤال جورکردنی."""

    left: str
    right: str


@dataclass(frozen=True, slots=True)
class Question:
    """یک سؤال، آن‌طور که موتور تصحیح می‌بیند.

    `payload` خام دیگر اینجا نیست: هر آنچه تصحیح لازم دارد، فیلد صریح
    است. این یعنی یک سؤال نیمه‌ساخته در مرز پارس رد می‌شود، نه وسط
    تصحیحِ سی دانشجو.
    """

    id: str
    kind: QuestionKind
    points: Decimal

    # ── چندگزینه‌ای ──────────────────────────────────────────────────
    options: tuple[Option, ...] = ()
    correct_options: frozenset[str] = frozenset()

    # ── درست/نادرست ─────────────────────────────────────────────────
    correct_boolean: bool | None = None

    # ── پاسخ کوتاه ──────────────────────────────────────────────────
    accepted: tuple[str, ...] = ()
    case_sensitive: bool = False

    # ── عددی ────────────────────────────────────────────────────────
    correct_number: Decimal | None = None
    tolerance: Decimal = ZERO
    unit: str | None = None

    # ── جورکردنی ────────────────────────────────────────────────────
    left_items: tuple[Option, ...] = ()
    right_items: tuple[Option, ...] = ()
    correct_pairs: tuple[MatchPair, ...] = ()

    # ── تشریحی ──────────────────────────────────────────────────────
    min_words: int | None = None
    max_words: int | None = None
    rubric: str | None = None

    @property
    def is_auto_graded(self) -> bool:
        return self.kind in AUTO_GRADED_KINDS


@dataclass(frozen=True, slots=True)
class GradedAnswer:
    """نتیجهٔ تصحیح یک پاسخ.

    `is_correct` سه‌حالته است و این عمدی است:

    * `True`  — کامل درست
    * `False` — کامل غلط
    * `None`  — قضاوت نشده (تشریحی، یا نمرهٔ جزئی که نه این است نه آن)

    اگر دو‌حالته بود، «۰.۶ از ۱» مجبور بود یکی از دو دروغ را بگوید.
    """

    score: Decimal
    is_correct: bool | None
    needs_manual: bool = False

    @property
    def is_partial(self) -> bool:
        return self.is_correct is None and not self.needs_manual


__all__ = [
    "AUTO_GRADED_KINDS",
    "CHOICE_KINDS",
    "QUESTION_KIND_TITLE_FA",
    "SCORE_QUANTUM",
    "GradedAnswer",
    "MatchPair",
    "Option",
    "Question",
    "QuestionKind",
]
