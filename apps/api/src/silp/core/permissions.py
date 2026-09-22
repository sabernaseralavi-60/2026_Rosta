"""چارچوب مجوز — PRD §6.

قواعد کلیدی (§6.4):
۱. هرگز در لایهٔ مسیر بررسی نقش خام نکنید؛ همیشه مجوز نام‌دار.
۲. بررسی در لایهٔ سرویس تکرار می‌شود — دفاع در عمق.
۳. فیلتر در سطح کوئری، نه پس از واکشی.
۴. ۴۰۴ به‌جای ۴۰۳ برای منابع خصوصی.
۵. نقش‌های کاربر در Redis با TTL ۶۰ ثانیه کش می‌شوند.

رتبهٔ بالاتر به‌صورت خودکار مجوزهای پایین‌تر را **ندارد**. هر مجوز صریح است.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import StrEnum


class Role(StrEnum):
    """§6.1 — کدهای نقش. با ستون roles.code یکسان است."""

    GUEST = "GUEST"
    PUBLIC_LEARNER = "PUBLIC_LEARNER"
    STUDENT = "STUDENT"
    PROJECT_MEMBER = "PROJECT_MEMBER"
    PROJECT_LEAD = "PROJECT_LEAD"
    MENTOR = "MENTOR"
    TA = "TA"
    INSTRUCTOR = "INSTRUCTOR"
    COORDINATOR = "COORDINATOR"
    SUPPORT = "SUPPORT"
    ADMIN = "ADMIN"


ROLE_RANK: dict[Role, int] = {
    Role.GUEST: 0,
    Role.PUBLIC_LEARNER: 10,
    Role.STUDENT: 20,
    Role.PROJECT_MEMBER: 25,
    Role.PROJECT_LEAD: 30,
    Role.MENTOR: 40,
    Role.TA: 45,
    Role.INSTRUCTOR: 50,
    Role.COORDINATOR: 60,
    Role.SUPPORT: 70,
    Role.ADMIN: 90,
}

ROLE_TITLE_FA: dict[Role, str] = {
    Role.GUEST: "مهمان",
    Role.PUBLIC_LEARNER: "فراگیر عمومی",
    Role.STUDENT: "دانشجو",
    Role.PROJECT_MEMBER: "عضو پروژه",
    Role.PROJECT_LEAD: "مدیر پروژه",
    Role.MENTOR: "منتور",
    Role.TA: "دستیار آموزشی",
    Role.INSTRUCTOR: "استاد",
    Role.COORDINATOR: "مدیر آموزشی",
    Role.SUPPORT: "پشتیبانی",
    Role.ADMIN: "مدیر سامانه",
}

# نقش‌هایی که از عضویت مشتق می‌شوند و در user_roles ذخیره نمی‌گردند (§6.1).
DERIVED_ROLES: frozenset[Role] = frozenset({Role.PROJECT_MEMBER, Role.PROJECT_LEAD})


class ScopeType(StrEnum):
    GLOBAL = "GLOBAL"
    OFFERING = "OFFERING"
    PROJECT = "PROJECT"
    VENTURE = "VENTURE"


class Permission(StrEnum):
    """مجوزهای نام‌دار. با پیشرفت مراحل M1..M7 به این فهرست افزوده می‌شود."""

    # ── حساب و نیمرخ ───────────────────────────────────────────────────
    PROFILE_VIEW_SELF = "profile.view.self"
    PROFILE_EDIT_SELF = "profile.edit.self"
    PROFILE_VIEW_FULL = "profile.view.full"
    PROFILE_VIEW_CONTACT = "profile.view.contact"
    PROFILE_VIEW_NATIONAL_ID = "profile.view.national_id"
    SKILL_VERIFY = "profile.skill.verify"

    # ── مدیریت ─────────────────────────────────────────────────────────
    USER_ROLE_ASSIGN = "user.role.assign"
    USER_DEACTIVATE = "user.deactivate"
    AUDIT_LOG_VIEW = "audit.log.view"
    IMPERSONATE = "user.impersonate"

    # ── آموزش (M3) ─────────────────────────────────────────────────────
    COURSE_CREATE = "course.create"
    OFFERING_CREATE = "offering.create"
    OFFERING_MANAGE = "offering.manage"
    COURSE_WEEK_EDIT = "course.week.edit"
    COURSE_WEEK_PUBLISH = "course.week.publish"
    COURSE_WEEK_VIEW_DRAFT = "course.week.view_draft"
    RESOURCE_UPLOAD = "course.resource.upload"
    ATTENDANCE_RECORD = "course.attendance.record"
    ENROLLMENT_APPROVE = "course.enrollment.approve"
    GRADE_FINAL_SUBMIT = "course.grade.submit"

    # ── آزمون (M4) ─────────────────────────────────────────────────────
    QUIZ_CREATE = "quiz.create"
    QUIZ_GRADE = "quiz.grade"
    QUIZ_VIEW_OTHERS_RESULT = "quiz.result.view_others"
    QUIZ_ATTEMPT_INVALIDATE = "quiz.attempt.invalidate"
    GRADE_OVERRIDE = "grade.override"
    APPEAL_RESOLVE = "quiz.appeal.resolve"

    # ── پروژه (M2) ─────────────────────────────────────────────────────
    PROJECT_CREATE_MANAGED = "project.create.managed"
    PROJECT_WORKSPACE_VIEW = "project.workspace.view"
    PROJECT_APPLICATION_DECIDE = "project.application.decide"
    PROJECT_MILESTONE_MANAGE = "project.milestone.manage"
    PROJECT_MEMBER_REMOVE = "project.member.remove"
    PROJECT_CLOSE = "project.close"
    DELIVERABLE_SUBMIT = "deliverable.submit"
    DELIVERABLE_REVIEW = "deliverable.review"
    CERTIFICATE_ISSUE = "certificate.issue"

    # ── گیمیفیکیشن (M5) ────────────────────────────────────────────────
    POINTS_VIEW_OTHERS = "points.view_others"
    POINTS_AWARD_MANUAL = "points.award.manual"
    POINTS_RULE_EDIT = "points.rule.edit"
    POINTS_RECALCULATE = "points.recalculate"


_SELF_SERVICE_ROLES: frozenset[Role] = frozenset(
    {
        Role.PUBLIC_LEARNER,
        Role.STUDENT,
        Role.MENTOR,
        Role.TA,
        Role.INSTRUCTOR,
        Role.COORDINATOR,
        Role.SUPPORT,
        Role.ADMIN,
    }
)

# ── ماتریس مجوز (§6.2) ─────────────────────────────────────────────────
# هر ورودی: مجوز ← نقش‌هایی که آن را دارند. صریح، نه ارث‌بری رتبه‌ای.
# مجوزهای مشروط (نشان خورشیدی در سند) اینجا اعطا می‌شوند و شرط قلمرو
# توسط SCOPED_PERMISSIONS و resolver قلمرو در لایهٔ مسیر اعمال می‌گردد.
PERMISSION_MATRIX: dict[Permission, frozenset[Role]] = {
    # حساب و نیمرخ
    Permission.PROFILE_VIEW_SELF: _SELF_SERVICE_ROLES,
    Permission.PROFILE_EDIT_SELF: _SELF_SERVICE_ROLES,
    Permission.PROFILE_VIEW_FULL: frozenset({Role.TA, Role.INSTRUCTOR, Role.ADMIN}),
    Permission.PROFILE_VIEW_CONTACT: frozenset({Role.INSTRUCTOR, Role.ADMIN}),
    Permission.PROFILE_VIEW_NATIONAL_ID: frozenset({Role.ADMIN}),
    Permission.SKILL_VERIFY: frozenset({Role.TA, Role.INSTRUCTOR, Role.ADMIN}),
    # مدیریت
    Permission.USER_ROLE_ASSIGN: frozenset({Role.ADMIN}),
    Permission.USER_DEACTIVATE: frozenset({Role.ADMIN}),
    Permission.AUDIT_LOG_VIEW: frozenset({Role.SUPPORT, Role.ADMIN}),
    Permission.IMPERSONATE: frozenset({Role.SUPPORT, Role.ADMIN}),
    # آموزش
    Permission.COURSE_CREATE: frozenset({Role.COORDINATOR, Role.ADMIN}),
    Permission.OFFERING_CREATE: frozenset({Role.INSTRUCTOR, Role.COORDINATOR, Role.ADMIN}),
    Permission.OFFERING_MANAGE: frozenset({Role.INSTRUCTOR, Role.COORDINATOR, Role.ADMIN}),
    Permission.COURSE_WEEK_EDIT: frozenset(
        {Role.TA, Role.INSTRUCTOR, Role.COORDINATOR, Role.ADMIN}
    ),
    Permission.COURSE_WEEK_PUBLISH: frozenset({Role.INSTRUCTOR, Role.COORDINATOR, Role.ADMIN}),
    Permission.COURSE_WEEK_VIEW_DRAFT: frozenset(
        {Role.TA, Role.INSTRUCTOR, Role.COORDINATOR, Role.ADMIN}
    ),
    Permission.RESOURCE_UPLOAD: frozenset({Role.TA, Role.INSTRUCTOR, Role.COORDINATOR, Role.ADMIN}),
    Permission.ATTENDANCE_RECORD: frozenset({Role.TA, Role.INSTRUCTOR, Role.ADMIN}),
    Permission.ENROLLMENT_APPROVE: frozenset({Role.INSTRUCTOR, Role.COORDINATOR, Role.ADMIN}),
    Permission.GRADE_FINAL_SUBMIT: frozenset({Role.INSTRUCTOR, Role.ADMIN}),
    # آزمون
    Permission.QUIZ_CREATE: frozenset({Role.TA, Role.INSTRUCTOR, Role.ADMIN}),
    Permission.QUIZ_GRADE: frozenset({Role.TA, Role.INSTRUCTOR, Role.ADMIN}),
    Permission.QUIZ_VIEW_OTHERS_RESULT: frozenset({Role.TA, Role.INSTRUCTOR, Role.ADMIN}),
    Permission.QUIZ_ATTEMPT_INVALIDATE: frozenset({Role.INSTRUCTOR, Role.ADMIN}),
    Permission.GRADE_OVERRIDE: frozenset({Role.INSTRUCTOR, Role.ADMIN}),
    Permission.APPEAL_RESOLVE: frozenset({Role.INSTRUCTOR, Role.ADMIN}),
    # پروژه
    Permission.PROJECT_CREATE_MANAGED: frozenset({Role.MENTOR, Role.INSTRUCTOR, Role.ADMIN}),
    Permission.PROJECT_WORKSPACE_VIEW: frozenset(
        {Role.PROJECT_MEMBER, Role.PROJECT_LEAD, Role.MENTOR, Role.INSTRUCTOR, Role.ADMIN}
    ),
    Permission.PROJECT_APPLICATION_DECIDE: frozenset(
        {Role.PROJECT_LEAD, Role.INSTRUCTOR, Role.ADMIN}
    ),
    Permission.PROJECT_MILESTONE_MANAGE: frozenset(
        {Role.PROJECT_LEAD, Role.MENTOR, Role.INSTRUCTOR, Role.ADMIN}
    ),
    Permission.PROJECT_MEMBER_REMOVE: frozenset({Role.PROJECT_LEAD, Role.INSTRUCTOR, Role.ADMIN}),
    Permission.PROJECT_CLOSE: frozenset({Role.PROJECT_LEAD, Role.INSTRUCTOR, Role.ADMIN}),
    Permission.DELIVERABLE_SUBMIT: frozenset({Role.PROJECT_MEMBER, Role.PROJECT_LEAD}),
    Permission.DELIVERABLE_REVIEW: frozenset(
        {Role.PROJECT_LEAD, Role.MENTOR, Role.INSTRUCTOR, Role.ADMIN}
    ),
    Permission.CERTIFICATE_ISSUE: frozenset({Role.INSTRUCTOR, Role.ADMIN}),
    # گیمیفیکیشن
    Permission.POINTS_VIEW_OTHERS: frozenset({Role.INSTRUCTOR, Role.SUPPORT, Role.ADMIN}),
    Permission.POINTS_AWARD_MANUAL: frozenset({Role.INSTRUCTOR, Role.ADMIN}),
    Permission.POINTS_RULE_EDIT: frozenset({Role.ADMIN}),
    Permission.POINTS_RECALCULATE: frozenset({Role.ADMIN}),
}

# مجوزهایی که قلمرو دارند: داشتن نقش کافی نیست، scope_id باید تطابق کند.
SCOPED_PERMISSIONS: frozenset[Permission] = frozenset(
    {
        Permission.OFFERING_MANAGE,
        Permission.COURSE_WEEK_EDIT,
        Permission.COURSE_WEEK_PUBLISH,
        Permission.COURSE_WEEK_VIEW_DRAFT,
        Permission.RESOURCE_UPLOAD,
        Permission.ATTENDANCE_RECORD,
        Permission.ENROLLMENT_APPROVE,
        Permission.GRADE_FINAL_SUBMIT,
        Permission.QUIZ_CREATE,
        Permission.QUIZ_GRADE,
        Permission.QUIZ_VIEW_OTHERS_RESULT,
        Permission.QUIZ_ATTEMPT_INVALIDATE,
        Permission.GRADE_OVERRIDE,
        Permission.APPEAL_RESOLVE,
        Permission.PROJECT_WORKSPACE_VIEW,
        Permission.PROJECT_APPLICATION_DECIDE,
        Permission.PROJECT_MILESTONE_MANAGE,
        Permission.PROJECT_MEMBER_REMOVE,
        Permission.PROJECT_CLOSE,
        Permission.DELIVERABLE_SUBMIT,
        Permission.DELIVERABLE_REVIEW,
    }
)

# نقش‌هایی که قلمرو محدودشان نمی‌کند — دسترسی سراسری دارند.
GLOBAL_OVERRIDE_ROLES: frozenset[Role] = frozenset({Role.ADMIN})


@dataclass(frozen=True, slots=True)
class RoleGrant:
    """یک اعطای نقش در یک قلمرو مشخص."""

    role: Role
    scope_type: ScopeType = ScopeType.GLOBAL
    scope_id: uuid.UUID | None = None

    def covers(self, scope_id: uuid.UUID | None) -> bool:
        """آیا این اعطا، قلمرو خواسته‌شده را پوشش می‌دهد؟"""
        if self.scope_type is ScopeType.GLOBAL:
            return True
        if scope_id is None:
            return False
        return self.scope_id == scope_id


@dataclass(frozen=True, slots=True)
class CurrentUser:
    """کاربر احرازشدهٔ درخواست جاری."""

    id: uuid.UUID
    session_id: uuid.UUID
    grants: tuple[RoleGrant, ...] = ()
    # §6.5 — در حالت جعل هویت، شناسهٔ پشتیبان اینجا می‌نشیند.
    impersonated_by: uuid.UUID | None = None

    @property
    def role_codes(self) -> list[str]:
        """فهرست یکتا و مرتب‌شدهٔ کد نقش‌ها — برای JWT و پاسخ /me."""
        return sorted({g.role.value for g in self.grants})

    @property
    def is_impersonating(self) -> bool:
        return self.impersonated_by is not None

    @property
    def highest_rank(self) -> int:
        return max((ROLE_RANK[g.role] for g in self.grants), default=0)

    def has_role(self, role: Role, scope_id: uuid.UUID | None = None) -> bool:
        return any(g.role is role and g.covers(scope_id) for g in self.grants)

    def has_permission(self, permission: Permission, scope_id: uuid.UUID | None = None) -> bool:
        """بررسی خالص مجوز — بدون I/O، قابل تست مستقیم.

        جعل هویت فقط خواندنی است (§6.5)؛ مسدودسازی نوشتن در میان‌افزار انجام
        می‌شود، نه اینجا، چون آنجا متد HTTP در دسترس است.
        """
        allowed = PERMISSION_MATRIX.get(permission, frozenset())
        needs_scope = permission in SCOPED_PERMISSIONS

        for grant in self.grants:
            if grant.role not in allowed:
                continue
            if grant.role in GLOBAL_OVERRIDE_ROLES:
                return True
            if not needs_scope or grant.covers(scope_id):
                return True
        return False


GUEST = CurrentUser(
    id=uuid.UUID(int=0),
    session_id=uuid.UUID(int=0),
    grants=(RoleGrant(Role.GUEST),),
)
