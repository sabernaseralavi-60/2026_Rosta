"""قواعد خالص حلقهٔ یادگیری — ADR-0036."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest

from silp.domain.learning import (
    StreakState,
    advance_streak,
    draw_questions,
    mastery_level,
    streak_is_alive,
    tehran_day,
    update_mastery,
    week_start,
)

# شنبه ۱۴۰۵/۰۷/۱۳ = ۲۰۲۶-۱۰-۰۵ (دوشنبه)؛ از یک شنبهٔ مشخص می‌شماریم.
SAT = date(2026, 10, 3)


def test_week_starts_on_saturday() -> None:
    assert SAT.weekday() == 5
    assert week_start(SAT) == SAT
    assert week_start(SAT + timedelta(days=6)) == SAT  # جمعه
    assert week_start(SAT + timedelta(days=7)) == SAT + timedelta(days=7)


def test_tehran_day_crosses_midnight_before_utc() -> None:
    # ۲۱:۰۰ UTC = ۰۰:۳۰ فردای تهران (UTC+3:30)
    moment = datetime(2026, 10, 4, 21, 0, tzinfo=UTC)
    assert tehran_day(moment) == date(2026, 10, 5)


def test_consecutive_days_build_streak_and_hit_milestone() -> None:
    state = StreakState()
    milestones = []
    for offset in range(7):
        step = advance_streak(state, SAT + timedelta(days=offset))
        state = step.state
        if step.milestone:
            milestones.append(step.milestone)
    assert state.current == 7
    assert state.longest == 7
    assert milestones == [7]


def test_same_day_twice_is_a_no_op() -> None:
    first = advance_streak(StreakState(), SAT)
    again = advance_streak(first.state, SAT)
    assert again.state == first.state
    assert again.milestone is None


def test_one_missed_day_is_forgiven_once_per_week() -> None:
    state = advance_streak(StreakState(), SAT).state  # شنبه
    step = advance_streak(state, SAT + timedelta(days=2))  # دوشنبه؛ یکشنبه جا ماند
    assert step.froze is True
    assert step.state.current == 2

    # همان هفته، دوباره یک روز جا بیفتد ⇒ معافیت نیست و رشته می‌شکند.
    broken = advance_streak(step.state, SAT + timedelta(days=4))  # چهارشنبه؛ سه‌شنبه جا ماند
    assert broken.froze is False
    assert broken.state.current == 1
    assert broken.state.longest == 2


def test_two_missed_days_break_the_streak() -> None:
    state = advance_streak(StreakState(), SAT).state
    step = advance_streak(state, SAT + timedelta(days=3))
    assert step.state.current == 1


def test_freeze_resets_next_week() -> None:
    state = StreakState()
    state = advance_streak(state, SAT).state
    state = advance_streak(state, SAT + timedelta(days=2)).state  # معافیت هفتهٔ اول
    for offset in (3, 4, 5, 6):
        state = advance_streak(state, SAT + timedelta(days=offset)).state
    nxt = SAT + timedelta(days=7)
    state = advance_streak(state, nxt).state
    skip = advance_streak(state, nxt + timedelta(days=2))  # هفتهٔ تازه: دوباره می‌شود
    assert skip.froze is True


def test_streak_is_alive_window() -> None:
    state = advance_streak(StreakState(), SAT).state
    assert streak_is_alive(state, SAT)
    assert streak_is_alive(state, SAT + timedelta(days=1))
    assert not streak_is_alive(state, SAT + timedelta(days=2))
    assert not streak_is_alive(StreakState(), SAT)


def test_single_answer_cannot_make_a_student_strong_or_weak() -> None:
    score, n = update_mastery(0.5, 0, [True])
    assert n == 1
    assert 0.5 < score < 0.9
    assert mastery_level(score, n) == "LOW_DATA"


def test_mastery_converges_toward_performance() -> None:
    score, n = 0.5, 0
    for _ in range(4):
        score, n = update_mastery(score, n, [True, True, True, False])
    assert n == 16
    assert mastery_level(score, n) in ("STRONG", "MEDIUM")
    weak, m = 0.5, 0
    for _ in range(5):
        weak, m = update_mastery(weak, m, [False, False, True])
    assert mastery_level(weak, m) == "WEAK"


@pytest.mark.parametrize(
    ("score", "n", "level"),
    [(0.9, 10, "STRONG"), (0.6, 10, "MEDIUM"), (0.3, 10, "WEAK"), (0.9, 2, "LOW_DATA")],
)
def test_mastery_levels(score: float, n: int, level: str) -> None:
    assert mastery_level(score, n) == level


def _pool(per_concept: dict[str, int]) -> list[tuple[uuid.UUID, uuid.UUID | None]]:
    concepts = {name: uuid.uuid4() for name in per_concept}
    return [(uuid.uuid4(), concepts[name]) for name, k in per_concept.items() for _ in range(k)]


def test_draw_is_deterministic_per_seed_and_differs_across_seeds() -> None:
    pool = _pool({"a": 10, "b": 10, "c": 10})
    seed = uuid.uuid4()
    assert draw_questions(pool, 6, seed=seed) == draw_questions(pool, 6, seed=seed)
    other = draw_questions(pool, 6, seed=uuid.uuid4())
    assert set(other) != set(draw_questions(pool, 6, seed=seed))


def test_draw_balances_across_concepts() -> None:
    pool = _pool({"a": 20, "b": 20, "c": 1})
    concept_of = dict(pool)
    chosen = draw_questions(pool, 6, seed=uuid.uuid4())
    counts: dict[uuid.UUID | None, int] = {}
    for item in chosen:
        counts[concept_of[item]] = counts.get(concept_of[item], 0) + 1
    assert len(chosen) == 6
    assert max(counts.values()) <= 3  # هیچ مفهومی بیش از سهمش نمی‌گیرد
    assert len(counts) == 3  # مفهوم کم‌سؤال هم نماینده دارد


def test_draw_returns_everything_when_pool_is_small() -> None:
    pool = _pool({"a": 3})
    assert set(draw_questions(pool, 10, seed="x")) == {item for item, _ in pool}
