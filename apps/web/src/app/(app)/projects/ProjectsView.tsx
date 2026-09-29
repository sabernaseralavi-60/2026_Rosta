'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';

import { PageBanner } from '@/components/domain/PageBanner';
import { ProjectCard } from '@/components/domain/ProjectCard';
import { Button } from '@/components/ui/Button';
import { EmptyState } from '@/components/ui/EmptyState';
import { Input } from '@/components/ui/Input';
import { SkeletonCard } from '@/components/ui/Skeleton';
import { ApiError, NetworkError } from '@/lib/api/client';
import {
  type ProjectKind,
  type ProjectSummary,
  type Recommendation,
  fetchProjects,
  fetchRecommendations,
} from '@/lib/api/projects';
import { useSession } from '@/lib/auth/use-session';
import { cn } from '@/lib/cn';
import { toPersianDigits } from '@/lib/format/digits';

/**
 * `/projects` — §3.4.
 *
 * «پیشنهادهای من + بانک پروژه با فیلتر.» ترتیب عمدی است: دانشجو اول
 * چیزی را می‌بیند که به او می‌خورد، بعد فهرست کامل.
 */

const SEARCH_DEBOUNCE_MS = 350;
const RECOMMENDED_COUNT = 3;

const KIND_FILTERS: { value: ProjectKind | ''; label: string }[] = [
  { value: '', label: 'همه' },
  { value: 'A_VENTURE', label: 'کارآفرینی' },
  { value: 'B_RESEARCH', label: 'پژوهشی' },
  { value: 'C_PROBLEM', label: 'حل مسئله' },
  { value: 'D_PERSONAL', label: 'شخصی' },
];

export function ProjectsView() {
  const { accessToken, loading: sessionLoading } = useSession({ required: false });

  const [recommended, setRecommended] = useState<Recommendation[] | null>(null);
  const [projects, setProjects] = useState<ProjectSummary[] | null>(null);
  const [total, setTotal] = useState(0);
  const [kind, setKind] = useState<ProjectKind | ''>('');
  const [query, setQuery] = useState('');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (sessionLoading || !accessToken) {
      if (!sessionLoading) setRecommended([]);
      return;
    }
    let cancelled = false;
    fetchRecommendations(accessToken, RECOMMENDED_COUNT)
      .then((result) => !cancelled && setRecommended(result.items))
      // نبود پیشنهاد نباید کل صفحه را بشکند؛ بانک پروژه مستقل است.
      .catch(() => !cancelled && setRecommended([]));
    return () => {
      cancelled = true;
    };
  }, [accessToken, sessionLoading]);

  useEffect(() => {
    let cancelled = false;
    const timer = setTimeout(() => {
      fetchProjects({ ...(kind ? { kind } : {}), ...(query.trim() ? { q: query.trim() } : {}) })
        .then((page) => {
          if (cancelled) return;
          setProjects(page.items);
          setTotal(page.total);
          setError(null);
        })
        .catch((cause) => {
          if (cancelled) return;
          setError(messageFor(cause));
          setProjects([]);
        });
    }, SEARCH_DEBOUNCE_MS);

    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [kind, query]);

  return (
    <div className="flex flex-col gap-10">
      <PageBanner
        photo="solve"
        title="پروژه‌ها"
        description="واحد ارزش در سیلپ، پروژه است — نه درس."
      />

      {recommended === null ? (
        // هم‌قد بخش واقعی (عنوان + سه کارت) تا بانک پروژه با آمدن پیشنهادها
        // پایین نپرد؛ برای مهمان اصلاً ساخته نمی‌شود (M7-15، CLS ۰٫۴۸ ← ۰).
        <div className="signed-in-only flex flex-col gap-4">
          <div className="h-7 w-40 rounded-[var(--radius-sm)] bg-[var(--bg-sunken)]" />
          <SkeletonCard label="در حال آماده‌سازی پیشنهادها" className="min-h-[200px]" />
          <SkeletonCard className="min-h-[200px]" />
          <SkeletonCard className="min-h-[200px]" />
        </div>
      ) : recommended.length > 0 ? (
        <section className="flex flex-col gap-4">
          <div className="flex items-baseline justify-between gap-3">
            <h2 className="text-[19px] font-semibold">پیشنهادهای تو</h2>
            <Link
              href="/onboarding/results"
              className="text-[13.5px] font-medium text-[var(--fg-brand)] hover:underline"
            >
              دیدن همه
            </Link>
          </div>
          <ul className="flex flex-col gap-4">
            {recommended.map((item) => (
              <li key={item.project.id}>
                <ProjectCard
                  project={item.project}
                  matchScore={item.match_score}
                  reasons={item.reasons}
                  isStretch={item.is_stretch}
                />
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <section className="flex flex-col gap-4">
        <h2 className="text-[19px] font-semibold">بانک پروژه</h2>

        <div className="flex flex-col gap-3">
          <Input
            label="جستجو"
            hint="نام یا موضوع پروژه"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            type="search"
          />
          <div className="flex flex-wrap gap-2" role="group" aria-label="فیلتر نوع پروژه">
            {KIND_FILTERS.map((filter) => (
              <button
                key={filter.value || 'all'}
                type="button"
                aria-pressed={kind === filter.value}
                onClick={() => {
                  if (filter.value === kind) return;
                  setKind(filter.value);
                  // اسکلت همان لحظهٔ کلیک، نه وقتی نتیجه رسید: جابه‌جایی کارت‌ها
                  // پس از ۵۰۰ms از کلیک جهش چیدمان حساب می‌شد (CLS ۰٫۳۲، M7-15).
                  setProjects(null);
                }}
                className={cn(
                  'h-9 rounded-[var(--radius-full)] border px-4 text-[13.5px] font-medium',
                  'transition-colors duration-[var(--dur-instant)]',
                  kind === filter.value
                    ? 'border-[var(--brand-600)] bg-[var(--brand-600)] text-[var(--fg-on-brand)]'
                    : 'border-[var(--border-default)] bg-[var(--bg-surface)] text-[var(--fg-secondary)] hover:border-[var(--border-strong)]',
                )}
              >
                {filter.label}
              </button>
            ))}
          </div>
        </div>

        {error && (
          <p role="alert" className="text-[13.5px] text-[var(--fg-danger)]">
            {error}
          </p>
        )}

        {projects === null ? (
          <div className="flex flex-col gap-4">
            <SkeletonCard label="در حال بارگذاری پروژه‌ها" />
            <SkeletonCard />
          </div>
        ) : projects.length === 0 ? (
          <EmptyState
            title="پروژه‌ای با این فیلترها پیدا نشد"
            description="فیلتر را بردار یا واژهٔ دیگری جستجو کن."
            action={
              <Button
                variant="secondary"
                onClick={() => {
                  setKind('');
                  setQuery('');
                }}
              >
                برداشتن فیلترها
              </Button>
            }
          />
        ) : (
          <>
            <p className="text-[13px] text-[var(--fg-tertiary)]">
              {toPersianDigits(total)} پروژهٔ باز
            </p>
            <ul className="flex flex-col gap-4">
              {projects.map((project) => (
                <li key={project.id}>
                  <ProjectCard project={project} />
                </li>
              ))}
            </ul>
          </>
        )}
      </section>
    </div>
  );
}

function messageFor(cause: unknown): string {
  if (cause instanceof ApiError || cause instanceof NetworkError) return cause.message;
  return 'فهرست پروژه‌ها بارگذاری نشد. کمی بعد دوباره تلاش کن.';
}
