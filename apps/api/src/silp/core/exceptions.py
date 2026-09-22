"""خطاهای دامنه و نگاشت آن‌ها به پاسخ HTTP — PRD §5.1، NFR-12.

قاعده: هر خطای قابل انتظار یک کلاس دارد با `code` ثابت انگلیسی و `message`
فارسی قابل نمایش مستقیم به کاربر. هیچ Stack Trace به کاربر نمی‌رسد.
"""

from __future__ import annotations

from typing import Any


class SILPError(Exception):
    """ریشهٔ همهٔ خطاهای دامنه."""

    status_code: int = 400
    code: str = "BAD_REQUEST"
    message: str = "درخواست نادرست است."
    # خطاهای مورد انتظار در سطح INFO لاگ می‌شوند تا سیگنال واقعی گم نشود.
    log_level: str = "info"

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        details: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.message = message or self.message
        self.code = code or self.code
        self.details = details or {}
        self.headers = headers or {}
        super().__init__(self.message)


# ── ۴۰۱ / ۴۰۳ ──────────────────────────────────────────────────────────
class Unauthenticated(SILPError):
    status_code = 401
    code = "UNAUTHENTICATED"
    message = "برای این کار باید وارد شوید."


class InvalidToken(Unauthenticated):
    code = "TOKEN_INVALID"
    message = "نشست شما معتبر نیست. دوباره وارد شوید."


class TokenExpired(Unauthenticated):
    code = "TOKEN_EXPIRED"
    message = "نشست شما منقضی شده است. دوباره وارد شوید."


class TokenReuseDetected(Unauthenticated):
    """FR-AUTH-03 — استفادهٔ دوباره از توکن باطل‌شده."""

    code = "TOKEN_REUSE_DETECTED"
    message = "به دلیل فعالیت مشکوک، همهٔ نشست‌های شما بسته شد. دوباره وارد شوید."
    log_level = "warning"


class PermissionDenied(SILPError):
    status_code = 403
    code = "PERMISSION_DENIED"
    message = "شما اجازهٔ این کار را ندارید."

    def __init__(
        self,
        message: str | None = None,
        *,
        permission: str | None = None,
        **kwargs: Any,
    ) -> None:
        details = kwargs.pop("details", {}) or {}
        if permission:
            details["permission"] = permission
        super().__init__(message, details=details, **kwargs)


class AccountSuspended(SILPError):
    status_code = 403
    code = "ACCOUNT_SUSPENDED"
    message = "حساب شما غیرفعال شده است. با پشتیبانی تماس بگیرید."


# ── ۴۰۴ / ۴۰۹ ──────────────────────────────────────────────────────────
class NotFound(SILPError):
    status_code = 404
    code = "NOT_FOUND"
    message = "موردی که دنبالش هستید پیدا نشد."


class Conflict(SILPError):
    status_code = 409
    code = "CONFLICT"
    message = "این عملیات با وضعیت فعلی سازگار نیست."


class ProfileIncomplete(SILPError):
    """§7.1 — اقداماتی که نیمرخ کامل می‌خواهند."""

    status_code = 409
    code = "PROFILE_INCOMPLETE"
    message = "برای این کار باید نیمرخ خود را کامل کنید."


# ── ۴۲۲ ────────────────────────────────────────────────────────────────
class ValidationFailed(SILPError):
    status_code = 422
    code = "VALIDATION_FAILED"
    message = "اطلاعات واردشده معتبر نیست."


class InvalidDestination(ValidationFailed):
    code = "INVALID_DESTINATION"
    message = "شمارهٔ موبایل یا ایمیل واردشده معتبر نیست."


# ── OTP — FR-AUTH-01 ───────────────────────────────────────────────────
class OTPInvalid(SILPError):
    status_code = 400
    code = "OTP_INVALID"
    message = "کد واردشده درست نیست."


class OTPExpired(SILPError):
    status_code = 400
    code = "OTP_EXPIRED"
    message = "این کد منقضی شده است. کد تازه بگیرید."


class OTPTooManyAttempts(SILPError):
    status_code = 429
    code = "OTP_TOO_MANY_ATTEMPTS"
    message = "تعداد تلاش‌های شما بیش از حد مجاز بود. کد تازه بگیرید."


# ── ۴۲۹ ────────────────────────────────────────────────────────────────
class RateLimited(SILPError):
    status_code = 429
    code = "RATE_LIMITED"
    message = "تعداد درخواست‌های شما زیاد بود. کمی صبر کنید."

    def __init__(self, *, retry_after: int, **kwargs: Any) -> None:
        details = kwargs.pop("details", {}) or {}
        details["retry_after"] = retry_after
        super().__init__(details=details, headers={"Retry-After": str(retry_after)}, **kwargs)


class OTPRateLimited(RateLimited):
    code = "OTP_RATE_LIMITED"
    message = "برای این شماره به‌تازگی کد فرستاده شده است. کمی صبر کنید."


# ── ۵۰۰ ────────────────────────────────────────────────────────────────
class InternalError(SILPError):
    status_code = 500
    code = "INTERNAL_ERROR"
    message = "خطای غیرمنتظره‌ای رخ داد. اگر ادامه داشت، شناسهٔ خطا را به پشتیبانی بدهید."
    log_level = "error"


class ServiceUnavailable(SILPError):
    status_code = 503
    code = "SERVICE_UNAVAILABLE"
    message = "سرویس موقتاً در دسترس نیست. کمی بعد دوباره تلاش کنید."
    log_level = "error"
