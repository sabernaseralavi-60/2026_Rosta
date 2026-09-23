"""M7 بخش د — منطق خالص گواهی، نیمرخ عمومی، حسابرسی و مجوز. بدون دیتابیس."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from silp.core.permissions import PERMISSION_MATRIX, CurrentUser, Permission, Role, RoleGrant
from silp.domain import audit, certificates, public_profile
from silp.services.admin_service import NON_GRANTABLE, grantable_roles, scopes_for
from silp.services.audit_service import _valid_ip, jsonable


# ── کد گواهی ───────────────────────────────────────────────────────────
def test_new_codes_are_short_unambiguous_and_distinct() -> None:
    codes = {certificates.new_code() for _ in range(500)}
    assert len(codes) == 500
    for code in codes:
        assert certificates.CODE_PATTERN.match(code)
        assert not set(code) & set("ILOU")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("ab12-cd34", "AB12-CD34"),
        ("AB12CD34", "AB12-CD34"),
        (" ab12 cd34 ", "AB12-CD34"),
        ("۴۵۶۷-ABCD", "4567-ABCD"),
        ("O0I1-L234", "0011-1234"),  # O و I و L با رقم اشتباه می‌شوند
    ],
)
def test_codes_typed_by_people_are_normalized(raw: str, expected: str) -> None:
    assert certificates.normalize_code(raw) == expected


@pytest.mark.parametrize("raw", ["", "ABC", "AB12-CD345", "AB12-CDU4", "../etc/passwd"])
def test_impossible_codes_are_rejected_before_the_database(raw: str) -> None:
    assert certificates.normalize_code(raw) is None


def test_course_pass_mark_is_ten_of_twenty() -> None:
    assert certificates.course_passed(Decimal("10"))
    assert certificates.course_passed(17.5)
    assert not certificates.course_passed(Decimal("9.99"))
    assert not certificates.course_passed(None)


def test_titles_use_persian_digits() -> None:
    assert certificates.research_title(3, "مقالهٔ کنفرانس") == "سطح ۳ مسیر پژوهش — مقالهٔ کنفرانس"
    assert certificates.project_title("خرما") == "تکمیل پروژهٔ «خرما»"


# ── نیمرخ عمومی ────────────────────────────────────────────────────────
def test_sections_default_to_visible_once_the_profile_is_public() -> None:
    assert public_profile.sections({}) == dict.fromkeys(public_profile.SECTIONS, True)
    assert public_profile.sections({"points": False})["points"] is False
    assert public_profile.sections(None)["skills"] is True


def test_merge_keeps_other_keys_and_refuses_unknown_sections() -> None:
    merged = public_profile.merge({"points": False, "legacy": 1}, {"skills": False})
    assert merged == {"points": False, "legacy": 1, "skills": False}
    with pytest.raises(ValueError, match="mobile"):
        public_profile.merge({}, {"mobile": True})


def test_no_section_could_ever_expose_contact_or_grades() -> None:
    """FR-PROF-03 «هرگز نمایش داده نمی‌شود» — حتی کلیدی برای روشن کردنش نیست."""
    forbidden = {"mobile", "email", "national_id", "grades", "rank"}
    assert not forbidden & set(public_profile.SECTIONS)


# ── حسابرسی ────────────────────────────────────────────────────────────
def test_audit_values_become_plain_json() -> None:
    uid = uuid.uuid4()
    moment = datetime(2026, 9, 23, 10, 30, tzinfo=UTC)
    assert jsonable({"id": uid, "at": moment, "score": Decimal("17.50"), "tags": {"a"}}) == {
        "id": str(uid),
        "at": "2026-09-23T10:30:00+00:00",
        "score": "17.50",
        "tags": ["a"],
    }


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("127.0.0.1", "127.0.0.1"),
        ("::1", "::1"),
        ("unknown", None),
        ("testclient", None),
        (None, None),
    ],
)
def test_only_real_addresses_reach_the_inet_column(raw: str | None, expected: str | None) -> None:
    assert _valid_ip(raw) == expected


def test_every_action_has_a_persian_title() -> None:
    codes = [v for k, v in vars(audit).items() if k.isupper() and isinstance(v, str)]
    assert codes
    for code in codes:
        assert code in audit.ACTION_TITLE_FA, code


# ── مجوز و نقش ─────────────────────────────────────────────────────────
def _user(*roles: Role) -> CurrentUser:
    return CurrentUser(
        id=uuid.uuid4(), session_id=uuid.uuid4(), grants=tuple(RoleGrant(r) for r in roles)
    )


def test_support_finds_and_views_users_but_does_not_change_them() -> None:
    support = _user(Role.SUPPORT)
    assert support.has_permission(Permission.USER_VIEW_ALL)
    assert support.has_permission(Permission.IMPERSONATE)
    assert support.has_permission(Permission.AUDIT_LOG_VIEW)
    assert not support.has_permission(Permission.USER_ROLE_ASSIGN)
    assert not support.has_permission(Permission.USER_DEACTIVATE)
    assert not support.has_permission(Permission.CERTIFICATE_REVOKE)
    assert not support.has_permission(Permission.PROFILE_VIEW_CONTACT)


def test_only_admins_revoke_certificates() -> None:
    assert PERMISSION_MATRIX[Permission.CERTIFICATE_REVOKE] == frozenset({Role.ADMIN})
    assert not _user(Role.INSTRUCTOR).has_permission(Permission.CERTIFICATE_REVOKE)


def test_derived_roles_are_not_grantable_and_only_teaching_roles_take_an_offering() -> None:
    assert NON_GRANTABLE == {Role.GUEST, Role.PROJECT_MEMBER, Role.PROJECT_LEAD}
    assert Role.PROJECT_LEAD not in grantable_roles()
    assert scopes_for(Role.INSTRUCTOR) == ["GLOBAL", "OFFERING"]
    assert scopes_for(Role.TA) == ["GLOBAL", "OFFERING"]
    assert scopes_for(Role.MENTOR) == ["GLOBAL"]
