"""قواعد پرسش‌وپاسخ درس — ADR-0024 برش ج. خالص، بدون دیتابیس."""

from __future__ import annotations

import pytest

from silp.domain import qa as rules


def test_three_student_votes_or_an_endorsement_make_an_answer_helpful() -> None:
    assert rules.helpful_earned(endorsed=False, student_votes=2) is False
    assert rules.helpful_earned(endorsed=False, student_votes=3) is True
    assert rules.helpful_earned(endorsed=True, student_votes=0) is True


@pytest.mark.parametrize(
    ("endorsed", "votes", "expected"),
    [
        (False, 0, ()),
        (False, 2, ()),
        (False, 3, (rules.HELPFUL_RULE,)),
        (True, 0, (rules.HELPFUL_RULE, rules.OFFICIAL_RULE)),
        (True, 9, (rules.HELPFUL_RULE, rules.OFFICIAL_RULE)),
    ],
)
def test_an_endorsed_answer_earns_both_rules(
    endorsed: bool, votes: int, expected: tuple[str, ...]
) -> None:
    """بند ۱۶ — افزایشی است: تأیید هم ۱۰ می‌دهد و هم ۲۰."""
    assert rules.rules_earned(endorsed=endorsed, student_votes=votes) == expected


def test_title_is_a_single_line() -> None:
    dirty = "  چرا   اصطکاک\n در باران کم می‌شود؟ "
    assert rules.clean_title(dirty) == "چرا اصطکاک در باران کم می‌شود؟"


def test_thread_limits() -> None:
    assert rules.validate_thread("عنوان درست", "شرح کافی برای پرسش") is None
    assert "عنوان" in (rules.validate_thread("ابر", "شرح کافی برای پرسش") or "")
    assert "عنوان" in (rules.validate_thread("ع" * 151, "شرح کافی برای پرسش") or "")
    assert "شرح" in (rules.validate_thread("عنوان درست", "کوتاه") or "")
    assert "شرح" in (rules.validate_thread("عنوان درست", "ش" * 4001) or "")


def test_reply_limits() -> None:
    assert rules.validate_reply("پاسخ") is None
    assert rules.validate_reply("ب") is not None
    assert rules.validate_reply("پ" * 4001) is not None


def test_both_rules_share_one_source_type() -> None:
    """امتیاز به خودِ پاسخ می‌رسد؛ منبع مشترک، کلید بی‌اثریِ جدا برای هر قاعده."""
    assert rules.RULES == (rules.HELPFUL_RULE, rules.OFFICIAL_RULE)
    assert rules.POINT_SOURCE_TYPE == "QA_REPLY"
