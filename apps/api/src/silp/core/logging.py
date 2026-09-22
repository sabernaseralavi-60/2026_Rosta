"""لاگ ساختاریافتهٔ JSON — NFR-13.

فیلدهای اجباری: timestamp, level, trace_id, user_id, route, duration_ms.
هرگز لاگ نمی‌شود: رمز، توکن، OTP، کد ملی، پاسخ آزمون، محتوای پیام.
"""

from __future__ import annotations

import logging
import sys
from contextvars import ContextVar
from typing import Any, Literal

import structlog

# trace_id و user_id از میان‌افزار تا کوئری و کار پس‌زمینه منتشر می‌شوند (NFR-16).
trace_id_var: ContextVar[str | None] = ContextVar("trace_id", default=None)
user_id_var: ContextVar[str | None] = ContextVar("user_id", default=None)

# کلیدهایی که هرگز نباید در لاگ ظاهر شوند (NFR-13). تطبیق روی زیررشته است،
# پس `otp_code`، `new_password` و `national_id_enc` هم گرفته می‌شوند.
REDACTED_KEY_PARTS = (
    "password",
    "secret",
    "token",
    "otp",
    "code_hash",
    "national_id",
    "authorization",
    "cookie",
    "api_key",
    "answer",
)
REDACTED = "[حذف‌شده]"


def _scrub(_logger: Any, _name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    """پاک‌سازی مقادیر حساس پیش از نوشتن. دفاع در عمق، نه جایگزین دقت."""
    for key in list(event_dict):
        lowered = key.lower()
        if any(part in lowered for part in REDACTED_KEY_PARTS):
            event_dict[key] = REDACTED
    return event_dict


def _bind_context(_logger: Any, _name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    """افزودن trace_id و user_id از context به هر رکورد."""
    event_dict.setdefault("trace_id", trace_id_var.get())
    event_dict.setdefault("user_id", user_id_var.get())
    return event_dict


def configure_logging(
    level: str = "INFO",
    *,
    renderer: Literal["json", "console"] = "json",
) -> None:
    """پیکربندی سراسری لاگ. یک‌بار در زمان راه‌اندازی صدا زده می‌شود."""
    shared: list[Any] = [
        structlog.contextvars.merge_contextvars,
        _bind_context,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        _scrub,
    ]

    final: Any = (
        structlog.dev.ConsoleRenderer(colors=True)
        if renderer == "console"
        else structlog.processors.JSONRenderer(ensure_ascii=False)
    )

    structlog.configure(
        processors=[
            *shared,
            structlog.processors.format_exc_info,
            final,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelNamesMapping()[level]),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )

    # لاگ‌های کتابخانه‌ها (uvicorn، sqlalchemy) هم از همین مسیر عبور کنند.
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level)
    for noisy in ("uvicorn.access", "uvicorn.error", "sqlalchemy.engine"):
        logging.getLogger(noisy).handlers.clear()
        logging.getLogger(noisy).propagate = True


def get_logger(name: str = "silp") -> Any:
    return structlog.get_logger(name)
