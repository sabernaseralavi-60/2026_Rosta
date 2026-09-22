/**
 * صف پاسخ آفلاین و زمان‌سنج — FR-QUIZ-02، وظیفه‌های M4-06 و M4-15.
 *
 * این دو ماژول تنها چیزی‌اند که بین «اینترنت قطع شد» و «کارم را از
 * دست دادم» ایستاده‌اند، پس مستقیم آزموده می‌شوند، نه از راه کامپوننت.
 */

import { beforeEach, describe, expect, it } from 'vitest';

import {
  clearAnswer,
  clearAttempt,
  isAnswered,
  pendingCount,
  queueAnswer,
  readPending,
  toSyncPayload,
} from '@/lib/quiz/offline-store';
import {
  DANGER_SECONDS,
  WARN_SECONDS,
  anchor,
  crossedWarning,
  formatClock,
  levelFor,
  remainingAt,
} from '@/lib/quiz/timer';

const ATTEMPT = 'attempt-1';
const Q1 = 'question-1';
const Q2 = 'question-2';

describe('صف پاسخ آفلاین', () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it('پاسخ را پیش از ارسال روی دیسک می‌نشاند', () => {
    queueAnswer(ATTEMPT, Q1, { response: { selected: ['a'] }, is_flagged: false });

    const stored = readPending(ATTEMPT);
    expect(pendingCount(stored)).toBe(1);
    expect(stored[Q1]?.response).toEqual({ selected: ['a'] });
  });

  it('صف از بارگذاری دوبارهٔ صفحه جان سالم به در می‌برد', () => {
    queueAnswer(ATTEMPT, Q1, { response: { text: 'پاسخ من' }, is_flagged: false });

    // `readPending` تازه، همان چیزی را می‌خواند که در `localStorage` است.
    expect(readPending(ATTEMPT)[Q1]?.response).toEqual({ text: 'پاسخ من' });
  });

  it('`client_ts` لحظهٔ نوشتن است، نه لحظهٔ ارسال', () => {
    const writtenAt = new Date('2026-03-01T10:05:00Z');
    queueAnswer(ATTEMPT, Q1, { response: { selected: ['b'] }, is_flagged: false }, writtenAt);

    expect(readPending(ATTEMPT)[Q1]?.client_ts).toBe(writtenAt.toISOString());
  });

  it('پس از ارسال موفق، پاسخ از صف پاک می‌شود', () => {
    const at = new Date('2026-03-01T10:05:00Z');
    queueAnswer(ATTEMPT, Q1, { response: { selected: ['b'] }, is_flagged: false }, at);

    const left = clearAnswer(ATTEMPT, Q1, at.toISOString());
    expect(pendingCount(left)).toBe(0);
  });

  it('پاسخی که بین ارسال و پاسخ سرور عوض شده، پاک نمی‌شود', () => {
    const first = new Date('2026-03-01T10:05:00Z');
    const second = new Date('2026-03-01T10:05:30Z');
    queueAnswer(ATTEMPT, Q1, { response: { selected: ['a'] }, is_flagged: false }, first);
    queueAnswer(ATTEMPT, Q1, { response: { selected: ['b'] }, is_flagged: false }, second);

    // تأیید سرور برای نسخهٔ **اول** می‌رسد؛ نسخهٔ دوم باید بماند.
    const left = clearAnswer(ATTEMPT, Q1, first.toISOString());
    expect(pendingCount(left)).toBe(1);
    expect(left[Q1]?.response).toEqual({ selected: ['b'] });
  });

  it('بدنهٔ همگام‌سازی همان شکلی است که سرور می‌خواهد', () => {
    const at = new Date('2026-03-01T10:05:00Z');
    queueAnswer(ATTEMPT, Q1, { response: { selected: ['a'] }, is_flagged: true }, at);
    queueAnswer(ATTEMPT, Q2, { response: { text: 'x' }, is_flagged: false }, at);

    const payload = toSyncPayload(readPending(ATTEMPT));
    expect(payload).toHaveLength(2);
    expect(payload[0]).toEqual({
      question_id: Q1,
      response: { selected: ['a'] },
      is_flagged: true,
      client_ts: at.toISOString(),
    });
  });

  it('صف هر تلاش از تلاش دیگر جداست', () => {
    queueAnswer(ATTEMPT, Q1, { response: { selected: ['a'] }, is_flagged: false });
    queueAnswer('attempt-2', Q1, { response: { selected: ['b'] }, is_flagged: false });

    clearAttempt(ATTEMPT);
    expect(pendingCount(readPending(ATTEMPT))).toBe(0);
    expect(pendingCount(readPending('attempt-2'))).toBe(1);
  });

  it('صف خراب، آزمون را متوقف نمی‌کند', () => {
    window.localStorage.setItem('silp.attempt.attempt-1', 'not json');
    expect(readPending(ATTEMPT)).toEqual({});
  });
});

describe('شمارش بی‌پاسخ‌ها', () => {
  it('گزینهٔ خالی و متن خالی، بی‌پاسخ‌اند', () => {
    expect(isAnswered(null)).toBe(false);
    expect(isAnswered({ selected: [] })).toBe(false);
    expect(isAnswered({ text: '   ' })).toBe(false);
    expect(isAnswered({ pairs: [] })).toBe(false);
    expect(isAnswered({ value: '' })).toBe(false);
  });

  it('پاسخ واقعی، پاسخ حساب می‌شود', () => {
    expect(isAnswered({ selected: ['a'] })).toBe(true);
    expect(isAnswered({ text: 'پاسخ' })).toBe(true);
    expect(isAnswered({ pairs: [['l1', 'r1']] })).toBe(true);
    expect(isAnswered({ value: '12.5' })).toBe(true);
  });

  it('«نادرست» در درست/نادرست، پاسخ است نه بی‌پاسخ', () => {
    // اگر `false` بی‌پاسخ حساب می‌شد، دانشجویی که «نادرست» زده هشدار
    // «سؤال بی‌پاسخ دارید» می‌گرفت.
    expect(isAnswered({ value: false })).toBe(true);
  });
});

describe('زمان‌سنج', () => {
  it('باقی‌مانده را از لنگر سرور می‌شمارد، نه از ساعت مرورگر', () => {
    const timer = anchor(600, 1_000_000);
    expect(remainingAt(timer, 1_000_000)).toBe(600);
    expect(remainingAt(timer, 1_030_000)).toBe(570); // ۳۰ ثانیه بعد
  });

  it('هرگز منفی نمی‌شود', () => {
    const timer = anchor(10, 1_000_000);
    expect(remainingAt(timer, 1_100_000)).toBe(0);
  });

  it('آستانه‌های هشدار همان‌اند که سند گفته', () => {
    expect(levelFor(WARN_SECONDS + 1)).toBe('normal');
    expect(levelFor(WARN_SECONDS)).toBe('warn');
    expect(levelFor(DANGER_SECONDS)).toBe('danger');
    expect(levelFor(0)).toBe('expired');
  });

  it('هشدار فقط در لحظهٔ عبور از آستانه ساخته می‌شود', () => {
    expect(crossedWarning(301, 300)).toContain('پنج دقیقه');
    expect(crossedWarning(300, 299)).toBeNull(); // یک ثانیه بعد، دوباره نه
    expect(crossedWarning(61, 60)).toContain('یک دقیقه');
  });

  it('ساعت را با ارقام فارسی نشان می‌دهد', () => {
    expect(formatClock(90)).toBe('۱:۳۰');
    expect(formatClock(3661)).toBe('۱:۰۱:۰۱');
    expect(formatClock(0)).toBe('۰:۰۰');
  });
});
