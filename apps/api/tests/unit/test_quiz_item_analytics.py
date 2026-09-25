"""تحلیل پیشرفتهٔ آزمون — ADR-0028. منطق خالص، بدون دیتابیس."""

from __future__ import annotations

import math

from silp.domain.quiz import analytics


# ── توزیع نمره ─────────────────────────────────────────────────────────
def test_summary_reports_median_sd_and_a_histogram_that_includes_one_hundred() -> None:
    summary = analytics.summarize_scores([0.0, 50.0, 100.0, 100.0])

    assert summary is not None
    assert summary.n == 4
    assert summary.mean_percent == 62.5
    assert summary.median_percent == 75.0
    assert summary.min_percent == 0.0
    assert summary.max_percent == 100.0
    # ۱۰۰٪ در سطل آخر می‌نشیند، نه سطل یازدهم.
    assert summary.histogram == (1, 0, 0, 0, 0, 1, 0, 0, 0, 2)
    assert sum(summary.histogram) == summary.n


def test_summary_of_one_attempt_has_no_standard_deviation() -> None:
    summary = analytics.summarize_scores([80.0])

    assert summary is not None
    assert summary.sd_percent is None
    assert summary.median_percent == 80.0


def test_summary_of_nothing_is_none() -> None:
    assert analytics.summarize_scores([]) is None


# ── پایایی ─────────────────────────────────────────────────────────────
def test_alpha_is_one_when_items_agree_perfectly() -> None:
    matrix = [[1.0, 1.0, 1.0] if i % 2 else [0.0, 0.0, 0.0] for i in range(12)]

    assert math.isclose(analytics.cronbach_alpha(matrix) or 0, 1.0)


def test_alpha_is_low_when_items_measure_different_things() -> None:
    # دو سؤال کاملاً مستقل: الگوی چهارحالتهٔ مساوی.
    matrix = [[float(a), float(b)] for a in (0, 1) for b in (0, 1)] * 3

    alpha = analytics.cronbach_alpha(matrix)

    assert alpha is not None
    assert abs(alpha) < 1e-9


def test_alpha_needs_ten_attempts_two_items_and_spread() -> None:
    assert analytics.cronbach_alpha([[1.0, 0.0]] * 9) is None  # کم‌تلاش
    assert analytics.cronbach_alpha([[1.0]] * 12) is None  # یک سؤال
    assert analytics.cronbach_alpha([[1.0, 0.0]] * 12) is None  # همه یک نمره


def test_reliability_turns_a_weak_alpha_into_advice_and_a_sem() -> None:
    matrix = [[float(a), float(b)] for a in (0, 1) for b in (0, 1)] * 3

    result = analytics.reliability(matrix, max_total=2.0)

    assert result is not None
    assert result.label_fa == "نامطمئن"
    assert result.advice_fa
    # α≈۰ یعنی خطای معیار برابر انحراف معیار نمرهٔ کل؛ روی بارم ۲ ≈ ۳۵٪.
    assert 30 < result.sem_percent < 40


# ── همبستگی سؤال با بقیه ───────────────────────────────────────────────
def test_item_rest_is_one_when_the_item_tracks_the_rest() -> None:
    item = [float(i % 2) for i in range(12)]
    totals = [2 * v for v in item]  # بقیه = خود سؤال

    assert math.isclose(analytics.item_rest_correlation(item, totals) or 0, 1.0)


def test_item_rest_is_negative_when_strong_students_miss_the_item() -> None:
    item = [1.0] * 6 + [0.0] * 6
    rest = [0.0] * 6 + [4.0] * 6
    totals = [i + r for i, r in zip(item, rest, strict=True)]

    value = analytics.item_rest_correlation(item, totals)

    assert value is not None
    assert value < -0.9


def test_item_rest_is_none_below_ten_attempts_or_without_variance() -> None:
    assert analytics.item_rest_correlation([1.0, 0.0] * 4, [2.0, 0.0] * 4) is None
    assert analytics.item_rest_correlation([1.0] * 12, [3.0, 1.0] * 6) is None


