"""موتور تصحیح خودکار — منطق خالص، بدون I/O. PRD FR-QUIZ-03.

وظیفهٔ نقشهٔ راه: M4-08.

**چرا خالص:** نمرهٔ آزمون چیزی است که دانشجو رویش حساب می‌کند و به آن
اعتراض می‌کند. قاعده‌ای که فقط با یک دیتابیس و سی سطر داده قابل آزمون
باشد، عملاً آزمون نمی‌شود. اینجا ورودی یک دیتاکلاس است و خروجی یک عدد؛
هر قاعده مستقیم تست می‌شود.

## قواعد نمره

| نوع | قاعده |
|-----|-------|
| `SINGLE_CHOICE` | درست ⇒ کل بارم، غلط ⇒ صفر |
| `TRUE_FALSE` | همان |
| `MULTI_CHOICE` | `max(0, (درست‌های انتخابی − غلط‌های انتخابی) / کل درست‌ها) × بارم` |
| `SHORT_ANSWER` | تطبیق نرمال‌شده با فهرست پذیرفته |
| `NUMERIC` | `|پاسخ − درست| ≤ tolerance` |
| `MATCHING` | نسبت جفت‌های درست (ADR-0011) |
| `ESSAY` | صف تصحیح دستی |

نمرهٔ منفی وجود ندارد. در `MULTI_CHOICE` جریمهٔ گزینهٔ غلط تا صفرِ
**همان سؤال** پایین می‌آید و نه پایین‌تر؛ یعنی حدس زدن سودی ندارد ولی
نمرهٔ سؤال دیگر را هم نمی‌خورد.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from silp.domain.quiz.normalize import answers_match
from silp.domain.quiz.schemas import (
    SCORE_QUANTUM,
    ZERO,
    GradedAnswer,
    Question,
    QuestionKind,
)


def quantize(value: Decimal) -> Decimal:
    """گرد کردن به دو رقم اعشار — دقت ستون `NUMERIC(5,2)`."""
    return value.quantize(SCORE_QUANTUM, rounding=ROUND_HALF_UP)


def grade_answer(question: Question, response: Mapping[str, Any] | None) -> GradedAnswer:
    """تصحیح یک پاسخ. `response` می‌تواند `None` باشد (بی‌پاسخ)."""
    if question.kind is QuestionKind.ESSAY:
        return _grade_essay(question, response)

    if not response:
        return GradedAnswer(score=ZERO, is_correct=False)

    match question.kind:
        case QuestionKind.SINGLE_CHOICE:
            return _grade_single_choice(question, response)
        case QuestionKind.MULTI_CHOICE:
            return _grade_multi_choice(question, response)
        case QuestionKind.TRUE_FALSE:
            return _grade_true_false(question, response)
        case QuestionKind.SHORT_ANSWER:
            return _grade_short_answer(question, response)
        case QuestionKind.NUMERIC:
            return _grade_numeric(question, response)
        case QuestionKind.MATCHING:
            return _grade_matching(question, response)


# ── تک‌گزینه‌ای و درست/نادرست ───────────────────────────────────────────


def _grade_single_choice(question: Question, response: Mapping[str, Any]) -> GradedAnswer:
    selected = _selected_ids(response)
    # انتخاب دو گزینه در سؤال تک‌پاسخی غلط است، نه «نیمه‌درست».
    correct = len(selected) == 1 and selected == set(question.correct_options)
    return _all_or_nothing(question, correct)


def _grade_true_false(question: Question, response: Mapping[str, Any]) -> GradedAnswer:
    value = response.get("value")
    if not isinstance(value, bool):
        return GradedAnswer(score=ZERO, is_correct=False)
    return _all_or_nothing(question, value is question.correct_boolean)


def _all_or_nothing(question: Question, correct: bool) -> GradedAnswer:
    return GradedAnswer(
        score=quantize(question.points) if correct else ZERO,
        is_correct=correct,
    )


# ── چندپاسخی با نمرهٔ جزئی ─────────────────────────────────────────────


def _grade_multi_choice(question: Question, response: Mapping[str, Any]) -> GradedAnswer:
    selected = _selected_ids(response)
    if not selected:
        return GradedAnswer(score=ZERO, is_correct=False)

    correct_set = set(question.correct_options)
    hits = len(selected & correct_set)
    misses = len(selected - correct_set)
    total_correct = len(correct_set)

    if total_correct == 0:  # pragma: no cover — پارس اجازه نمی‌دهد
        return GradedAnswer(score=ZERO, is_correct=False)

    ratio = Decimal(hits - misses) / Decimal(total_correct)
    ratio = max(ZERO, ratio)
    score = quantize(ratio * question.points)

    if selected == correct_set:
        return GradedAnswer(score=score, is_correct=True)
    if score == ZERO:
        return GradedAnswer(score=ZERO, is_correct=False)
    # نه کامل درست، نه کامل غلط — `is_correct` سه‌حالته برای همین است.
    return GradedAnswer(score=score, is_correct=None)


def _selected_ids(response: Mapping[str, Any]) -> set[str]:
    raw = response.get("selected")
    if isinstance(raw, str):
        return {raw}
    if isinstance(raw, Iterable):
        return {str(item) for item in raw}
    return set()


# ── پاسخ کوتاه ─────────────────────────────────────────────────────────


def _grade_short_answer(question: Question, response: Mapping[str, Any]) -> GradedAnswer:
    given = response.get("text")
    if not isinstance(given, str) or not given.strip():
        return GradedAnswer(score=ZERO, is_correct=False)
    correct = any(
        answers_match(given, accepted, case_sensitive=question.case_sensitive)
        for accepted in question.accepted
    )
    return _all_or_nothing(question, correct)


# ── عددی ───────────────────────────────────────────────────────────────


def _grade_numeric(question: Question, response: Mapping[str, Any]) -> GradedAnswer:
    given = _to_decimal(response.get("value"))
    if given is None or question.correct_number is None:
        return GradedAnswer(score=ZERO, is_correct=False)
    correct = abs(given - question.correct_number) <= question.tolerance
    return _all_or_nothing(question, correct)


def _to_decimal(value: Any) -> Decimal | None:
    """عدد دانشجو — که ممکن است رشته، با رقم فارسی، یا خالی باشد."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int | float):
        return Decimal(str(value))
    if isinstance(value, str):
        from silp.domain.identity.normalize import to_latin_digits

        text = to_latin_digits(value.strip()).replace("٫", ".").replace(",", "")
        if not text:
            return None
        try:
            return Decimal(text)
        except InvalidOperation:
            return None
    return None


