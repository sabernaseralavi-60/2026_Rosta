/**
 * تاریخ شمسی — PRD §10.9، D-12.
 *
 * ذخیره همیشه UTC، نمایش همیشه شمسی. تبدیل **فقط** در لایهٔ نمایش.
 * از Intl بومی استفاده می‌شود، نه کتابخانهٔ جانبی: تقویم فارسی در همهٔ
 * مرورگرهای هدف پشتیبانی می‌شود و یک وابستگی کمتر یعنی باندل کوچک‌تر.
 */

const TIMEZONE = 'Asia/Tehran';
const CALENDAR = 'fa-IR-u-ca-persian';

const SHORT = new Intl.DateTimeFormat(CALENDAR, {
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  timeZone: TIMEZONE,
});

const LONG = new Intl.DateTimeFormat(CALENDAR, {
  year: 'numeric',
  month: 'long',
  day: 'numeric',
  timeZone: TIMEZONE,
});

const TIME = new Intl.DateTimeFormat(CALENDAR, {
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
  timeZone: TIMEZONE,
});

function toDate(value: Date | string | number): Date {
  return value instanceof Date ? value : new Date(value);
}

/** `۱۴۰۴/۱۲/۱۵` */
export function formatDateShort(value: Date | string | number): string {
  return SHORT.format(toDate(value));
}

/** `۱۵ اسفند ۱۴۰۴` */
export function formatDateLong(value: Date | string | number): string {
  return LONG.format(toDate(value));
}

/** `۱۵ اسفند ۱۴۰۴، ساعت ۱۴:۳۰` */
export function formatDateTime(value: Date | string | number): string {
  const date = toDate(value);
  return `${LONG.format(date)}، ساعت ${TIME.format(date)}`;
}

const MINUTE = 60_000;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;
const WEEK = 7 * DAY;

/**
 * `۳ روز پیش`، `۲ ساعت پیش`، `همین الان`.
 *
 * بیش از یک هفته، تاریخ کامل نشان داده می‌شود: «۹ روز پیش» کمتر از
 * «۱۵ اسفند» به کاربر می‌گوید.
 */
export function formatRelative(
  value: Date | string | number,
  now: Date = new Date(),
): string {
  const date = toDate(value);
  const diff = now.getTime() - date.getTime();

  if (diff < 0) return formatDateLong(date);
  if (diff < MINUTE) return 'همین الان';
  if (diff < HOUR) return `${persian(Math.floor(diff / MINUTE))} دقیقه پیش`;
  if (diff < DAY) return `${persian(Math.floor(diff / HOUR))} ساعت پیش`;
  if (diff < WEEK) return `${persian(Math.floor(diff / DAY))} روز پیش`;
  return formatDateLong(date);
}

/** `۲ روز تا مهلت` یا `مهلت گذشته` — §10.9. */
export function formatDeadline(
  value: Date | string | number,
  now: Date = new Date(),
): { label: string; isOverdue: boolean } {
  const date = toDate(value);
  const remaining = date.getTime() - now.getTime();

  if (remaining < 0) return { label: 'مهلت گذشته', isOverdue: true };
  if (remaining < HOUR) {
    return { label: `${persian(Math.ceil(remaining / MINUTE))} دقیقه تا مهلت`, isOverdue: false };
  }
  if (remaining < DAY) {
    return { label: `${persian(Math.ceil(remaining / HOUR))} ساعت تا مهلت`, isOverdue: false };
  }
  return { label: `${persian(Math.ceil(remaining / DAY))} روز تا مهلت`, isOverdue: false };
}

function persian(value: number): string {
  return new Intl.NumberFormat('fa-IR', { useGrouping: false }).format(value);
}
