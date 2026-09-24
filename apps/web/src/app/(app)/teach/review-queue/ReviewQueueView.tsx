'use client';

import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';

import { errorText, ErrorLine, FactList } from '@/components/admin/common';
import { DeliverableReviewForm } from '@/components/domain/DeliverableReviewForm';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { SkeletonRow } from '@/components/ui/Skeleton';
import { type ReviewQueue, type ReviewQueueItem, fetchReviewQueue } from '@/lib/api/teach';
import { useSession } from '@/lib/auth/use-session';
import { toPersianDigits } from '@/lib/format/digits';

/**
 * `/teach/review-queue` — صف واحد بررسی (§3.5، ADR-0022).
 *
 * همهٔ تحویل‌های منتظر در همهٔ پروژه‌های تحت نظارت، قدیمی‌ترین اول؛ هر
 * تحویل همین‌جا بررسی می‌شود، بی‌آنکه استاد از پروژه‌ای به پروژهٔ دیگر برود.
 * فرم همان فرم فضای کاری است (`DeliverableReviewForm`)، پس قاعدهٔ «بازخورد
 * برای اصلاح و رد اجباری است» یکی می‌ماند.
 *
 * تحویل بررسی‌شده بی‌درنگ از صف می‌رود: صف باید «آنچه باقی مانده» را نشان
 * بدهد، نه تاریخچه را. شمارش کل از سرور می‌آید و با هر بررسی یکی کم می‌شود.
 */
export function ReviewQueueView() {
  const { accessToken } = useSession();
  const [queue, setQueue] = useState<ReviewQueue | null>(null);
  const [reviewed, setReviewed] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    if (!accessToken) return;
    fetchReviewQueue(accessToken)
      .then(setQueue)
      .catch((cause) => setError(errorText(cause)));
  }, [accessToken]);

  useEffect(load, [load]);

  function handleReviewed(id: string) {
    setReviewed((count) => count + 1);
    setQueue((current) =>
      current
        ? {
            ...current,
            total: Math.max(current.total - 1, 0),
            items: current.items.filter((item) => item.deliverable_id !== id),
          }
        : current,
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-1">
        <h1>صف بررسی تحویل‌ها</h1>
        <p className="text-[14px] text-[var(--fg-secondary)]">
          تحویل‌دادنی‌های منتظر بررسی در همهٔ پروژه‌های ارائه‌هایت و پروژه‌هایی که خودت مدیرشان
          هستی؛ قدیمی‌ترین بالا.
        </p>
      </header>

      {error && <ErrorLine>{error}</ErrorLine>}
      {!queue && !error && (
        <div className="flex flex-col gap-3">
          <SkeletonRow />
          <SkeletonRow />
          <SkeletonRow />
        </div>
      )}

      {queue && (
        <>
          <p role="status" className="text-[14px] text-[var(--fg-secondary)]">
            {queue.total > 0
              ? `${toPersianDigits(queue.total)} تحویل منتظر بررسی است` +
                (queue.oldest_days === null
                  ? '.'
                  : queue.oldest_days === 0
                    ? ' — همه امروز رسیده‌اند.'
                    : ` — قدیمی‌ترین ${toPersianDigits(queue.oldest_days)} روز پیش.`)
              : reviewed > 0
                ? `همه بررسی شد — ${toPersianDigits(reviewed)} تحویل در این نشست.`
                : ''}
          </p>

          {queue.items.length === 0 ? (
            <EmptyState
              title={reviewed > 0 ? 'صف خالی شد' : 'تحویلی منتظر بررسی نیست'}
              description={
                reviewed > 0
                  ? 'همهٔ تحویل‌ها بررسی شد.'
                  : 'وقتی دانشجویی برای پروژه‌ای از ارائه‌هایت تحویل بفرستد، اینجا می‌آید.'
              }
              action={
                <Link
                  href="/teach/projects"
                  className="text-[14px] font-medium text-[var(--fg-brand)]"
                >
                  دیدن پروژه‌ها
                </Link>
              }
            />
          ) : (
            <ul className="flex flex-col gap-3">
              {queue.items.map((item) => (
                <li key={item.deliverable_id}>
                  <QueueCard
                    item={item}
                    accessToken={accessToken}
                    onReviewed={() => handleReviewed(item.deliverable_id)}
                  />
                </li>
              ))}
            </ul>
          )}

          {queue.total > queue.items.length && queue.items.length > 0 && (
            <p className="text-[13px] text-[var(--fg-tertiary)]">
              فقط {toPersianDigits(queue.items.length)} تحویل قدیمی‌تر نمایش داده شد؛ پس از بررسی،
              بقیه می‌آیند.
            </p>
          )}
        </>
      )}
    </div>
  );
}

function QueueCard({
  item,
  accessToken,
  onReviewed,
}: {
  item: ReviewQueueItem;
  accessToken: string | null;
  onReviewed: () => void;
}) {
  const [open, setOpen] = useState(false);
  const formId = `review-${item.deliverable_id}`;

  return (
    <Card className="flex flex-col gap-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="flex min-w-0 flex-col gap-0.5">
          <h2 className="text-[16px]">
            <Link href={`/projects/${item.project_id}/workspace`} className="hover:underline">
              {item.project_title_fa}
            </Link>
          </h2>
          <p className="text-[13.5px] text-[var(--fg-secondary)]">{item.milestone_title_fa}</p>
        </div>
        <div className="flex flex-wrap gap-1.5">
          <Badge tone="info">{item.status_fa}</Badge>
          {item.version > 1 && <Badge tone="neutral">نسخهٔ {toPersianDigits(item.version)}</Badge>}
          {item.is_late && <Badge tone="warning">با تأخیر</Badge>}
        </div>
      </div>

      <FactList
        className="text-[var(--fg-secondary)]"
        items={[
          <span key="who">تحویل‌دهنده: {item.submitter_name ?? 'بدون نام'}</span>,
          <span key="wait">
            {item.days_waiting === 0
              ? 'امروز رسیده'
              : `منتظر: ${toPersianDigits(item.days_waiting)} روز`}
          </span>,
          item.course_title_fa && <span key="course">درس: {item.course_title_fa}</span>,
          item.link_count > 0 && (
            <span key="links">پیوند پیوست: {toPersianDigits(item.link_count)}</span>
          ),
        ]}
      />

      {item.excerpt && (
        <p className="rounded-[var(--radius-sm)] bg-[var(--bg-sunken)] px-3 py-2 text-[13.5px] leading-relaxed">
          {item.excerpt}
        </p>
      )}

      {open && accessToken ? (
        <div id={formId} className="flex flex-col gap-2">
          <DeliverableReviewForm
            deliverableId={item.deliverable_id}
            accessToken={accessToken}
            onReviewed={onReviewed}
          />
          <Button variant="ghost" size="sm" className="self-start" onClick={() => setOpen(false)}>
            بستن
          </Button>
        </div>
      ) : (
        <div className="flex flex-wrap items-center gap-3">
          <Button
            size="sm"
            aria-expanded={open}
            aria-controls={formId}
            onClick={() => setOpen(true)}
          >
            بررسی
          </Button>
          <Link
            href={`/projects/${item.project_id}/workspace`}
            className="text-[13.5px] text-[var(--fg-brand)]"
          >
            دیدن همهٔ فایل‌ها و پیوندها
          </Link>
        </div>
      )}
    </Card>
  );
}
