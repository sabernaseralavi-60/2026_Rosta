"""موتور تصحیح خودکار — FR-QUIZ-03، وظیفه‌های M4-08 و M4-09.

چهار تای فهرست تست‌های اجباری §13 اینجا هستند (بقیه دیتابیس می‌خواهند
و در `tests/integration/test_quiz_flow.py` آمده‌اند):

* `test_partial_credit_multi_choice`
* `test_persian_short_answer_normalization`
* `test_question_order_stable_across_refresh`
* `test_correct_answers_never_leak_in_active_attempt`
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from silp.domain.quiz import (
    InvalidQuestionPayload,
    QuizAvailability,
    accepts_answer,
    availability,
    compute_expires_at,
    grade_answer,
    grade_attempt,
    needs_manual_grading,
    normalize_answer,
    option_order,
    parse_question,
    public_payload,
    question_order,
    review_payload,
    total_auto_score,
)

ONE = Decimal("1")
TWO = Decimal("2")


def q(kind: str, payload: dict, points: Decimal = ONE, qid: str = "q1"):  # type: ignore[no-untyped-def]
    return parse_question(question_id=qid, kind=kind, points=points, payload=payload)


# ── تک‌گزینه‌ای ────────────────────────────────────────────────────────

SINGLE = {
    "options": [{"id": "a", "text": "پواسون"}, {"id": "b", "text": "دوجمله‌ای منفی"}],
    "correct": ["b"],
}


def test_single_choice_correct_gets_full_points() -> None:
    graded = grade_answer(q("SINGLE_CHOICE", SINGLE, TWO), {"selected": ["b"]})
    assert graded.score == Decimal("2.00")
    assert graded.is_correct is True


def test_single_choice_wrong_gets_zero() -> None:
    graded = grade_answer(q("SINGLE_CHOICE", SINGLE, TWO), {"selected": ["a"]})
    assert graded.score == Decimal("0")
    assert graded.is_correct is False


def test_selecting_two_options_in_single_choice_is_wrong_not_partial() -> None:
    """انتخاب «هر دو» در سؤال تک‌پاسخی، نیمه‌درست نیست."""
    graded = grade_answer(q("SINGLE_CHOICE", SINGLE, TWO), {"selected": ["a", "b"]})
    assert graded.score == Decimal("0")
    assert graded.is_correct is False


def test_unanswered_question_scores_zero() -> None:
    assert grade_answer(q("SINGLE_CHOICE", SINGLE), None).score == Decimal("0")
    assert grade_answer(q("SINGLE_CHOICE", SINGLE), {}).score == Decimal("0")


# ── چندپاسخی با نمرهٔ جزئی — تست اجباری §13 ────────────────────────────

MULTI = {
    "options": [
        {"id": "a", "text": "TTC"},
        {"id": "b", "text": "PET"},
        {"id": "c", "text": "DRAC"},
        {"id": "d", "text": "AADT"},
    ],
    "correct": ["a", "b", "c"],
}


@pytest.mark.parametrize(
    ("selected", "expected"),
    [
        (["a", "b", "c"], Decimal("3.00")),  # هر سه درست
        (["a", "b"], Decimal("2.00")),  # دو از سه
        (["a"], Decimal("1.00")),  # یک از سه
        (["a", "b", "c", "d"], Decimal("2.00")),  # سه درست منهای یک غلط
        (["a", "d"], Decimal("0")),  # یک درست منهای یک غلط
        (["d"], Decimal("0")),  # فقط غلط — کف صفر است، نه منفی
    ],
)
def test_partial_credit_multi_choice(selected: list[str], expected: Decimal) -> None:
    """`max(0, (درست − غلط) / کل درست‌ها) × بارم` — FR-QUIZ-03."""
    graded = grade_answer(q("MULTI_CHOICE", MULTI, Decimal("3")), {"selected": selected})
    assert graded.score == expected


def test_multi_choice_partial_is_neither_correct_nor_wrong() -> None:
    graded = grade_answer(q("MULTI_CHOICE", MULTI, Decimal("3")), {"selected": ["a", "b"]})
    assert graded.is_correct is None
    assert graded.is_partial


def test_multi_choice_penalty_never_goes_below_zero_for_the_question() -> None:
    """جریمهٔ گزینهٔ غلط نمرهٔ سؤال دیگر را نمی‌خورد."""
    graded = grade_answer(q("MULTI_CHOICE", MULTI, Decimal("3")), {"selected": ["d"]})
    assert graded.score == Decimal("0")


# ── درست/نادرست ───────────────────────────────────────────────────────


def test_true_false() -> None:
    question = q("TRUE_FALSE", {"correct": True})
    assert grade_answer(question, {"value": True}).is_correct is True
    assert grade_answer(question, {"value": False}).is_correct is False
    # پاسخ غیرمنطقی، غلط است نه خطا
    assert grade_answer(question, {"value": "بله"}).is_correct is False


# ── پاسخ کوتاه فارسی — تست اجباری §13 ─────────────────────────────────

SHORT = {"accepted": ["دوجمله‌ای منفی", "negative binomial"]}


@pytest.mark.parametrize(
    "given",
    [
        "دوجمله‌ای منفی",  # عیناً
        "دوجمله ای منفی",  # نیم‌فاصله ← فاصله
        "دوجمله‌اي منفي",  # ی عربی
        "  دوجمله‌ای   منفی  ",  # فاصلهٔ اضافی
        "دُوجمله‌ای مَنفی",  # اعراب
        "دوجمله‌ای منفی.",  # نقطهٔ پایانی
    ],
)
def test_persian_short_answer_normalization(given: str) -> None:
    """شش شکلِ یک پاسخ، یک نمره — M4-09."""
    assert grade_answer(q("SHORT_ANSWER", SHORT), {"text": given}).is_correct is True


def test_short_answer_wrong_is_still_wrong() -> None:
    assert grade_answer(q("SHORT_ANSWER", SHORT), {"text": "پواسون"}).is_correct is False


def test_short_answer_matches_any_accepted_form() -> None:
    assert grade_answer(q("SHORT_ANSWER", SHORT), {"text": "Negative Binomial"}).is_correct is True


def test_case_sensitive_short_answer_still_ignores_diacritics() -> None:
    """«حساس به بزرگی و کوچکی» یعنی همان، نه «حساس به اعراب»."""
    question = q("SHORT_ANSWER", {"accepted": ["glm"], "case_sensitive": True})
    assert grade_answer(question, {"text": "GLM"}).is_correct is False
    assert grade_answer(question, {"text": " glm "}).is_correct is True


def test_normalize_keeps_distinct_answers_distinct() -> None:
    assert normalize_answer("پواسون") != normalize_answer("دوجمله‌ای")


# ── عددی ──────────────────────────────────────────────────────────────

NUMERIC = {"correct": 12.5, "tolerance": 0.05, "unit": "km/h"}


@pytest.mark.parametrize(
    ("value", "correct"),
    [
        (12.5, True),
        (12.54, True),  # داخل تحمل
        (12.46, True),
        (12.56, False),  # بیرون تحمل
        ("۱۲٫۵", True),  # ارقام فارسی با ممیز فارسی
        ("12.5", True),
        ("", False),
        ("سیزده", False),
    ],
)
def test_numeric_tolerance(value: object, correct: bool) -> None:
    assert grade_answer(q("NUMERIC", NUMERIC), {"value": value}).is_correct is correct


def test_numeric_without_tolerance_is_exact() -> None:
    question = q("NUMERIC", {"correct": 7})
    assert grade_answer(question, {"value": 7}).is_correct is True
    assert grade_answer(question, {"value": 7.01}).is_correct is False


# ── جورکردنی ──────────────────────────────────────────────────────────

MATCHING = {
    "left": [{"id": "l1", "text": "TTC"}, {"id": "l2", "text": "PET"}],
    "right": [{"id": "r1", "text": "زمان تا تصادف"}, {"id": "r2", "text": "زمان پس از تخطی"}],
    "correct": [["l1", "r1"], ["l2", "r2"]],
}


def test_matching_all_correct() -> None:
    graded = grade_answer(q("MATCHING", MATCHING, TWO), {"pairs": [["l1", "r1"], ["l2", "r2"]]})
    assert graded.score == Decimal("2.00")
    assert graded.is_correct is True


def test_matching_gives_proportional_credit() -> None:
    """ADR-0011 — نیمی از جفت‌ها، نیمی از بارم."""
    graded = grade_answer(q("MATCHING", MATCHING, TWO), {"pairs": [["l1", "r1"], ["l2", "r1"]]})
    assert graded.score == Decimal("1.00")
    assert graded.is_correct is None


def test_matching_all_wrong_scores_zero() -> None:
    graded = grade_answer(q("MATCHING", MATCHING, TWO), {"pairs": [["l1", "r2"], ["l2", "r1"]]})
    assert graded.score == Decimal("0")
    assert graded.is_correct is False


# ── تشریحی ────────────────────────────────────────────────────────────

ESSAY = {"min_words": 50, "max_words": 500, "rubric": "سه معیار"}


def test_essay_goes_to_manual_queue() -> None:
    graded = grade_answer(q("ESSAY", ESSAY, Decimal("5")), {"text": "پاسخ من این است."})
    assert graded.needs_manual
    assert graded.score == Decimal("0")


def test_empty_essay_does_not_enter_the_queue() -> None:
    """صفِ سی پاسخِ خالی، صف واقعی را می‌پوشاند."""
    assert not grade_answer(q("ESSAY", ESSAY), {"text": "   "}).needs_manual
    assert not grade_answer(q("ESSAY", ESSAY), None).needs_manual


# ── جمع‌بندی تلاش ─────────────────────────────────────────────────────


def test_attempt_total_and_provisional_flag() -> None:
    questions = [
        q("SINGLE_CHOICE", SINGLE, TWO, qid="q1"),
        q("MULTI_CHOICE", MULTI, Decimal("3"), qid="q2"),
        q("ESSAY", ESSAY, Decimal("5"), qid="q3"),
    ]
    graded = grade_attempt(
        questions,
        {"q1": {"selected": ["b"]}, "q2": {"selected": ["a", "b"]}, "q3": {"text": "متن"}},
    )
    assert total_auto_score(graded) == Decimal("4.00")
    assert needs_manual_grading(graded)


def test_attempt_without_essay_is_final() -> None:
    graded = grade_attempt([q("SINGLE_CHOICE", SINGLE)], {"q1": {"selected": ["b"]}})
    assert not needs_manual_grading(graded)


def test_unreached_question_is_still_graded() -> None:
    """«بی‌پاسخ» هم یک واقعیت است و باید در کارنامه دیده شود."""
    graded = grade_attempt([q("SINGLE_CHOICE", SINGLE, qid="q9")], {})
    assert graded["q9"].score == Decimal("0")


# ── ترتیب قطعی — تست اجباری §13 ───────────────────────────────────────


# شناسه‌های ثابت، نه `uuid4()`. تابعی که قرار است قطعی باشد، تست قطعی
# می‌خواهد: با شناسهٔ تصادفی، «ترتیب دو سؤال یکی نشود» در چهار گزینه از
# هر ۲۴ اجرا یک بار به‌تصادف شکست می‌خورد و به‌نظر باگ می‌آید.
ATTEMPT_A = uuid.UUID("018f0000-0000-7000-8000-00000000000a")
ATTEMPT_B = uuid.UUID("018f0000-0000-7000-8000-00000000000b")
QUESTION_1 = uuid.UUID("018f0000-0000-7000-8000-000000000011")
QUESTION_2 = uuid.UUID("018f0000-0000-7000-8000-000000000022")
OPTION_IDS = ["a", "b", "c", "d"]
TWENTY_IDS = [uuid.UUID(int=0x018F << 80 | n) for n in range(20)]


def test_question_order_stable_across_refresh() -> None:
    first = question_order(TWENTY_IDS, attempt_id=ATTEMPT_A, shuffle=True)
    second = question_order(TWENTY_IDS, attempt_id=ATTEMPT_A, shuffle=True)
    assert first == second
    assert sorted(first, key=str) == sorted(TWENTY_IDS, key=str)


def test_question_order_differs_between_students() -> None:
    a = question_order(TWENTY_IDS, attempt_id=ATTEMPT_A, shuffle=True)
    b = question_order(TWENTY_IDS, attempt_id=ATTEMPT_B, shuffle=True)
    assert a != b


def test_shuffle_off_keeps_author_order() -> None:
    assert question_order(TWENTY_IDS, attempt_id=ATTEMPT_A, shuffle=False) == TWENTY_IDS


def test_option_order_is_stable_across_refresh() -> None:
    first = option_order(OPTION_IDS, attempt_id=ATTEMPT_A, question_id=QUESTION_1, shuffle=True)
    again = option_order(OPTION_IDS, attempt_id=ATTEMPT_A, question_id=QUESTION_1, shuffle=True)
    assert first == again
    assert sorted(first) == sorted(OPTION_IDS)


def test_option_order_is_scoped_to_the_question() -> None:
    """وگرنه همهٔ سؤال‌های یک تلاش گزینه‌هایشان را به یک الگو جابه‌جا می‌کردند."""
    q1 = option_order(OPTION_IDS, attempt_id=ATTEMPT_A, question_id=QUESTION_1, shuffle=True)
    q2 = option_order(OPTION_IDS, attempt_id=ATTEMPT_A, question_id=QUESTION_2, shuffle=True)
    assert q1 == ("b", "a", "c", "d")
    assert q2 == ("a", "c", "b", "d")


def test_option_order_differs_between_students() -> None:
    a = option_order(OPTION_IDS, attempt_id=ATTEMPT_A, question_id=QUESTION_1, shuffle=True)
    b = option_order(OPTION_IDS, attempt_id=ATTEMPT_B, question_id=QUESTION_1, shuffle=True)
    assert a != b


# ── کلید پاسخ نشت نمی‌کند — تست اجباری §13 ────────────────────────────


@pytest.mark.parametrize(
    ("kind", "payload"),
    [
        ("SINGLE_CHOICE", SINGLE),
        ("MULTI_CHOICE", MULTI),
        ("TRUE_FALSE", {"correct": True}),
        ("SHORT_ANSWER", SHORT),
        ("NUMERIC", NUMERIC),
        ("MATCHING", MATCHING),
        ("ESSAY", ESSAY),
    ],
)
def test_correct_answers_never_leak_in_active_attempt(kind: str, payload: dict) -> None:
    """§5.6 «الزام امنیتی» — هیچ ردی از کلید پاسخ در تلاش فعال."""
    public = public_payload(q(kind, payload))
    flat = repr(public)

    assert "correct" not in public
    assert "accepted" not in public
    assert "tolerance" not in public  # از تحملْ پاسخ حدس زده می‌شود
    # و هیچ مقدار پاسخی هم به‌صورت غیرمستقیم داخل متن نیفتاده باشد
    if kind == "NUMERIC":
        assert "12.5" not in flat
    if kind == "SHORT_ANSWER":
        assert "دوجمله‌ای منفی" not in flat


def test_public_payload_keeps_what_the_student_needs() -> None:
    public = public_payload(q("MULTI_CHOICE", MULTI))
    assert [o["id"] for o in public["options"]] == ["a", "b", "c", "d"]
    assert public["multiple"] is True


def test_public_payload_respects_shuffled_option_order() -> None:
    public = public_payload(q("MULTI_CHOICE", MULTI), option_order=("d", "c", "b", "a"))
    assert [o["id"] for o in public["options"]] == ["d", "c", "b", "a"]


def test_option_added_after_attempt_started_is_not_dropped() -> None:
    """گزینه‌ای که در ترتیب نیست، حذف نمی‌شود — ته فهرست می‌آید."""
    public = public_payload(q("MULTI_CHOICE", MULTI), option_order=("b", "a"))
    assert [o["id"] for o in public["options"]] == ["b", "a", "c", "d"]


def test_review_payload_does_reveal_the_key() -> None:
    review = review_payload(q("SINGLE_CHOICE", SINGLE))
    assert review["correct"] == ["b"]


# ── اعتبارسنجی هنگام نوشتن سؤال ───────────────────────────────────────


@pytest.mark.parametrize(
    ("kind", "payload", "hint"),
    [
        ("SINGLE_CHOICE", {"options": [], "correct": ["a"]}, "ناخالی"),
        ("SINGLE_CHOICE", {**SINGLE, "correct": ["a", "b"]}, "دقیقاً یک"),
        ("SINGLE_CHOICE", {**SINGLE, "correct": ["z"]}, "ناشناخته"),
        ("MULTI_CHOICE", {"options": SINGLE["options"], "correct": ["a", "b"]}, "نمره‌ای نمی‌سنجد"),
        ("TRUE_FALSE", {"correct": "بله"}, "true یا false"),
        ("SHORT_ANSWER", {"accepted": []}, "دست‌کم یک"),
        ("NUMERIC", {"tolerance": 1}, "لازم است"),
        ("NUMERIC", {"correct": 1, "tolerance": -1}, "منفی"),
        ("ESSAY", {"min_words": 100, "max_words": 10}, "بیشتر است"),
        ("MATCHING", {**MATCHING, "correct": [["l1", "r1"], ["l1", "r2"]]}, "بیش از یک جفت"),
    ],
)
def test_bad_payload_is_rejected_at_authoring_time(kind: str, payload: dict, hint: str) -> None:
    with pytest.raises(InvalidQuestionPayload) as exc:
        q(kind, payload)
    assert hint in exc.value.message


def test_unknown_kind_is_rejected() -> None:
    with pytest.raises(InvalidQuestionPayload):
        q("TELEPATHY", {})


def test_duplicate_option_id_is_rejected() -> None:
    with pytest.raises(InvalidQuestionPayload) as exc:
        q(
            "SINGLE_CHOICE",
            {"options": [{"id": "a", "text": "۱"}, {"id": "a", "text": "۲"}], "correct": ["a"]},
        )
    assert "تکراری" in exc.value.message


# ── زمان ──────────────────────────────────────────────────────────────

NOW = datetime(2026, 3, 1, 10, 0, tzinfo=UTC)


def test_expires_at_never_passes_the_quiz_close_time() -> None:
    """شروع پنج دقیقه مانده به پایان، یعنی پنج دقیقه وقت."""
    closes = NOW + timedelta(minutes=5)
    expires = compute_expires_at(started_at=NOW, duration_min=30, closes_at=closes)
    assert expires == closes


def test_expires_at_is_start_plus_duration_when_there_is_room() -> None:
    closes = NOW + timedelta(hours=3)
    expires = compute_expires_at(started_at=NOW, duration_min=30, closes_at=closes)
    assert expires == NOW + timedelta(minutes=30)


@pytest.mark.parametrize(
    ("now", "active", "used", "expected"),
    [
        (NOW - timedelta(hours=1), False, 0, QuizAvailability.NOT_OPEN),
        (NOW + timedelta(hours=5), False, 0, QuizAvailability.CLOSED),
        (NOW + timedelta(minutes=5), True, 1, QuizAvailability.IN_PROGRESS),
        (NOW + timedelta(minutes=5), False, 2, QuizAvailability.EXHAUSTED),
        (NOW + timedelta(minutes=5), False, 1, QuizAvailability.AVAILABLE),
    ],
)
def test_availability(now: datetime, active: bool, used: int, expected: QuizAvailability) -> None:
    result = availability(
        now=now,
        opens_at=NOW,
        closes_at=NOW + timedelta(hours=4),
        has_active_attempt=active,
        used_attempts=used,
        max_attempts=2,
    )
    assert result is expected


def test_active_attempt_wins_over_exhausted() -> None:
    """دانشجویی که آخرین تلاشش را در دست دارد، در را بسته نمی‌بیند."""
    result = availability(
        now=NOW + timedelta(minutes=5),
        opens_at=NOW,
        closes_at=NOW + timedelta(hours=4),
        has_active_attempt=True,
        used_attempts=2,
        max_attempts=2,
    )
    assert result is QuizAvailability.IN_PROGRESS


EXPIRES = NOW + timedelta(minutes=30)


def test_answer_before_expiry_is_accepted() -> None:
    assert accepts_answer(now=EXPIRES - timedelta(seconds=1), expires_at=EXPIRES, client_ts=None)


def test_answer_after_expiry_without_client_ts_is_rejected() -> None:
    assert not accepts_answer(
        now=EXPIRES + timedelta(seconds=5), expires_at=EXPIRES, client_ts=None
    )


def test_late_network_within_grace_is_accepted() -> None:
    """پاسخی که کلاینت سر وقت نوشت و شبکه دیر رساند — §7.3 قاعدهٔ ۳."""
    assert accepts_answer(
        now=EXPIRES + timedelta(seconds=20),
        expires_at=EXPIRES,
        client_ts=EXPIRES - timedelta(seconds=2),
    )


def test_late_network_beyond_grace_is_rejected() -> None:
    assert not accepts_answer(
        now=EXPIRES + timedelta(seconds=45),
        expires_at=EXPIRES,
        client_ts=EXPIRES - timedelta(seconds=2),
    )


def test_client_ts_after_expiry_is_rejected_even_inside_grace() -> None:
    """ادعای «زودتر نوشتمش» باید واقعاً زودتر باشد."""
    assert not accepts_answer(
        now=EXPIRES + timedelta(seconds=5),
        expires_at=EXPIRES,
        client_ts=EXPIRES + timedelta(seconds=1),
    )
