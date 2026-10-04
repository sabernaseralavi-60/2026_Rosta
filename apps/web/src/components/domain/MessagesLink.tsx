'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';

import { fetchUnread } from '@/lib/api/messaging';
import { readSession } from '@/lib/auth/session';
import { toPersianDigits } from '@/lib/format/digits';

const REFRESH_MS = 60_000;

/** پیوند «پیام‌ها» با شمارندهٔ خوانده‌نشده؛ خطای شبکه شمارنده را فقط پنهان می‌کند. */
export function MessagesLink() {
  const [unread, setUnread] = useState(0);

  useEffect(() => {
    let alive = true;
    const refresh = () => {
      const session = readSession();
      if (!session || document.visibilityState !== 'visible') return;
      fetchUnread(session.accessToken)
        .then((result) => alive && setUnread(result.unread))
        .catch(() => undefined);
    };
    refresh();
    const timer = window.setInterval(refresh, REFRESH_MS);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, []);

  return (
    <Link
      href="/messages"
      aria-label={unread > 0 ? `پیام‌ها، ${toPersianDigits(unread)} خوانده‌نشده` : 'پیام‌ها'}
      className="relative inline-flex size-10 items-center justify-center rounded-[var(--radius-md)] text-[18px] hover:bg-[var(--bg-sunken)]"
    >
      <span aria-hidden="true">✉</span>
      {unread > 0 && (
        <span
          aria-hidden="true"
          className="absolute -top-0.5 -end-0.5 min-w-[18px] rounded-full bg-[var(--brand-600)] px-1 text-center text-[11px] font-bold leading-[18px] text-[var(--fg-on-brand)]"
        >
          {toPersianDigits(unread > 99 ? '99+' : unread)}
        </span>
      )}
    </Link>
  );
}
