"""سنجش دسترسی به کتابخانه — ADR-0009.

جدول سه‌در‌پنج بالای `entitlement_service` اینجا سطر به سطر آزموده
می‌شود. منطق خالص است، پس نه دیتابیس لازم دارد نه اپ.
"""

from __future__ import annotations

import uuid

import pytest

from silp.core.exceptions import EnrollmentRequired, SubscriptionRequired
from silp.services.entitlement_service import (
    GUEST_CONTEXT,
    AccessBlocker,
    AccessContext,
    AccessReason,
    decide,
    raise_for,
)

COURSE = uuid.uuid4()
OTHER_COURSE = uuid.uuid4()


def ctx(**kwargs) -> AccessContext:  # type: ignore[no-untyped-def]
    return AccessContext(is_authenticated=True, **kwargs)


# ── سطر PUBLIC ─────────────────────────────────────────────────────────
def test_public_material_is_open_to_guest() -> None:
    result = decide(course_id=COURSE, tier="PUBLIC", ctx=GUEST_CONTEXT)
    assert result.allowed
    assert result.reason is AccessReason.PUBLIC


def test_public_material_is_open_to_plain_user() -> None:
    assert decide(course_id=COURSE, tier="PUBLIC", ctx=ctx()).allowed


# ── سطر SUBSCRIBER — قاعدهٔ اصلی محصول ─────────────────────────────────
def test_enrolled_student_gets_course_material_free() -> None:
    """«متریال هر درس برای دانشجوی همان درس رایگان است.»"""
    result = decide(
        course_id=COURSE,
        tier="SUBSCRIBER",
        ctx=ctx(enrolled_course_ids=frozenset({COURSE})),
    )
    assert result.allowed
    assert result.reason is AccessReason.ENROLLED


def test_enrollment_in_another_course_does_not_help() -> None:
    result = decide(
        course_id=COURSE,
        tier="SUBSCRIBER",
        ctx=ctx(enrolled_course_ids=frozenset({OTHER_COURSE})),
    )
    assert not result.allowed
    assert result.blocker is AccessBlocker.SUBSCRIPTION


def test_non_student_needs_subscription() -> None:
    """«برای بقیه با اشتراک ماهانه در دسترس است.»"""
    result = decide(course_id=COURSE, tier="SUBSCRIBER", ctx=ctx())
    assert not result.allowed
    assert result.blocker is AccessBlocker.SUBSCRIPTION
    assert "اشتراک" in result.note_fa


def test_global_subscription_opens_every_course() -> None:
    result = decide(course_id=COURSE, tier="SUBSCRIBER", ctx=ctx(has_global_subscription=True))
    assert result.allowed
    assert result.reason is AccessReason.SUBSCRIPTION


def test_single_course_subscription_is_scoped() -> None:
    context = ctx(subscribed_course_ids=frozenset({COURSE}))
    assert decide(course_id=COURSE, tier="SUBSCRIBER", ctx=context).allowed
    assert not decide(course_id=OTHER_COURSE, tier="SUBSCRIBER", ctx=context).allowed


def test_guest_never_reaches_subscriber_tier() -> None:
    assert not decide(course_id=COURSE, tier="SUBSCRIBER", ctx=GUEST_CONTEXT).allowed


# ── سطر ENROLLED — فروختنی نیست ────────────────────────────────────────
def test_subscription_does_not_unlock_enrolled_only_material() -> None:
    """کلید آزمون با پول باز نمی‌شود — هستهٔ ADR-0009."""
    result = decide(course_id=COURSE, tier="ENROLLED", ctx=ctx(has_global_subscription=True))
    assert not result.allowed
    assert result.blocker is AccessBlocker.ENROLLMENT


def test_enrolled_student_reaches_enrolled_only_material() -> None:
    result = decide(
        course_id=COURSE, tier="ENROLLED", ctx=ctx(enrolled_course_ids=frozenset({COURSE}))
    )
    assert result.allowed
    assert result.reason is AccessReason.ENROLLED


# ── کادر آموزشی ────────────────────────────────────────────────────────
def test_staff_sees_everything() -> None:
    for tier in ("PUBLIC", "SUBSCRIBER", "ENROLLED"):
        result = decide(course_id=COURSE, tier=tier, ctx=ctx(is_staff=True))
        assert result.allowed
        assert result.reason is AccessReason.STAFF


def test_instructor_of_the_course_sees_its_library() -> None:
    result = decide(
        course_id=COURSE,
        tier="ENROLLED",
        ctx=ctx(instructing_course_ids=frozenset({COURSE})),
    )
    assert result.allowed


def test_instructor_of_another_course_does_not() -> None:
    result = decide(
        course_id=COURSE,
        tier="SUBSCRIBER",
        ctx=ctx(instructing_course_ids=frozenset({OTHER_COURSE})),
    )
    assert not result.allowed


# ── ترتیب دلیل‌ها ──────────────────────────────────────────────────────
def test_enrollment_wins_over_subscription_in_the_message() -> None:
    """دانشجویی که اشتراک هم دارد، باید پیام «چون دانشجوی این درسی» ببیند."""
    result = decide(
        course_id=COURSE,
        tier="SUBSCRIBER",
        ctx=ctx(enrolled_course_ids=frozenset({COURSE}), has_global_subscription=True),
    )
    assert result.reason is AccessReason.ENROLLED


# ── تبدیل به خطای HTTP ─────────────────────────────────────────────────
def test_raise_for_allows_silently() -> None:
    raise_for(decide(course_id=COURSE, tier="PUBLIC", ctx=GUEST_CONTEXT))


def test_raise_for_maps_subscription_blocker_to_402() -> None:
    decision = decide(course_id=COURSE, tier="SUBSCRIBER", ctx=ctx())
    with pytest.raises(SubscriptionRequired) as exc:
        raise_for(decision, course_slug="road-safety-modeling")
    assert exc.value.status_code == 402
    assert exc.value.details["course_slug"] == "road-safety-modeling"


def test_raise_for_maps_enrollment_blocker_to_403() -> None:
    decision = decide(course_id=COURSE, tier="ENROLLED", ctx=ctx(has_global_subscription=True))
    with pytest.raises(EnrollmentRequired) as exc:
        raise_for(decision)
    assert exc.value.status_code == 403
