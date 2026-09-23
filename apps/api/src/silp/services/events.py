"""رویدادهای دامنه — PRD §7.13، M5-04.

«رویدادها **درون‌فرایندی** هستند (الگوی ناظر در لایهٔ سرویس)، نه صف
پیام.» سرویس دامنه پیش از `commit` رویداد را منتشر می‌کند و شنونده‌ها
روی **همان نشست** اجرا می‌شوند. پس امتیاز و رویدادی که آن را ساخت با هم
تثبیت می‌شوند یا هیچ‌کدام — تأیید مرحله‌ای که امتیازش ثبت نشده باشد،
وجود ندارد.

## شکست شنونده

هر شنونده داخل savepoint خودش اجرا می‌شود. اگر بشکند، کارش برمی‌گردد،
خطا با جزئیات لاگ می‌شود، و **عمل اصلی ادامه می‌یابد**: استادی که
تحویل‌دادنی را تأیید می‌کند نباید به‌خاطر یک اشکال در محاسبهٔ امتیاز خطای
۵۰۰ ببیند. امتیاز جاافتاده با بازمحاسبه (`reconcile`) قابل ترمیم است؛
تأییدی که انجام نشد، نه.

در تست همین رفتار خطا را پنهان می‌کند. پس `STRICT` در محیط `test`
روشن است و خطای شنونده بالا می‌آید (`tests/conftest.py`).

## شنونده‌ها

شنونده‌ها با `@subscribe` ثبت می‌شوند و ماژولشان در اولین `publish`
بارگذاری می‌شود — نه در import این ماژول، که حلقهٔ `service → events →
listeners → service` می‌ساخت.
"""

from __future__ import annotations

import importlib
import uuid
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

from silp.core.logging import get_logger

log = get_logger("silp.events")

#: ماژول‌هایی که شنونده ثبت می‌کنند. ترتیب مهم است: اعلان پس از امتیاز
#: اجرا می‌شود تا «… و ۵۰ امتیاز گرفتی» امتیاز همین رویداد را ببیند.
LISTENER_MODULES: tuple[str, ...] = (
    "silp.services.point_listeners",
    "silp.services.notification_listeners",
)

#: خطای شنونده بالا بیاید؟ فقط در تست روشن می‌شود.
STRICT = False


# ── رویدادها ───────────────────────────────────────────────────────────
@dataclass(frozen=True, slots=True)
class ResourceCompleted:
    user_id: uuid.UUID
    resource_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class QuizGraded:
    """نمرهٔ یک تلاش ثبت یا عوض شد — تصحیح خودکار، دستی، اعتراض، یا ابطال."""

    attempt_id: uuid.UUID
    #: تصحیح به دست استاد (تشریحی، نهایی کردن) — فقط این به دانشجو اعلان
    #: می‌شود؛ نتیجهٔ تصحیح خودکار را دانشجو همان لحظه روی صفحه می‌بیند.
    manual: bool = False


@dataclass(frozen=True, slots=True)
class QuizResultsPublished:
    quiz_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class AttendanceRecorded:
    offering_id: uuid.UUID
    student_ids: tuple[uuid.UUID, ...]


@dataclass(frozen=True, slots=True)
class EnrollmentCompleted:
    enrollment_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class ApplicationSubmitted:
    application_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class ApplicationDecided:
    """پذیرش، رد یا فهرست انتظار — §7.13. تا M5 فقط پذیرش رویداد داشت."""

    application_id: uuid.UUID
    decision: str


@dataclass(frozen=True, slots=True)
class DeliverableSubmitted:
    deliverable_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class DeliverableReviewed:
    deliverable_id: uuid.UUID
    reviewer_id: uuid.UUID
    decision: str


@dataclass(frozen=True, slots=True)
class ProjectCompleted:
    project_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class SurveyStepCompleted:
    user_id: uuid.UUID
    completed_steps: int


# ── از M6 — فقط شنوندهٔ اعلان دارند ─────────────────────────────────────
@dataclass(frozen=True, slots=True)
class UserRegistered:
    user_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class SessionsRevoked:
    """FR-AUTH-03 — استفادهٔ دوباره از توکن باطل‌شده؛ همهٔ نشست‌ها بسته شد."""

    user_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class EnrollmentRequested:
    """ثبت‌نامی که تأیید استاد می‌خواهد (`PENDING`)."""

    enrollment_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class EnrollmentDecided:
    enrollment_id: uuid.UUID
    approved: bool


@dataclass(frozen=True, slots=True)
class WeekPublished:
    week_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class QuizPublished:
    quiz_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class AppealResolved:
    appeal_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class AnnouncementPublished:
    announcement_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class BadgeAwarded:
    user_id: uuid.UUID
    badge_code: str


@dataclass(frozen=True, slots=True)
class ProjectStalled:
    """شاخص سلامت تازه به `STALLED` رسید — FR-PRJ-07."""

    project_id: uuid.UUID
    days_inactive: int


