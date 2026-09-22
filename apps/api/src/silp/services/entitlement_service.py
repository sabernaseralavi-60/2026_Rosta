"""سنجش دسترسی به کتابخانهٔ درس — ADR-0009.

یک قاعده، و همهٔ این ماژول برای اجرای بی‌استثنای همان است:

> متریال هر درس برای **دانشجوی همان درس** رایگان است؛ برای بقیه با
> **اشتراک ماهانه**.

سه سطح مادهٔ درسی (`course_materials.access_tier`) و پنج دلیل مجاز بودن
در جدول زیر به هم می‌رسند:

| سطح ماده  | مهمان | کاربر عادی | مشترک | دانشجوی درس | کارکنان آموزش |
|-----------|-------|------------|-------|--------------|----------------|
| PUBLIC    | ✓     | ✓          | ✓     | ✓            | ✓              |
| SUBSCRIBER| ✗     | ✗ (۴۰۲)    | ✓     | ✓            | ✓              |
| ENROLLED  | ✗     | ✗ (۴۰۳)    | ✗     | ✓            | ✓              |

**سطر `ENROLLED` عمداً با اشتراک باز نمی‌شود.** کلید آزمون و تکلیف
نمره‌دار فروختنی نیست؛ اگر یک روز فروخته شود، «رایگان برای دانشجوی
درس» دیگر امتیاز نیست، و درس هم دیگر درس نیست.

**بدون N+1 (§5.14):** هیچ تابعی اینجا برای یک ماده کوئری نمی‌زند.
`context_for()` یک بار همهٔ دروسِ دخیل را برای یک کاربر می‌خواند و
`decide()` پس از آن محاسبهٔ خالص است — بدون I/O، و به همین دلیل مستقیم
قابل تست.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from silp.core.exceptions import EnrollmentRequired, SubscriptionRequired
from silp.core.permissions import CurrentUser, Permission
from silp.models.access import Subscription
from silp.models.education import CourseMaterial, CourseOffering, Enrollment

# ثبت‌نامی که دسترسی رایگان می‌سازد. `COMPLETED` هم هست: دانشجویی که
# درس را پاس کرده، جزوهٔ همان درس را از دست نمی‌دهد.
ENTITLING_ENROLLMENT_STATUSES = ("ACTIVE", "COMPLETED")


class AccessReason(StrEnum):
    """چرا این کاربر اجازه دارد. در رابط کاربری و در لاگ رویداد می‌آید."""

    PUBLIC = "PUBLIC"
    ENROLLED = "ENROLLED"
    SUBSCRIPTION = "SUBSCRIPTION"
    STAFF = "STAFF"


class AccessBlocker(StrEnum):
    """چه چیزی لازم است تا اجازه پیدا کند — کلاینت از همین دکمه می‌سازد."""

    SUBSCRIPTION = "SUBSCRIPTION"
    ENROLLMENT = "ENROLLMENT"


REASON_TITLE_FA: dict[AccessReason, str] = {
    AccessReason.PUBLIC: "این محتوا برای همه آزاد است.",
    AccessReason.ENROLLED: "شما دانشجوی این درس هستید؛ محتوای درس برایتان رایگان است.",
    AccessReason.SUBSCRIPTION: "با اشتراک فعال شما در دسترس است.",
    AccessReason.STAFF: "به‌عنوان عضو کادر آموزشی به همهٔ محتوا دسترسی دارید.",
}

BLOCKER_TITLE_FA: dict[AccessBlocker, str] = {
    AccessBlocker.SUBSCRIPTION: "برای دیدن این محتوا اشتراک بگیرید — یا در همین درس ثبت‌نام کنید.",
    AccessBlocker.ENROLLMENT: "این محتوا فقط برای دانشجویان ثبت‌نام‌شدهٔ همین درس است.",
}


@dataclass(frozen=True, slots=True)
class AccessDecision:
    """نتیجهٔ سنجش — همیشه دلیل‌دار، چه مجاز چه غیرمجاز.

    رابط کاربری هرگز نباید خودش تصمیم بگیرد قفل را نشان دهد یا نه؛
    `note_fa` همان جمله‌ای است که کنار قفل می‌نشیند (اصل ۳ §00).
    """

    allowed: bool
    tier: str
    reason: AccessReason | None = None
    blocker: AccessBlocker | None = None

    @property
    def note_fa(self) -> str:
        if self.allowed and self.reason is not None:
            return REASON_TITLE_FA[self.reason]
        if self.blocker is not None:
            return BLOCKER_TITLE_FA[self.blocker]
        return "این محتوا در دسترس شما نیست."


@dataclass(frozen=True, slots=True)
class AccessContext:
    """آنچه برای سنجش لازم است، یک‌بار خوانده و بارها استفاده می‌شود.

    `is_staff` سراسری است، نه به‌ازای درس: مجوز `MATERIAL_VIEW_ALL`
    قلمرو ندارد (کتابخانه به درس تعلق دارد، نه به ارائه).
    """

    enrolled_course_ids: frozenset[uuid.UUID] = field(default_factory=frozenset)
    subscribed_course_ids: frozenset[uuid.UUID] = field(default_factory=frozenset)
    has_global_subscription: bool = False
    instructing_course_ids: frozenset[uuid.UUID] = field(default_factory=frozenset)
    is_staff: bool = False
    is_authenticated: bool = False

    def is_enrolled_in(self, course_id: uuid.UUID) -> bool:
        return course_id in self.enrolled_course_ids

    def is_subscribed_to(self, course_id: uuid.UUID) -> bool:
        return self.has_global_subscription or course_id in self.subscribed_course_ids

    def teaches(self, course_id: uuid.UUID) -> bool:
        return course_id in self.instructing_course_ids


GUEST_CONTEXT = AccessContext()


def decide(*, course_id: uuid.UUID, tier: str, ctx: AccessContext) -> AccessDecision:
    """سنجش خالص — بدون I/O. جدول بالای این فایل، سطر به سطر.

    ترتیب بررسی از «قوی‌ترین دلیل» شروع می‌شود تا `reason` همان چیزی
    باشد که کاربر انتظارش را دارد: دانشجویی که اشتراک هم دارد، پیام
    «چون دانشجوی این درسی» می‌بیند، نه «چون اشتراک داری».
    """
    if ctx.is_staff or ctx.teaches(course_id):
        return AccessDecision(allowed=True, tier=tier, reason=AccessReason.STAFF)

    if tier == "PUBLIC":
        return AccessDecision(allowed=True, tier=tier, reason=AccessReason.PUBLIC)

    if ctx.is_enrolled_in(course_id):
        return AccessDecision(allowed=True, tier=tier, reason=AccessReason.ENROLLED)

    if tier == "ENROLLED":
        # اشتراک اینجا عمداً بررسی نمی‌شود — این سطح فروختنی نیست.
        return AccessDecision(allowed=False, tier=tier, blocker=AccessBlocker.ENROLLMENT)

    if ctx.is_subscribed_to(course_id):
        return AccessDecision(allowed=True, tier=tier, reason=AccessReason.SUBSCRIPTION)

    return AccessDecision(allowed=False, tier=tier, blocker=AccessBlocker.SUBSCRIPTION)


def raise_for(decision: AccessDecision, *, course_slug: str | None = None) -> None:
    """تبدیل یک سنجش ردشده به خطای HTTP درست — ۴۰۲ یا ۴۰۳."""
    if decision.allowed:
        return
    if decision.blocker is AccessBlocker.ENROLLMENT:
        raise EnrollmentRequired(decision.note_fa, course_slug=course_slug)
    raise SubscriptionRequired(decision.note_fa, course_slug=course_slug)


class EntitlementService:
    """خواندن وضعیت دسترسی کاربر از پایگاه‌داده."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def context_for(
        self,
        user: CurrentUser | None,
        *,
        course_ids: list[uuid.UUID] | None = None,
    ) -> AccessContext:
        """بافت دسترسی یک کاربر — سه کوئری، مستقل از تعداد مواد.

        `course_ids` اختیاری است و فقط کوئری‌ها را باریک‌تر می‌کند؛ نبودش
        یعنی «همهٔ دروسی که این کاربر با آن‌ها نسبتی دارد».
        """
        if user is None:
            return GUEST_CONTEXT

        is_staff = user.has_permission(Permission.MATERIAL_VIEW_ALL)
        if is_staff:
            # کارکنان همه چیز را می‌بینند؛ سه کوئری بعدی بی‌فایده است.
            return AccessContext(is_staff=True, is_authenticated=True)

        enrolled = await self._enrolled_course_ids(user.id, course_ids)
        instructing = await self._instructing_course_ids(user.id, course_ids)
        global_sub, scoped = await self._subscriptions(user.id)

        return AccessContext(
            enrolled_course_ids=enrolled,
            subscribed_course_ids=scoped,
            has_global_subscription=global_sub,
            instructing_course_ids=instructing,
            is_staff=False,
            is_authenticated=True,
        )

    async def _enrolled_course_ids(
        self, user_id: uuid.UUID, course_ids: list[uuid.UUID] | None
    ) -> frozenset[uuid.UUID]:
        stmt = (
            select(CourseOffering.course_id)
            .join(Enrollment, Enrollment.offering_id == CourseOffering.id)
            .where(
                Enrollment.student_id == user_id,
                Enrollment.status.in_(ENTITLING_ENROLLMENT_STATUSES),
                CourseOffering.deleted_at.is_(None),
            )
            .distinct()
        )
        if course_ids:
            stmt = stmt.where(CourseOffering.course_id.in_(course_ids))
        return frozenset(await self.session.scalars(stmt))

    async def _instructing_course_ids(
        self, user_id: uuid.UUID, course_ids: list[uuid.UUID] | None
    ) -> frozenset[uuid.UUID]:
        """درسی که خودِ کاربر ارائه‌اش را می‌دهد.

        استادی که نقش سراسری `INSTRUCTOR` ندارد (مثلاً مدرس مهمان با
        اعطای قلمرودار) از این راه به کتابخانهٔ درس خودش می‌رسد.
        """
        stmt = (
            select(CourseOffering.course_id)
            .where(
                CourseOffering.instructor_id == user_id,
                CourseOffering.deleted_at.is_(None),
            )
            .distinct()
        )
        if course_ids:
            stmt = stmt.where(CourseOffering.course_id.in_(course_ids))
        return frozenset(await self.session.scalars(stmt))

    async def _subscriptions(self, user_id: uuid.UUID) -> tuple[bool, frozenset[uuid.UUID]]:
        """(اشتراک همه‌دروس دارد؟، دروسی که اشتراک تک‌درسی دارند)."""
        now = _now()
        rows = await self.session.scalars(
            select(Subscription).where(
                Subscription.user_id == user_id,
                Subscription.status == "ACTIVE",
                Subscription.starts_at <= now,
                Subscription.ends_at > now,
            )
        )
        has_global = False
        scoped: set[uuid.UUID] = set()
        for sub in rows:
            if sub.course_id is None:
                has_global = True
            else:
                scoped.add(sub.course_id)
        return has_global, frozenset(scoped)

    async def decide_for_material(
        self, material: CourseMaterial, user: CurrentUser | None
    ) -> AccessDecision:
        """سنجش یک مادهٔ منفرد — برای مسیر دانلود که فقط یکی را می‌خواهد."""
        ctx = await self.context_for(user, course_ids=[material.course_id])
        return decide(course_id=material.course_id, tier=material.access_tier, ctx=ctx)

    async def active_subscriptions(self, user_id: uuid.UUID) -> list[Subscription]:
        now = _now()
        rows = await self.session.scalars(
            select(Subscription)
            .where(
                Subscription.user_id == user_id,
                Subscription.status.in_(("ACTIVE", "PENDING")),
                or_(Subscription.ends_at > now, Subscription.status == "PENDING"),
            )
            .order_by(Subscription.ends_at.desc())
        )
        return list(rows)


def _now() -> datetime:
    return datetime.now(UTC)


__all__ = [
    "BLOCKER_TITLE_FA",
    "ENTITLING_ENROLLMENT_STATUSES",
    "GUEST_CONTEXT",
    "REASON_TITLE_FA",
    "AccessBlocker",
    "AccessContext",
    "AccessDecision",
    "AccessReason",
    "EntitlementService",
    "decide",
    "raise_for",
]
