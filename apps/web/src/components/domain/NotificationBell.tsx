'use client';

import Link from 'next/link';
import { useCallback, useEffect, useId, useRef, useState } from 'react';

import { SkeletonText } from '@/components/ui/Skeleton';
import { type AppNotification, fetchNotifications } from '@/lib/api/notifications';
import { useSession } from '@/lib/auth/use-session';
import { formatNumber } from '@/lib/format/digits';

import { NotificationItem } from './NotificationItem';
import { useNotifications } from './NotificationsProvider';

/**
 * زنگولهٔ هدر — FR-MSG-01 «زنگولهٔ اعلان با شمارندهٔ خوانده‌نشده در
 * تمام صفحات».
 *
 * پنل یک disclosure ساده است (دکمه + `aria-expanded` + `aria-controls`)،
 * نه منو: محتوایش پیوند و دکمه است و کاربر صفحه‌کلید با Tab در آن حرکت
 * می‌کند. Esc و کلیک بیرون می‌بندند و فوکوس به زنگوله برمی‌گردد.
 */

const PANEL_SIZE = 8;

export function bellLabel(unread: number | null): string {
  if (!unread) return 'اعلان‌ها';
  return `اعلان‌ها — ${formatNumber(unread)} خوانده‌نشده`;
}

export function badgeText(unread: number): string {
  return unread > 99 ? '+۹۹' : formatNumber(unread);
}

export function NotificationBell() {
  const { accessToken } = useSession({ required: false });
  const { unread, version, markRead, markAllRead } = useNotifications();
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<AppNotification[] | null>(null);
  const [failed, setFailed] = useState(false);
  const panelId = useId();
  const root = useRef<HTMLDivElement>(null);
  const button = useRef<HTMLButtonElement>(null);

  const load = useCallback(async () => {
    if (!accessToken) return;
    try {
      const feed = await fetchNotifications(accessToken, { limit: PANEL_SIZE });
      setItems(feed.items);
      setFailed(false);
    } catch {
      setFailed(true);
    }
  }, [accessToken]);

  // پنل باز است و اعلان تازه رسید ⇒ همان‌جا دیده شود.
  useEffect(() => {
    if (open) void load();
  }, [open, version, load]);

  useEffect(() => {
    if (!open) return;
    const onPointer = (event: PointerEvent) => {
      if (root.current && !root.current.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setOpen(false);
        button.current?.focus();
      }
    };
    document.addEventListener('pointerdown', onPointer);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('pointerdown', onPointer);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  if (!accessToken) return null;

  return (
    <div ref={root} className="relative">
      <button
        ref={button}
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        aria-label={bellLabel(unread)}
        onClick={() => setOpen((value) => !value)}
        className="relative flex size-10 items-center justify-center rounded-[var(--radius-md)] text-[var(--fg-secondary)] transition-colors hover:bg-[var(--bg-sunken)] hover:text-[var(--fg-primary)]"
      >
        <BellIcon />
        {unread ? (
          <span
            aria-hidden="true"
            className="absolute -top-0.5 end-0 flex h-[18px] min-w-[18px] items-center justify-center rounded-[var(--radius-full)] bg-[var(--accent-600)] px-1 text-[11px] font-bold leading-none text-[var(--neutral-0)]"
          >
            {badgeText(unread)}
          </span>
        ) : null}
      </button>

      {open && (
        <div
          id={panelId}
          role="region"
          aria-label="آخرین اعلان‌ها"
          className="absolute end-0 top-12 z-40 flex w-[min(92vw,380px)] flex-col overflow-hidden rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-raised)] shadow-[var(--shadow-lg)]"
        >
          <div className="flex items-center justify-between border-b border-[var(--border-subtle)] px-4 py-3">
            <h2 className="text-[15px] font-semibold">اعلان‌ها</h2>
            {unread ? (
              <button
                type="button"
                onClick={() => void markAllRead()}
                className="text-[13px] font-medium text-[var(--brand-700)] hover:underline"
              >
                همه را خواندم
              </button>
            ) : null}
          </div>

          <div className="max-h-[60vh] overflow-y-auto">
            {failed ? (
              <p className="px-4 py-6 text-center text-[13.5px] text-[var(--fg-secondary)]">
                اعلان‌ها بارگذاری نشد. کمی بعد دوباره باز کن.
              </p>
            ) : items === null ? (
              <div className="p-4">
                <SkeletonText label="در حال بارگذاری اعلان‌ها" />
              </div>
            ) : items.length === 0 ? (
              <p className="px-4 py-8 text-center text-[13.5px] text-[var(--fg-secondary)]">
                هنوز اعلانی نداری. خبرهای درس و پروژه اینجا می‌آید.
              </p>
            ) : (
              <ul className="divide-y divide-[var(--border-subtle)]">
                {items.map((notification) => (
                  <li key={notification.id}>
                    <NotificationItem
                      compact
                      notification={notification}
                      onOpen={async (n) => {
                        setOpen(false);
                        await markRead(n);
                      }}
                    />
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="flex items-center justify-between border-t border-[var(--border-subtle)] px-4 py-2.5 text-[13px]">
            <Link
              href="/notifications"
              onClick={() => setOpen(false)}
              className="font-medium text-[var(--brand-700)] hover:underline"
            >
              همهٔ اعلان‌ها
            </Link>
            <Link
              href="/me/settings"
              onClick={() => setOpen(false)}
              className="text-[var(--fg-secondary)] hover:underline"
            >
              تنظیمات اعلان
            </Link>
          </div>
        </div>
      )}
    </div>
  );
}

function BellIcon() {
  return (
    <svg viewBox="0 0 24 24" className="size-[22px]" fill="none" aria-hidden="true">
      <path
        d="M6 16V11a6 6 0 1 1 12 0v5l1.5 2h-15L6 16Z"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
      <path
        d="M10 20.5a2.2 2.2 0 0 0 4 0"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
    </svg>
  );
}
