'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';

import { QaBoard, type QaWeekOption } from '@/components/domain/qa/QaBoard';
import { Card } from '@/components/ui/Card';
import { SkeletonCard } from '@/components/ui/Skeleton';
import { ApiError, NetworkError } from '@/lib/api/client';
import { fetchOffering } from '@/lib/api/courses';
import { useSession } from '@/lib/auth/use-session';

/**
 * `/courses/[offeringId]/qa` — پرسش‌وپاسخ همهٔ درس.
 *
 * نمای کلی ارائه فقط برای عنوان و فهرست هفته‌ها (انتخاب هفته هنگام پرسیدن) خوانده
 * می‌شود؛ دسترسی به خودِ پرسش‌ها را `QaBoard` از سرور می‌گیرد. کسی که در درس
 * نیست، همین‌جا ۴۰۳ می‌گیرد و صفحه توضیحش را نشان می‌دهد.
 */
export function QaView({
  offeringId,
  initialThreadId,
}: {
  offeringId: string;
  initialThreadId: string | null;
}) {
  const { accessToken, loading: sessionLoading } = useSession();
  const [weeks, setWeeks] = useState<QaWeekOption[] | null>(null);
  const [title, setTitle] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (sessionLoading || !accessToken) return;
    let cancelled = false;
    fetchOffering(offeringId, accessToken)
      .then((offering) => {
        if (cancelled) return;
        setTitle(offering.course_title_fa);
        setWeeks(
          offering.weeks.map((week) => ({
            week_number: week.week_number,
            title_fa: week.title_fa,
          })),
        );
      })
      .catch((cause) => !cancelled && setError(messageFor(cause)));
    return () => {
      cancelled = true;
    };
  }, [offeringId, accessToken, sessionLoading]);

  if (error) {
    return (
      <Card className="flex flex-col gap-3">
        <p role="alert" className="text-[14px] text-[var(--fg-danger)]">
          {error}
        </p>
        <Link href="/courses" className="text-[13.5px] text-[var(--fg-brand)]">
          بازگشت به درس‌ها
        </Link>
      </Card>
    );
  }
  if (sessionLoading || !weeks) return <SkeletonCard />;

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-2">
        <Link
          href={`/courses/${offeringId}`}
          className="text-[13px] text-[var(--fg-secondary)] hover:text-[var(--fg-brand)]"
        >
          ← بازگشت به نمای درس
        </Link>
        <h1 className="text-[24px] font-bold text-[var(--fg-primary)]">پرسش‌وپاسخ درس</h1>
        {title && <p className="text-[14px] text-[var(--fg-secondary)]">{title}</p>}
      </header>
      <QaBoard offeringId={offeringId} weeks={weeks} initialThreadId={initialThreadId} />
    </div>
  );
}

function messageFor(cause: unknown): string {
  if (cause instanceof ApiError || cause instanceof NetworkError) return cause.message;
  return 'خطای غیرمنتظره‌ای رخ داد.';
}
