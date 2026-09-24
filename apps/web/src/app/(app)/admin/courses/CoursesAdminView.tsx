'use client';

import { useCallback, useEffect, useState } from 'react';

import { errorText, ErrorLine } from '@/components/admin/common';
import { SkeletonCard } from '@/components/ui/Skeleton';
import {
  type AdminCourse,
  type AdminOffering,
  type AdminTerm,
  fetchAdminCourses,
  fetchAdminOfferings,
  fetchTerms,
} from '@/lib/api/course-admin';
import { useSession } from '@/lib/auth/use-session';
import { cn } from '@/lib/cn';

import { CatalogPanel } from './CatalogPanel';
import { OfferingsPanel } from './OfferingsPanel';
import { TermsPanel } from './TermsPanel';

type Tab = 'offerings' | 'courses' | 'terms';

const TABS: { value: Tab; label: string }[] = [
  { value: 'offerings', label: 'ارائه‌ها' },
  { value: 'courses', label: 'دروس' },
  { value: 'terms', label: 'نیم‌سال‌ها' },
];

export interface CatalogData {
  terms: AdminTerm[];
  courses: AdminCourse[];
  offerings: AdminOffering[];
}

/**
 * `/admin/courses` — تعریف درس، نیم‌سال و ارائه (§3.6، ADR-0020).
 *
 * ترتیب کار برای ترم تازه: نیم‌سال ← (درس، اگر پوشه ندارد) ← ارائه با استاد.
 * پس از آن استاد وضعیت، کد ثبت‌نام و هفته‌ها را در «تدریس» می‌چیند. سه
 * فهرست یک بار خوانده می‌شوند و بعد از هر نوشتن دوباره؛ هیچ‌کدام بزرگ نیست.
 */
export function CoursesAdminView() {
  const { accessToken } = useSession();
  const [tab, setTab] = useState<Tab>('offerings');
  const [data, setData] = useState<CatalogData | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    if (!accessToken) return;
    setError(null);
    Promise.all([
      fetchTerms(accessToken),
      fetchAdminCourses(accessToken),
      fetchAdminOfferings(accessToken),
    ])
      .then(([terms, courses, offerings]) => setData({ terms, courses, offerings }))
      .catch((cause) => setError(errorText(cause)));
  }, [accessToken]);

  useEffect(load, [load]);

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-1">
        <h1>درس‌ها و ارائه‌ها</h1>
        <p className="max-w-[70ch] text-[14px] text-[var(--fg-secondary)]">
          برای ترم تازه: نیم‌سال را تعریف کن، سپس برای هر درس ارائه‌ای بساز و به استادش بسپار.
          وضعیت، کد ثبت‌نام و انتشار هفته‌ها پس از آن با خود استاد است.
        </p>
      </header>

      <div className="flex flex-wrap gap-2" role="group" aria-label="بخش">
        {TABS.map((item) => (
          <button
            key={item.value}
            type="button"
            aria-pressed={tab === item.value}
            onClick={() => setTab(item.value)}
            className={cn(
              'rounded-[var(--radius-sm)] border px-3 py-1.5 text-[13.5px]',
              tab === item.value
                ? 'border-[var(--brand-600)] bg-[var(--brand-50)] font-semibold text-[var(--fg-brand)]'
                : 'border-[var(--border-default)] text-[var(--fg-secondary)]',
            )}
          >
            {item.label}
          </button>
        ))}
      </div>

      {error && <ErrorLine>{error}</ErrorLine>}
      {!data && !error && <SkeletonCard label="در حال بارگذاری دروس و ارائه‌ها" />}
      {data && accessToken && (
        <>
          {tab === 'offerings' && (
            <OfferingsPanel token={accessToken} data={data} onChanged={load} />
          )}
          {tab === 'courses' && <CatalogPanel token={accessToken} data={data} onChanged={load} />}
          {tab === 'terms' && <TermsPanel token={accessToken} data={data} onChanged={load} />}
        </>
      )}
    </div>
  );
}
