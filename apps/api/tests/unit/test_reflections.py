"""قواعد بازتاب پایان پروژه — ADR-0024. خالص، بدون دیتابیس."""

from __future__ import annotations

import pytest

from silp.domain import reflections as rules
from silp.domain.reflections import ReflectionDraft

FULL_SENTENCE = "یاد گرفتم پیش از شروع، خروجی نهایی را دقیق تعریف کنم."


def test_a_full_sentence_is_accepted() -> None:
    assert rules.validate(ReflectionDraft(learned=FULL_SENTENCE)) is None


@pytest.mark.parametrize("learned", ["", "   ", "خوب بود", "ا" * (rules.MIN_LEARNED_CHARS - 1)])
def test_too_little_to_learn_from_is_refused(learned: str) -> None:
    assert rules.validate(ReflectionDraft(learned=learned)) is not None


def test_the_minimum_counts_after_stripping() -> None:
    padded = "  " + "ا" * (rules.MIN_LEARNED_CHARS - 1) + "  "
    assert rules.validate(ReflectionDraft(learned=padded)) is not None
    assert rules.validate(ReflectionDraft(learned="ا" * rules.MIN_LEARNED_CHARS)) is None


def test_optional_fields_may_be_missing_but_not_absurd() -> None:
    assert rules.validate(ReflectionDraft(learned=FULL_SENTENCE, satisfaction=1)) is None
    assert rules.validate(ReflectionDraft(learned=FULL_SENTENCE, satisfaction=5)) is None
    assert rules.validate(ReflectionDraft(learned=FULL_SENTENCE, satisfaction=6)) is not None
    too_long = "ا" * (rules.MAX_FIELD_CHARS + 1)
    assert rules.validate(ReflectionDraft(learned=FULL_SENTENCE, challenges=too_long)) is not None


def test_clean_turns_blank_into_none() -> None:
    assert rules.clean("   ") is None
    assert rules.clean(None) is None
    assert rules.clean("  متن  ") == "متن"
