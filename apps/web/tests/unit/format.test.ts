import { describe, expect, it } from 'vitest';

import {
  formatDateLong,
  formatDateShort,
  formatDeadline,
  formatRelative,
} from '@/lib/format/date';
import { formatNumber, formatRial, toLatinDigits, toPersianDigits } from '@/lib/format/digits';

describe('ارقام — §10.3 قاعدهٔ ۵', () => {
  it('ارقام لاتین را به فارسی تبدیل می‌کند', () => {
    expect(toPersianDigits('1404')).toBe('۱۴۰۴');
    expect(toPersianDigits(2026)).toBe('۲۰۲۶');
  });

  it('ارقام فارسی و عربی را به لاتین برمی‌گرداند', () => {
    expect(toLatinDigits('۰۹۱۲۱۲۳۴۵۶۷')).toBe('09121234567');
    expect(toLatinDigits('٠٩١٢')).toBe('0912');
  });

  it('متن غیرعددی را دست‌نخورده می‌گذارد', () => {
    expect(toLatinDigits('مریم')).toBe('مریم');
  });

  it('رفت‌وبرگشت تبدیل، مقدار را حفظ می‌کند', () => {
    expect(toLatinDigits(toPersianDigits('09121234567'))).toBe('09121234567');
  });

  it('مبلغ را به ریال نمایش می‌دهد — §4.0', () => {
    expect(formatRial(460_000_000)).toContain('ریال');
    expect(formatNumber(1234567)).not.toBe('1234567');
  });
});

describe('تاریخ شمسی — §10.9، D-12', () => {
  // ۲۰۲۶-۰۳-۰۶ برابر ۱۵ اسفند ۱۴۰۴ است.
  const date = new Date('2026-03-06T11:00:00Z');

  it('تاریخ کوتاه را شمسی نشان می‌دهد', () => {
    expect(formatDateShort(date)).toContain('۱۴۰۴');
  });

  it('تاریخ بلند نام ماه شمسی دارد', () => {
    expect(formatDateLong(date)).toContain('اسفند');
  });

  it('رشتهٔ ISO را هم می‌پذیرد', () => {
    expect(formatDateShort('2026-03-06T11:00:00Z')).toBe(formatDateShort(date));
  });
});

describe('زمان نسبی — §10.9', () => {
  const now = new Date('2026-03-06T12:00:00Z');

  it('کمتر از یک دقیقه: همین الان', () => {
    expect(formatRelative(new Date('2026-03-06T11:59:30Z'), now)).toBe('همین الان');
  });

  it('ساعت و روز را با رقم فارسی می‌گوید', () => {
    expect(formatRelative(new Date('2026-03-06T10:00:00Z'), now)).toBe('۲ ساعت پیش');
    expect(formatRelative(new Date('2026-03-03T12:00:00Z'), now)).toBe('۳ روز پیش');
  });

  it('بیش از یک هفته، تاریخ کامل نشان می‌دهد', () => {
    // «۹ روز پیش» کمتر از «۲۵ بهمن» به کاربر می‌گوید.
    expect(formatRelative(new Date('2026-02-20T12:00:00Z'), now)).toContain('۱۴۰۴');
  });
});

describe('مهلت — §10.9', () => {
  const now = new Date('2026-03-06T12:00:00Z');

  it('مهلت گذشته را علامت می‌زند', () => {
    const result = formatDeadline(new Date('2026-03-05T12:00:00Z'), now);
    expect(result).toEqual({ label: 'مهلت گذشته', isOverdue: true });
  });

  it('روزهای باقی‌مانده را می‌شمارد', () => {
    const result = formatDeadline(new Date('2026-03-08T12:00:00Z'), now);
    expect(result.isOverdue).toBe(false);
    expect(result.label).toBe('۲ روز تا مهلت');
  });
});
