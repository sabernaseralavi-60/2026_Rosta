/**
 * صف پاسخ آفلاین — FR-QUIZ-02، وظیفهٔ M4-06.
 *
 * ## مسئله
 *
 * دانشجو وسط آزمون اینترنتش قطع می‌شود. اگر پاسخ‌ها فقط در حافظهٔ
 * صفحه باشند، یک رفرش یا یک تب بسته‌شده همه را می‌برد — و آزمون
 * دوباره برگزار نمی‌شود.
 *
 * ## راه‌حل
 *
 * هر پاسخ **اول** در `localStorage` می‌نشیند و بعد فرستاده می‌شود.
 * ارسال موفق، آن را از صف پاک می‌کند. پس هر چیزی که در صف مانده،
 * یعنی «نوشته شد ولی نرسید» و در اولین فرصت با `/sync` می‌رود.
 *
 * `client_ts` لحظهٔ **نوشتن** است، نه لحظهٔ ارسال. سرور با همین
 * تصمیم می‌گیرد پاسخِ دیررسیده را بپذیرد (§7.3 قاعدهٔ ۳)؛ اگر لحظهٔ
 * ارسال را می‌فرستادیم، پاسخی که دانشجو سر وقت نوشته بود پس از وصل
 * شدن دوبارهٔ اینترنت رد می‌شد.
 *
 * ## چرا اینجا و نه داخل کامپوننت
 *
 * این منطق باید بدون مرورگر تست شود. هر تابع خالص است و `localStorage`
 * فقط از دو تابع `read`/`write` صدا زده می‌شود که هر دو در برابر
 * استثنا مقاوم‌اند — حالت ناشناس مرورگر و سهمیهٔ پرشده، `throw`
 * می‌کنند و آزمون نباید با آن بمیرد.
 */

import type { AnswerResponse, OfflineAnswer } from '../api/quizzes';

const PREFIX = 'silp.attempt.';

export interface PendingEntry {
  response: AnswerResponse | null;
  is_flagged: boolean;
  client_ts: string;
}

/** نگاشت `question_id` به آخرین پاسخِ ارسال‌نشده. */
export type PendingMap = Record<string, PendingEntry>;

function storageKey(attemptId: string): string {
  return `${PREFIX}${attemptId}`;
}

/**
 * خواندن صف. هر خطایی یعنی «صفی نیست» — نه توقف آزمون.
 *
 * در حالت ناشناس مرورگر یا وقتی کاربر ذخیره‌سازی سایت را بسته باشد،
 * دسترسی به `localStorage` خودش استثنا می‌دهد؛ آزمون باید بدون صف هم
 * کار کند، فقط بدون تاب‌آوری آفلاین.
 */
export function readPending(attemptId: string): PendingMap {
  try {
    const raw = window.localStorage.getItem(storageKey(attemptId));
    if (!raw) return {};
    const parsed: unknown = JSON.parse(raw);
    if (typeof parsed !== 'object' || parsed === null) return {};
    return parsed as PendingMap;
  } catch {
    return {};
  }
}

function writePending(attemptId: string, pending: PendingMap): void {
  try {
    if (Object.keys(pending).length === 0) {
      window.localStorage.removeItem(storageKey(attemptId));
      return;
    }
    window.localStorage.setItem(storageKey(attemptId), JSON.stringify(pending));
  } catch {
    // سهمیهٔ پرشده یا ذخیره‌سازی بسته — بی‌صدا رد می‌شویم.
  }
}

/**
 * ثبت یک پاسخ در صف، پیش از تلاش برای ارسال.
 *
 * `now` آرگومان است تا تابع قابل تست بماند و به ساعت سیستم گره نخورد.
 */
export function queueAnswer(
  attemptId: string,
  questionId: string,
  entry: { response: AnswerResponse | null; is_flagged: boolean },
  now: Date = new Date(),
): PendingMap {
  const pending = readPending(attemptId);
  pending[questionId] = {
    response: entry.response,
    is_flagged: entry.is_flagged,
    client_ts: now.toISOString(),
  };
  writePending(attemptId, pending);
  return pending;
}

/**
 * پاک کردن یک پاسخ از صف پس از ارسال موفق.
 *
 * **فقط وقتی پاک می‌شود که از زمان ثبت‌شده جلوتر نرفته باشد.** اگر
 * دانشجو بین ارسال و پاسخ سرور دوباره همان سؤال را عوض کرده باشد،
 * نسخهٔ تازه‌تر باید در صف بماند؛ وگرنه آخرین تغییرش بی‌صدا گم می‌شود.
 */
export function clearAnswer(
  attemptId: string,
  questionId: string,
  syncedClientTs: string,
): PendingMap {
  const pending = readPending(attemptId);
  const current = pending[questionId];
  if (current && current.client_ts === syncedClientTs) {
    delete pending[questionId];
    writePending(attemptId, pending);
  }
  return pending;
}

/** پاک کردن کل صف — پس از ارسال نهایی آزمون. */
export function clearAttempt(attemptId: string): void {
  try {
    window.localStorage.removeItem(storageKey(attemptId));
  } catch {
    // بی‌اهمیت: نهایتاً چند کیلوبایت می‌ماند.
  }
}

/** صف به شکلی که `POST /attempts/{id}/sync` می‌خواهد. */
export function toSyncPayload(pending: PendingMap): OfflineAnswer[] {
  return Object.entries(pending).map(([questionId, entry]) => ({
    question_id: questionId,
    response: entry.response,
    is_flagged: entry.is_flagged,
    client_ts: entry.client_ts,
  }));
}

export function pendingCount(pending: PendingMap): number {
  return Object.keys(pending).length;
}

/**
 * آیا این پاسخ «داده‌شده» حساب می‌شود؟
 *
 * شمارندهٔ «بی‌پاسخ» که هنگام ارسال به دانشجو نشان داده می‌شود از
 * همین می‌آید، پس باید با تصحیح سرور یکی باشد: گزینهٔ خالی، متن خالی
 * و جفت‌های خالی همه بی‌پاسخ‌اند.
 */
export function isAnswered(response: AnswerResponse | null | undefined): boolean {
  if (!response) return false;
  if ('selected' in response) return response.selected.length > 0;
  if ('pairs' in response) return response.pairs.length > 0;
  if ('text' in response) return response.text.trim().length > 0;
  if ('value' in response) {
    if (typeof response.value === 'boolean') return true;
    return String(response.value).trim().length > 0;
  }
  return false;
}
