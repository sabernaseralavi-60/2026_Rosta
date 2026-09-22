/**
 * زمان‌سنج آزمون — FR-QUIZ-02، وظیفهٔ M4-15.
 *
 * **ساعت مرجع، سرور است.** این ماژول هرگز `expires_at` را با ساعت
 * مرورگر مقایسه نمی‌کند؛ اگر می‌کرد، دانشجویی که ساعت سیستمش عقب است
 * وقت اضافه می‌دید و کسی که جلوست زودتر بیرون می‌افتاد.
 *
 * به‌جایش، هر پاسخ سرور `seconds_remaining` می‌دهد و ما فقط **اختلاف
 * زمان محلی از آن لحظه** را از آن کم می‌کنیم. یعنی ساعت مرورگر فقط
 * برای «چند ثانیه گذشت» به کار می‌رود، نه برای «الان ساعت چند است» —
 * و آن اولی حتی روی ساعت غلط هم درست است.
 */

/** لنگرِ زمان: آخرین باری که سرور گفت چقدر مانده. */
export interface TimerAnchor {
  /** `seconds_remaining` که سرور داد. */
  secondsRemaining: number;
  /** `performance.now()` یا `Date.now()` در همان لحظه. */
  measuredAt: number;
}

export function anchor(secondsRemaining: number, measuredAt: number = Date.now()): TimerAnchor {
  return { secondsRemaining: Math.max(0, secondsRemaining), measuredAt };
}

/** ثانیه‌های باقی‌مانده در لحظهٔ `now` — هرگز منفی. */
export function remainingAt(timer: TimerAnchor, now: number = Date.now()): number {
  const elapsed = Math.floor((now - timer.measuredAt) / 1000);
  return Math.max(0, timer.secondsRemaining - elapsed);
}

/** آستانه‌های هشدار — FR-QUIZ-02: «۵ دقیقه و ۱ دقیقهٔ پایانی». */
export const WARN_SECONDS = 5 * 60;
export const DANGER_SECONDS = 60;

export type TimerLevel = 'normal' | 'warn' | 'danger' | 'expired';

export function levelFor(seconds: number): TimerLevel {
  if (seconds <= 0) return 'expired';
  if (seconds <= DANGER_SECONDS) return 'danger';
  if (seconds <= WARN_SECONDS) return 'warn';
  return 'normal';
}

/**
 * قالب `mm:ss` یا `h:mm:ss` با ارقام فارسی.
 *
 * ارقام فارسی‌اند چون کل رابط فارسی است؛ ولی جداکننده دونقطهٔ لاتین
 * می‌ماند تا در متن راست‌به‌چپ جابه‌جا نشود.
 */
export function formatClock(totalSeconds: number): string {
  const safe = Math.max(0, Math.floor(totalSeconds));
  const hours = Math.floor(safe / 3600);
  const minutes = Math.floor((safe % 3600) / 60);
  const seconds = safe % 60;

  const parts = hours > 0 ? [hours, minutes, seconds] : [minutes, seconds];
  const text = parts
    .map((part, index) => (index === 0 ? String(part) : String(part).padStart(2, '0')))
    .join(':');
  return toPersian(text);
}

const PERSIAN_DIGITS = '۰۱۲۳۴۵۶۷۸۹';

function toPersian(value: string): string {
  return value.replace(/\d/g, (digit) => PERSIAN_DIGITS[Number(digit)] ?? digit);
}

/**
 * متن هشدار برای آستانه‌ای که همین الان رد شد، یا `null`.
 *
 * `previous` و `current` هر دو لازم‌اند تا هشدار فقط **یک بار** در
 * لحظهٔ عبور ساخته شود، نه در هر تیک ثانیه.
 */
export function crossedWarning(previous: number, current: number): string | null {
  if (previous > DANGER_SECONDS && current <= DANGER_SECONDS) {
    return 'یک دقیقه تا پایان آزمون.';
  }
  if (previous > WARN_SECONDS && current <= WARN_SECONDS) {
    return 'پنج دقیقه تا پایان آزمون.';
  }
  return null;
}
