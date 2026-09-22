import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { MilestoneTracker } from '@/components/domain/MilestoneTracker';
import { Textarea } from '@/components/ui/Textarea';
import { formatBytes } from '@/lib/api/files';
import type { Milestone } from '@/lib/api/workspace';

function milestone(overrides: Partial<Milestone> = {}): Milestone {
  return {
    id: overrides.id ?? 'm-1',
    project_id: 'p-1',
    title_fa: 'مرحلهٔ اول',
    description: null,
    sort_order: 1,
    due_on: null,
    points: 0,
    is_required: true,
    output_kind: null,
    output_kind_fa: null,
    checklist: [],
    status: 'PENDING',
    status_fa: 'شروع نشده',
    approved_at: null,
    my_deliverable: null,
    deliverable_count: 0,
    ...overrides,
  };
}

describe('MilestoneTracker — §10.6، M2-12', () => {
  it('وضعیت هر مرحله را با متن می‌گوید، نه فقط با رنگ — §10.2', () => {
    render(
      <MilestoneTracker
        milestones={[
          milestone({ id: 'a', status: 'APPROVED', status_fa: 'تأیید شده' }),
          milestone({ id: 'b', title_fa: 'مرحلهٔ دوم', status: 'OVERDUE', status_fa: 'از مهلت گذشته' }),
        ]}
      />,
    );

    expect(screen.getByText('تأیید شده')).toBeInTheDocument();
    expect(screen.getByText('از مهلت گذشته')).toBeInTheDocument();
  });

  it('مرحلهٔ اختیاری و بارم امتیاز را جدا نشان می‌دهد', () => {
    render(
      <MilestoneTracker
        milestones={[milestone({ is_required: false, points: 30 })]}
      />,
    );

    expect(screen.getByText('اختیاری')).toBeInTheDocument();
    expect(screen.getByText('۳۰ امتیاز')).toBeInTheDocument();
  });

  it('چک‌لیست معیارهای کیفیت را فهرست می‌کند', () => {
    render(
      <MilestoneTracker
        milestones={[milestone({ checklist: ['ده مصاحبه', 'گزارش یک‌صفحه‌ای'] })]}
      />,
    );

    expect(screen.getByText('ده مصاحبه')).toBeInTheDocument();
    expect(screen.getByText('گزارش یک‌صفحه‌ای')).toBeInTheDocument();
  });

  it('محتوای اضافی هر مرحله را همان‌جا رندر می‌کند', () => {
    render(
      <MilestoneTracker
        milestones={[milestone()]}
        renderExtra={(item) => <button>تحویل {item.title_fa}</button>}
      />,
    );

    expect(screen.getByRole('button', { name: 'تحویل مرحلهٔ اول' })).toBeInTheDocument();
  });

  it('ترتیب مراحل همان ترتیب ورودی است', () => {
    render(
      <MilestoneTracker
        milestones={[
          milestone({ id: 'a', title_fa: 'اول' }),
          milestone({ id: 'b', title_fa: 'دوم' }),
          milestone({ id: 'c', title_fa: 'سوم' }),
        ]}
      />,
    );

    const headings = screen.getAllByRole('heading', { level: 3 });
    expect(headings.map((node) => node.textContent)).toEqual(['اول', 'دوم', 'سوم']);
  });
});

describe('Textarea — §10.6، §10.8', () => {
  function Controlled({ maxLength }: { maxLength?: number }) {
    const [value, setValue] = useState('');
    return (
      <Textarea
        label="انگیزه‌نامه"
        maxLength={maxLength}
        value={value}
        onChange={(event) => setValue(event.target.value)}
      />
    );
  }

  it('برچسب به فیلد وصل است — placeholder برچسب نیست', () => {
    render(<Controlled />);
    expect(screen.getByLabelText('انگیزه‌نامه')).toBeInTheDocument();
  });

  it('شمارندهٔ نویسه با ارقام فارسی به‌روز می‌شود', async () => {
    const user = userEvent.setup();
    render(<Controlled maxLength={500} />);

    await user.type(screen.getByLabelText('انگیزه‌نامه'), 'سلام');
    expect(screen.getByText('۴/۵۰۰')).toBeInTheDocument();
  });

  it('خطا با role="alert" اعلام می‌شود و به فیلد وصل است', () => {
    render(<Textarea label="بازخورد" error="بازخورد اجباری است." value="" onChange={vi.fn()} />);

    const field = screen.getByLabelText('بازخورد');
    expect(field).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByRole('alert')).toHaveTextContent('بازخورد اجباری است.');
    expect(field.getAttribute('aria-describedby')).toContain(
      screen.getByRole('alert').getAttribute('id'),
    );
  });

  it('بدون maxLength شمارنده‌ای نشان داده نمی‌شود', () => {
    render(<Controlled />);
    expect(screen.queryByText(/\//)).not.toBeInTheDocument();
  });
});

describe('formatBytes — §5.9', () => {
  it('اندازه را با واحد فارسی می‌نویسد', () => {
    expect(formatBytes(512)).toBe('۵۱۲ بایت');
    expect(formatBytes(2048)).toBe('۲ کیلوبایت');
  });

  it('برای اندازه‌های بزرگ یک رقم اعشار نگه می‌دارد', () => {
    expect(formatBytes(2_516_582)).toBe('۲٫۴ مگابایت');
  });

  it('از گیگابایت بالاتر نمی‌رود', () => {
    expect(formatBytes(5 * 1024 ** 4)).toContain('گیگابایت');
  });
});
