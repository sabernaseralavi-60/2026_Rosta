"""کدهای عمل حسابرسی — FR-ADM-02، ADR-0017.

«اعمال حساس: تغییر نقش، تغییر نمره، حذف، جعل هویت، تغییر قواعد امتیاز.»
هر ردیف `audit_logs` یکی از این کدهاست؛ عنوان فارسی فقط برای نمایش است و
در دیتابیس نمی‌نشیند تا تغییر متن، لاگ هفت‌سالهٔ قدیمی را بی‌معنا نکند.
"""

from __future__ import annotations

from typing import Final

# ── کاربر و نقش ────────────────────────────────────────────────────────
ROLE_GRANTED: Final = "ROLE_GRANTED"
ROLE_REVOKED: Final = "ROLE_REVOKED"
USER_STATUS_CHANGED: Final = "USER_STATUS_CHANGED"
# ── جعل هویت — §6.5 ────────────────────────────────────────────────────
IMPERSONATION_STARTED: Final = "IMPERSONATION_STARTED"
IMPERSONATION_ENDED: Final = "IMPERSONATION_ENDED"
IMPERSONATED_REQUEST: Final = "IMPERSONATED_REQUEST"
# ── نمره ───────────────────────────────────────────────────────────────
GRADE_OVERRIDDEN: Final = "GRADE_OVERRIDDEN"
FINAL_GRADE_SET: Final = "FINAL_GRADE_SET"
ATTEMPT_VOIDED: Final = "ATTEMPT_VOIDED"
APPEAL_RESOLVED: Final = "APPEAL_RESOLVED"
# ── امتیاز ─────────────────────────────────────────────────────────────
POINT_RULE_UPDATED: Final = "POINT_RULE_UPDATED"
POINTS_RECALCULATED: Final = "POINTS_RECALCULATED"
POINT_ENTRY_REVERSED: Final = "POINT_ENTRY_REVERSED"
# ── گواهی و پیام ───────────────────────────────────────────────────────
CERTIFICATE_REVOKED: Final = "CERTIFICATE_REVOKED"
MESSAGE_TEMPLATE_UPDATED: Final = "MESSAGE_TEMPLATE_UPDATED"

ACTION_TITLE_FA: dict[str, str] = {
    ROLE_GRANTED: "اعطای نقش",
    ROLE_REVOKED: "سلب نقش",
    USER_STATUS_CHANGED: "تغییر وضعیت حساب",
    IMPERSONATION_STARTED: "شروع مشاهده به‌عنوان کاربر",
    IMPERSONATION_ENDED: "پایان مشاهده به‌عنوان کاربر",
    IMPERSONATED_REQUEST: "درخواست در حالت مشاهده به‌عنوان کاربر",
    GRADE_OVERRIDDEN: "بازنویسی نمرهٔ سؤال",
    FINAL_GRADE_SET: "ثبت یا تغییر نمرهٔ نهایی درس",
    ATTEMPT_VOIDED: "ابطال تلاش آزمون",
    APPEAL_RESOLVED: "رسیدگی به اعتراض نمره",
    POINT_RULE_UPDATED: "ویرایش قاعدهٔ امتیاز",
    POINTS_RECALCULATED: "بازمحاسبهٔ گذشته‌نگر امتیاز",
    POINT_ENTRY_REVERSED: "اصلاح ردیف امتیاز",
    CERTIFICATE_REVOKED: "ابطال گواهی",
    MESSAGE_TEMPLATE_UPDATED: "ویرایش الگوی پیام",
}

ENTITY_TITLE_FA: dict[str, str] = {
    "USER": "کاربر",
    "QUIZ_ANSWER": "پاسخ آزمون",
    "QUIZ_ATTEMPT": "تلاش آزمون",
    "GRADE_APPEAL": "اعتراض نمره",
    "ENROLLMENT": "ثبت‌نام درس",
    "POINT_RULE": "قاعدهٔ امتیاز",
    "POINT_ENTRY": "ردیف امتیاز",
    "CERTIFICATE": "گواهی",
    "MESSAGE_TEMPLATE": "الگوی پیام",
    "REQUEST": "درخواست",
}


def title_of(action: str) -> str:
    return ACTION_TITLE_FA.get(action, action)


__all__ = [
    "ACTION_TITLE_FA",
    "APPEAL_RESOLVED",
    "ATTEMPT_VOIDED",
    "CERTIFICATE_REVOKED",
    "ENTITY_TITLE_FA",
    "FINAL_GRADE_SET",
    "GRADE_OVERRIDDEN",
    "IMPERSONATED_REQUEST",
    "IMPERSONATION_ENDED",
    "IMPERSONATION_STARTED",
    "MESSAGE_TEMPLATE_UPDATED",
    "POINTS_RECALCULATED",
    "POINT_ENTRY_REVERSED",
    "POINT_RULE_UPDATED",
    "ROLE_GRANTED",
    "ROLE_REVOKED",
    "USER_STATUS_CHANGED",
    "title_of",
]
