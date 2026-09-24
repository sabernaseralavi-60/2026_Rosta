'use client';

import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { type ReactNode, useCallback, useEffect, useState } from 'react';

import { CategoryDot, CategoryTiles } from '@/components/domain/CategoryTiles';
import { Button } from '@/components/ui/Button';
import { EmptyState } from '@/components/ui/EmptyState';
import { SkeletonText } from '@/components/ui/Skeleton';
import { ApiError } from '@/lib/api/client';
import {
  CATEGORIES,
  CATEGORY_LABELS,
  fetchLedger,
  fetchPointsSummary,
  type LedgerFilters,
  type PointCategory,
  type PointEntry,
  points,
  type PointsSummary,
} from '@/lib/api/points';
import { useSession } from '@/lib/auth/use-session';
import { cn } from '@/lib/cn';
import { formatDateTime } from '@/lib/format/date';
import { formatNumber, toPersianDigits } from '@/lib/format/digits';

/**
 * دفتر امتیاز شخصی — M5-09، FR-GAM-01، §9.10.
 *
 * دفتر کل تغییرناپذیر است و همین‌طور هم نمایش داده می‌شود: ردیف اصلاح‌شده
 * پاک نمی‌شود، خط می‌خورد، و ردیف معکوسش زیرش با دلیل می‌آید. دانشجویی که
 * امتیازش کم شده، باید بتواند ببیند چرا — شفافیت یعنی همین.
 */

function isCategory(value: string | null): value is PointCategory {
  return value !== null && (CATEGORIES as string[]).includes(value);
}

export function PointsLedgerView() {
  const params = useSearchParams();
  const { accessToken, loading } = useSession({ required: false });
  const category = isCategory(params.get('category'))
    ? (params.get('category') as PointCategory)
    : undefined;
  const sourceType = params.get('source_type') ?? undefined;
  const sourceId = params.get('source_id') ?? undefined;

  const [summary, setSummary] = useState<PointsSummary | null>(null);
  const [items, setItems] = useState<PointEntry[] | null>(null);
  const [cursor, setCursor] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);

  useEffect(() => {
    if (loading || !accessToken) return;
    let cancelled = false;
    setItems(null);
    Promise.all([
      fetchPointsSummary(accessToken),
      fetchLedger(accessToken, { category, source_type: sourceType, source_id: sourceId }),
    ])
      .then(([summaryValue, page]) => {
        if (cancelled) return;
        setSummary(summaryValue);
        setItems(page.items);
        setCursor(page.next_cursor);
      })
      .catch((cause: unknown) => {
        if (!cancelled)
          setError(cause instanceof ApiError ? cause.message : 'دفتر امتیاز بارگذاری نشد.');
      });
    return () => {
      cancelled = true;
    };
  }, [accessToken, loading, category, sourceType, sourceId]);

  const loadMore = useCallback(async () => {
    if (!accessToken || !cursor) return;
    setLoadingMore(true);
    try {
      const filters: LedgerFilters = {
        category,
        source_type: sourceType,
        source_id: sourceId,
        cursor,
      };
      const page = await fetchLedger(accessToken, filters);
      setItems((current) => [...(current ?? []), ...page.items]);
      setCursor(page.next_cursor);
    } finally {
      setLoadingMore(false);
    }
  }, [accessToken, cursor, category, sourceType, sourceId]);

  const filtered = Boolean(category || sourceType);

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h1>دفتر امتیاز</h1>
        <p className="text-[15px] text-[var(--fg-secondary)]">
          هر امتیاز با منبع و تاریخش. امتیازی که اصلاح شده خط می‌خورد، پاک نمی‌شود.
        </p>
      </div>

      {summary && (
        <CategoryTiles
          totals={summary.by_category}
          caption={`کل امتیاز: ${formatNumber(points(summary.total))} — سطح ${toPersianDigits(summary.level.level)}، ${summary.level.title_fa}`}
        />
      )}

      <nav aria-label="فیلتر دسته" className="flex flex-wrap gap-2">
        <FilterChip href="/me/points" active={!filtered}>
          همه
        </FilterChip>
        {CATEGORIES.map((value) => (
          <FilterChip key={value} href={`/me/points?category=${value}`} active={category === value}>
            <CategoryDot category={value} />
            {CATEGORY_LABELS[value]}
          </FilterChip>
        ))}
      </nav>

      {sourceType && (
        <p className="text-[13.5px] text-[var(--fg-secondary)]">
          فقط امتیازهای یک منبع نمایش داده می‌شود.{' '}
          <Link href="/me/points" className="font-medium text-[var(--fg-brand)] hover:underline">
            نمایش همه
          </Link>
        </p>
      )}

      {error ? (
        <EmptyState title="دفتر امتیاز بارگذاری نشد" description={error} />
      ) : items === null ? (
        <SkeletonText label="در حال بارگذاری ردیف‌ها" />
      ) : items.length === 0 ? (
        <EmptyState
          title={filtered ? 'در این دسته هنوز امتیازی نداری' : 'هنوز امتیازی نگرفته‌ای'}
          description="امتیاز از کار واقعی می‌آید: خواندن جزوه، آزمون، تحویل مرحلهٔ پروژه."
          action={
            <Button asChild>
              <Link href="/dashboard">قدم بعدی من</Link>
            </Button>
          }
        />
      ) : (
        <ol className="flex flex-col divide-y divide-[var(--border-subtle)] rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-surface)]">
          {items.map((entry) => (
            <LedgerRow key={entry.id} entry={entry} />
          ))}
        </ol>
      )}

      {cursor && (
        <Button
          variant="secondary"
          onClick={loadMore}
          loading={loadingMore}
          className="self-center"
        >
          ردیف‌های قدیمی‌تر
        </Button>
      )}
    </div>
  );
}

