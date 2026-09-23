"""میان‌افزارها — ردیابی، لاگ درخواست، و محدودیت جعل هویت.

NFR-16: trace_id از هدر ورودی تا کوئری دیتابیس و کار پس‌زمینه منتشر می‌شود.
NFR-13: هر درخواست یک رکورد با route و duration_ms تولید می‌کند.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from silp.core.logging import (
    client_ip_var,
    get_logger,
    trace_id_var,
    user_agent_var,
    user_id_var,
)

log = get_logger("silp.request")

TRACE_HEADER = "X-Trace-Id"
# مسیرهایی که لاگ درخواست برایشان نویز است.
QUIET_PATHS = frozenset({"/health", "/health/live", "/health/ready", "/metrics"})

RequestHandler = Callable[[Request], Awaitable[Response]]


class TraceMiddleware(BaseHTTPMiddleware):
    """اختصاص یا پذیرش trace_id و انتشار آن در context."""

    async def dispatch(self, request: Request, call_next: RequestHandler) -> Response:
        incoming = request.headers.get(TRACE_HEADER, "").strip()
        # شناسهٔ ورودی فقط وقتی پذیرفته می‌شود که UUID معتبر باشد؛ در غیر این
        # صورت مهاجم می‌تواند لاگ را با مقدار دلخواه آلوده کند.
        try:
            trace_id = str(uuid.UUID(incoming)) if incoming else str(uuid.uuid4())
        except ValueError:
            trace_id = str(uuid.uuid4())

        token = trace_id_var.set(trace_id)
        ip_token = client_ip_var.set(client_ip(request))
        agent_token = user_agent_var.set((request.headers.get("User-Agent") or "")[:500] or None)
        structlog.contextvars.bind_contextvars(trace_id=trace_id)
        request.state.trace_id = trace_id
        try:
            response = await call_next(request)
        finally:
            trace_id_var.reset(token)
            client_ip_var.reset(ip_token)
            user_agent_var.reset(agent_token)
            structlog.contextvars.unbind_contextvars("trace_id")

        response.headers[TRACE_HEADER] = trace_id
        return response


class RequestLogMiddleware(BaseHTTPMiddleware):
    """یک رکورد JSON به‌ازای هر درخواست — NFR-13."""

    async def dispatch(self, request: Request, call_next: RequestHandler) -> Response:
        started = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - started) * 1000, 2)

        path = request.url.path
        if path in QUIET_PATHS:
            return response

        # الگوی مسیر (نه مقدار واقعی پارامتر) تا کاردینالیتی لاگ منفجر نشود.
        route = getattr(request.scope.get("route"), "path", path)
        log.info(
            "http_request",
            route=route,
            method=request.method,
            status=response.status_code,
            duration_ms=duration_ms,
            client_ip=client_ip(request),
        )
        response.headers["Server-Timing"] = f"app;dur={duration_ms}"
        return response


# §6.5 — جعل هویت فقط خواندنی است. این بررسی در وابستگی احراز هویت
# (silp.api.deps.get_current_user) انجام می‌شود، چون فقط آنجا توکن رمزگشایی
# شده و مشخص است که درخواست جعل هویت است یا نه.
UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def client_ip(request: Request) -> str:
    """IP واقعی کاربر پشت Nginx.

    فقط اولین مقدار X-Forwarded-For خوانده می‌شود و تنها زمانی که پروکسی
    مورد اعتماد آن را گذاشته باشد؛ Nginx در §12 این هدر را بازنویسی می‌کند.
    """
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real = request.headers.get("X-Real-IP")
    if real:
        return real.strip()
    return request.client.host if request.client else "unknown"


def bind_user(user_id: uuid.UUID | None) -> None:
    """اتصال user_id به context لاگ پس از احراز هویت."""
    value = str(user_id) if user_id else None
    user_id_var.set(value)
    if value:
        structlog.contextvars.bind_contextvars(user_id=value)
