'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';

import { errorText, ErrorLine } from '@/components/admin/common';
import { RequestTimeline } from '@/components/domain/RequestTimeline';
import { Badge } from '@/components/ui/Badge';
import { Card } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { SkeletonCard } from '@/components/ui/Skeleton';
import {
  CLIENT_STATUS_LABELS,
  fetchMyRequests,
  KIND_LABELS,
  type MyRequest,
  NEED_TYPE_LABELS,
  STATUS_TONES,
} from '@/lib/api/inbox';
import { useSession } from '@/lib/auth/use-session';
import { formatDateShort } from '@/lib/format/date';

/**
 * `/me/requests` — داشبورد مشتری (ADR-0032).
 *
 * درخواست‌های حساب خودم، و آنچه با موبایل یا ایمیلِ **تأییدشدهٔ** من پیش از ثبت‌نام ثبت شده بود.
 * پیام‌های تیم (`public_note`) در تاریخچه می‌آید؛ یادداشت خصوصی مالک هیچ‌وقت به اینجا نمی‌رسد.
 */
export function MyRequestsView() {
  const { accessToken } = useSession();
  const [rows, setRows] = useState<MyRequest[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!accessToken) return;
    fetchMyRequests(accessToken)
      .then(setRows)
      .catch((cause) => setError(errorText(cause)));
  }, [accessToken]);

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-1">
        <h1>درخواست‌های من</h1>
        <p className="max-w-[70ch] text-[14px] text-[var(--fg-secondary)]">
          مسئله‌ها و درخواست‌های همکاری که ثبت کرده‌ای، با وضعیت و پیام‌های تیم.
        </p>
      </header>

      {error && <ErrorLine>{error}</ErrorLine>}
      {!rows && !error && <SkeletonCard label="در حال بارگذاری درخواست‌ها" />}
      {rows && rows.length === 0 && (
        <EmptyState
          title="هنوز درخواستی ثبت نکرده‌ای"
          description="مسئلهٔ کاری یا پژوهشی‌ات را بنویس، یا بگو چطور می‌توانی همکاری کنی. اگر پیش‌تر با همین شماره یا ایمیلِ تأییدشده ثبت کرده‌ای، خودکار اینجا می‌آید."
          action={
            <span className="flex flex-wrap justify-center gap-4 text-[14px] font-medium">
              <Link href="/intake" className="text-[var(--fg-brand)]">
                طرح مسئله / نیاز
              </Link>
              <Link href="/collaborate" className="text-[var(--fg-brand)]">
                همکاری با ما
              </Link>
            </span>
          }
        />
      )}
      {rows && rows.length > 0 && (
        <ul className="flex flex-col gap-4">
          {rows.map((row) => (
            <li key={row.tracking_code}>
              <RequestCard row={row} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function RequestCard({ row }: { row: MyRequest }) {
  return (
    <Card className="flex flex-col gap-4 p-5">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={STATUS_TONES[row.status]}>{CLIENT_STATUS_LABELS[row.status]}</Badge>
        <span className="text-[14px] text-[var(--fg-secondary)]">
          {KIND_LABELS[row.kind]}
          {row.need_type && ` (${NEED_TYPE_LABELS[row.need_type] ?? row.need_type})`}
        </span>
        <span className="font-mono text-[13px] text-[var(--fg-tertiary)]" dir="ltr">
          {row.tracking_code}
        </span>
        <span className="ms-auto text-[12.5px] text-[var(--fg-tertiary)]">
          ثبت: {formatDateShort(row.created_at)}
        </span>
      </div>
      <p className="max-w-[80ch] whitespace-pre-line text-[14.5px] leading-[1.9]">{row.summary}</p>
      {row.services.length > 0 && (
        <p className="text-[13px] text-[var(--fg-secondary)]">خدمات: {row.services.join('، ')}</p>
      )}
      <RequestTimeline
        createdAt={row.created_at}
        events={row.events}
        labels={CLIENT_STATUS_LABELS}
      />
    </Card>
  );
}
