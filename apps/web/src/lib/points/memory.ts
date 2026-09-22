/**
 * «کاربر کدام امتیاز و سطح را قبلاً دیده؟» — §9.10 فوریت و جشن.
 *
 * این یک راحتیِ هر مرورگر است، نه منبع حقیقت: امتیاز و سطح از سرور
 * می‌آیند و اینجا فقط یادمان است Toast کدام ردیف را نشان داده‌ایم. اگر
 * `localStorage` در دسترس نبود (پنجرهٔ خصوصی، سیاست مرورگر)، بدترین حالت
 * این است که Toast یا جشنی نمایش داده نشود — نه اینکه صفحه بشکند.
 *
 * جشن نشان این‌جا نیست: آن در سرور (`user_badges.seen_at`) ثبت می‌شود،
 * چون نشان نادر است و نباید روی دستگاه دوم دوباره جشن گرفته شود.
 */

import type { PointEntry } from '@/lib/api/points';

const KEY_ENTRY = 'silp.points.lastEntry';
const KEY_LEVEL = 'silp.points.lastLevel';

/** حداکثر Toast هم‌زمان — §10.6. */
export const MAX_TOASTS = 3;

function read(key: string, userId: string): string | null {
  try {
    return window.localStorage.getItem(`${key}:${userId}`);
  } catch {
    return null;
  }
}

function write(key: string, userId: string, value: string): void {
  try {
    window.localStorage.setItem(`${key}:${userId}`, value);
  } catch {
    // در دسترس نبودن حافظهٔ مرورگر فقط یعنی Toast تکراری — نه خطا.
  }
}

export function lastSeenEntry(userId: string): string | null {
  return read(KEY_ENTRY, userId);
}

export function rememberEntry(userId: string, entryId: string): void {
  write(KEY_ENTRY, userId, entryId);
}

export function lastSeenLevel(userId: string): number | null {
  const value = Number(read(KEY_LEVEL, userId));
  return Number.isInteger(value) && value > 0 ? value : null;
}

export function rememberLevel(userId: string, level: number): void {
  write(KEY_LEVEL, userId, String(level));
}

/**
 * امتیازهای تازه‌ای که باید Toast شوند.
 *
 * * شناسه‌ها UUIDv7 هستند و به‌صورت رشته با زمان مرتب‌اند، پس «تازه‌تر
 *   از آخرین دیده‌شده» مقایسهٔ رشته‌ای است.
 * * بار اول (`lastSeen = null`) هیچ‌چیز Toast نمی‌شود: کاربری که تازه
 *   وارد شده نباید با ده Toast از امتیازهای دیروزش استقبال شود.
 * * **فقط مثبت‌ها** — «امتیاز منفی هرگز به‌صورت انیمیشن یا اعلان پرسروصدا
 *   نمایش داده نمی‌شود» (§9.10). اصلاح امتیاز در دفتر کل دیده می‌شود.
 */
export function freshAwards(recent: PointEntry[], lastSeen: string | null): PointEntry[] {
  if (lastSeen === null) return [];
  return recent
    .filter((entry) => entry.id > lastSeen && Number(entry.amount) > 0)
    .sort((a, b) => (a.id < b.id ? -1 : 1))
    .slice(-MAX_TOASTS);
}
