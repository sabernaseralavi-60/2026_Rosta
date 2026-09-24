'use client';

import { useCallback, useEffect, useState } from 'react';

import { MetricRow } from '@/components/domain/MetricsView';
import { EmptyState } from '@/components/ui/EmptyState';
import { SkeletonCard } from '@/components/ui/Skeleton';
import { ApiError, NetworkError } from '@/lib/api/client';
import { type Metric, fetchMetricReviewQueue } from '@/lib/api/ventures';
import { useSession } from '@/lib/auth/use-session';
import { toPersianDigits } from '@/lib/format/digits';

/**
 * `/metrics/review` — صف تأیید فعالیت و فروش، FR-VEN-02.
 *
 * منتور همهٔ کسب‌وکارها را می‌بیند و مدیر پروژه فقط پروژه‌های خودش را؛
 * سرور صف را بر اساس مجوز هر ردیف فیلتر کرده است. قدیمی‌ترین اول.
 */
export function MetricReviewView() {
  const { accessToken, loading: sessionLoading } = useSession();
  const [items, setItems] = useState<Metric[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    if (sessionLoading || !accessToken) return;
    fetchMetricReviewQueue(accessToken)
      .then(setItems)
      .catch((cause) =>
        setError(
          cause instanceof ApiError || cause instanceof NetworkError
            ? cause.message
            : 'صف بارگذاری نشد.',
        ),
      );
  }, [accessToken, sessionLoading]);

  useEffect(load, [load]);

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-1">
        <h1>تأیید فعالیت و فروش</h1>
        <p className="text-[15px] text-[var(--fg-secondary)]">
          امتیاز کارآفرینی دانشجو از همین تأیید می‌آید؛ اگر مستندی نیست، با یادداشت رد کن.
        </p>
      </header>
      {error && (
        <p role="alert" className="text-[13.5px] text-[var(--fg-danger)]">
          {error}
        </p>
      )}
      {items === null ? (
        !error && <SkeletonCard label="در حال بارگذاری صف" />
      ) : items.length === 0 ? (
        <EmptyState title="صف خالی است" description="ثبتی منتظر بررسی تو نیست." />
      ) : (
        <>
          <p className="text-[13px] text-[var(--fg-tertiary)]">
            {toPersianDigits(items.length)} ثبت در انتظار
          </p>
          <ul className="flex flex-col gap-3">
            {items.map((item) => (
              <li key={item.id}>
                <MetricRow
                  item={item}
                  accessToken={accessToken}
                  onChanged={load}
                  onError={setError}
                  showOwner
                />
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
