import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { RequestTimeline } from '@/components/domain/RequestTimeline';
import { TrackForm } from '@/components/public/TrackForm';
import {
  CLIENT_STATUS_LABELS,
  canManageInbox,
  type IntakeEvent,
  STATUS_LABELS,
  STATUS_TONES,
  STATUSES,
} from '@/lib/api/inbox';

/** صندوق درخواست، داشبورد مالک و پیگیری مشتری — ADR-0032. */

const EVENTS: IntakeEvent[] = [
  {
    id: 'e1',
    from_status: 'NEW',
    to_status: 'IN_REVIEW',
    public_note: 'درخواست شما بررسی شد.',
    created_at: '2026-09-28T08:00:00Z',
  },
  {
    id: 'e2',
    from_status: 'IN_REVIEW',
    to_status: 'IN_REVIEW',
    public_note: 'یک سؤال دربارهٔ بودجه داریم.',
    created_at: '2026-09-29T08:00:00Z',
  },
];

afterEach(() => vi.unstubAllGlobals());

describe('برچسب وضعیت‌ها', () => {
  it('هر وضعیت برای مالک و مشتری برچسب و رنگ دارد', () => {
    for (const status of STATUSES) {
      expect(STATUS_LABELS[status]).toBeTruthy();
      expect(CLIENT_STATUS_LABELS[status]).toBeTruthy();
      expect(STATUS_TONES[status]).toBeTruthy();
    }
  });

  it('«جدید» برای مشتری «دریافت شد» است، نه برچسب صندوقِ مالک', () => {
    expect(STATUS_LABELS.NEW).toBe('جدید');
    expect(CLIENT_STATUS_LABELS.NEW).toBe('دریافت شد');
  });

  it('فقط ADMIN صندوق را می‌بیند (همان ماتریس مجوز سرور)', () => {
    expect(canManageInbox(['ADMIN'])).toBe(true);
    for (const role of ['SUPPORT', 'COORDINATOR', 'INSTRUCTOR', 'STUDENT']) {
      expect(canManageInbox([role])).toBe(false);
    }
    expect(canManageInbox(undefined)).toBe(false);
  });
});

describe('تاریخچهٔ رسیدگی', () => {
  it('«ثبت شد» و هر رویداد با برچسبِ مخاطب را نشان می‌دهد', () => {
    render(
      <RequestTimeline
        createdAt="2026-09-27T08:00:00Z"
        events={EVENTS}
        labels={CLIENT_STATUS_LABELS}
      />,
    );
    expect(screen.getByText('ثبت شد')).toBeInTheDocument();
    expect(screen.getAllByText('در حال بررسی')).toHaveLength(2);
    expect(screen.getByText('درخواست شما بررسی شد.')).toBeInTheDocument();
    expect(screen.getByText('یک سؤال دربارهٔ بودجه داریم.')).toBeInTheDocument();
  });

  it('پیام بدون تغییر وضعیت «پیام تازه» علامت می‌خورد', () => {
    render(
      <RequestTimeline createdAt="2026-09-27T08:00:00Z" events={EVENTS} labels={STATUS_LABELS} />,
    );
    expect(screen.getAllByText('پیام تازه')).toHaveLength(1);
  });

  it('بدون رویداد فقط «ثبت شد» می‌ماند', () => {
    render(<RequestTimeline createdAt="2026-09-27T08:00:00Z" events={[]} labels={STATUS_LABELS} />);
    expect(screen.getAllByRole('listitem')).toHaveLength(1);
  });
});

function stubFetch(status: number, body: unknown) {
  const fetchMock = vi.fn().mockResolvedValue(
    new Response(JSON.stringify(body), {
      status,
      headers: { 'Content-Type': 'application/json' },
    }),
  );
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

describe('فرم پیگیری بی‌ورود', () => {
  it('دکمه تا پر شدن هر دو فیلد غیرفعال است', async () => {
    render(<TrackForm />);
    const button = screen.getByRole('button', { name: 'پیگیری' });
    expect(button).toBeDisabled();
    await userEvent.type(screen.getByLabelText('کد پیگیری'), 'Q-1001');
    expect(button).toBeDisabled();
    await userEvent.type(screen.getByLabelText(/شمارهٔ موبایل یا ایمیل/), '09121234567');
    expect(button).toBeEnabled();
  });

  it('کد و راه تماس را می‌فرستد و وضعیت را با برچسب مشتری نشان می‌دهد', async () => {
    const fetchMock = stubFetch(200, {
      tracking_code: 'Q-1001',
      kind: 'INTAKE',
      status: 'NEW',
      need_type: 'Commercial',
      created_at: '2026-09-27T08:00:00Z',
      updated_at: '2026-09-27T08:00:00Z',
      events: [],
    });
    render(<TrackForm />);
    await userEvent.type(screen.getByLabelText('کد پیگیری'), 'Q-1001');
    await userEvent.type(screen.getByLabelText(/شمارهٔ موبایل یا ایمیل/), '09121234567');
    await userEvent.click(screen.getByRole('button', { name: 'پیگیری' }));

    expect(await screen.findByText('دریافت شد')).toBeInTheDocument();
    expect(screen.getByText(/مسئله \/ نیاز \(تجاری\)/)).toBeInTheDocument();
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain('/public/track');
    expect(JSON.parse(String(init.body))).toEqual({
      tracking_code: 'Q-1001',
      contact: '09121234567',
    });
  });

  it('خطای سرور را همان‌طور نشان می‌دهد و نتیجهٔ قبلی را پاک می‌کند', async () => {
    stubFetch(404, {
      error: {
        code: 'NOT_FOUND',
        message: 'درخواستی با این کد و راه تماس پیدا نشد.',
        details: {},
        trace_id: 't',
      },
    });
    render(<TrackForm />);
    await userEvent.type(screen.getByLabelText('کد پیگیری'), 'Q-1');
    await userEvent.type(screen.getByLabelText(/شمارهٔ موبایل یا ایمیل/), '09120000000');
    await userEvent.click(screen.getByRole('button', { name: 'پیگیری' }));
    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent(
        'درخواستی با این کد و راه تماس پیدا نشد.',
      ),
    );
  });

  it('سهمیه که شکست پیام آرام و بی‌جزئیات می‌دهد', async () => {
    stubFetch(429, {
      error: { code: 'RATE_LIMITED', message: 'x', details: { retry_after: 60 }, trace_id: 't' },
    });
    render(<TrackForm />);
    await userEvent.type(screen.getByLabelText('کد پیگیری'), 'Q-1');
    await userEvent.type(screen.getByLabelText(/شمارهٔ موبایل یا ایمیل/), '09120000000');
    await userEvent.click(screen.getByRole('button', { name: 'پیگیری' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('تلاش‌های زیادی شد');
  });
});
