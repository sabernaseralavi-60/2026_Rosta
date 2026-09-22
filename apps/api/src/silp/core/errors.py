"""تبدیل استثنا به پاسخ HTTP با قالب یکسان — PRD §5.1، NFR-12.

قالب ثابت:
    {"error": {"code": ..., "message": ..., "details": {...}, "trace_id": ...}}

هیچ Stack Trace به کاربر نمی‌رسد. خطاهای ۴۰۹ و ۴۲۲ در سطح INFO لاگ می‌شوند،
نه ERROR، تا سیگنال واقعی در نویز گم نشود.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from silp.core.exceptions import InternalError, SILPError
from silp.core.logging import get_logger, trace_id_var

log = get_logger("silp.error")

# پیام فارسی برای کدهای وضعیتی که از خود Starlette می‌آیند.
_STATUS_MESSAGES: dict[int, tuple[str, str]] = {
    400: ("BAD_REQUEST", "درخواست نادرست است."),
    401: ("UNAUTHENTICATED", "برای این کار باید وارد شوید."),
    403: ("PERMISSION_DENIED", "شما اجازهٔ این کار را ندارید."),
    404: ("NOT_FOUND", "موردی که دنبالش هستید پیدا نشد."),
    405: ("METHOD_NOT_ALLOWED", "این عملیات روی این نشانی پشتیبانی نمی‌شود."),
    409: ("CONFLICT", "این عملیات با وضعیت فعلی سازگار نیست."),
    413: ("PAYLOAD_TOO_LARGE", "حجم ارسالی بیش از حد مجاز است."),
    415: ("UNSUPPORTED_MEDIA_TYPE", "قالب ارسالی پشتیبانی نمی‌شود."),
    429: ("RATE_LIMITED", "تعداد درخواست‌های شما زیاد بود. کمی صبر کنید."),
    500: ("INTERNAL_ERROR", "خطای غیرمنتظره‌ای رخ داد."),
    503: ("SERVICE_UNAVAILABLE", "سرویس موقتاً در دسترس نیست."),
}


def error_body(
    *,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
    trace_id: str | None = None,
) -> dict[str, Any]:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
            "trace_id": trace_id or trace_id_var.get() or "",
        }
    }


def _log_for(level: str, event: str, **fields: Any) -> None:
    getattr(log, level, log.info)(event, **fields)


async def silp_error_handler(request: Request, exc: Exception) -> JSONResponse:
    # امضای Starlette `Exception` است. بررسی نوع صریح انجام می‌شود، نه با
    # assert: در اجرای با `python -O` همهٔ assertها حذف می‌شوند.
    if not isinstance(exc, SILPError):
        return await unhandled_error_handler(request, exc)
    _log_for(
        exc.log_level,
        "domain_error",
        code=exc.code,
        status=exc.status_code,
        route=request.url.path,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=error_body(code=exc.code, message=exc.message, details=exc.details),
        headers=exc.headers or None,
    )


async def http_error_handler(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, StarletteHTTPException):
        return await unhandled_error_handler(request, exc)
    code, message = _STATUS_MESSAGES.get(
        exc.status_code, ("HTTP_ERROR", "درخواست قابل انجام نبود.")
    )
    # جزئیات متنی Starlette انگلیسی است و به کاربر نمایش داده نمی‌شود.
    _log_for(
        "warning" if exc.status_code >= 500 else "info",
        "http_error",
        code=code,
        status=exc.status_code,
        route=request.url.path,
        detail=str(exc.detail),
    )
    headers = dict(exc.headers or {})
    return JSONResponse(
        status_code=exc.status_code,
        content=error_body(code=code, message=message),
        headers=headers or None,
    )


async def validation_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """۴۲۲ با details.fields — کلید هر خطا نام فیلد است (§5.1)."""
    if not isinstance(exc, RequestValidationError):
        return await unhandled_error_handler(request, exc)
    fields: dict[str, str] = {}
    for err in exc.errors():
        # loc معمولاً ("body", "field", ...) است؛ بخش اول حذف می‌شود.
        parts = [str(p) for p in err.get("loc", ()) if p not in ("body", "query", "path")]
        name = ".".join(parts) or "__root__"
        fields.setdefault(name, _translate_pydantic(err))

    _log_for("info", "validation_error", route=request.url.path, fields=list(fields))
    return JSONResponse(
        status_code=422,
        content=error_body(
            code="VALIDATION_FAILED",
            message="اطلاعات واردشده معتبر نیست.",
            details={"fields": fields},
        ),
    )


# پیام‌های پرتکرار Pydantic به فارسی. بقیه پیام عمومی می‌گیرند تا جزئیات
# فنی انگلیسی به کاربر نشت نکند.
_PYDANTIC_FA: dict[str, str] = {
    "missing": "این فیلد الزامی است.",
    "string_too_short": "مقدار واردشده کوتاه‌تر از حد مجاز است.",
    "string_too_long": "مقدار واردشده بلندتر از حد مجاز است.",
    "string_pattern_mismatch": "قالب مقدار واردشده درست نیست.",
    "value_error": "مقدار واردشده معتبر نیست.",
    "int_parsing": "باید یک عدد صحیح باشد.",
    "float_parsing": "باید یک عدد باشد.",
    "bool_parsing": "باید بله یا خیر باشد.",
    "uuid_parsing": "شناسهٔ واردشده معتبر نیست.",
    "enum": "مقدار واردشده جزو گزینه‌های مجاز نیست.",
    "greater_than_equal": "مقدار کمتر از حد مجاز است.",
    "less_than_equal": "مقدار بیشتر از حد مجاز است.",
    "too_short": "تعداد موارد کمتر از حد مجاز است.",
    "too_long": "تعداد موارد بیشتر از حد مجاز است.",
}


def _translate_pydantic(err: dict[str, Any]) -> str:
    return _PYDANTIC_FA.get(str(err.get("type", "")), "مقدار واردشده معتبر نیست.")


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """آخرین سد. هر چیزی که تا اینجا رسیده یک اشکال است، نه یک وضعیت."""
    log.error(
        "unhandled_error",
        route=request.url.path,
        method=request.method,
        error_type=type(exc).__name__,
        exc_info=exc,
    )
    fallback = InternalError()
    return JSONResponse(
        status_code=fallback.status_code,
        content=error_body(code=fallback.code, message=fallback.message),
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(SILPError, silp_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_error_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)