# ── از M7 — ایده، کارآفرینی، دعوت ──────────────────────────────────────
@dataclass(frozen=True, slots=True)
class IdeaSubmitted:
    idea_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class IdeaWithdrawn:
    """ایده حذف یا بایگانی شد — امتیاز ثبتش برمی‌گردد (§09 «بدون خلق ارزش»)."""

    idea_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class IdeaVoted:
    idea_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class IdeaCommented:
    comment_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class IdeaPromoted:
    idea_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class VentureCreated:
    venture_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class VentureDeleted:
    venture_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class VentureStageChanged:
    change_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class MetricReviewed:
    metric_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class InvitationSent:
    invitation_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class InvitationAccepted:
    invitation_id: uuid.UUID


# ── از M7 بخش ب — پژوهش و آگهی هم‌تیمی ─────────────────────────────────
@dataclass(frozen=True, slots=True)
class ResearchSubmitted:
    submission_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class ResearchReviewed:
    """تأیید یا درخواست اصلاح تحویل یک سطح — §7.13 `ResearchLevelApproved`."""

    submission_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class TopicReviewed:
    """پیشنهاد موضوع دانشجو پذیرفته یا رد شد."""

    topic_id: uuid.UUID
    approved: bool


@dataclass(frozen=True, slots=True)
class OutputReviewed:
    """راستی‌آزمایی یا رد ادعای وضعیت یک خروجی پژوهشی."""

    output_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class OpeningCreated:
    opening_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class OpeningApplied:
    application_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class OpeningDecided:
    """پذیرش، رد، یا بسته شدن خودکار با پر شدن آگهی."""

    application_id: uuid.UUID


# ── از M7 بخش ج — آزمایشگاه شهر هوشمند ─────────────────────────────────
@dataclass(frozen=True, slots=True)
class MilestoneOwnerAssigned:
    milestone_id: uuid.UUID
    assigned_by: uuid.UUID


@dataclass(frozen=True, slots=True)
class CityWorkflowCompleted:
    """هر هشت مرحلهٔ الگوی شهری تأیید شد — منبع نشان «شهرساز» (ADR-0016)."""

    project_id: uuid.UUID


# ── ناظر ───────────────────────────────────────────────────────────────
E = TypeVar("E")
Handler = Callable[[AsyncSession, Any], Awaitable[None]]

_handlers: dict[type, list[Handler]] = defaultdict(list)
_loaded = False


def subscribe(event_type: type[E]) -> Callable[[Callable[[AsyncSession, E], Awaitable[None]]], Any]:
    def register(fn: Callable[[AsyncSession, E], Awaitable[None]]) -> Any:
        _handlers[event_type].append(fn)
        return fn

    return register


def _ensure_loaded() -> None:
    global _loaded  # noqa: PLW0603 — ثبت یک‌بارهٔ شنونده‌ها
    if _loaded:
        return
    for module in LISTENER_MODULES:
        importlib.import_module(module)
    _loaded = True


async def publish(session: AsyncSession, event: object) -> None:
    """اجرای همهٔ شنونده‌های `event` روی همان نشست، هرکدام در savepoint خودش."""
    _ensure_loaded()
    for handler in _handlers.get(type(event), ()):
        try:
            async with session.begin_nested():
                await handler(session, event)
        except Exception:
            if STRICT:
                raise
            log.exception(
                "event_listener_failed",
                event=type(event).__name__,
                listener=getattr(handler, "__qualname__", repr(handler)),
            )


__all__ = [
    "AnnouncementPublished",
    "AppealResolved",
    "ApplicationDecided",
    "ApplicationSubmitted",
    "AttendanceRecorded",
    "BadgeAwarded",
    "CityWorkflowCompleted",
    "DeliverableReviewed",
    "DeliverableSubmitted",
    "EnrollmentCompleted",
    "EnrollmentDecided",
    "EnrollmentRequested",
    "IdeaCommented",
    "IdeaPromoted",
    "IdeaSubmitted",
    "IdeaVoted",
    "IdeaWithdrawn",
    "InvitationAccepted",
    "InvitationSent",
    "MetricReviewed",
    "MilestoneOwnerAssigned",
    "OpeningApplied",
    "OpeningCreated",
    "OpeningDecided",
    "OutputReviewed",
    "ProjectCompleted",
    "ProjectStalled",
    "QuizGraded",
    "QuizPublished",
    "QuizResultsPublished",
    "ResearchReviewed",
    "ResearchSubmitted",
    "ResourceCompleted",
    "SessionsRevoked",
    "SurveyStepCompleted",
    "TopicReviewed",
    "UserRegistered",
    "VentureCreated",
    "VentureDeleted",
    "VentureStageChanged",
    "WeekPublished",
    "publish",
    "subscribe",
]
