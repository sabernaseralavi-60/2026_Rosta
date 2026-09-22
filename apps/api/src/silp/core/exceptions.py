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


# ── پروژه — §5.13 ──────────────────────────────────────────────────────
class ProjectNotOpen(Conflict):
    code = "PROJECT_NOT_OPEN"
    message = "این پروژه پذیرش ندارد."


class ProjectCapacityFull(Conflict):
    code = "PROJECT_CAPACITY_FULL"
    message = "ظرفیت این پروژه تکمیل شده است."


class DuplicateApplication(Conflict):
    code = "DUPLICATE_APPLICATION"
    message = "شما قبلاً برای این پروژه درخواست داده‌اید."


class TooManyOpenApplications(Conflict):
    code = "TOO_MANY_OPEN_APPLICATIONS"
    message = "حداکثر ۵ درخواست باز می‌توانید داشته باشید."


class NotTeamMember(PermissionDenied):
    code = "NOT_TEAM_MEMBER"
    message = "شما عضو تیم این پروژه نیستید."


class MilestoneNotOpen(Conflict):
    code = "MILESTONE_NOT_OPEN"
    message = "این مرحله پذیرای تحویل نیست."


class ConcurrentModification(Conflict):
    """§7.12 — تصادم شماره‌گذاری پس از چند تلاش برطرف نشد."""

    code = "CONCURRENT_MODIFICATION"
    message = "هم‌زمان کس دیگری همین را تغییر داد. دوباره تلاش کنید."
    log_level = "warning"


# ── آموزش — §5.5 ───────────────────────────────────────────────────────
class AlreadyEnrolled(Conflict):
    code = "ALREADY_ENROLLED"
    message = "شما قبلاً در این درس ثبت‌نام کرده‌اید."


class EnrollmentCodeInvalid(PermissionDenied):
    code = "ENROLLMENT_CODE_INVALID"
    message = "کد ثبت‌نام درست نیست."


class OfferingFull(Conflict):
    code = "OFFERING_FULL"
    message = "ظرفیت این ارائه تکمیل شده است."


class OfferingNotOpen(Conflict):
    code = "OFFERING_NOT_OPEN"
    message = "این ارائه پذیرش ثبت‌نام ندارد."


class NotEnrolled(PermissionDenied):
    code = "NOT_ENROLLED"
    message = "شما در این درس ثبت‌نام نکرده‌اید."


class WeekNotPublished(NotFound):
    """هفتهٔ منتشرنشده برای دانشجو **وجود ندارد** — §6.4 قاعدهٔ ۴.

    ۴۰۴ می‌دهد نه ۴۰۳: «این هفته هنوز آماده نیست» خودش افشای برنامهٔ
    درسی است و ۴۰۳ در عمل همان را لو می‌دهد.
    """

    code = "WEEK_NOT_PUBLISHED"
    message = "این هفته هنوز منتشر نشده است."


# ── اشتراک و دسترسی به کتابخانه — ADR-0009 ─────────────────────────────
class SubscriptionRequired(SILPError):
    """پاسخ ۴۰۲: محتوا هست، ولی این کاربر حق دیدنش را نخریده.

    ۴۰۳ نیست چون «اجازه نداری» غلط است؛ راهی برای داشتنِ اجازه هست و
    کلاینت باید همان را نشان دهد. `details.course_slug` و
    `details.plans` به رابط کاربری می‌گویند کدام طرح را پیشنهاد کند.
    """

    status_code = 402
    code = "SUBSCRIPTION_REQUIRED"
    message = "برای دسترسی به این محتوا، اشتراک لازم است."

    def __init__(
        self,
        message: str | None = None,
        *,
        course_slug: str | None = None,
        **kwargs: Any,
    ) -> None:
        details = kwargs.pop("details", {}) or {}
        if course_slug:
            details["course_slug"] = course_slug
        super().__init__(message, details=details, **kwargs)


class EnrollmentRequired(SubscriptionRequired):
    """مادهٔ `ENROLLED` فروختنی نیست — اشتراک هم بازش نمی‌کند."""

    status_code = 403
    code = "ENROLLMENT_REQUIRED"
    message = "این محتوا فقط برای دانشجویان ثبت‌نام‌شدهٔ همین درس است."


class SubscriptionAlreadyActive(Conflict):
    code = "SUBSCRIPTION_ALREADY_ACTIVE"
    message = "شما هم‌اکنون اشتراک فعال دارید."


