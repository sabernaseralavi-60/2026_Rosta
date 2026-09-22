"""پارس و اعتبارسنجی `payload` سؤال — منطق خالص. PRD §4.5.

سه کار اینجا انجام می‌شود و هر سه یک موضوع دارند: **کلید پاسخ نباید
جایی برود که نباید.**

| تابع | کِی | چه چیزی بیرون می‌دهد |
|------|-----|------------------------|
| `parse_question` | تصحیح، و هنگام ذخیرهٔ سؤال | همه چیز، با کلید پاسخ |
| `public_payload` | تلاش فعالِ دانشجو | گزینه‌ها بدون `correct` |
| `review_payload` | پس از انتشار نتیجه | با کلید پاسخ و توضیح |

`public_payload` **allow-list** است، نه حذف چند کلید از دیکشنری خام.
فرق این دو وقتی معلوم می‌شود که کسی فردا کلید تازه‌ای به `payload`
بیفزاید: با حذف، کلید تازه بی‌صدا به دانشجو می‌رسد؛ با allow-list،
نمی‌رسد مگر کسی عمداً اضافه‌اش کند. §5.6 این را «الزام امنیتی» نامیده
و `test_correct_answers_never_leak_in_active_attempt` نگهبانش است.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from silp.domain.quiz.schemas import MatchPair, Option, Question, QuestionKind

MAX_OPTIONS = 12
MAX_ACCEPTED_ANSWERS = 20
MAX_MATCH_PAIRS = 12


class InvalidQuestionPayload(ValueError):
    """`payload` با `kind` نمی‌خواند — خطای نویسندهٔ سؤال، نه دانشجو."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise InvalidQuestionPayload(message)


def _as_decimal(value: Any, field: str) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise InvalidQuestionPayload(f"مقدار «{field}» عدد نیست.") from exc


def _parse_options(raw: Any, field: str) -> tuple[Option, ...]:
    _require(isinstance(raw, list) and bool(raw), f"«{field}» باید فهرستی ناخالی باشد.")
    _require(len(raw) <= MAX_OPTIONS, f"«{field}» بیش از {MAX_OPTIONS} مورد دارد.")

    options: list[Option] = []
    seen: set[str] = set()
    for item in raw:
        _require(isinstance(item, dict), f"هر مورد «{field}» باید شیء باشد.")
        option_id = item.get("id")
        text = item.get("text")
        _require(
            isinstance(option_id, str) and bool(option_id.strip()),
            f"هر مورد «{field}» باید `id` متنی داشته باشد.",
        )
        _require(isinstance(text, str), f"هر مورد «{field}» باید `text` متنی داشته باشد.")
        _require(option_id not in seen, f"شناسهٔ «{option_id}» در «{field}» تکراری است.")
        seen.add(option_id)
        options.append(Option(id=option_id, text=text))
    return tuple(options)


def _parse_correct_ids(raw: Any, valid: set[str], *, exactly_one: bool) -> frozenset[str]:
    _require(isinstance(raw, list), "«correct» باید فهرست شناسهٔ گزینه باشد.")
    ids = {str(item) for item in raw}
    _require(bool(ids), "دست‌کم یک گزینهٔ درست لازم است.")
    unknown = ids - valid
    _require(not unknown, f"گزینهٔ درستِ ناشناخته: {'، '.join(sorted(unknown))}.")
    if exactly_one:
        _require(len(ids) == 1, "سؤال «یک پاسخ» باید دقیقاً یک گزینهٔ درست داشته باشد.")
    return frozenset(ids)


