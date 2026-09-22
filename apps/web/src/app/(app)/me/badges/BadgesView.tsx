'use client';

import { useEffect, useState } from 'react';

import { BadgeTile } from '@/components/domain/BadgeTile';
import { EmptyState } from '@/components/ui/EmptyState';
import { SkeletonCard } from '@/components/ui/Skeleton';
import { ApiError } from '@/lib/api/client';
import { type Badge, fetchBadges } from '@/lib/api/points';
import { useSession } from '@/lib/auth/use-session';
import { toPersianDigits } from '@/lib/format/digits';

/**
 * نشان‌ها — §9.5، FR-GAM-03.
 *
 * «کاربر نشان‌های قفل‌شده را با شرایطشان می‌بیند — این خودش یک راهنمای
 * مسیر است.» قفل‌ها به ترتیب نزدیکی به کسب‌اند (سرور مرتب می‌کند): نشانی
 * که «۴ از ۵» است بالاتر از نشانی است که هنوز شروع نشده.
 */
export function BadgesView() {
  const { accessToken, loading } = useSession({ required: false });
  const [data, setData] = useState<{ earned: Badge[]; locked: Badge[] } | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (loading || !accessToken) return;
    let cancelled = false;
    fetchBadges(accessToken)
      .then((value) => !cancelled && setData(value))
      .catch((cause: unknown) => {
        if (!cancelled) setError(cause instanceof ApiError ? cause.message : 'نشان‌ها بارگذاری نشد.');
      });
    return () => {
      cancelled = true;
    };
  }, [accessToken, loading]);

  if (error) return <EmptyState title="نشان‌ها بارگذاری نشد" description={error} />;
  if (!data) return <SkeletonCard label="در حال بارگذاری نشان‌ها" />;

  const total = data.earned.length + data.locked.length;
  return (
    <div className="flex flex-col gap-8">
      <div className="flex flex-col gap-1">
        <h1>نشان‌ها</h1>
        <p className="text-[15px] text-[var(--fg-secondary)]">
          {toPersianDigits(data.earned.length)} از {toPersianDigits(total)} نشان را گرفته‌ای. شرط
          هر نشان پیداست؛ قفل‌ها نقشهٔ راه‌اند.
        </p>
      </div>

      <section aria-labelledby="earned-title" className="flex flex-col gap-3">
        <h2 id="earned-title" className="text-[19px] font-semibold">
          کسب‌شده
        </h2>
        {data.earned.length === 0 ? (
          <p className="text-[14px] text-[var(--fg-secondary)]">
            اولین نشان معمولاً «قدم اول» است: نیمرخت را کامل کن.
          </p>
        ) : (
          <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {data.earned.map((badge) => (
              <li key={badge.code}>
                <BadgeTile badge={badge} />
              </li>
            ))}
          </ul>
        )}
      </section>

      <section aria-labelledby="locked-title" className="flex flex-col gap-3">
        <h2 id="locked-title" className="text-[19px] font-semibold">
          در راه
        </h2>
        <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {data.locked.map((badge) => (
            <li key={badge.code}>
              <BadgeTile badge={badge} />
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