# ── آزمون — §5.13، §7.3 ────────────────────────────────────────────────
class QuizNotOpen(Conflict):
    code = "QUIZ_NOT_OPEN"
    message = "این آزمون هنوز باز نشده است."


class QuizClosed(Conflict):
    code = "QUIZ_CLOSED"
    message = "مهلت این آزمون به پایان رسیده است."


class AttemptsExhausted(Conflict):
    code = "ATTEMPTS_EXHAUSTED"
    message = "تعداد دفعات مجاز شرکت در آزمون تمام شده است."


class AttemptExpired(Conflict):
    """زمان تلاش تمام شده — پاسخ تازه پذیرفته نمی‌شود (§7.3 قاعدهٔ ۳)."""

    code = "ATTEMPT_EXPIRED"
    message = "زمان آزمون شما به پایان رسیده است."


class AttemptAlreadySubmitted(Conflict):
    code = "ATTEMPT_ALREADY_SUBMITTED"
    message = "این آزمون قبلاً ارسال شده است."


class ActiveAttemptExists(Conflict):
    """دو کلیک سریع روی «شروع آزمون» — قید `idx_one_active_attempt`."""

    code = "ACTIVE_ATTEMPT_EXISTS"
    message = "شما یک آزمون نیمه‌تمام دارید."


class AttemptStillRunning(Conflict):
    """تلاشی که دانشجو هنوز در آن است، نمره نمی‌گیرد."""

    code = "ATTEMPT_STILL_RUNNING"
    message = "این آزمون هنوز تمام نشده است."


class AppealWindowClosed(Conflict):
    """مهلت ۷ روزهٔ اعتراض گذشته — §7.3."""

    code = "APPEAL_WINDOW_CLOSED"
    message = "مهلت اعتراض به این نمره به پایان رسیده است."


class ResultNotAvailable(Conflict):
    """نتیجه هنوز منتشر نشده — `result_visibility` تصمیم می‌گیرد."""

    code = "RESULT_NOT_AVAILABLE"
    message = "نتیجهٔ این آزمون هنوز منتشر نشده است."


class QuizHasAttempts(Conflict):
    """ویرایش سؤال‌های آزمونی که دانشجو در آن شرکت کرده."""

    code = "QUIZ_HAS_ATTEMPTS"
    message = "این آزمون تلاش ثبت‌شده دارد و سؤال‌هایش قابل تغییر نیست."


class QuizHasNoQuestions(Conflict):
    code = "QUIZ_HAS_NO_QUESTIONS"
    message = "آزمون بدون سؤال منتشر نمی‌شود."


# ── فایل — §5.13 ───────────────────────────────────────────────────────
class FileTooLarge(SILPError):
    status_code = 413
    code = "FILE_TOO_LARGE"
    message = "حجم فایل بیش از حد مجاز است."

    def __init__(self, *, max_bytes: int, **kwargs: Any) -> None:
        details = kwargs.pop("details", {}) or {}
        details["max_bytes"] = max_bytes
        super().__init__(details=details, **kwargs)


class ContentTypeNotAllowed(SILPError):
    status_code = 415
    code = "CONTENT_TYPE_NOT_ALLOWED"
    message = "این نوع فایل مجاز نیست."


class FileScanPending(Conflict):
    code = "FILE_SCAN_PENDING"
    message = "فایل در حال بررسی است. کمی صبر کنید."


class UploadIncomplete(Conflict):
    """آپلود روی فضای ذخیره‌سازی تمام نشده — §5.9."""

    code = "UPLOAD_INCOMPLETE"
    message = "آپلود این فایل کامل نشده است."


# ── ۴۲۲ ────────────────────────────────────────────────────────────────
class ValidationFailed(SILPError):
    status_code = 422
    code = "VALIDATION_FAILED"
    message = "اطلاعات واردشده معتبر نیست."


class InvalidDestination(ValidationFailed):
    code = "INVALID_DESTINATION"
    message = "شمارهٔ موبایل یا ایمیل واردشده معتبر نیست."


class PlanScopeMismatch(ValidationFailed):
    """ADR-0009 — طرح «یک درس» بدون درس، یا طرح «همهٔ دروس» با درس."""

    code = "PLAN_SCOPE_MISMATCH"
    message = "این طرح با درس انتخاب‌شده سازگار نیست."


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
