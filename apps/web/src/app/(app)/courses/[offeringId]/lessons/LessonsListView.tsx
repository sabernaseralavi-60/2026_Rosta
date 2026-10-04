'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';

import { ErrorLine, errorText } from '@/components/admin/common';
import { EmptyState } from '@/components/ui/EmptyState';
import { SkeletonCard } from '@/components/ui/Skeleton';
import { fetchStudentLessons, type LessonSummary } from '@/lib/api/learning';
import { useSession } from '@/lib/auth/use-session';
import { formatDateShort } from '@/lib/format/date';
import { toPersianDigits } from '@/lib/format/digits';

export function LessonsListView({ offeringId }: { offeringId: string }) {
  const { accessToken } = useSession();
  const [rows, setRows] = useState<LessonSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!accessToken) return;
    fetchStudentLessons(offeringId, accessToken)
      .then(setRows)
      .catch((cause) => setError(errorText(cause)));
  }, [accessToken, offeringId]);

  return (
    <div className="flex flex-col gap-6">
      <nav aria-label="مسیر" className="text-[13.5px]">
        <Link href={`/courses/${offeringId}`} className="text-[var(--fg-brand)]">
          ← صفحهٔ درس
        </Link>
      </nav>
      <header className="flex flex-col gap-1">
        <h1>درس‌نامه‌ها</h1>
        <p className="text-[14px] text-[var(--fg-secondary)]">
          تازه‌ترین بالا. هر روز یک درس‌نامهٔ کوتاه و یک چالش.
        </p>
      </header>
      {error && <ErrorLine>{error}</ErrorLine>}
      {!rows && !error && <SkeletonCard label="در حال بارگذاری" />}
      {rows && rows.length === 0 && (
        <EmptyState
          title="هنوز درس‌نامه‌ای منتشر نشده"
          description="وقتی استاد درس‌نامه‌ای منتشر کند همین‌جا می‌آید."
        />
      )}
      <ul className="flex flex-col gap-3">
        {rows?.map((lesson) => (
          <li key={lesson.id}>
            <Link
              href={`/lessons/${lesson.id}`}
              className="flex items-center justify-between gap-4 rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-4 hover:border-[var(--border-strong)]"
            >
              <span className="text-[15px] font-medium">{lesson.title_fa}</span>
              <span className="shrink-0 text-[12.5px] text-[var(--fg-tertiary)]">
                {toPersianDigits(lesson.est_minutes)} دقیقه ·{' '}
                {toPersianDigits(formatDateShort(lesson.publish_at ?? lesson.updated_at))}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
