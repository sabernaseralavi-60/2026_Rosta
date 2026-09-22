"""تست چارچوب مجوز — §6.

قاعدهٔ محوری §6.1: «رتبهٔ بالاتر به‌صورت خودکار مجوزهای پایین‌تر را ندارد.»
این فایل دقیقاً همان را تضمین می‌کند.
"""

from __future__ import annotations

import uuid

import pytest

from silp.core.permissions import (
    GUEST,
    PERMISSION_MATRIX,
    ROLE_RANK,
    ROLE_TITLE_FA,
    SCOPED_PERMISSIONS,
    CurrentUser,
    Permission,
    Role,
    RoleGrant,
    ScopeType,
)

OFFERING_A = uuid.UUID("018f0000-0000-7000-8000-00000000000a")
OFFERING_B = uuid.UUID("018f0000-0000-7000-8000-00000000000b")


def user_with(*grants: RoleGrant) -> CurrentUser:
    return CurrentUser(id=uuid.uuid4(), session_id=uuid.uuid4(), grants=grants)


# ── یکپارچگی ماتریس ────────────────────────────────────────────────────
def test_every_role_has_rank_and_title() -> None:
    for role in Role:
        assert role in ROLE_RANK
        assert ROLE_TITLE_FA[role]


def test_scoped_permissions_all_exist_in_matrix() -> None:
    """مجوز قلمرودار که در ماتریس نباشد، یعنی هیچ‌کس آن را ندارد."""
    missing = SCOPED_PERMISSIONS - set(PERMISSION_MATRIX)
    assert not missing, f"مجوزهای بدون ورودی در ماتریس: {missing}"


def test_guest_has_no_permission_at_all() -> None:
    for permission in Permission:
        assert GUEST.has_permission(permission) is False


# ── §6.1 — رتبه ارث‌بری نمی‌آورد ───────────────────────────────────────
def test_higher_rank_does_not_inherit_lower_permissions() -> None:
    """COORDINATOR رتبهٔ ۶۰ دارد ولی حق ثبت حضور و غیاب ندارد (§6.2)."""
    coordinator = user_with(RoleGrant(Role.COORDINATOR))
    assert coordinator.has_permission(Permission.COURSE_CREATE) is True
    assert coordinator.has_permission(Permission.ATTENDANCE_RECORD) is False
    assert coordinator.has_permission(Permission.GRADE_FINAL_SUBMIT) is False


def test_support_can_read_audit_but_not_assign_roles() -> None:
    support = user_with(RoleGrant(Role.SUPPORT))
    assert support.has_permission(Permission.AUDIT_LOG_VIEW) is True
    assert support.has_permission(Permission.USER_ROLE_ASSIGN) is False


def test_ta_cannot_publish_week_but_can_edit_it() -> None:
    """§6.2 — TA محتوا می‌سازد، استاد منتشر می‌کند."""
    ta = user_with(RoleGrant(Role.TA, ScopeType.OFFERING, OFFERING_A))
    assert ta.has_permission(Permission.COURSE_WEEK_EDIT, OFFERING_A) is True
    assert ta.has_permission(Permission.COURSE_WEEK_PUBLISH, OFFERING_A) is False


def test_student_has_no_teaching_permission() -> None:
    student = user_with(RoleGrant(Role.STUDENT))
    for permission in (
        Permission.COURSE_WEEK_PUBLISH,
        Permission.QUIZ_CREATE,
        Permission.GRADE_OVERRIDE,
        Permission.PROJECT_APPLICATION_DECIDE,
        Permission.POINTS_AWARD_MANUAL,
    ):
        assert student.has_permission(permission) is False


# ── قلمرو ──────────────────────────────────────────────────────────────
def test_instructor_permission_does_not_cross_offerings() -> None:
    """استاد ارائهٔ A نباید در ارائهٔ B کاری بکند — §6.4 پانویس ۵."""
    instructor = user_with(RoleGrant(Role.INSTRUCTOR, ScopeType.OFFERING, OFFERING_A))
    assert instructor.has_permission(Permission.COURSE_WEEK_PUBLISH, OFFERING_A) is True
    assert instructor.has_permission(Permission.COURSE_WEEK_PUBLISH, OFFERING_B) is False


def test_scoped_permission_without_scope_id_is_denied() -> None:
    instructor = user_with(RoleGrant(Role.INSTRUCTOR, ScopeType.OFFERING, OFFERING_A))
    assert instructor.has_permission(Permission.COURSE_WEEK_PUBLISH, None) is False


def test_global_grant_covers_every_scope() -> None:
    instructor = user_with(RoleGrant(Role.INSTRUCTOR, ScopeType.GLOBAL))
    assert instructor.has_permission(Permission.COURSE_WEEK_PUBLISH, OFFERING_A) is True
    assert instructor.has_permission(Permission.COURSE_WEEK_PUBLISH, OFFERING_B) is True


def test_admin_is_not_limited_by_scope() -> None:
    admin = user_with(RoleGrant(Role.ADMIN))
    assert admin.has_permission(Permission.COURSE_WEEK_PUBLISH, OFFERING_B) is True
    assert admin.has_permission(Permission.GRADE_OVERRIDE, OFFERING_A) is True


def test_admin_still_lacks_permissions_not_granted_to_it() -> None:
    """ADMIN «همه‌کاره» نیست: ارسال تحویل‌دادنی کار عضو تیم است (§6.2)."""
    admin = user_with(RoleGrant(Role.ADMIN))
    assert admin.has_permission(Permission.DELIVERABLE_SUBMIT) is False


# ── چند نقش هم‌زمان ────────────────────────────────────────────────────
def test_multiple_roles_are_combined() -> None:
    """یک نفر می‌تواند استاد یک درس و دانشجوی درس دیگر باشد (§6.1)."""
    person = user_with(
        RoleGrant(Role.STUDENT),
        RoleGrant(Role.INSTRUCTOR, ScopeType.OFFERING, OFFERING_A),
    )
    assert person.has_permission(Permission.PROFILE_EDIT_SELF) is True
    assert person.has_permission(Permission.COURSE_WEEK_PUBLISH, OFFERING_A) is True
    assert person.has_permission(Permission.COURSE_WEEK_PUBLISH, OFFERING_B) is False


def test_role_codes_are_sorted_and_unique() -> None:
    person = user_with(
        RoleGrant(Role.STUDENT),
        RoleGrant(Role.INSTRUCTOR, ScopeType.OFFERING, OFFERING_A),
        RoleGrant(Role.INSTRUCTOR, ScopeType.OFFERING, OFFERING_B),
    )
    assert person.role_codes == ["INSTRUCTOR", "STUDENT"]


def test_highest_rank_reflects_strongest_role() -> None:
    person = user_with(RoleGrant(Role.STUDENT), RoleGrant(Role.TA))
    assert person.highest_rank == ROLE_RANK[Role.TA]


@pytest.mark.parametrize("role", list(Role))
def test_no_role_can_edit_point_rules_except_admin(role: Role) -> None:
    """§6.3 — دفتر کل امتیاز فقط با قواعد ادمین تغییر می‌کند."""
    actor = user_with(RoleGrant(role))
    expected = role is Role.ADMIN
    assert actor.has_permission(Permission.POINTS_RULE_EDIT) is expected
