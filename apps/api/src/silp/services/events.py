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

#: ماژول‌هایی که شنونده ثبت می‌کنند. M6 شنوندهٔ اعلان را اینجا می‌افزاید.
LISTENER_MODULES: tuple[str, ...] = ("silp.services.point_listeners",)

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
class ApplicationAccepted:
    application_id: uuid.UUID


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
    "ApplicationAccepted",
    "AttendanceRecorded",
    "DeliverableReviewed",
    "EnrollmentCompleted",
    "ProjectCompleted",
    "QuizGraded",
    "QuizResultsPublished",
    "ResourceCompleted",
    "SurveyStepCompleted",
    "publish",
    "subscribe",
]