function FilterChip({
  href,
  active,
  children,
}: {
  href: string;
  active: boolean;
  children: ReactNode;
}) {
  return (
    <Link
      href={href}
      aria-current={active ? 'page' : undefined}
      className={cn(
        'inline-flex items-center gap-1.5 rounded-[var(--radius-full)] border px-3 py-1.5 text-[13px]',
        active
          ? 'border-[var(--brand-600)] bg-[var(--brand-50)] font-medium text-[var(--fg-brand)]'
          : 'border-[var(--border-subtle)] text-[var(--fg-secondary)] hover:border-[var(--border-default)]',
      )}
    >
      {children}
    </Link>
  );
}

export function LedgerRow({ entry, action }: { entry: PointEntry; action?: ReactNode }) {
  const amount = points(entry.amount);
  const reversal = entry.reverses_id !== null;
  return (
    <li className="flex flex-wrap items-start justify-between gap-3 px-4 py-3">
      <div className="flex min-w-0 flex-1 flex-col gap-0.5">
        <span
          className={cn(
            'flex items-center gap-1.5 text-[14.5px] font-medium',
            entry.is_reversed && 'text-[var(--fg-tertiary)] line-through',
          )}
        >
          <CategoryDot category={entry.category} />
          {reversal ? `اصلاح: ${entry.rule_title_fa}` : entry.rule_title_fa}
        </span>
        <span className="text-[13px] text-[var(--fg-secondary)]">
          {entry.source_href && entry.source_label ? (
            <Link href={entry.source_href} className="hover:underline">
              {toPersianDigits(entry.source_label)}
            </Link>
          ) : (
            toPersianDigits(entry.source_label ?? entry.source_type_fa ?? entry.source_type)
          )}
          {' · '}
          {entry.category_fa}
        </span>
        {entry.note && (
          <span className="text-[12.5px] text-[var(--fg-tertiary)]">
            {toPersianDigits(entry.note)}
          </span>
        )}
        <time dateTime={entry.created_at} className="text-[12px] text-[var(--fg-tertiary)]">
          {formatDateTime(entry.created_at)}
        </time>
        {action}
      </div>
      <span
        className={cn(
          'text-[16px] font-semibold tabular-nums',
          // کاهش دیده می‌شود ولی هشدار نمی‌دهد — §9.10 «احترام به کاهش».
          amount < 0 ? 'text-[var(--fg-secondary)]' : 'text-[var(--fg-primary)]',
          entry.is_reversed && 'text-[var(--fg-tertiary)] line-through',
        )}
        dir="ltr"
      >
        {amount > 0 ? '+' : '−'}
        {formatNumber(Math.abs(amount))}
      </span>
    </li>
  );
}
