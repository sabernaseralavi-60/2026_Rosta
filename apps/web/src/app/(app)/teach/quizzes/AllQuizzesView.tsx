'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';

import { errorText, ErrorLine } from '@/components/admin/common';
import { QuizList } from '@/components/teach/QuizList';
import { Badge } from '@/components/ui/Badge';
import { EmptyState } from '@/components/ui/EmptyState';
import { SkeletonRow } from '@/components/ui/Skeleton';
import { fetchOfferingQuizzesForStaff, fetchTeachOfferings, type TeachQuiz } from '@/lib/api/teach';
import { useSession } from '@/lib/auth/use-session';

type Row = TeachQuiz & { course: string };

/**
 * `/teach/quizzes` — همهٔ آزمون‌های ارائه‌های من (§3.5).
 *
 * منتشرشده‌ها اول، سپس پیش‌نویس و بسته؛ در هر گروه تازه‌ترین بالا.
 */
export function AllQuizzesView() {
  const { accessToken } = useSession();
  const [rows, setRows] = useState<Row[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!accessToken) return;
    (async () => {
      const offerings = await fetchTeachOfferings(accessToken);
      const lists = await Promise.all(
        offerings.map(async (offering) =>
          (await fetchOfferingQuizzesForStaff(offering.id, accessToken)).map((quiz) => ({
            ...quiz,
            course: offering.course_title_fa,
          })),
        ),
      );
      const order = { PUBLISHED: 0, DRAFT: 1, CLOSED: 2 } as const;
      setRows(
        lists
          .flat()
          .sort(
            (a, b) =>
              order[a.status] - order[b.status] ||
              new Date(b.opens_at).getTime() - new Date(a.opens_at).getTime(),
          ),
      );
    })().catch((cause) => setError(errorText(cause)));
  }, [accessToken]);

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-1">
        <h1>آزمون‌ها</h1>
        <p className="text-[14px] text-[var(--fg-secondary)]">
          آزمون‌های همهٔ ارائه‌هایت. آزمون تازه را از صفحهٔ همان ارائه بساز.
        </p>
      </header>
      {error && <ErrorLine>{error}</ErrorLine>}
      {!rows && !error && <SkeletonRow label="در حال بارگذاری آزمون‌ها" />}
      {rows && rows.length === 0 && (
        <EmptyState
          title="هنوز آزمونی نساخته‌ای"
          description="از «ارائه‌های من» یک ارائه را باز کن و در زبانهٔ آزمون‌ها، آزمون تازه بساز."
          action={
            <Link
              href="/teach/offerings"
              className="text-[14px] font-medium text-[var(--fg-brand)]"
            >
              ارائه‌های من
            </Link>
          }
        />
      )}
      {rows && rows.length > 0 && (
        <>
          <p className="flex flex-wrap gap-2 text-[13px]">
            <Badge tone="success">
              {rows.filter((r) => r.status === 'PUBLISHED').length.toLocaleString('fa-IR')} منتشرشده
            </Badge>
            <Badge tone="neutral">
              {rows.filter((r) => r.status === 'DRAFT').length.toLocaleString('fa-IR')} پیش‌نویس
            </Badge>
          </p>
          <QuizList quizzes={rows} showCourse />
        </>
      )}
    </div>
  );
}
