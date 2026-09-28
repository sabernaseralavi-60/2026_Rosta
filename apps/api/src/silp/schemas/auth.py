"""مدل‌های Pydantic برای /auth — قرارداد §5.2.

نام فیلدها دقیقاً با سند API یکی است؛ این مدل‌ها منبع تولید OpenAPI و
سپس تایپ‌های TypeScript در packages/shared هستند.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from silp.domain.identity.normalize import to_latin_digits
from silp.schemas.gamification import MePointsOut
from silp.schemas.profile import ProfileOut

Channel = Literal["SMS", "EMAIL"]
Purpose = Literal["LOGIN", "VERIFY_EMAIL", "VERIFY_MOBILE", "RESET_PASSWORD"]
OnboardingState = Literal["BASIC_INFO_REQUIRED", "SURVEY_REQUIRED", "SURVEY_INCOMPLETE", "COMPLETE"]


class OTPRequestIn(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {"destination": "09121234567", "channel": "SMS", "purpose": "LOGIN"}
        }
    )

    destination: Annotated[str, Field(min_length=3, max_length=254)]
    # None یعنی «خودت تشخیص بده» — کاربر نباید مجبور به انتخاب باشد.
    channel: Channel | None = None
    purpose: Purpose = "LOGIN"


class OTPRequestOut(BaseModel):
    challenge_id: str
    expires_in: int
    resend_after: int
    masked_destination: str


class OTPVerifyIn(BaseModel):
    challenge_id: uuid.UUID
    code: Annotated[str, Field(min_length=4, max_length=8)]

    @field_validator("code")
    @classmethod
    def _normalize_code(cls, v: str) -> str:
        """کاربر کد را از پیامک کپی می‌کند و گاهی ارقام فارسی یا فاصله دارد."""
        digits = to_latin_digits(v).strip().replace(" ", "").replace("-", "")
        if not digits.isdigit():
            msg = "کد فقط می‌تواند رقم باشد."
            raise ValueError(msg)
        return digits


class PasswordLoginIn(BaseModel):
    """FR-AUTH-02 — موبایل یا ایمیل + رمز."""

    identifier: Annotated[str, Field(min_length=3, max_length=254)]
    password: Annotated[str, Field(min_length=1, max_length=256)]


class RefreshIn(BaseModel):
    refresh_token: Annotated[str, Field(min_length=20, max_length=512)]


class LogoutIn(BaseModel):
    refresh_token: Annotated[str, Field(min_length=20, max_length=512)]


class OnboardingOut(BaseModel):
    state: OnboardingState
    completed_steps: int
    total_steps: int
    next_route: str


class AuthUserOut(BaseModel):
    """کاربر در پاسخ ورود — §5.2. اطلاعات تماس پوشانده می‌شود (NFR-01)."""

    id: uuid.UUID
    display_name: str | None = None
    username: str | None = None
    roles: list[str]
    onboarding_state: OnboardingState


class TokenPairOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int


class LoginOut(TokenPairOut):
    user: AuthUserOut


class SessionOut(BaseModel):
    """یک نشست فعال — §5.2 `GET /auth/sessions`."""

    id: uuid.UUID
    user_agent: str | None
    ip_address: str | None
    created_at: datetime
    expires_at: datetime
    is_current: bool


class MeOut(BaseModel):
    """§5.3 `GET /me`.

    امتیاز از M5 و شمارندهٔ اعلان از M6 است.
    """

    id: uuid.UUID
    person_code: str
    """ADR-0030 — کد شخصی دائمی؛ با تغییر نقش عوض نمی‌شود."""
    mobile: str | None = None
    email: str | None = None
    email_verified: bool = False
    mobile_verified: bool = False
    username: str | None = None
    profile: ProfileOut | None = None
    roles: list[RoleGrantOut]
    onboarding: OnboardingOut
    points: MePointsOut | None = None
    """§5.3 — افزوده در M5. `None` فقط اگر محاسبه ممکن نبود؛ کاربر تازه `0` می‌گیرد."""
    unread_notifications: int = 0
    """§5.3 — افزوده در M6. همان عدد `GET /notifications/unread-count`."""


class RoleGrantOut(BaseModel):
    code: str
    scope_type: str
    scope_id: uuid.UUID | None = None


MeOut.model_rebuild()