# ── جورکردنی ───────────────────────────────────────────────────────────


def _grade_matching(question: Question, response: Mapping[str, Any]) -> GradedAnswer:
    given = _given_pairs(response)
    expected = {p.left: p.right for p in question.correct_pairs}
    if not expected:  # pragma: no cover — پارس اجازه نمی‌دهد
        return GradedAnswer(score=ZERO, is_correct=False)

    hits = sum(1 for left, right in given.items() if expected.get(left) == right)
    ratio = Decimal(hits) / Decimal(len(expected))
    score = quantize(ratio * question.points)

    if hits == len(expected) and len(given) == len(expected):
        return GradedAnswer(score=score, is_correct=True)
    if hits == 0:
        return GradedAnswer(score=ZERO, is_correct=False)
    return GradedAnswer(score=score, is_correct=None)


def _given_pairs(response: Mapping[str, Any]) -> dict[str, str]:
    raw = response.get("pairs")
    if not isinstance(raw, Iterable) or isinstance(raw, str | bytes):
        return {}
    pairs: dict[str, str] = {}
    for item in raw:
        if isinstance(item, list | tuple) and len(item) == 2:
            pairs[str(item[0])] = str(item[1])
    return pairs


# ── تشریحی ─────────────────────────────────────────────────────────────


def _grade_essay(question: Question, response: Mapping[str, Any] | None) -> GradedAnswer:
    """تشریحی به صف استاد می‌رود — مگر خالی باشد.

    پاسخ خالی به صف نمی‌رود: چیزی برای خواندن نیست و صفِ سی پاسخِ خالی،
    صف واقعی را می‌پوشاند. نمره‌اش صفر است و استاد در بازبینی می‌تواند
    دستی بازنویسی کند (FR-QUIZ-03).
    """
    text = response.get("text") if response else None
    if not isinstance(text, str) or not text.strip():
        return GradedAnswer(score=ZERO, is_correct=False, needs_manual=False)
    return GradedAnswer(score=ZERO, is_correct=None, needs_manual=True)


# ── جمع‌بندی یک تلاش ───────────────────────────────────────────────────


def grade_attempt(
    questions: Iterable[Question],
    responses: Mapping[str, Mapping[str, Any] | None],
) -> dict[str, GradedAnswer]:
    """تصحیح همهٔ سؤال‌های یک تلاش.

    سؤالی که دانشجو اصلاً به آن نرسیده هم تصحیح می‌شود (با پاسخ `None`)
    تا نمرهٔ هر سؤال در نتیجه وجود داشته باشد؛ «بی‌پاسخ» هم یک واقعیت
    است و باید در کارنامه دیده شود.
    """
    return {q.id: grade_answer(q, responses.get(q.id)) for q in questions}


def total_auto_score(graded: Mapping[str, GradedAnswer]) -> Decimal:
    return quantize(sum((g.score for g in graded.values()), ZERO))


def needs_manual_grading(graded: Mapping[str, GradedAnswer]) -> bool:
    """آیا نمره تا تصحیح دستی «موقت» است؟ — §7.3."""
    return any(g.needs_manual for g in graded.values())


__all__ = [
    "grade_answer",
    "grade_attempt",
    "needs_manual_grading",
    "quantize",
    "total_auto_score",
]
