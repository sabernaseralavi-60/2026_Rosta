'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';

import { IdeaCard } from '@/components/domain/IdeaCard';
import { Button } from '@/components/ui/Button';
import { ChipGroup, type ChipOption } from '@/components/ui/ChipGroup';
import { EmptyState } from '@/components/ui/EmptyState';
import { Input } from '@/components/ui/Input';
import { SkeletonCard } from '@/components/ui/Skeleton';
import { ApiError, NetworkError } from '@/lib/api/client';
import {
  type IdeaCategory,
  type IdeaCategoryOption,
  type IdeaSort,
  type IdeaSummary,
  fetchIdeaCategories,
  fetchIdeas,
} from '@/lib/api/ideas';
import { useSession } from '@/lib/auth/use-session';
import { toPersianDigits } from '@/lib/format/digits';

/**
 * `/ideas` — بانک ایده، FR-IDEA-01/02.
 *
 * پیش‌فرض «داغ» است: رأی با زوال زمانی (`votes / (hours + 2)^1.5`)، تا
 * ایدهٔ تازه در برابر ایدهٔ قدیمیِ پررأی شانس دیده‌شدن داشته باشد.
 */

const SEARCH_DEBOUNCE_MS = 350;

type Scope = 'OPEN' | 'PROMOTED' | 'MINE';

const SORTS: ChipOption<IdeaSort>[] = [
  { value: 'hot', label: 'داغ' },
  { value: 'new', label: 'تازه' },
  { value: 'top', label: 'پررأی' },
];

const SCOPES: ChipOption<Scope>[] = [
  { value: 'OPEN', label: 'ایده‌های باز' },
  { value: 'PROMOTED', label: 'ارتقایافته' },
  { value: 'MINE', label: 'ایده‌های من' },
];

export function IdeasView() {
  const { accessToken, loading: sessionLoading } = useSession();
  const [categories, setCategories] = useState<IdeaCategoryOption[]>([]);
  const [ideas, setIdeas] = useState<IdeaSummary[] | null>(null);
  const [total, setTotal] = useState(0);
  const [sort, setSort] = useState<IdeaSort>('hot');
  const [scope, setScope] = useState<Scope>('OPEN');
  const [category, setCategory] = useState<IdeaCategory | ''>('');
  const [query, setQuery] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    fetchIdeaCategories()
      .then(setCategories)
      .catch(() => setCategories([]));
  }, []);

  useEffect(() => {
    if (sessionLoading) return;
    let cancelled = false;
    const timer = setTimeout(() => {
      fetchIdeas(
        {
          sort,
          ...(scope === 'MINE' ? { mine: true } : { status: scope }),
          ...(category ? { category } : {}),
          ...(query.trim() ? { q: query.trim() } : {}),
        },
        accessToken,
      )
        .then((page) => {
          if (cancelled) return;
          setIdeas(page.items);
          setTotal(page.total);
          setError(null);
        })
        .catch((cause) => {
          if (cancelled) return;
          setError(messageFor(cause));
          setIdeas([]);
        });
    }, SEARCH_DEBOUNCE_MS);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [accessToken, sessionLoading, sort, scope, category, query, reload]);

  const categoryOptions: ChipOption<IdeaCategory | ''>[] = [
    { value: '', label: 'همهٔ دسته‌ها' },
    ...categories.map((c) => ({ value: c.code, label: c.title_fa })),
  ];

  return (
    <div className="flex flex-col gap-8">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="flex flex-col gap-1">
          <h1>بانک ایده</h1>
          <p className="text-[15px] text-[var(--fg-secondary)]">
            ایده‌ات را بنویس، رأی جمع کن؛ ایدهٔ خوب به پروژه یا کسب‌وکار تبدیل می‌شود.
          </p>
        </div>
        <Button asChild>
          <Link href="/ideas/new">ثبت ایده</Link>
        </Button>
      </header>

      <div className="flex flex-col gap-3">
        <Input
          label="جستجو"
          hint="عنوان یا شرح ایده"
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        <ChipGroup label="کدام ایده‌ها" options={SCOPES} value={scope} onChange={setScope} />
        <ChipGroup label="مرتب‌سازی" options={SORTS} value={sort} onChange={setSort} />
        {categories.length > 0 && (
          <ChipGroup
            label="دستهٔ ایده"
            options={categoryOptions}
            value={category}
            onChange={setCategory}
          />
        )}
      </div>

      {error && (
        <div
          role="alert"
          className="flex items-center gap-3 text-[13.5px] text-[var(--danger-600)]"
        >
          {error}
          <Button variant="secondary" size="sm" onClick={() => setReload((n) => n + 1)}>
            تلاش دوباره
          </Button>
        </div>
      )}

      {ideas === null ? (
        <div className="flex flex-col gap-4">
          <SkeletonCard label="در حال بارگذاری ایده‌ها" />
          <SkeletonCard />
        </div>
      ) : ideas.length === 0 ? (
        <EmptyState
          title={scope === 'MINE' ? 'هنوز ایده‌ای ثبت نکرده‌ای' : 'ایده‌ای با این فیلترها نیست'}
          description={
            scope === 'MINE'
              ? 'هر مسئله‌ای که هر روز می‌بینی، می‌تواند شروع یک ایده باشد.'
              : 'فیلتر را بردار، یا اولین ایدهٔ این دسته را خودت بنویس.'
          }
          action={
            <Button asChild>
              <Link href="/ideas/new">ثبت ایده</Link>
            </Button>
          }
        />
      ) : (
        <>
          <p className="text-[13px] text-[var(--fg-tertiary)]">{toPersianDigits(total)} ایده</p>
          <ul className="flex flex-col gap-4">
            {ideas.map((idea) => (
              <li key={idea.id}>
                <IdeaCard idea={idea} accessToken={accessToken} onError={setError} />
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
  return 'ایده‌ها بارگذاری نشدند. کمی بعد دوباره تلاش کن.';
}
