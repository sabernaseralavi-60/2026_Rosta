'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';

import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { Input } from '@/components/ui/Input';
import { SkeletonCard } from '@/components/ui/Skeleton';
import { ApiError, NetworkError } from '@/lib/api/client';
import { type CourseSummary, fetchCourses } from '@/lib/api/courses';
import { useSession } from '@/lib/auth/use-session';
import { toPersianDigits } from '@/lib/format/digits';

/**
 * `/library` — ویترین دروس.
 *
 * هر درس با شمار محتوایش دیده می‌شود، چه کاربر دانشجویش باشد چه نه.
 * قفل در سطح **دانلود** است، نه در سطح دیدن (ADR-0009): کسی که نمی‌داند
 * چه چیزی هست، دلیلی برای اشتراک گرفتن هم ندارد.
 */

const SEARCH_DEBOUNCE_MS = 350;

const LEVEL_FILTERS: { value: string; label: string }[] = [
  { value: '', label: 'همه' },
  { value: 'BACHELOR', label: 'کارشناسی' },
  { value: 'MASTER', label: 'ارشد' },
  { value: 'PHD', label: 'دکتری' },
  { value: 'PUBLIC', label: 'عمومی' },
];

export function LibraryView() {
  const { accessToken, loading: sessionLoading } = useSession({ required: false });
  const [courses, setCourses] = useState<CourseSummary[] | null>(null);
  const [total, setTotal] = useState(0);
  const [query, setQuery] = useState('');
  const [level, setLevel] = useState('');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (sessionLoading) return;
    let cancelled = false;
    const timer = setTimeout(() => {
      fetchCourses(
        { ...(query.trim() ? { q: query.trim() } : {}), ...(level ? { degree_level: level } : {}) },
        accessToken,
      )
        .then((page) => {
          if (cancelled) return;
          setCourses(page.items);
          setTotal(page.total);
          setError(null);
        })
        .catch((cause) => {
          if (cancelled) return;
          setError(messageFor(cause));
          setCourses([]);
        });
    }, SEARCH_DEBOUNCE_MS);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [accessToken, level, query, sessionLoading]);

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="flex flex-col gap-1">
          <h1 className="text-[26px] font-bold text-[var(--fg-primary)]">کتابخانهٔ دروس</h1>
          <p className="max-w-[60ch] text-[14px] leading-7 text-[var(--fg-secondary)]">
            محتوای هر درس برای دانشجویان همان درس رایگان است. برای بقیه، با اشتراک ماهانه در دسترس
            است.
          </p>
        </div>
        <Button variant="secondary" asChild>
          <Link href="/pricing">طرح‌های اشتراک</Link>
        </Button>
      </header>

      <div className="flex flex-wrap items-end gap-3">
        <Input
          label="جستجو"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="نام درس یا موضوع…"
          className="max-w-xs"
        />
        <div className="flex flex-wrap gap-2">
          {LEVEL_FILTERS.map((filter) => (
            <Button
              key={filter.value || 'all'}
              size="sm"
              variant={level === filter.value ? 'primary' : 'secondary'}
              onClick={() => setLevel(filter.value)}
            >
              {filter.label}
            </Button>
          ))}
        </div>
      </div>

      {error && (
        <p role="alert" className="text-[13.5px] text-[var(--fg-danger)]">
          {error}
        </p>
      )}

      {courses === null ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <SkeletonCard />
          <SkeletonCard />
          <SkeletonCard />
        </div>
      ) : courses.length === 0 ? (
        <EmptyState
          title="درسی با این مشخصات پیدا نشد"
          description="عبارت جستجو را کوتاه‌تر کنید یا فیلتر مقطع را بردارید."
        />
      ) : (
        <>
          <p className="text-[13px] text-[var(--fg-tertiary)]">{toPersianDigits(total)} درس</p>
          <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {courses.map((course) => (
              <li key={course.id}>
                <Card variant="interactive" className="flex h-full flex-col gap-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <Link
                      href={`/library/${course.slug}`}
                      className="text-[17px] font-semibold text-[var(--fg-primary)]"
                    >
                      {course.title_fa}
                    </Link>
                    {course.degree_level_fa && (
                      <Badge tone="neutral">{course.degree_level_fa}</Badge>
                    )}
                  </div>

                  {course.description && (
                    <p className="line-clamp-3 text-[13.5px] leading-6 text-[var(--fg-secondary)]">
                      {course.description}
                    </p>
                  )}

                  {course.topics.length > 0 && (
                    <ul className="flex flex-wrap gap-1.5">
                      {course.topics.slice(0, 4).map((topic) => (
                        <li key={topic}>
                          <Badge tone="brand">{topic}</Badge>
                        </li>
                      ))}
                    </ul>
                  )}

                  <p className="mt-auto text-[12.5px] text-[var(--fg-tertiary)]">
                    {toPersianDigits(course.material_count)} محتوا
                    {course.free_material_count > 0 &&
                      ` · ${toPersianDigits(course.free_material_count)} رایگان`}
                    {course.open_offering_count > 0 &&
                      ` · ${toPersianDigits(course.open_offering_count)} ارائهٔ باز`}
                  </p>
                </Card>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

function messageFor(cause: unknown): string {
  if (cause instanceof ApiError || cause instanceof NetworkError) return cause.message;
  return 'خطای غیرمنتظره‌ای رخ داد.';
}
