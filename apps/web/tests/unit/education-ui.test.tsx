import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { MaterialRow } from '@/components/domain/MaterialRow';
import { WeekTimeline } from '@/components/domain/WeekTimeline';
import type { Access, Material, WeekSummary } from '@/lib/api/courses';

function access(overrides: Partial<Access> = {}): Access {
  return {
    allowed: true,
    tier: 'SUBSCRIBER',
    reason: 'ENROLLED',
    blocker: null,
    note_fa: 'شما دانشجوی این درس هستید؛ محتوای درس برایتان رایگان است.',
    ...overrides,
  };
}

function material(overrides: Partial<Material> = {}): Material {
  return {
    id: 'm-1',
    kind: 'BOOK',
    kind_fa: 'کتاب',
    title_fa: 'مهندسی شبیه‌سازی ترافیک با SUMO',
    description: null,
    authors: ['سید صابر ناصرعلوی'],
    edition: null,
    language: 'fa',
    size_bytes: null,
    page_count: null,
    duration_sec: null,
    is_downloadable: true,
    external_url: 'https://example.invalid/book.pdf',
    section: null,
    is_required: true,
    access: access(),
    ...overrides,
  };
}

function week(overrides: Partial<WeekSummary> = {}): WeekSummary {
  return {
    id: 'w-1',
    week_number: 1,
    title_fa: 'مفاهیم ایمنی راه',
    description: null,
    status: 'PUBLISHED',
    published_at: '2026-09-23T08:00:00Z',
    publish_at: null,
    resource_count: 2,
    material_count: 1,
    completed_count: 1,
    progress_percent: 50,
    ...overrides,
  };
}

describe('MaterialRow — ADR-0008/0009', () => {
  it('محتوای قفل‌شده را پنهان نمی‌کند، فقط دانلودش را می‌بندد', () => {
    render(
      <MaterialRow
        material={material({
          access: access({
            allowed: false,
            reason: null,
            blocker: 'SUBSCRIPTION',
            note_fa: 'برای دیدن این محتوا اشتراک بگیرید — یا در همین درس ثبت‌نام کنید.',
          }),
        })}
        accessToken="token"
      />,
    );

    // عنوان دیده می‌شود…
    expect(screen.getByText('مهندسی شبیه‌سازی ترافیک با SUMO')).toBeInTheDocument();
    // …ولی دکمهٔ دانلود نه.
    expect(screen.queryByRole('button', { name: 'دانلود' })).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'تهیهٔ اشتراک' })).toBeInTheDocument();
  });

  it('متن دلیل را از سرور می‌گیرد و بازنویسی نمی‌کند', () => {
    const note = 'شما دانشجوی این درس هستید؛ محتوای درس برایتان رایگان است.';
    render(<MaterialRow material={material()} accessToken="token" />);
    expect(screen.getByText(note)).toBeInTheDocument();
  });

  it('برای مادهٔ ویژهٔ دانشجویان، دکمهٔ اشتراک نشان نمی‌دهد', () => {
    render(
      <MaterialRow
        material={material({
          kind: 'QUESTION_BANK',
          kind_fa: 'بانک سؤال',
          access: access({
            allowed: false,
            tier: 'ENROLLED',
            reason: null,
            blocker: 'ENROLLMENT',
            note_fa: 'این محتوا فقط برای دانشجویان ثبت‌نام‌شدهٔ همین درس است.',
          }),
        })}
        accessToken="token"
      />,
    );

    expect(screen.getByText('ویژهٔ دانشجویان درس')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'تهیهٔ اشتراک' })).not.toBeInTheDocument();
  });

  it('نشانی بیرونی محتوای قفل‌شده را در DOM نمی‌گذارد', () => {
    const { container } = render(
      <MaterialRow
        material={material({
          external_url: null,
          access: access({ allowed: false, reason: null, blocker: 'SUBSCRIPTION', note_fa: '…' }),
        })}
        accessToken="token"
      />,
    );
    expect(container.innerHTML).not.toContain('example.invalid');
  });
});

describe('WeekTimeline — §10.6، M3-11', () => {
  it('هفتهٔ منتشرنشده را با متن مشخص می‌کند، نه فقط با رنگ — §10.2', () => {
    render(<WeekTimeline weeks={[week({ status: 'DRAFT', published_at: null })]} />);
    expect(screen.getByText('منتشر نشده')).toBeInTheDocument();
  });

  it('فقط هفتهٔ منتشرشده لینک می‌گیرد', () => {
    render(
      <WeekTimeline
        weeks={[
          week({ id: 'a', week_number: 1 }),
          week({ id: 'b', week_number: 2, status: 'DRAFT', title_fa: 'هفتهٔ دوم' }),
        ]}
        hrefFor={(w) => `/courses/o-1/weeks/${w.week_number}`}
      />,
    );

    expect(screen.getAllByRole('link')).toHaveLength(1);
  });

  it('هفتهٔ بدون محتوا را صریح می‌گوید', () => {
    render(<WeekTimeline weeks={[week({ resource_count: 0, material_count: 0 })]} />);
    expect(screen.getByText('هنوز محتوایی برای این هفته گذاشته نشده.')).toBeInTheDocument();
  });

  it('هفتهٔ جاری را نشان‌دار می‌کند', () => {
    render(<WeekTimeline weeks={[week()]} currentWeekNumber={1} />);
    expect(screen.getByText('هفتهٔ جاری')).toBeInTheDocument();
  });

  it('فهرست خالی را با پیام روشن نشان می‌دهد، نه با هیچ', () => {
    render(<WeekTimeline weeks={[]} />);
    expect(screen.getByText('هنوز هفته‌ای منتشر نشده است.')).toBeInTheDocument();
  });
});
