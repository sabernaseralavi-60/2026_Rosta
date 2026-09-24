import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { Card, CardTitle } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { Progress } from '@/components/ui/Progress';

/**
 * ممیزی دسترس‌پذیری M7-14 — سه اصلاح در اجزای پایه که هر صفحه از آن‌ها
 * ارث می‌برد. axe در e2e همان را می‌سنجد؛ اینجا سریع و بی‌مرورگر.
 */

describe('Progress — نام دسترس‌پذیر', () => {
  it('بی‌برچسب دیدنی هم نام دارد', () => {
    render(<Progress value={30} valueText="۳۰٪" />);
    const bar = screen.getByRole('progressbar', { name: 'پیشرفت' });
    expect(bar).toHaveAttribute('aria-valuetext', '۳۰٪');
  });

  it('ariaLabel وقتی برچسب بیرون از نوار است', () => {
    render(<Progress value={30} ariaLabel="پیشرفت مطالعه" />);
    expect(screen.getByRole('progressbar', { name: 'پیشرفت مطالعه' })).toBeInTheDocument();
  });
});

describe('سطح عنوان', () => {
  it('حالت خالی h2 است، نه h3', () => {
    render(<EmptyState title="هنوز چیزی نیست" />);
    expect(screen.getByRole('heading', { level: 2, name: 'هنوز چیزی نیست' })).toBeInTheDocument();
  });

  it('CardTitle پیش‌فرض h3 است و `as` سطح را عوض می‌کند', () => {
    render(
      <Card>
        <CardTitle>زیر بخش</CardTitle>
        <CardTitle as="h1">تمام صفحه</CardTitle>
      </Card>,
    );
    expect(screen.getByRole('heading', { level: 3, name: 'زیر بخش' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 1, name: 'تمام صفحه' })).toBeInTheDocument();
  });
});
