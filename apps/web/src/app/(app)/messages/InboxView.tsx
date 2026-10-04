'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';

import { ErrorLine, errorText } from '@/components/admin/common';
import { Badge } from '@/components/ui/Badge';
import { EmptyState } from '@/components/ui/EmptyState';
import { SkeletonCard } from '@/components/ui/Skeleton';
import { type Conversation, fetchInbox } from '@/lib/api/messaging';
import { useSession } from '@/lib/auth/use-session';
import { formatDateShort } from '@/lib/format/date';
import { toPersianDigits } from '@/lib/format/digits';

/** `/messages` — گفت‌وگوهای خصوصی و کانال درس‌های من، تازه‌ترین بالا. */
export function InboxView() {
  const { accessToken } = useSession();
  const [rows, setRows] = useState<Conversation[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!accessToken) return;
    fetchInbox(accessToken)
      .then(setRows)
      .catch((cause) => setError(errorText(cause)));
  }, [accessToken]);

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-1">
        <h1>پیام‌ها</h1>
        <p className="max-w-[70ch] text-[14px] text-[var(--fg-secondary)]">
          پیام‌های استاد و کانال درس‌هایت. متن گفت‌وگو فقط همین‌جا می‌ماند.
        </p>
      </header>

      {error && <ErrorLine>{error}</ErrorLine>}
      {!rows && !error && <SkeletonCard label="در حال بارگذاری پیام‌ها" />}
      {rows && rows.length === 0 && (
        <EmptyState
          title="هنوز پیامی نداری"
          description="وقتی استاد برایت بنویسد یا در کانال درس پیامی بگذارد، همین‌جا می‌آید."
          action={
            <Link href="/courses" className="text-[14px] font-medium text-[var(--fg-brand)]">
              دروس من
            </Link>
          }
        />
      )}
      <ul className="flex flex-col gap-3">
        {rows?.map((conversation) => (
          <li key={conversation.id}>
            <Link
              href={`/messages/${conversation.id}`}
              className="flex items-start justify-between gap-4 rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-4 hover:border-[var(--border-strong)]"
            >
              <div className="flex min-w-0 flex-col gap-1">
                <span className="text-[15px] font-semibold">{conversation.title}</span>
                <span className="truncate text-[13.5px] text-[var(--fg-secondary)]">
                  {conversation.last_preview ?? 'هنوز پیامی نیست'}
                </span>
              </div>
              <div className="flex shrink-0 flex-col items-end gap-1">
                {conversation.unread > 0 && (
                  <Badge tone="brand">{toPersianDigits(conversation.unread)} تازه</Badge>
                )}
                {conversation.last_message_at && (
                  <span className="text-[12px] text-[var(--fg-tertiary)]">
                    {toPersianDigits(formatDateShort(conversation.last_message_at))}
                  </span>
                )}
              </div>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
