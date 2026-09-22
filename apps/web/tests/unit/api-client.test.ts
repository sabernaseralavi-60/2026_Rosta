import { describe, expect, it } from 'vitest';

import { ApiError } from '@/lib/api/client';

describe('ApiError — قالب خطای §5.1', () => {
  function makeError(status: number, overrides = {}) {
    return new ApiError(status, {
      code: 'PROJECT_CAPACITY_FULL',
      message: 'ظرفیت این پروژه تکمیل شده است.',
      details: { capacity: 5, current: 5 },
      trace_id: '018f2a00-0000-7000-8000-000000000001',
      ...overrides,
    });
  }

  it('پیام فارسی سرور را مستقیماً حمل می‌کند', () => {
    // §5.1 — پیام «قابل نمایش مستقیم به کاربر» است؛ رابط بازنویسی‌اش نمی‌کند.
    expect(makeError(409).message).toBe('ظرفیت این پروژه تکمیل شده است.');
  });

  it('کد و شناسهٔ ردیابی را نگه می‌دارد', () => {
    const error = makeError(409);
    expect(error.code).toBe('PROJECT_CAPACITY_FULL');
    expect(error.traceId).toBe('018f2a00-0000-7000-8000-000000000001');
  });

  it('خطای اعتبارسنجی را به تفکیک فیلد می‌دهد', () => {
    const error = makeError(422, {
      code: 'VALIDATION_FAILED',
      details: { fields: { destination: 'این فیلد الزامی است.' } },
    });
    expect(error.fieldErrors).toEqual({ destination: 'این فیلد الزامی است.' });
  });

  it('وقتی فیلدی نیست، شیء خالی می‌دهد نه undefined', () => {
    expect(makeError(500, { details: {} }).fieldErrors).toEqual({});
  });

  it('محدودیت نرخ و زمان انتظار را تشخیص می‌دهد', () => {
    const error = makeError(429, {
      code: 'OTP_RATE_LIMITED',
      details: { retry_after: 45 },
    });
    expect(error.isRateLimited).toBe(true);
    expect(error.retryAfterSeconds).toBe(45);
  });

  it('خطای غیر ۴۲۹ محدودیت نرخ نیست', () => {
    expect(makeError(409).isRateLimited).toBe(false);
    expect(makeError(409).retryAfterSeconds).toBe(0);
  });
});
