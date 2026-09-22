import { render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { apiFetch, WRITE_EVENT } from '@/lib/api/client';
import { BadgeTile } from '@/components/domain/BadgeTile';
import { CategoryTiles } from '@/components/domain/CategoryTiles';
import { NextStepCard } from '@/components/domain/NextStepCard';
import { PointsTrend } from '@/components/domain/PointsTrend';
import type { Badge, PointEntry } from '@/lib/api/points';
import { LedgerRow } from '@/app/(app)/me/points/PointsLedgerView';
import { freshAwards, lastSeenLevel, rememberLevel } from '@/lib/points/memory';

function entry(overrides: Partial<PointEntry> = {}): PointEntry {
  return {
    id: '01a0cae5-0000-7000-8000-000000000001',
    rule_code: 'MILESTONE_APPROVED',
    rule_title_fa: 'تأیید مرحلهٔ پروژه',
    category: 'LEARNING',
    category_fa: 'یادگیری',
    amount: '50.00',
    source_type: 'MILESTONE',
    source_type_fa: 'مرحلهٔ پروژه',
    source_id: 'm-1',
    source_label: 'تحقیق بازار — خرمای صابر',
    source_href: '/projects/p-1/workspace',
    note: null,
    created_at: '2026-10-01T08:00:00Z',
    reverses_id: null,
    is_reversed: false,
    ...overrides,
  };
}

function badge(overrides: Partial<Badge> = {}): Badge {
  return {
    code: 'SHARP_MIND',
    title_fa: 'ذهن تیز',
    description: 'در ۵ آزمون نمرهٔ کامل بگیر.',
    icon: 'brain',
    tier: 'SILVER',
    tier_fa: 'نقره‌ای',
    earned: false,
    awarded_at: null,
    seen: true,
    progress_current: '3',
    progress_target: '5',
    progress_ratio: '0.60',
    ...overrides,
  };
}

// ── Toast امتیاز — §9.10 ───────────────────────────────────────────────
describe('freshAwards — §9.10 فوریت و احترام به کاهش', () => {
  const older = entry({ id: '01a0cae5-0000-7000-8000-000000000001' });
  const newer = entry({ id: '01a0cae5-0000-7000-8000-000000000002', amount: '15.00' });
  const reversal = entry({
    id: '01a0cae5-0000-7000-8000-000000000003',
    amount: '-15.00',
    reverses_id: older.id,
  });

  it('بار اول هیچ Toast نمی‌دهد — کاربر با امتیازهای دیروز استقبال نمی‌شود', () => {
    expect(freshAwards([newer, older], null)).toEqual([]);
  });

  it('فقط امتیاز تازه‌تر از آخرین دیده‌شده، به ترتیب زمان', () => {
    expect(freshAwards([newer, older], older.id).map((e) => e.id)).toEqual([newer.id]);
  });

  it('کاهش امتیاز هرگز Toast نمی‌شود', () => {
    expect(freshAwards([reversal, newer, older], older.id).map((e) => e.id)).toEqual([newer.id]);
  });

  it('حداکثر سه Toast هم‌زمان', () => {
    const many = Array.from({ length: 5 }, (_, i) =>
      entry({ id: `01a0cae5-0000-7000-8000-00000000001${i}` }),
    );
    expect(freshAwards(many, older.id)).toHaveLength(3);
  });
});

describe('حافظهٔ سطح', () => {
  afterEach(() => window.localStorage.clear());

  it('سطح دیده‌شده به‌ازای هر کاربر جدا نگه داشته می‌شود', () => {
    expect(lastSeenLevel('u-1')).toBeNull();
    rememberLevel('u-1', 4);
    expect(lastSeenLevel('u-1')).toBe(4);
    expect(lastSeenLevel('u-2')).toBeNull();
  });
});

describe('WRITE_EVENT — هر نوشتن موفق اعلام می‌شود', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('POST موفق رویداد می‌فرستد و GET نه', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response('{}', { status: 200 })),
    );
    const listener = vi.fn();
    window.addEventListener(WRITE_EVENT, listener);
    await apiFetch('/x');
    expect(listener).not.toHaveBeenCalled();
    await apiFetch('/x', { method: 'POST', body: {} });
    expect(listener).toHaveBeenCalledTimes(1);
    window.removeEventListener(WRITE_EVENT, listener);
  });
});