def parse_question(
    *,
    question_id: str,
    kind: str,
    points: Decimal,
    payload: dict[str, Any],
) -> Question:
    """`payload` خام را به یک `Question` تایپ‌دار تبدیل می‌کند."""
    try:
        parsed_kind = QuestionKind(kind)
    except ValueError as exc:
        raise InvalidQuestionPayload(f"نوع سؤال «{kind}» شناخته نیست.") from exc

    _require(isinstance(payload, dict), "`payload` باید شیء باشد.")
    base = {"question_id": question_id, "kind": parsed_kind, "points": points}

    match parsed_kind:
        case QuestionKind.SINGLE_CHOICE | QuestionKind.MULTI_CHOICE:
            options = _parse_options(payload.get("options"), "options")
            correct = _parse_correct_ids(
                payload.get("correct"),
                {o.id for o in options},
                exactly_one=parsed_kind is QuestionKind.SINGLE_CHOICE,
            )
            _require(
                len(correct) < len(options),
                "همهٔ گزینه‌ها درست‌اند؛ چنین سؤالی نمره‌ای نمی‌سنجد.",
            )
            return _build(base, options=options, correct_options=correct)

        case QuestionKind.TRUE_FALSE:
            correct_value = payload.get("correct")
            _require(isinstance(correct_value, bool), "«correct» باید true یا false باشد.")
            return _build(base, correct_boolean=bool(correct_value))

        case QuestionKind.SHORT_ANSWER:
            raw_accepted = payload.get("accepted")
            if not isinstance(raw_accepted, list) or not raw_accepted:
                raise InvalidQuestionPayload("«accepted» باید دست‌کم یک پاسخ پذیرفته داشته باشد.")
            _require(
                len(raw_accepted) <= MAX_ACCEPTED_ANSWERS,
                f"بیش از {MAX_ACCEPTED_ANSWERS} پاسخ پذیرفته مجاز نیست.",
            )
            accepted = tuple(str(item) for item in raw_accepted)
            _require(all(item.strip() for item in accepted), "پاسخ پذیرفتهٔ خالی مجاز نیست.")
            return _build(
                base,
                accepted=accepted,
                case_sensitive=bool(payload.get("case_sensitive", False)),
            )

        case QuestionKind.NUMERIC:
            _require("correct" in payload, "«correct» برای سؤال عددی لازم است.")
            correct_number = _as_decimal(payload["correct"], "correct")
            tolerance = _as_decimal(payload.get("tolerance", 0), "tolerance")
            _require(tolerance >= 0, "«tolerance» نمی‌تواند منفی باشد.")
            unit = payload.get("unit")
            _require(unit is None or isinstance(unit, str), "«unit» باید متن باشد.")
            return _build(
                base, correct_number=correct_number, tolerance=tolerance, unit=unit or None
            )

        case QuestionKind.MATCHING:
            left = _parse_options(payload.get("left"), "left")
            right = _parse_options(payload.get("right"), "right")
            pairs = _parse_pairs(
                payload.get("correct"), {o.id for o in left}, {o.id for o in right}
            )
            return _build(base, left_items=left, right_items=right, correct_pairs=pairs)

        case QuestionKind.ESSAY:
            min_words = payload.get("min_words")
            max_words = payload.get("max_words")
            for name, value in (("min_words", min_words), ("max_words", max_words)):
                _require(
                    value is None or (isinstance(value, int) and value > 0),
                    f"«{name}» باید عدد صحیح مثبت باشد.",
                )
            if isinstance(min_words, int) and isinstance(max_words, int):
                _require(min_words <= max_words, "«min_words» از «max_words» بیشتر است.")
            rubric = payload.get("rubric")
            _require(rubric is None or isinstance(rubric, str), "«rubric» باید متن باشد.")
            return _build(base, min_words=min_words, max_words=max_words, rubric=rubric or None)

    raise InvalidQuestionPayload(f"نوع سؤال «{kind}» پشتیبانی نمی‌شود.")  # pragma: no cover


def _parse_pairs(raw: Any, left_ids: set[str], right_ids: set[str]) -> tuple[MatchPair, ...]:
    _require(isinstance(raw, list) and bool(raw), "«correct» باید فهرست جفت‌ها باشد.")
    _require(len(raw) <= MAX_MATCH_PAIRS, f"بیش از {MAX_MATCH_PAIRS} جفت مجاز نیست.")

    pairs: list[MatchPair] = []
    used_left: set[str] = set()
    for item in raw:
        _require(
            isinstance(item, list | tuple) and len(item) == 2,
            "هر جفت باید دقیقاً دو شناسه داشته باشد.",
        )
        left, right = str(item[0]), str(item[1])
        _require(left in left_ids, f"شناسهٔ سمت راست «{left}» ناشناخته است.")
        _require(right in right_ids, f"شناسهٔ سمت چپ «{right}» ناشناخته است.")
        # یک مورد سمت راست می‌تواند به چند مورد وصل باشد، ولی یک مورد
        # سمت چپ دو پاسخ درست ندارد — وگرنه نمرهٔ جزئی بی‌معنا می‌شود.
        _require(left not in used_left, f"برای «{left}» بیش از یک جفت درست تعریف شده است.")
        used_left.add(left)
        pairs.append(MatchPair(left=left, right=right))
    return tuple(pairs)


