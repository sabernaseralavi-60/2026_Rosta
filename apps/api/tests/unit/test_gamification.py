"""منطق خالص گیمیفیکیشن — سطح، فرمول‌ها، معیار نشان، نمرهٔ یادگیری.

مرجع: PRD §9.2 تا §9.6، ADR-0012. هیچ تستی اینجا دیتابیس نمی‌خواهد.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from silp.domain.gamification import formulas
from silp.domain.gamification.badges import (
    BadgeFacts,
    InvalidCriteria,
    evaluate,
    longest_weekly_streak,
    validate,
)
from silp.domain.gamification.learning_score import (
    Fraction,
    LearningInputs,
    compute,
    weights_from_policy,
)
from silp.domain.gamification.levels import level_for, progress, threshold, title_for

D = Decimal


# ── سطح — §9.4 ─────────────────────────────────────────────────────────
#: جدول §9.4 — مرجع تست. اصلاح‌شده در ADR-0012 تا با فرمول بخواند.
LEVEL_TABLE = {
    1: 0,
    2: 50,
    3: 152,
    4: 290,
    5: 459,
    6: 657,
    7: 879,
    8: 1125,
    9: 1393,
    10: 1682,
    12: 2318,
    15: 3410,
    20: 5559,
}


def test_level_thresholds_match_table() -> None:
    """§9.4 — «باید دقیقاً همین اعداد را از فرمول تولید کند»."""
    assert {n: threshold(n) for n in LEVEL_TABLE} == LEVEL_TABLE


@pytest.mark.parametrize(
    ("total", "level"),
    [(0, 1), (49, 1), (50, 2), (151, 2), (152, 3), (340, 4), (5559, 20), (-30, 1)],
)
def test_level_for_boundaries(total: int, level: int) -> None:
    assert level_for(total) == level


def test_progress_shows_points_to_next_level() -> None:
    """«۱۳۰ امتیاز تا سطح بعد» — نه فقط عدد خام (§9.4)."""
    p = progress(340)
    assert (p.level, p.current_at, p.next_at, p.to_next) == (4, 290, 459, D(119))
    assert D(0) < p.ratio < D(1)


def test_intermediate_levels_keep_the_last_named_title() -> None:
    assert title_for(10) == "معمار"
    assert title_for(11) == "معمار"
    assert title_for(12) == "استاد کار"


# ── فرمول‌ها — §9.2، §9.3 ───────────────────────────────────────────────
def test_difficulty_factor_spans_the_documented_range() -> None:
    assert formulas.difficulty_factor(1) == D("0.85")
    assert formulas.difficulty_factor(5) == D("1.45")


def test_personal_project_completion_is_halved() -> None:
    """§9.8 — پروژهٔ شخصی خودتأییدی نصف امتیاز تکمیل می‌گیرد."""
    research = formulas.project_completion_multiplier(kind="B_RESEARCH", difficulty=3)
    personal = formulas.project_completion_multiplier(kind="D_PERSONAL", difficulty=3)
    assert personal * 2 == research == D("1.15")


def test_project_kind_decides_the_category() -> None:
    assert formulas.category_for_project("A_VENTURE") == "STARTUP"
    assert formulas.category_for_project("B_RESEARCH") == "RESEARCH"
    assert formulas.category_for_project("C_PROBLEM") == "LEARNING"


def test_late_and_early_factors_never_stack() -> None:
    due = date(2026, 10, 10)
    late = formulas.adjustment_factors(
        is_late=True,
        submitted_on=date(2026, 10, 1),  # «زود» به تاریخ، ولی عکسِ لحظهٔ ارسال می‌گوید دیر
        due_on=due,
        had_changes_requested=False,
        rubric_scores=None,
    )
    assert late == [("تحویل با تأخیر", D("0.70"))]

    early = formulas.adjustment_factors(
        is_late=False,
        submitted_on=due - timedelta(days=3),
        due_on=due,
        had_changes_requested=False,
        rubric_scores=None,
    )
    assert early == [("تحویل زودهنگام", D("1.05"))]


def test_all_adjustments_multiply() -> None:
    """`amount = base × difficulty × Π adjustments` — §9.3."""
    factors = formulas.adjustment_factors(
        is_late=True,
        submitted_on=date(2026, 10, 12),
        due_on=date(2026, 10, 10),
        had_changes_requested=True,
        rubric_scores={"completeness": 5, "quality": 4.5, "note": "عالی"},
    )
    assert [f for _, f in factors] == [D("0.70"), D("0.85"), D("1.20")]
    assert formulas.milestone_multiplier(D(100), factors) == D("71.4000")
    assert (
        formulas.factors_note(factors)
        == "تحویل با تأخیر ×0.7، نیاز به اصلاح ×0.85، کیفیت بالا ×1.2"
    )


def test_rubric_average_ignores_non_numeric_and_out_of_range() -> None:
    assert formulas.rubric_average({"a": 5, "b": "4", "c": True, "d": 9, "e": "خوب"}) == D("4.5")
    assert formulas.rubric_average({}) is None


def test_quiz_score_ratio_is_clamped() -> None:
    assert formulas.score_ratio(D(15), D(20)) == D("0.7500")
    assert formulas.score_ratio(D(25), D(20)) == D(1)
    assert formulas.score_ratio(D(5), D(0)) == D(0)


def test_pass_falls_back_to_half_when_no_passing_score() -> None:
    assert formulas.passed(D(10), D(20), None)
    assert not formulas.passed(D("9.99"), D(20), None)
    assert formulas.passed(D(12), D(20), D(12))


def test_amount_is_capped_to_the_column() -> None:
    assert formulas.amount_of(D(1), D("12000")) == D("9999.99")


@pytest.mark.parametrize(
    ("statuses", "closes"),
    [
        (["PRESENT"] * 8, [3, 7]),
        (["PRESENT", "LATE", "PRESENT", "PRESENT"], [3]),
        (["PRESENT", "PRESENT", "ABSENT", "PRESENT", "PRESENT", "PRESENT", "PRESENT"], [6]),
        (["PRESENT", "PRESENT", None, "PRESENT", "PRESENT"], []),
        (["PRESENT", "EXCUSED", "PRESENT", "PRESENT", "PRESENT"], []),
    ],
)
def test_attendance_streak_counts_each_session_once(
    statuses: list[str | None], closes: list[int]
) -> None:
    """§9.2 — ۴ جلسهٔ پیاپی بدون غیبت؛ هشت حضور دو پاداش است، نه پنج."""
    assert formulas.streak_completions(statuses) == closes


def test_local_day_and_week_follow_tehran() -> None:
    # ۲۲:۰۰ UTC سه‌شنبه = ۱:۳۰ بامداد چهارشنبهٔ تهران.
    moment = datetime(2026, 9, 22, 22, 0, tzinfo=UTC)
    assert formulas.local_day_start(moment) == datetime(2026, 9, 22, 20, 30, tzinfo=UTC)
    # هفتهٔ ایرانی از شنبه (۱۹ سپتامبر ۲۰۲۶) شروع می‌شود.
    assert formulas.week_key(moment) == date(2026, 9, 19)
    assert formulas.is_night(moment)
    assert not formulas.is_night(datetime(2026, 9, 22, 10, 0, tzinfo=UTC))


# ── معیار نشان — §9.5 ──────────────────────────────────────────────────
FACTS = BadgeFacts(
    points_by_category={"RESEARCH": D(520), "LEARNING": D(80)},
    counts={
        "QUIZ_PERFECT": 3,
        "PROJECT_COMPLETED": 2,
        "PROJECT_COMPLETED:A_VENTURE": 1,
        "PROJECT_COMPLETED:B_RESEARCH": 1,
    },
    streaks={"WEEKLY_ACTIVITY": 8},
    sums={"SALES_AMOUNT": D(40_000_000)},
    maxima={"SALES_AMOUNT": D(25_000_000)},
    days_to_first={"APPLICATION_SUBMITTED": 3},
)


def test_count_reports_progress_for_locked_badges() -> None:
    """«۳ از ۵» راهنماست، «قفل» نیست — §9.5."""
    result = evaluate({"type": "COUNT", "entity": "QUIZ_PERFECT", "n": 5}, FACTS)
    assert (result.met, result.current, result.target) == (False, D(3), D(5))
    assert result.ratio == D("0.6")


def test_point_threshold_by_category_and_total() -> None:
    assert evaluate({"type": "POINT_THRESHOLD", "category": "RESEARCH", "amount": 500}, FACTS).met
    assert not evaluate({"type": "POINT_THRESHOLD", "amount": 601}, FACTS).met


def test_composite_counts_satisfied_parts() -> None:
    polymath = {
        "type": "COMPOSITE",
        "all_of": [
            {"type": "COUNT", "entity": "PROJECT_COMPLETED", "kind": kind, "n": 1}
            for kind in ("A_VENTURE", "B_RESEARCH", "C_PROBLEM", "D_PERSONAL")
        ],
    }
    result = evaluate(polymath, FACTS)
    assert (result.met, result.current, result.target) == (False, D(2), D(4))


def test_streak_first_sum_and_within_days() -> None:
    assert evaluate({"type": "STREAK", "entity": "WEEKLY_ACTIVITY", "n": 8}, FACTS).met
    assert evaluate({"type": "FIRST", "entity": "SALES_AMOUNT", "min_value": 1}, FACTS).met
    assert not evaluate(
        {"type": "SUM", "entity": "SALES_AMOUNT", "min_value": 100_000_001}, FACTS
    ).met
    assert evaluate(
        {"type": "WITHIN_DAYS", "entity": "APPLICATION_SUBMITTED", "days": 7}, FACTS
    ).met


def test_unknown_fact_is_zero_not_an_error() -> None:
    """نشان «شهرساز» پیش از M7 قفل می‌ماند، ولی ارزیابی نمی‌شکند."""
    result = evaluate({"type": "COUNT", "entity": "CITY_WORKFLOW_COMPLETED", "n": 1}, BadgeFacts())
    assert not result.met


@pytest.mark.parametrize(
    "criteria",
    [
        {"type": "MAGIC"},
        {"type": "COUNT", "entity": "QUIZ_PERFECT"},
        {"type": "COUNT", "entity": "QUIZ_PERFECT", "n": 0},
        {"type": "COMPOSITE", "all_of": []},
        {"type": "POINT_THRESHOLD", "amount": -5},
        {"type": "WITHIN_DAYS", "entity": "X", "days": True},
        "not a mapping",
    ],
)
def test_malformed_criteria_are_rejected(criteria: object) -> None:
    with pytest.raises(InvalidCriteria):
        validate(criteria)


def test_longest_weekly_streak() -> None:
    sat = date(2026, 9, 19)
    weeks = [sat, sat + timedelta(weeks=1), sat + timedelta(weeks=2), sat + timedelta(weeks=4)]
    assert longest_weekly_streak([*weeks, sat]) == 3
    assert longest_weekly_streak([]) == 0


# ── نمرهٔ یادگیری — §9.6 ───────────────────────────────────────────────
def _inputs(
    q: tuple[int, int] = (0, 0),
    s: tuple[int, int] = (0, 0),
    p: tuple[int, int] = (0, 0),
    a: tuple[str, int] = ("0", 0),
) -> LearningInputs:
    return LearningInputs(
        quiz=Fraction(D(q[0]), D(q[1])),
        study=Fraction(D(s[0]), D(s[1])),
        project=Fraction(D(p[0]), D(p[1])),
        attendance=Fraction(D(a[0]), D(a[1])),
    )


def test_learning_score_uses_the_documented_weights() -> None:
    """`100 × (0.40Q + 0.25S + 0.20P + 0.15A)`."""
    result = compute(_inputs(q=(15, 20), s=(4, 8), p=(1, 4), a=("9", 10)), weights_from_policy({}))
    # 0.4×0.75 + 0.25×0.5 + 0.2×0.25 + 0.15×0.9 = 0.61
    assert result.score == D("61.0")
    assert result.suggested_grade == D("12.20")


def test_missing_component_is_renormalised_not_zeroed() -> None:
    """درس بدون حضور و غیاب، نمره را به‌خاطر نبودِ حضور پایین نمی‌آورد."""
    result = compute(_inputs(q=(20, 20), s=(8, 8), p=(4, 4)), weights_from_policy(None))
    assert result.score == D("100.0")
    attendance = next(c for c in result.components if c.key == "attendance")
    assert attendance.ratio is None and attendance.weight == 0


def test_policy_participation_weights_the_study_component() -> None:
    weights = weights_from_policy(
        {"quiz": 30, "project": 50, "attendance": 10, "participation": 10}
    )
    assert weights == {"quiz": D(30), "study": D(10), "project": D(50), "attendance": D(10)}


def test_policy_zero_weight_drops_the_component() -> None:
    """§01 — `grading_policy.attendance = 0` یعنی حضور اصلاً شمرده نمی‌شود."""
    weights = weights_from_policy({"quiz": 100, "project": 0, "attendance": 0, "participation": 0})
    result = compute(_inputs(q=(10, 20), a=("0", 5)), weights)
    assert result.score == D("50.0")


def test_no_component_means_no_score() -> None:
    result = compute(_inputs(), weights_from_policy({}))
    assert result.score is None and result.suggested_grade is None
