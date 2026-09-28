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
DERIVED_ROLES: frozenset[Role] = frozenset(
    {Role.PROJECT_MEMBER, Role.PROJECT_LEAD, Role.INSTRUCTOR}
)

# §6.1 جدول نقش‌ها: قلمرو `TA` و `INSTRUCTOR` برابر OFFERING است —
# «اختیار کامل روی **ارائهٔ خود**». پس اعطای سراسری این دو، برخلاف
# `COORDINATOR` و `ADMIN` که ذاتاً سراسری‌اند، نباید همهٔ ارائه‌ها را
# باز کند؛ وگرنه «استاد» عملاً یعنی «استاد همهٔ دروس دانشگاه».
#
# اعطای سراسری بی‌معنا نیست: هنوز مجوزهای بی‌قلمرو (مثل
# `PROFILE_VIEW_FULL`) را می‌دهد. فقط دروازهٔ ارائه را باز نمی‌کند.
OFFERING_SCOPED_ROLES: frozenset[Role] = frozenset({Role.TA, Role.INSTRUCTOR})


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
    # M7-12 — پنل مدیریت (ADR-0017)
    USER_VIEW_ALL = "user.view_all"
    ADMIN_METRICS_VIEW = "admin.metrics.view"

    # ── آموزش (M3) ─────────────────────────────────────────────────────
    COURSE_CREATE = "course.create"
    TERM_MANAGE = "term.manage"
    OFFERING_CREATE = "offering.create"
    OFFERING_MANAGE = "offering.manage"
    COURSE_WEEK_EDIT = "course.week.edit"
    COURSE_WEEK_PUBLISH = "course.week.publish"
    COURSE_WEEK_VIEW_DRAFT = "course.week.view_draft"
    RESOURCE_UPLOAD = "course.resource.upload"
    ATTENDANCE_RECORD = "course.attendance.record"
    ENROLLMENT_APPROVE = "course.enrollment.approve"
    GRADE_FINAL_SUBMIT = "course.grade.submit"
    ANNOUNCEMENT_PUBLISH = "course.announcement.publish"
    # ── کتابخانهٔ درس و اشتراک (M3، ADR-0008/0009) ─────────────────────
    MATERIAL_MANAGE = "course.material.manage"
    MATERIAL_VIEW_ALL = "course.material.view_all"
    SUBSCRIPTION_GRANT = "subscription.grant"
    SUBSCRIPTION_VIEW_ALL = "subscription.view_all"
    # ── محتوا و درِ ورودی (ADR-0030/0031) ──────────────────────────────
    CONTENT_PUBLISH = "content.publish"
    INTAKE_MANAGE = "intake.manage"

    # ── آزمون (M4) ─────────────────────────────────────────────────────
    QUIZ_CREATE = "quiz.create"
    QUIZ_GRADE = "quiz.grade"
    QUIZ_VIEW_OTHERS_RESULT = "quiz.result.view_others"
    QUIZ_ATTEMPT_INVALIDATE = "quiz.attempt.invalidate"
    GRADE_OVERRIDE = "grade.override"
    APPEAL_RESOLVE = "quiz.appeal.resolve"

    # ── پروژه (M2) ─────────────────────────────────────────────────────
    PROJECT_CREATE_MANAGED = "project.create.managed"
    PROJECT_EDIT = "project.edit"
    PROJECT_PUBLISH = "project.publish"
    PROJECT_WORKSPACE_VIEW = "project.workspace.view"
    PROJECT_APPLICATION_DECIDE = "project.application.decide"
    PROJECT_MILESTONE_MANAGE = "project.milestone.manage"
    PROJECT_MEMBER_REMOVE = "project.member.remove"
    PROJECT_CLOSE = "project.close"
    DELIVERABLE_SUBMIT = "deliverable.submit"
    DELIVERABLE_REVIEW = "deliverable.review"
    CERTIFICATE_ISSUE = "certificate.issue"
    CERTIFICATE_REVOKE = "certificate.revoke"

    # ── گیمیفیکیشن (M5) ────────────────────────────────────────────────
    POINTS_VIEW_OTHERS = "points.view_others"
    POINTS_AWARD_MANUAL = "points.award.manual"
    POINTS_RULE_EDIT = "points.rule.edit"
    POINTS_RECALCULATE = "points.recalculate"

    # ── اعلان (M6) ─────────────────────────────────────────────────────
    OUTBOX_VIEW = "message.outbox.view"
    OUTBOX_RETRY = "message.outbox.retry"
    MESSAGE_TEMPLATE_EDIT = "message.template.edit"

    # ── ایده و کارآفرینی (M7) ──────────────────────────────────────────
    IDEA_PROMOTE = "idea.promote"
    IDEA_MODERATE = "idea.moderate"
    VENTURE_MANAGE = "venture.manage"
    VENTURE_METRIC_VERIFY = "venture.metric.verify"
    PROJECT_METRIC_VERIFY = "project.metric.verify"

    # ── پژوهش و تیم (M7 بخش ب) ────────────────────────────────────────
    RESEARCH_PARTICIPATE = "research.participate"
    RESEARCH_REVIEW = "research.review"
    RESEARCH_TOPIC_MANAGE = "research.topic.manage"
    TEAM_SEARCH = "team.search"


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
    # فهرست کاربران و شاخص‌های کلان: پشتیبانی باید کاربر را پیدا کند تا
    # بتواند «مشاهده به‌عنوان» بزند؛ تغییر نقش و وضعیت فقط با مدیر است.
    Permission.USER_VIEW_ALL: frozenset({Role.SUPPORT, Role.ADMIN}),
    Permission.ADMIN_METRICS_VIEW: frozenset({Role.SUPPORT, Role.ADMIN}),
    # آموزش
    # تعریف درس، نیم‌سال و ارائه با مدیر آموزشی است (`/admin/courses`،
    # ADR-0020). استاد ارائه نمی‌سازد: ارائه او را استاد می‌کند و کسی خودش را
    # استاد درسی نمی‌کند (ADR-0019 بند ۱).
    Permission.COURSE_CREATE: frozenset({Role.COORDINATOR, Role.ADMIN}),
    Permission.TERM_MANAGE: frozenset({Role.COORDINATOR, Role.ADMIN}),
    Permission.OFFERING_CREATE: frozenset({Role.COORDINATOR, Role.ADMIN}),
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
    Permission.ANNOUNCEMENT_PUBLISH: frozenset(
        {Role.TA, Role.INSTRUCTOR, Role.COORDINATOR, Role.ADMIN}
    ),
    # کتابخانه به درس تعلق دارد، نه به ارائه؛ پس قلمرو ندارد و
    # فقط مدیر آموزشی و مدیر سامانه آن را می‌چینند (ADR-0008).
    Permission.MATERIAL_MANAGE: frozenset({Role.COORDINATOR, Role.ADMIN}),
    # «همهٔ مواد را ببین» دروازهٔ اشتراک را دور می‌زند — کارکنان آموزش
    # برای پشتیبانی لازمش دارند (ADR-0009).
    Permission.MATERIAL_VIEW_ALL: frozenset(
        {Role.TA, Role.INSTRUCTOR, Role.COORDINATOR, Role.SUPPORT, Role.ADMIN}
    ),
    Permission.SUBSCRIPTION_GRANT: frozenset({Role.SUPPORT, Role.ADMIN}),
    Permission.SUBSCRIPTION_VIEW_ALL: frozenset({Role.SUPPORT, Role.ADMIN}),
    # مالک سایت = ADMIN؛ انتشار محتوا و صندوق درخواست‌ها (شمارهٔ تماس بازدیدکننده) دست او است.
    Permission.CONTENT_PUBLISH: frozenset({Role.ADMIN}),
    Permission.INTAKE_MANAGE: frozenset({Role.ADMIN}),
    # آزمون
    Permission.QUIZ_CREATE: frozenset({Role.TA, Role.INSTRUCTOR, Role.ADMIN}),
    Permission.QUIZ_GRADE: frozenset({Role.TA, Role.INSTRUCTOR, Role.ADMIN}),
    Permission.QUIZ_VIEW_OTHERS_RESULT: frozenset({Role.TA, Role.INSTRUCTOR, Role.ADMIN}),
    Permission.QUIZ_ATTEMPT_INVALIDATE: frozenset({Role.INSTRUCTOR, Role.ADMIN}),
    Permission.GRADE_OVERRIDE: frozenset({Role.INSTRUCTOR, Role.ADMIN}),
    Permission.APPEAL_RESOLVE: frozenset({Role.INSTRUCTOR, Role.ADMIN}),
    # پروژه
    Permission.PROJECT_CREATE_MANAGED: frozenset({Role.MENTOR, Role.INSTRUCTOR, Role.ADMIN}),
    # §5.7 «ویرایش» و «انتشار» را به مدیر پروژه می‌دهد. استاد هم
    # هست چون پروژهٔ متصل به ارائهٔ او زیر نظر اوست (پانویس ۷ §6.2).
    Permission.PROJECT_EDIT: frozenset({Role.PROJECT_LEAD, Role.INSTRUCTOR, Role.ADMIN}),
    Permission.PROJECT_PUBLISH: frozenset({Role.PROJECT_LEAD, Role.INSTRUCTOR, Role.ADMIN}),
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
    # ابطال، اعتبار یک سند عمومی را برمی‌دارد؛ فقط مدیر، با دلیل و لاگ.
    Permission.CERTIFICATE_REVOKE: frozenset({Role.ADMIN}),
    # گیمیفیکیشن
    Permission.POINTS_VIEW_OTHERS: frozenset({Role.INSTRUCTOR, Role.SUPPORT, Role.ADMIN}),
    Permission.POINTS_AWARD_MANUAL: frozenset({Role.INSTRUCTOR, Role.ADMIN}),
    Permission.POINTS_RULE_EDIT: frozenset({Role.ADMIN}),
    Permission.POINTS_RECALCULATE: frozenset({Role.ADMIN}),
    # اعلان — FR-ADM-04 «سلامت فنی: صف اعلان‌ها». پشتیبانی می‌بیند چرا
    # پیامک کاربری نرسید؛ فرستادن دوباره و ویرایش متن با مدیر است.
    Permission.OUTBOX_VIEW: frozenset({Role.SUPPORT, Role.ADMIN}),
    Permission.OUTBOX_RETRY: frozenset({Role.ADMIN}),
    Permission.MESSAGE_TEMPLATE_EDIT: frozenset({Role.ADMIN}),
    # ایده — FR-IDEA-03 «استاد یا مدیر می‌تواند ارتقا دهد». استاد اینجا
    # قلمرو ندارد: ایده به هیچ ارائه‌ای تعلق ندارد و هر استادی که ارائه‌ای
    # دارد، داور ایده هم هست.
    Permission.IDEA_PROMOTE: frozenset({Role.INSTRUCTOR, Role.COORDINATOR, Role.ADMIN}),
    Permission.IDEA_MODERATE: frozenset({Role.COORDINATOR, Role.SUPPORT, Role.ADMIN}),
    # کارآفرینی — ADR-0014. شاخص کسب‌وکار را کارکنان تأیید می‌کنند، نه
    # هم‌بنیان‌گذار: امتیاز `STARTUP` از «نتیجهٔ واقعی» می‌آید و تأیید
    # درون‌تیمی همان خوداظهاری است.
    Permission.VENTURE_MANAGE: frozenset({Role.COORDINATOR, Role.ADMIN}),
    Permission.VENTURE_METRIC_VERIFY: frozenset(
        {Role.MENTOR, Role.INSTRUCTOR, Role.COORDINATOR, Role.ADMIN}
    ),
    # شاخص پروژهٔ عملیاتی را مدیر همان پروژه تأیید می‌کند (FR-VEN-02
    # «داشبورد پروژه عملکرد هر عضو را نشان می‌دهد»)، و شاخص خود مدیر را
    # منتور یا استاد.
    Permission.PROJECT_METRIC_VERIFY: frozenset(
        {Role.PROJECT_LEAD, Role.MENTOR, Role.INSTRUCTOR, Role.ADMIN}
    ),
    # پژوهش — ADR-0015. مسیر چهارسطحی مال دانشجوست (FR-RES-01)؛ منتور و
    # دستیار آموزشی هم معمولاً دانشجوی ارشدند و مسیر خودشان را دارند.
    Permission.RESEARCH_PARTICIPATE: frozenset({Role.STUDENT, Role.MENTOR, Role.TA}),
    # تأیید سطح و راستی‌آزمایی مقاله: همان کسانی که تحویل‌دادنی را بازبینی
    # می‌کنند، بی‌قلمرو — مسیر پژوهش به هیچ پروژه یا ارائه‌ای تعلق ندارد.
    Permission.RESEARCH_REVIEW: frozenset(
        {Role.MENTOR, Role.INSTRUCTOR, Role.COORDINATOR, Role.ADMIN}
    ),
    # FR-RES-03 «استاد موضوعات پژوهشی باز را ثبت می‌کند». پیشنهاد دانشجو
    # هم پذیرفته است، ولی تا تأیید همین نقش‌ها باز نمی‌شود.
    Permission.RESEARCH_TOPIC_MANAGE: frozenset({Role.INSTRUCTOR, Role.COORDINATOR, Role.ADMIN}),
    # FR-TEAM-01 — جستجوی هم‌تیمی. کادر آموزشی هم برای تیم‌سازی پروژه‌هایش.
    Permission.TEAM_SEARCH: frozenset(
        {Role.STUDENT, Role.MENTOR, Role.TA, Role.INSTRUCTOR, Role.COORDINATOR, Role.ADMIN}
    ),
}

