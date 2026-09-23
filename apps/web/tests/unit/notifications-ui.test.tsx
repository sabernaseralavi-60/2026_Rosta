import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { canSelect, type Choices, toggle } from '@/app/(app)/me/settings/NotificationSettingsView';
import { badgeText, bellLabel } from '@/components/domain/NotificationBell';
import { NotificationItem } from '@/components/domain/NotificationItem';
import { type AppNotification, type ChannelStatus, parseSse } from '@/lib/api/notifications';

const push = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push, replace: vi.fn(), prefetch: vi.fn() }),
}));

function notification(overrides: Partial<AppNotification> = {}): AppNotification {
  return {
    id: '01a0cc28-0000-7000-8000-000000000001',
    kind: 'DELIVERABLE_APPROVED',
    group: 'PROJECT',
    group_fa: 'پروژه‌ها',
    title: 'تحویل «گزارش مرور ادبیات» تأیید شد',
    body: 'تحویل «گزارش مرور ادبیات» در پروژهٔ «خرمای صابر» تأیید شد و ۵۰ امتیاز گرفتی.',
    action_url: '/projects/p-1/workspace',
    priority: 'IMPORTANT',
    created_at: new Date(Date.now() - 5 * 60_000).toISOString(),
    read_at: null,
    is_read: false,
    ...overrides,
  };
}

// ── تجزیهٔ SSE ─────────────────────────────────────────────────────────
describe('parseSse — جریان اعلان', () => {
  it('reads named events and ignores retry and comments', () => {
    const text =
      'retry: 5000\n\n' +
      'event: unread\ndata: {"count":3}\n\n' +
      ': ping\n\n' +
      'event: notification\ndata: {"id":"x"}\n\n';
    const { events, rest } = parseSse(text);
    expect(events).toEqual([
      { event: 'unread', data: '{"count":3}' },
      { event: 'notification', data: '{"id":"x"}' },
    ]);
    expect(rest).toBe('');
  });

  it('keeps an unfinished event for the next chunk', () => {
    const first = parseSse('event: unread\ndata: {"cou');
    expect(first.events).toEqual([]);
    const second = parseSse(first.rest + 'nt":1}\n\n');
    expect(second.events).toEqual([{ event: 'unread', data: '{"count":1}' }]);
  });

  it('accepts CRLF line endings from proxies', () => {
    const { events } = parseSse('event: unread\r\ndata: {"count":0}\r\n\r\n');
    expect(events).toEqual([{ event: 'unread', data: '{"count":0}' }]);
  });

  it('keeps Persian text intact', () => {
    const { events } = parseSse('event: notification\ndata: {"title":"نشان تازه!"}\n\n');
    expect(JSON.parse(events[0]!.data).title).toBe('نشان تازه!');
  });
});

// ── زنگوله ─────────────────────────────────────────────────────────────
describe('NotificationBell labels', () => {
  it('announces the unread count in Persian', () => {
    expect(bellLabel(null)).toBe('اعلان‌ها');
    expect(bellLabel(0)).toBe('اعلان‌ها');
    expect(bellLabel(3)).toBe('اعلان‌ها — ۳ خوانده‌نشده');
  });

  it('caps the badge at 99', () => {
    expect(badgeText(7)).toBe('۷');
    expect(badgeText(120)).toBe('+۹۹');
  });
});

describe('NotificationItem', () => {
  it('marks unread items for screen readers, not just with colour', () => {
    render(<NotificationItem notification={notification()} onOpen={vi.fn()} />);
    expect(screen.getByText('خوانده‌نشده:', { exact: false })).toBeInTheDocument();
    expect(screen.getByText('۵ دقیقه پیش')).toBeInTheDocument();
    expect(screen.getByText('پروژه‌ها')).toBeInTheDocument();
  });

  it('marks read and follows the action link on click', async () => {
    const onOpen = vi.fn();
    push.mockClear();
    render(<NotificationItem notification={notification()} onOpen={onOpen} />);
    await userEvent.click(screen.getByRole('button'));
    expect(onOpen).toHaveBeenCalledOnce();
    expect(push).toHaveBeenCalledWith('/projects/p-1/workspace');
  });

  it('stays put when there is no action link', async () => {
    push.mockClear();
    render(
      <NotificationItem
        notification={notification({
          action_url: null,
          is_read: true,
          read_at: '2026-10-01T08:00:00Z',
        })}
        onOpen={vi.fn()}
      />,
    );
    await userEvent.click(screen.getByRole('button'));
    expect(push).not.toHaveBeenCalled();
    expect(screen.queryByText('خوانده‌نشده:', { exact: false })).not.toBeInTheDocument();
  });
});

// ── تنظیمات ────────────────────────────────────────────────────────────
function status(overrides: Partial<ChannelStatus> = {}): ChannelStatus {
  return {
    channel: 'TELEGRAM',
    title_fa: 'تلگرام',
    available: true,
    requires_link: true,
    linked: false,
    address_masked: null,
    link_flow: 'DEEP_LINK',
    pending_link: false,
    ...overrides,
  };
}

describe('notification preferences', () => {
  const choices: Choices = {
    COURSE: ['IN_APP', 'EMAIL'],
    PROJECT: ['IN_APP', 'SMS'],
    SOCIAL: ['IN_APP'],
    SYSTEM: ['IN_APP', 'EMAIL', 'SMS'],
  };

  it('toggles one channel in one category only', () => {
    const next = toggle(choices, 'PROJECT', 'SMS');
    expect(next.PROJECT).toEqual(['IN_APP']);
    expect(next.SYSTEM).toContain('SMS');
    expect(toggle(next, 'PROJECT', 'SMS').PROJECT).toEqual(['IN_APP', 'SMS']);
  });

  it('never turns the in-app centre off', () => {
    expect(toggle(choices, 'COURSE', 'IN_APP')).toBe(choices);
  });

  it('refuses a messenger that is not linked yet', () => {
    expect(canSelect(status())).toBe(false);
    expect(canSelect(status({ linked: true }))).toBe(true);
    expect(canSelect(status({ linked: true, available: false }))).toBe(false);
  });
});
