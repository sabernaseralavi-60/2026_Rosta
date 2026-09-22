'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';

import { WeekTimeline } from '@/components/domain/WeekTimeline';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card, CardDescription, CardTitle } from '@/components/ui/Card';
import { Progress } from '@/components/ui/Progress';
import { SkeletonCard } from '@/components/ui/Skeleton';
import { ApiError, NetworkError } from '@/lib/api/client';
import { type OfferingDetail, fetchOffering } from '@/lib/api/courses';
import { useSession } from '@/lib/auth/use-session';
import { formatDateLong } from '@/lib/format/date';
import { toPersianDigits } from '@/lib/format/digits';

/**
 * `/courses/[offeringId]` — §3.4.
 *
 * «نمای کلی: هفتهٔ جاری، پیشرفت، نمره، اعلانات.» ترتیب همین است و
 * عمدی: اول «از کجا ادامه بدهم»، بعد وضعیت، بعد خبرها.
 */

const PRIORITY_TONES = { NORMAL: 'neutral', IMPORTANT: 'warning', URGENT: 'danger' } as const;
const PRIORITY_LABELS = { NORMAL: 'اطلاعیه', IMPORTANT: 'مهم', URGENT: 'فوری' } as const;

export function OfferingView({ offeringId }: { offeringId: string }) {
  const { accessToken, loading: sessionLoading } = useSession();
  const [offering, setOffering] = useState<OfferingDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (sessionLoading || !accessToken) return;
    let cancelled = false;
    fetchOffering(offeringId, accessToken)
      .then((detail) => !cancelled && setOffering(detail))
      .catch((cause) => !cancelled && setError(messageFor(cause)));
    return () => {
      cancelled = true;
    };
  }, [accessToken, offeringId, sessionLoading]);

  if (error) {
    return (
      <Card className="flex flex-col gap-4">
        <CardTitle>این درس در دسترس شما نیست</CardTitle>
        <CardDescription>{error}</CardDescription>
        <div>
          <Button variant="secondary" asChild>
            <Link href="/courses">بازگشت به دروس من</Link>
          </Button>
        </div>
      </Card>
    );
  }

  if (!offering) return <SkeletonCard />;

  const pending = offering.my_status === 'PENDING';

  return (
    <div className="flex flex-col gap-8">
      <header className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-[26px] font-bold text-[var(--fg-primary)]">
            {offering.course_title_fa}
          </h1>
          {pending && <Badge tone="warning">در انتظار تأیید استاد</Badge>}
          {offering.my_status === 'COMPLETED' && <Badge tone="success">تمام‌شده</Badge>}
        </div>
        <p className="text-[14px] text-[var(--fg-secondary)]">
          {offering.term_title_fa}
          {offering.instructor_name ? ` · ${offering.instructor_name}` : ''} ·{' '}
          {toPersianDigits(offering.active_students)} دانشجو
        </p>
        {offering.description && (
          <p className="max-w-[70ch] text-[14px] leading-7 text-[var(--fg-secondary)]">
            {offering.description}
          </p>
        )}
      </header>

      <section className="grid gap-4 sm:grid-cols-3">
        <Card className="flex flex-col gap-3">
          <CardDescription>پیشرفت مطالعه</CardDescription>
          <Progress
            value={offering.progress_percent}
            valueText={`${toPersianDigits(offering.progress_percent)}٪`}
          />
        </Card>

        <Card className="flex flex-col gap-2">
          <CardDescription>هفتهٔ جاری</CardDescription>
          {offering.current_week_number ? (
            <Link
              href={`/courses/${offering.id}/weeks/${offering.current_week_number}`}
              className="text-[20px] font-semibold text-[var(--brand-700)]"
            >
              هفتهٔ {toPersianDigits(offering.current_week_number)}
            </Link>
          ) : (
            <span className="text-[14px] text-[var(--fg-tertiary)]">هنوز منتشر نشده</span>
          )}
        </Card>

        <Card className="flex flex-col gap-2">
          <CardDescription>نمرهٔ نهایی</CardDescription>
          <span className="text-[20px] font-semibold text-[var(--fg-primary)] tabular-nums">
            {offering.final_grade === null
              ? '—'
              : toPersianDigits(offering.final_grade.toFixed(2))}
          </span>
          {Object.keys(offering.grading_policy).length > 0 && (
            <p className="text-[12px] text-[var(--fg-tertiary)]">
              {describePolicy(offering.grading_policy)}
            </p>
          )}
        </Card>
      </section>

      {offering.announcements.length > 0 && (
        <section className="flex flex-col gap-3">
          <h2 className="text-[19px] font-semibold text-[var(--fg-primary)]">اعلانات درس</h2>
          <ul className="flex flex-col gap-3">
            {offering.announcements.map((announcement) => (
              <li key={announcement.id}>
                <Card className="flex flex-col gap-2">
                  <div className="flex flex-wrap items-center gap-2">
                    {announcement.priority !== 'NORMAL' && (
                      <Badge tone={PRIORITY_TONES[announcement.priority]}>
                        {PRIORITY_LABELS[announcement.priority]}
                      </Badge>
                    )}
                    <h3 className="text-[15px] font-semibold text-[var(--fg-primary)]">
                      {announcement.title}
                    </h3>
                  </div>
                  <p className="text-[13.5px] leading-6 whitespace-pre-line text-[var(--fg-secondary)]">
                    {announcement.body}
                  </p>
                  <p className="text-[12px] text-[var(--fg-tertiary)]">
                    {formatDateLong(announcement.published_at)}
                  </p>
                </Card>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="flex flex-col gap-3">
        <div className="flex items-baseline justify-between gap-3">
          <h2 className="text-[19px] font-semibold text-[var(--fg-primary)]">سرفصل هفتگی</h2>
          <div className="flex items-baseline gap-4">
            <Link
              href={`/courses/${offering.id}/quizzes`}
              className="text-[13.5px] text-[var(--brand-700)]"
            >
              آزمون‌های این درس
            </Link>
            <Link
              href={`/library/${offering.course_slug}`}
              className="text-[13.5px] text-[var(--brand-700)]"
            >
              کتابخانهٔ این درس
            </Link>
          </div>
        </div>
        <WeekTimeline
          weeks={offering.weeks}
          currentWeekNumber={offering.current_week_number}
          hrefFor={(week) => `/courses/${offering.id}/weeks/${week.week_number}`}
        />
      </section>
    </div>
  );
}

/** «آزمون ۳۰٪ · پروژه ۵۰٪ …» — از سیاست نمرهٔ ارائه. */
function describePolicy(policy: Record<string, number>): string {
  const labels: Record<string, string> = {
    quiz: 'آزمون',
    project: 'پروژه',
    attendance: 'حضور',
    participation: 'مشارکت',
  };
  return Object.entries(policy)
    .filter(([, weight]) => weight > 0)
    .map(([key, weight]) => `${labels[key] ?? key} ${toPersianDigits(weight)}٪`)
    .join(' · ');
}

function messageFor(cause: unknown): string {
  if (cause instanceof ApiError || cause instanceof NetworkError) return cause.message;
  return 'خطای غیرمنتظره‌ای رخ داد.';
}