def _build(base: dict[str, Any], **fields: Any) -> Question:
    return Question(
        id=str(base["question_id"]),
        kind=base["kind"],
        points=base["points"],
        **fields,
    )


def validate_payload(kind: str, payload: dict[str, Any], *, points: Decimal) -> None:
    """اعتبارسنجی هنگام ذخیرهٔ سؤال. خطا یعنی سؤال ذخیره نمی‌شود."""
    parse_question(question_id="validate", kind=kind, points=points, payload=payload)


# ── آنچه دانشجو در تلاش فعال می‌بیند ───────────────────────────────────


def public_payload(
    question: Question, *, option_order: tuple[str, ...] | None = None
) -> dict[str, Any]:
    """`payload` بدون کلید پاسخ — §5.6 «الزام امنیتی».

    `option_order` ترتیب درهم‌شدهٔ همین تلاش است. اگر داده نشود، ترتیب
    تعریف استاد می‌ماند (وقتی `shuffle_options` خاموش است).
    """
    match question.kind:
        case QuestionKind.SINGLE_CHOICE | QuestionKind.MULTI_CHOICE:
            options = _ordered(question.options, option_order)
            return {
                "options": [{"id": o.id, "text": o.text} for o in options],
                "multiple": question.kind is QuestionKind.MULTI_CHOICE,
            }

        case QuestionKind.TRUE_FALSE:
            return {}

        case QuestionKind.SHORT_ANSWER:
            return {"case_sensitive": question.case_sensitive}

        case QuestionKind.NUMERIC:
            # `tolerance` هم بیرون نمی‌رود: از آن می‌شود پاسخ را حدس زد.
            return {"unit": question.unit}

        case QuestionKind.MATCHING:
            return {
                "left": [{"id": o.id, "text": o.text} for o in question.left_items],
                "right": [
                    {"id": o.id, "text": o.text}
                    for o in _ordered(question.right_items, option_order)
                ],
            }

        case QuestionKind.ESSAY:
            return {
                "min_words": question.min_words,
                "max_words": question.max_words,
                "rubric": question.rubric,
            }


def _ordered(options: tuple[Option, ...], order: tuple[str, ...] | None) -> tuple[Option, ...]:
    if not order:
        return options
    by_id = {o.id: o for o in options}
    ordered = tuple(by_id[oid] for oid in order if oid in by_id)
    # هر گزینه‌ای که در ترتیب نیامده (سؤال پس از شروع تلاش ویرایش شده)
    # حذف نمی‌شود؛ ته فهرست می‌آید. حذفش یعنی دانشجو گزینه‌ای را که
    # نمره دارد اصلاً نبیند.
    missing = tuple(o for o in options if o.id not in set(order))
    return ordered + missing


# ── آنچه پس از انتشار نتیجه دیده می‌شود ────────────────────────────────


def review_payload(question: Question) -> dict[str, Any]:
    """`payload` همراه کلید پاسخ — فقط وقتی `show_correct_answers` روشن
    است و نتیجه منتشر شده (FR-QUIZ-04)."""
    data = public_payload(question)
    match question.kind:
        case QuestionKind.SINGLE_CHOICE | QuestionKind.MULTI_CHOICE:
            data["correct"] = sorted(question.correct_options)
        case QuestionKind.TRUE_FALSE:
            data["correct"] = question.correct_boolean
        case QuestionKind.SHORT_ANSWER:
            data["accepted"] = list(question.accepted)
        case QuestionKind.NUMERIC:
            data["correct"] = str(question.correct_number)
            data["tolerance"] = str(question.tolerance)
        case QuestionKind.MATCHING:
            data["correct"] = [[p.left, p.right] for p in question.correct_pairs]
        case QuestionKind.ESSAY:
            pass
    return data


__all__ = [
    "InvalidQuestionPayload",
    "parse_question",
    "public_payload",
    "review_payload",
    "validate_payload",
]
