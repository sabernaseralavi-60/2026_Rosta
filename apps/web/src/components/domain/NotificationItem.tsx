'use client';

import { useRouter } from 'next/navigation';

import type { AppNotification } from '@/lib/api/notifications';
import { cn } from '@/lib/cn';
import { formatRelative } from '@/lib/format/date';

/**
 * یک اعلان — در پنل زنگوله و در مرکز اعلان. FR-MSG-01: «نوع، عنوان،
 * متن، لینک اقدام، وضعیت خواندن».
 *
 * کل ردیف یک دکمه است: کلیک، اعلان را خوانده می‌کند و اگر لینک اقدام
 * دارد، به آن می‌رود. خوانده‌نشده با نقطه و وزن قلم مشخص است، نه فقط رنگ
 * (§10.8 — رنگ تنها حامل معنا نیست).
 */
export function NotificationItem({
  notification,
  onOpen,
  compact = false,
}: {
  notification: AppNotification;
  onOpen: (notification: AppNotification) => Promise<void> | void;
  compact?: boolean;
}) {
  const router = useRouter();
  const unread = !notification.is_read;
  const urgent = notification.priority === 'URGENT' || notification.priority === 'IMPORTANT';

  async function open() {
    try {
      await onOpen(notification);
    } finally {
      if (notification.action_url) router.push(notification.action_url);
    }
  }

  return (
    <button
      type="button"
      onClick={() => void open()}
      className={cn(
        'flex w-full items-start gap-3 text-start transition-colors hover:bg-[var(--bg-sunken)]',
        compact ? 'px-4 py-3' : 'px-5 py-4',
      )}
    >
      <span
        aria-hidden="true"
        className={cn(
          'mt-2 size-2 shrink-0 rounded-[var(--radius-full)]',
          unread ? (urgent ? 'bg-[var(--accent-600)]' : 'bg-[var(--brand-600)]') : 'bg-transparent',
        )}
      />
      <span className="flex min-w-0 flex-1 flex-col gap-0.5">
        <span className="sr-only">{unread ? 'خوانده‌نشده: ' : ''}</span>
        <span
          className={cn(
            'text-[14px] text-[var(--fg-primary)]',
            unread ? 'font-semibold' : 'font-medium',
          )}
        >
          {notification.title}
        </span>
        <span className={cn('text-[13px] text-[var(--fg-secondary)]', compact && 'line-clamp-2')}>
          {notification.body}
        </span>
        <span className="flex items-center gap-1.5 text-[12px] text-[var(--fg-tertiary)]">
          <time dateTime={notification.created_at}>{formatRelative(notification.created_at)}</time>
          <span aria-hidden="true">·</span>
          <span>{notification.group_fa}</span>
        </span>
      </span>
    </button>
  );
}
