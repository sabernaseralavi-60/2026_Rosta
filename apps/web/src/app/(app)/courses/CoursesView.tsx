'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';

import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { Progress } from '@/components/ui/Progress';
import { SkeletonCard } from '@/components/ui/Skeleton';
import { ApiError, NetworkError } from '@/lib/api/client';
import { type OfferingSummary, fetchMyOfferings } from '@/lib/api/courses';
import { useSession } from '@/lib/auth/use-session';
import { toPersianDigits } from '@/lib/format/digits';

/**
 * `/courses` — §3.4 «دروس من با نوار پیشرفت».
 *
 * درس در انتظار تأیید هم نشان داده می‌شود، با نشان خودش: دانشجویی که
 * منتظر است باید بداند منتظر چیست، نه اینکه درس را اصلاً نبیند.
 */

const STATUS_LABELS: Record<string, string> = {
  PENDING: 'در انتظار تأیید استاد',
  ACTIVE: 'فعال',
  COMPLETED: 'تمام‌شده',
  DROPPED: 'انصراف',
  REJECTED: 'رد شده',
};

export function CoursesView() {
  const { accessToken, loading: sessionLoading } = useSession();
  const [offerings, setOfferings] = useState<OfferingSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (sessionLoading || !accessToken) return;
    let cancelled = false;
    fetchMyOfferings(accessToken)
      .then((items) => !cancelled && setOfferings(items))
      .catch((cause) => {
        if (cancelled) return;
        setError(messageFor(cause));
        setOfferings([]);
      });
    return () => {
      cancelled = true;
    };
  }, [accessToken, sessionLoading]);

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="flex flex-col gap-1">
          <h1 className="text-[26px] font-bold text-[var(--fg-primary)]">دروس من</h1>
          <p className="text-[14px] text-[var(--fg-secondary)]">
            درس‌هایی که در آن‌ها ثبت‌نام کرده‌اید. محتوای هر درس برای دانشجویانش رایگان است.
          </p>
        </div>
        <Button variant="secondary" asChild>
          <Link href="/library">کتابخانهٔ دروس</Link>
        </Button>
      </header>

      {error && (
        <p role="alert" className="text-[13.5px] text-[var(--fg-danger)]">
          {error}
        </p>
      )}

      {offerings === null ? (
        <div className="grid gap-4 sm:grid-cols-2">
          <SkeletonCard />
          <SkeletonCard />
        </div>
      ) : offerings.length === 0 ? (
        <EmptyState
          title="هنوز در درسی ثبت‌نام نکرده‌اید"
          description="از کتابخانهٔ دروس شروع کنید: هر درس را ببینید، سرفصل‌هایش را بخوانید و در ارائهٔ باز ثبت‌نام کنید."
          action={
            <Button asChild>
              <Link href="/library">دیدن دروس</Link>
            </Button>
          }
        />
      ) : (
        <ul className="grid gap-4 sm:grid-cols-2">
          {offerings.map((offering) => (
            <li key={offering.id}>
              <Card variant="interactive" className="flex h-full flex-col gap-4">
                <div className="flex flex-col gap-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <Link
                      href={`/courses/${offering.id}`}
                      className="text-[17px] font-semibold text-[var(--fg-primary)]"
                    >
                      {offering.course_title_fa}
                    </Link>
                    {offering.my_status && offering.my_status !== 'ACTIVE' && (
                      <Badge tone={offering.my_status === 'COMPLETED' ? 'success' : 'warning'}>
                        {STATUS_LABELS[offering.my_status] ?? offering.my_status}
                      </Badge>
                    )}
                  </div>
                  <p className="text-[13px] text-[var(--fg-secondary)]">
                    {offering.term_title_fa}
                    {offering.instructor_name ? ` · ${offering.instructor_name}` : ''}
                  </p>
                </div>

                <Progress
                  value={offering.progress_percent}
                  label="پیشرفت مطالعه"
                  valueText={`${toPersianDigits(offering.progress_percent)}٪`}
                />

                <div className="mt-auto flex items-center justify-between gap-3">
                  <span className="text-[12.5px] text-[var(--fg-tertiary)]">
                    {offering.current_week_number
                      ? `هفتهٔ جاری: ${toPersianDigits(offering.current_week_number)}`
                      : 'هنوز هفته‌ای منتشر نشده'}
                  </span>
                  <Button size="sm" variant="secondary" asChild>
                    <Link
                      href={
                        offering.current_week_number
                          ? `/courses/${offering.id}/weeks/${offering.current_week_number}`
                          : `/courses/${offering.id}`
                      }
                    >
                      {offering.current_week_number ? 'ادامهٔ مطالعه' : 'نمای درس'}
                    </Link>
                  </Button>
                </div>
              </Card>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function messageFor(cause: unknown): string {
  if (cause instanceof ApiError || cause instanceof NetworkError) return cause.message;
  return 'خطای غیرمنتظره‌ای رخ داد.';
}