# ── توزیع گزینه ────────────────────────────────────────────────────────
def _twelve_attempts(picks: dict[int, list[str]]) -> tuple[dict[str, list[str]], dict[str, float]]:
    """دوازده تلاش با نمرهٔ کل ۱۲..۱، تلاش ۰ بهترین."""
    selections = {f"a{i}": picks.get(i, ["b"]) for i in range(12)}
    totals = {f"a{i}": float(12 - i) for i in range(12)}
    return selections, totals


OPTIONS = [("a", "الف", False), ("b", "ب", True), ("c", "ج", False), ("d", "د", False)]


def test_a_distractor_nobody_picks_is_flagged_as_dead() -> None:
    # همه b می‌زنند جز دو نفر که c می‌زنند؛ d را هیچ‌کس.
    selections, totals = _twelve_attempts({5: ["c"], 9: ["c"]})

    result = {
        o.option_id: o
        for o in analytics.option_stats(options=OPTIONS, selections=selections, totals=totals)
    }

    assert result["d"].chosen == 0
    assert result["d"].note_fa and "هیچ‌کس" in result["d"].note_fa
    assert result["b"].chosen == 10
    assert math.isclose(result["b"].share, 10 / 12)
    assert result["b"].note_fa is None


def test_a_distractor_the_strong_prefer_is_flagged() -> None:
    # سه نفر برتر a می‌زنند، سه نفر ته‌جدول b (کلید).
    picks = {0: ["a"], 1: ["a"], 2: ["a"], 9: ["b"], 10: ["b"], 11: ["b"]}
    selections, totals = _twelve_attempts({**{i: ["c"] for i in range(3, 9)}, **picks})

    result = {
        o.option_id: o
        for o in analytics.option_stats(options=OPTIONS, selections=selections, totals=totals)
    }

    assert result["a"].top_share == 1.0
    assert result["a"].bottom_share == 0.0
    assert result["a"].note_fa and "قوی‌ترها" in result["a"].note_fa
    # کلید را ضعیف‌ترها می‌زنند، نه قوی‌ترها: هشدار کلید.
    assert result["b"].note_fa and "کلید" in result["b"].note_fa


def test_a_question_everyone_gets_right_does_not_accuse_the_key() -> None:
    # همه b می‌زنند: گروه قوی و ضعیف برابرند، پس «کلید غلط» نیست.
    selections, totals = _twelve_attempts({})

    result = {
        o.option_id: o
        for o in analytics.option_stats(options=OPTIONS, selections=selections, totals=totals)
    }

    assert result["b"].top_share == result["b"].bottom_share == 1.0
    assert result["b"].note_fa is None


def test_unanswered_attempts_count_in_the_denominator() -> None:
    selections, totals = _twelve_attempts({3: [], 4: []})

    result = {
        o.option_id: o
        for o in analytics.option_stats(options=OPTIONS, selections=selections, totals=totals)
    }

    assert result["b"].chosen == 10
    assert math.isclose(result["b"].share, 10 / 12)


def test_small_cohorts_get_counts_but_no_group_shares_or_notes() -> None:
    selections = {"a0": ["a"], "a1": ["b"], "a2": ["b"]}
    totals = {"a0": 3.0, "a1": 2.0, "a2": 1.0}

    result = analytics.option_stats(options=OPTIONS, selections=selections, totals=totals)

    assert [o.chosen for o in result] == [1, 2, 0, 0]
    assert all(o.top_share is None and o.bottom_share is None for o in result)
    assert all(o.note_fa is None for o in result)


def test_multi_choice_selections_count_each_picked_option() -> None:
    selections, totals = _twelve_attempts({i: ["a", "b"] for i in range(12)})

    result = {
        o.option_id: o
        for o in analytics.option_stats(options=OPTIONS, selections=selections, totals=totals)
    }

    assert result["a"].chosen == 12
    assert result["b"].chosen == 12
