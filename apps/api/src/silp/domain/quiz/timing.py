"""قواعد زمان آزمون — منطق خالص. §7.3، FR-QUIZ-02.

**زمان‌سنج مرجع سرور است.** هر تابعی که به «حالا» نیاز دارد، `now` را
آرگومان می‌گیرد؛ هیچ‌کدام `datetime.now()` صدا نمی‌زنند. این هم قابل
تست‌شان می‌کند و هم جلوی اتکای تصادفی به ساعت ماشین را می‌گیرد.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

#: §7.3 قاعدهٔ ۳ — پاسخی که کلاینت پیش از انقضا ثبت کرده ولی شبکه دیر
#: رسانده، پذیرفته می‌شود. سه ثانیه کم است و پنج دقیقه یعنی وقت اضافه.
NETWORK_GRACE = timedelta(seconds=30)

#: مهلت اعتراض به نمره پس از انتشار نتیجه — §7.3.
APPEAL_WINDOW = timedelta(days=7)

#: هشدار بصری در این آستانه‌ها — FR-QUIZ-02.
WARN_AT_SECONDS: tuple[int, ...] = (300, 60)


class QuizAvailability(StrEnum):
    """وضعیت آزمون از دید دانشجو — §7.3."""

    NOT_OPEN = "NOT_OPEN"
    AVAILABLE = "AVAILABLE"
    IN_PROGRESS = "IN_PROGRESS"
    EXHAUSTED = "EXHAUSTED"
    CLOSED = "CLOSED"


QUIZ_AVAILABILITY_TITLE_FA: dict[QuizAvailability, str] = {
    QuizAvailability.NOT_OPEN: "هنوز باز نشده",
    QuizAvailability.AVAILABLE: "آماده شروع",
    QuizAvailability.IN_PROGRESS: "نیمه‌تمام",
    QuizAvailability.EXHAUSTED: "دفعات مجاز تمام شد",
    QuizAvailability.CLOSED: "مهلت تمام شد",
}


@dataclass(frozen=True, slots=True)
class AttemptWindow:
    """پنجرهٔ زمانی یک تلاش."""

    started_at: datetime
    expires_at: datetime

    def seconds_remaining(self, now: datetime) -> int:
        """ثانیه‌های باقی‌مانده — هرگز منفی."""
        return max(0, int((self.expires_at - now).total_seconds()))

    def is_expired(self, now: datetime) -> bool:
        return now >= self.expires_at


def compute_expires_at(
    *,
    started_at: datetime,
    duration_min: int,
    closes_at: datetime,
) -> datetime:
    """`expires_at` در لحظهٔ شروع، یک بار و برای همیشه.

    اگر دانشجو پنج دقیقه به بسته شدن آزمون شروع کند، مدت آزمون او همان
    پنج دقیقه است، نه سی دقیقه: مهلت آزمون از مدتِ تلاش جلو نمی‌افتد.
    شروع دیرهنگام یک انتخاب است، و جبرانش یعنی وقت اضافه نسبت به کسی
    که سر وقت شروع کرده.
    """
    natural_end = started_at + timedelta(minutes=duration_min)
    return min(natural_end, closes_at)


def availability(
    *,
    now: datetime,
    opens_at: datetime,
    closes_at: datetime,
    has_active_attempt: bool,
    used_attempts: int,
    max_attempts: int,
) -> QuizAvailability:
    """وضعیت آزمون از دید یک دانشجوی مشخص — §7.3.

    ترتیب بررسی‌ها همان ترتیب سند است و اهمیت دارد: تلاشِ فعال بر
    «تمام‌شدن دفعات» مقدم است، وگرنه دانشجویی که آخرین تلاشش را در
    دست دارد، وسط آزمون در را بسته می‌بیند.
    """
    if now < opens_at:
        return QuizAvailability.NOT_OPEN
    if now > closes_at:
        return QuizAvailability.CLOSED
    if has_active_attempt:
        return QuizAvailability.IN_PROGRESS
    if used_attempts >= max_attempts:
        return QuizAvailability.EXHAUSTED
    return QuizAvailability.AVAILABLE


def accepts_answer(
    *,
    now: datetime,
    expires_at: datetime,
    client_ts: datetime | None,
) -> bool:
    """آیا این پاسخ هنوز پذیرفته می‌شود؟ — §7.3 قاعدهٔ ۳.

    سه حالت:

    * پیش از انقضا ⇒ بله.
    * پس از انقضا، بدون `client_ts` ⇒ نه. نبودِ زمانِ کلاینت یعنی
      ادعایی برای «زودتر نوشتمش» وجود ندارد.
    * پس از انقضا، با `client_ts` پیش از انقضا و تأخیر ≤ ۳۰ ثانیه ⇒ بله.

    `client_ts` قابل جعل است و این پذیرفته شده: سقفِ سودش ۳۰ ثانیه است
    و در برابرش، دانشجویی که اینترنتش لحظهٔ آخر قطع شده پاسخش را از دست
    نمی‌دهد. این معاملهٔ آگاهانهٔ §7.3 است.
    """
    if now < expires_at:
        return True
    if client_ts is None:
        return False
    if client_ts >= expires_at:
        return False
    return (now - expires_at) <= NETWORK_GRACE


def appeal_window_open(*, now: datetime, results_published_at: datetime | None) -> bool:
    """آیا مهلت ۷ روزهٔ اعتراض هنوز باز است؟ — §7.3."""
    if results_published_at is None:
        return False
    return now <= results_published_at + APPEAL_WINDOW


__all__ = [
    "APPEAL_WINDOW",
    "NETWORK_GRACE",
    "QUIZ_AVAILABILITY_TITLE_FA",
    "WARN_AT_SECONDS",
    "AttemptWindow",
    "QuizAvailability",
    "accepts_answer",
    "appeal_window_open",
    "availability",
    "compute_expires_at",
]
