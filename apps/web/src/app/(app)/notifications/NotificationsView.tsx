'use client';

import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { type ReactNode, useCallback, useEffect, useState } from 'react';

import { NotificationItem } from '@/components/domain/NotificationItem';
import { useNotifications } from '@/components/domain/NotificationsProvider';
import { Button } from '@/components/ui/Button';
import { EmptyState } from '@/components/ui/EmptyState';
import { SkeletonText } from '@/components/ui/Skeleton';
import { ApiError } from '@/lib/api/client';
import {
  type AppNotification,
  fetchNotifications,
  GROUP_LABELS,
  GROUPS,
  type NotificationGroup,
} from '@/lib/api/notifications';
import { useSession } from '@/lib/auth/use-session';
import { cn } from '@/lib/cn';
import { formatNumber } from '@/lib/format/digits';

/**
 * مرکز اعلان — FR-MSG-01، §3 `/notifications`.
 *
 * فیلترها در نشانی‌اند (`?unread=1`، `?group=PROJECT`) تا «اعلان‌های
 * خوانده‌نشدهٔ پروژه» پیوند قابل اشتراک باشد. اعلان‌های خوانده‌شدهٔ
 * قدیمی‌تر از ۹۰ روز آرشیو می‌شوند و اینجا نمی‌آیند (§4.12).
 */

function isGroup(value: string | null): value is NotificationGroup {
  return value !== null && (GROUPS as string[]).includes(value);
}

export function NotificationsView() {
  const params = useSearchParams();
  const { accessToken, loading } = useSession();
  const { unread, version, markRead, markAllRead } = useNotifications();
  const group = isGroup(params.get('group'))
    ? (params.get('group') as NotificationGroup)
    : undefined;
  const unreadOnly = params.get('unread') === '1';

  const [items, setItems] = useState<AppNotification[] | null>(null);
  const [cursor, setCursor] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [clearing, setClearing] = useState(false);

  useEffect(() => {
    if (loading || !accessToken) return;
    let cancelled = false;
    fetchNotifications(accessToken, { group, unread_only: unreadOnly })
      .then((feed) => {
        if (cancelled) return;
        setItems(feed.items);
        setCursor(feed.next_cursor);
        setError(null);
      })
      .catch((cause: unknown) => {
        if (!cancelled)
          setError(cause instanceof ApiError ? cause.message : 'اعلان‌ها بارگذاری نشد.');
      });
    return () => {
      cancelled = true;
    };
    // `version`: اعلان تازه یا تغییر خواندن ⇒ صفحهٔ اول دوباره خوانده می‌شود.
  }, [accessToken, loading, group, unreadOnly, version]);

  const loadMore = useCallback(async () => {
    if (!accessToken || !cursor) return;
    setLoadingMore(true);
    try {
      const feed = await fetchNotifications(accessToken, {
        group,
        unread_only: unreadOnly,
        cursor,
      });
      setItems((current) => [...(current ?? []), ...feed.items]);
      setCursor(feed.next_cursor);
    } finally {
      setLoadingMore(false);
    }
  }, [accessToken, cursor, group, unreadOnly]);

  async function clearAll() {
    setClearing(true);
    try {
      await markAllRead();
    } finally {
      setClearing(false);
    }
  }

  const query = (next: { group?: NotificationGroup; unread?: boolean }) => {
    const search = new URLSearchParams();
    if (next.group) search.set('group', next.group);
    if (next.unread) search.set('unread', '1');
    const text = search.toString();
    return text ? `/notifications?${text}` : '/notifications';
  };

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="flex flex-col gap-1">
          <h1>اعلان‌ها</h1>
          <p className="text-[15px] text-[var(--fg-secondary)]">
            {unread
              ? `${formatNumber(unread)} اعلان خوانده‌نشده داری.`
              : 'همهٔ اعلان‌ها را خوانده‌ای.'}{' '}
            <Link
              href="/me/settings"
              className="font-medium text-[var(--fg-brand)] hover:underline"
            >
              کدام خبرها به پیامک و تلگرام بیاید؟
            </Link>
          </p>
        </div>
        {unread ? (
          <Button variant="secondary" size="sm" onClick={() => void clearAll()} loading={clearing}>
            همه را خواندم
          </Button>
        ) : null}
      </div>

      <nav aria-label="فیلتر اعلان‌ها" className="flex flex-wrap gap-2">
        <Chip href={query({ unread: unreadOnly })} active={!group}>
          همه
        </Chip>
        {GROUPS.map((value) => (
          <Chip
            key={value}
            href={query({ group: value, unread: unreadOnly })}
            active={group === value}
          >
            {GROUP_LABELS[value]}
          </Chip>
        ))}
        <span aria-hidden="true" className="mx-1 w-px self-stretch bg-[var(--border-subtle)]" />
        <Chip href={query({ group, unread: !unreadOnly })} active={unreadOnly}>
          فقط خوانده‌نشده
        </Chip>
      </nav>

      {error ? (
        <EmptyState title="اعلان‌ها بارگذاری نشد" description={error} />
      ) : items === null ? (
        <SkeletonText label="در حال بارگذاری اعلان‌ها" />
      ) : items.length === 0 ? (
        <EmptyState
          title={unreadOnly ? 'اعلان خوانده‌نشده‌ای نداری' : 'اینجا هنوز اعلانی نیست'}
          description="تأیید تحویل، هفتهٔ تازهٔ درس، نتیجهٔ آزمون و مهلت‌های نزدیک اینجا خبر داده می‌شوند."
        />
      ) : (
        <ul className="flex flex-col divide-y divide-[var(--border-subtle)] overflow-hidden rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-surface)]">
          {items.map((notification) => (
            <li key={notification.id}>
              <NotificationItem notification={notification} onOpen={markRead} />
            </li>
          ))}
        </ul>
      )}

      {cursor && (
        <Button
          variant="secondary"
          onClick={loadMore}
          loading={loadingMore}
          className="self-center"
        >
          اعلان‌های قدیمی‌تر
        </Button>
      )}
    </div>
  );
}

function Chip({ href, active, children }: { href: string; active: boolean; children: ReactNode }) {
  return (
    <Link
      href={href}
      aria-current={active ? 'page' : undefined}
      className={cn(
        'inline-flex items-center gap-1.5 rounded-[var(--radius-full)] border px-3 py-1.5 text-[13px]',
        active
          ? 'border-[var(--brand-600)] bg-[var(--brand-50)] font-medium text-[var(--fg-brand)]'
          : 'border-[var(--border-subtle)] text-[var(--fg-secondary)] hover:border-[var(--border-default)]',
      )}
    >
      {children}
    </Link>
  );
}