// ── اجزا ────────────────────────────────────────────────────────────────
describe('NextStepCard — FR-DASH-01', () => {
  it('یک اقدام با پیوند و مهلت خوانا', () => {
    render(
      <NextStepCard
        now={new Date('2026-10-01T08:00:00Z')}
        step={{
          kind: 'QUIZ_OPEN',
          title: 'آزمون «هفتهٔ سوم» باز است',
          description: '۳۰ دقیقه — پیش از بسته شدن شرکت کن.',
          href: '/courses/o-1/quizzes',
          due_at: '2026-10-01T13:00:00Z',
        }}
      />,
    );
    expect(screen.getByRole('heading', { name: 'آزمون «هفتهٔ سوم» باز است' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'برو به آزمون' })).toHaveAttribute(
      'href',
      '/courses/o-1/quizzes',
    );
    expect(screen.getByText('۵ ساعت تا مهلت')).toBeInTheDocument();
  });

  it('بدون کار عقب‌افتاده هم کارت خالی نمی‌ماند', () => {
    render(<NextStepCard step={null} />);
    expect(screen.getByRole('heading', { name: 'فعلاً کار عقب‌افتاده‌ای نداری' })).toBeInTheDocument();
  });
});

describe('LedgerRow — دفتر کل شفاف', () => {
  it('منشأ امتیاز پیوند دارد', () => {
    render(<ul><LedgerRow entry={entry()} /></ul>);
    expect(screen.getByRole('link', { name: 'تحقیق بازار — خرمای صابر' })).toHaveAttribute(
      'href',
      '/projects/p-1/workspace',
    );
    expect(screen.getByText('+۵۰')).toBeInTheDocument();
  });

  it('ردیف اصلاح‌شده خط می‌خورد، پاک نمی‌شود', () => {
    render(<ul><LedgerRow entry={entry({ is_reversed: true })} /></ul>);
    expect(screen.getByText('+۵۰')).toHaveClass('line-through');
  });

  it('ردیف معکوس با برچسب «اصلاح» و بدون رنگ هشدار', () => {
    render(
      <ul>
        <LedgerRow entry={entry({ amount: '-50.00', reverses_id: 'x', note: 'ثبت اشتباه' })} />
      </ul>,
    );
    expect(screen.getByText(/اصلاح: تأیید مرحلهٔ پروژه/)).toBeInTheDocument();
    expect(screen.getByText('ثبت اشتباه')).toBeInTheDocument();
    expect(screen.getByText('−۵۰')).not.toHaveClass('text-[var(--danger-600)]');
  });
});

describe('BadgeTile — §9.5', () => {
  it('نشان قفل شرط و پیشرفتش را نشان می‌دهد', () => {
    render(<BadgeTile badge={badge()} />);
    expect(screen.getByText('در ۵ آزمون نمرهٔ کامل بگیر.')).toBeInTheDocument();
    expect(screen.getByText('۳ از ۵')).toBeInTheDocument();
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '3');
  });

  it('نشان کسب‌شده با متن، نه فقط رنگ', () => {
    render(
      <BadgeTile
        badge={badge({ earned: true, awarded_at: '2026-10-01T08:00:00Z', progress_current: '5' })}
      />,
    );
    expect(screen.getByText(/^کسب‌شده/)).toBeInTheDocument();
    expect(screen.queryByRole('progressbar')).toBeNull();
  });
});

describe('CategoryTiles — چهار دستهٔ جدا', () => {
  it('هر دسته پیوندی به دفتر کل با همان فیلتر است، به ترتیب ایمن کوررنگی', () => {
    render(
      <CategoryTiles
        totals={{ LEARNING: '120.00', RESEARCH: '0.00', STARTUP: '35.50', COMMUNITY: '20.00' }}
      />,
    );
    const links = screen.getAllByRole('link');
    expect(links.map((l) => l.getAttribute('href'))).toEqual([
      '/me/points?category=LEARNING',
      '/me/points?category=STARTUP',
      '/me/points?category=RESEARCH',
      '/me/points?category=COMMUNITY',
    ]);
    expect(within(links[0] as HTMLElement).getByText('۱۲۰')).toBeInTheDocument();
  });
});

describe('PointsTrend — روند هفتگی', () => {
  const trend = [
    { week_start: '2026-09-12', total: '0.00' },
    { week_start: '2026-09-19', total: '40.00' },
    { week_start: '2026-09-26', total: '75.00' },
  ];

  it('جدول معادل برای صفحه‌خوان دارد', () => {
    render(<PointsTrend trend={trend} />);
    const table = screen.getByRole('table', { name: 'امتیاز هفتگی' });
    expect(within(table).getAllByRole('row')).toHaveLength(4);
  });

  it('برچسب مستقیم فقط روی هفتهٔ جاری است', () => {
    const { container } = render(<PointsTrend trend={trend} />);
    const labels = Array.from(container.querySelectorAll('svg text')).map((t) => t.textContent);
    expect(labels).toEqual(['۷۵']);
  });

  it('هر ستون با کیبورد قابل دسترسی و خواناست', () => {
    render(<PointsTrend trend={trend} />);
    expect(screen.getByLabelText(/۴۰ امتیاز$/)).toHaveAttribute('tabindex', '0');
  });
});