# مجوزهایی که قلمروشان **ارائه** است. برای این‌ها، اعطای سراسری
# `TA`/`INSTRUCTOR` کافی نیست و باید اعطای همان ارائه وجود داشته باشد —
# چه ثبت‌شده در `user_roles`، چه مشتق از `course_offerings.instructor_id`.
OFFERING_PERMISSIONS: frozenset[Permission] = frozenset(
    {
        Permission.OFFERING_MANAGE,
        Permission.COURSE_WEEK_EDIT,
        Permission.COURSE_WEEK_PUBLISH,
        Permission.COURSE_WEEK_VIEW_DRAFT,
        Permission.RESOURCE_UPLOAD,
        Permission.ATTENDANCE_RECORD,
        Permission.ENROLLMENT_APPROVE,
        Permission.GRADE_FINAL_SUBMIT,
        Permission.ANNOUNCEMENT_PUBLISH,
        Permission.QUIZ_CREATE,
        Permission.QUIZ_GRADE,
        Permission.QUIZ_VIEW_OTHERS_RESULT,
        Permission.QUIZ_ATTEMPT_INVALIDATE,
        Permission.GRADE_OVERRIDE,
        Permission.APPEAL_RESOLVE,
    }
)

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
        Permission.ANNOUNCEMENT_PUBLISH,
        Permission.QUIZ_CREATE,
        Permission.QUIZ_GRADE,
        Permission.QUIZ_VIEW_OTHERS_RESULT,
        Permission.QUIZ_ATTEMPT_INVALIDATE,
        Permission.GRADE_OVERRIDE,
        Permission.APPEAL_RESOLVE,
        Permission.PROJECT_EDIT,
        Permission.PROJECT_PUBLISH,
        Permission.PROJECT_WORKSPACE_VIEW,
        Permission.PROJECT_APPLICATION_DECIDE,
        Permission.PROJECT_MILESTONE_MANAGE,
        Permission.PROJECT_MEMBER_REMOVE,
        Permission.PROJECT_CLOSE,
        Permission.DELIVERABLE_SUBMIT,
        Permission.DELIVERABLE_REVIEW,
        Permission.PROJECT_METRIC_VERIFY,
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
        # قلمرو ارائه سخت‌گیرتر است: اعطای سراسریِ نقشِ ارائه‌ای کفایت
        # نمی‌کند و باید اعطای همان ارائه باشد (§6.1).
        offering_bound = permission in OFFERING_PERMISSIONS

        for grant in self.grants:
            if grant.role not in allowed:
                continue
            if grant.role in GLOBAL_OVERRIDE_ROLES:
                return True
            if (
                offering_bound
                and grant.role in OFFERING_SCOPED_ROLES
                and grant.scope_type is not ScopeType.OFFERING
            ):
                continue
            if not needs_scope or grant.covers(scope_id):
                return True
        return False


GUEST = CurrentUser(
    id=uuid.UUID(int=0),
    session_id=uuid.UUID(int=0),
    grants=(RoleGrant(Role.GUEST),),
)
