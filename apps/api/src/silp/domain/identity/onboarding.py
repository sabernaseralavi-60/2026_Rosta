"""وضعیت ورود اولیه — PRD §7.1. منطق خالص، بدون I/O.

`onboarding_state` توسط **سرور** محاسبه می‌شود، نه کلاینت. کلاینت فقط
بر اساس آن هدایت می‌کند.

در M0 جدول `profiles` هنوز ساخته نشده (مهاجرت ۰۰۴ در M1 است)، پس این تابع
یک ساختار سبک می‌گیرد، نه مدل ORM. وقتی نیمرخ اضافه شد، فقط جای فراخوانی
عوض می‌شود، نه خود منطق.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

TOTAL_SURVEY_STEPS = 4


class OnboardingState(StrEnum):
    BASIC_INFO_REQUIRED = "BASIC_INFO_REQUIRED"
    SURVEY_REQUIRED = "SURVEY_REQUIRED"
    SURVEY_INCOMPLETE = "SURVEY_INCOMPLETE"
    COMPLETE = "COMPLETE"


# §7.1 — رفتار کلاینت برای هر حالت. مسیر مقصد اینجا تعریف می‌شود تا
# فرانت‌اند آن را حدس نزند.
NEXT_ROUTE: dict[OnboardingState, str] = {
    OnboardingState.BASIC_INFO_REQUIRED: "/onboarding/basic",
    OnboardingState.SURVEY_REQUIRED: "/onboarding/survey/1",
    OnboardingState.SURVEY_INCOMPLETE: "/dashboard",
    OnboardingState.COMPLETE: "/dashboard",
}

# حالت‌هایی که ورود به بقیهٔ سامانه را مسدود می‌کنند.
BLOCKING_STATES: frozenset[OnboardingState] = frozenset(
    {OnboardingState.BASIC_INFO_REQUIRED, OnboardingState.SURVEY_REQUIRED}
)


@dataclass(frozen=True, slots=True)
class ProfileSnapshot:
    """کمینهٔ اطلاعات لازم برای تصمیم‌گیری دربارهٔ ورود اولیه."""

    first_name: str | None = None
    last_name: str | None = None
    survey_completed_steps: int = 0


@dataclass(frozen=True, slots=True)
class Onboarding:
    state: OnboardingState
    completed_steps: int
    total_steps: int = TOTAL_SURVEY_STEPS

    @property
    def next_route(self) -> str:
        return NEXT_ROUTE[self.state]

    @property
    def is_blocking(self) -> bool:
        return self.state in BLOCKING_STATES


def resolve(profile: ProfileSnapshot | None) -> Onboarding:
    """قاعدهٔ دقیق §7.1."""
    if profile is None or not profile.first_name or not profile.last_name:
        return Onboarding(OnboardingState.BASIC_INFO_REQUIRED, completed_steps=0)

    steps = max(0, min(profile.survey_completed_steps, TOTAL_SURVEY_STEPS))
    if steps < 1:
        return Onboarding(OnboardingState.SURVEY_REQUIRED, completed_steps=steps)
    if steps < TOTAL_SURVEY_STEPS:
        # قابل ادامه، مسدودکننده نیست — نوار دائمی «نیمرخت را کامل کن».
        return Onboarding(OnboardingState.SURVEY_INCOMPLETE, completed_steps=steps)
    return Onboarding(OnboardingState.COMPLETE, completed_steps=steps)
