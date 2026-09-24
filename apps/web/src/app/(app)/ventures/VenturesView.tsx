'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';

import { StageTrack } from '@/components/domain/StageTrack';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { ChipGroup, type ChipOption } from '@/components/ui/ChipGroup';
import { EmptyState } from '@/components/ui/EmptyState';
import { Input } from '@/components/ui/Input';
import { SkeletonCard } from '@/components/ui/Skeleton';
import { ApiError, NetworkError } from '@/lib/api/client';
import {
  type VentureStage,
  type VentureSummary,
  fetchMyVentures,
  fetchVentures,
} from '@/lib/api/ventures';
import { useSession } from '@/lib/auth/use-session';
import { toPersianDigits } from '@/lib/format/digits';

/**
 * `/ventures` — FR-VEN-01.
 *
 * بالای صفحه کسب‌وکارهای خودم، پایین فهرست همه. فیلتر «دنبال هم‌بنیان‌گذار»
 * همان چیزی است که FR-VEN-01 خواسته: «در ماژول TEAM دیده شود».
 */

const SEARCH_DEBOUNCE_MS = 350;

type Filter = '' | VentureStage | 'COFOUNDER';

const FILTERS: ChipOption<Filter>[] = [
  { value: '', label: 'همه' },
  { value: 'COFOUNDER', label: 'دنبال هم‌بنیان‌گذار' },
  { value: 'IDEA', label: 'ایده' },
  { value: 'VALIDATION', label: 'اعتبارسنجی' },
  { value: 'MVP', label: 'محصول کمینه' },
  { value: 'FIRST_REVENUE', label: 'اولین درآمد' },
  { value: 'GROWTH', label: 'رشد' },
];

export function VenturesView() {
  const { accessToken, loading: sessionLoading } = useSession();
  const [mine, setMine] = useState<VentureSummary[] | null>(null);
  const [ventures, setVentures] = useState<VentureSummary[] | null>(null);
  const [total, setTotal] = useState(0);
  const [filter, setFilter] = useState<Filter>('');
  const [query, setQuery] = useState('');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (sessionLoading || !accessToken) return;
    fetchMyVentures(accessToken)
      .then(setMine)
      .catch(() => setMine([]));
  }, [accessToken, sessionLoading]);

  useEffect(() => {
    let cancelled = false;
    const timer = setTimeout(() => {
      fetchVentures({
        ...(filter === 'COFOUNDER' ? { looking_for_cofounder: true } : {}),
        ...(filter && filter !== 'COFOUNDER' ? { stage: filter } : {}),
        ...(query.trim() ? { q: query.trim() } : {}),
      })
        .then((page) => {
          if (cancelled) return;
          setVentures(page.items);
          setTotal(page.total);
          setError(null);
        })
        .catch((cause) => {
          if (cancelled) return;
          setError(
            cause instanceof ApiError || cause instanceof NetworkError
              ? cause.message
              : 'فهرست کسب‌وکارها بارگذاری نشد.',
          );
          setVentures([]);
        });
    }, SEARCH_DEBOUNCE_MS);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [filter, query]);

  return (
    <div className="flex flex-col gap-10">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="flex flex-col gap-1">
          <h1>کسب‌وکارها</h1>
          <p className="text-[15px] text-[var(--fg-secondary)]">
            از ایده تا رشد، قدم‌به‌قدم — هر گام با معیاری روشن.
          </p>
        </div>
        <Button asChild>
          <Link href="/ventures/new">ثبت کسب‌وکار</Link>
        </Button>
      </header>

      {mine && mine.length > 0 && (
        <section className="flex flex-col gap-4">
          <h2 className="text-[19px] font-semibold">کسب‌وکارهای من</h2>
          <ul className="grid gap-4 md:grid-cols-2">
            {mine.map((venture) => (
              <li key={venture.id}>
                <VentureCard venture={venture} />
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="flex flex-col gap-4">
        <h2 className="text-[19px] font-semibold">همهٔ کسب‌وکارها</h2>
        <Input
          label="جستجو"
          hint="نام یا معرفی کسب‌وکار"
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        <ChipGroup label="فیلتر کسب‌وکار" options={FILTERS} value={filter} onChange={setFilter} />

        {error && (
          <p role="alert" className="text-[13.5px] text-[var(--fg-danger)]">
            {error}
          </p>
        )}
        {ventures === null ? (
          <SkeletonCard label="در حال بارگذاری کسب‌وکارها" />
        ) : ventures.length === 0 ? (
          <EmptyState
            title="کسب‌وکاری با این فیلتر پیدا نشد"
            description="شاید اولین کسب‌وکار این دسته مال تو باشد."
            action={
              <Button asChild>
                <Link href="/ventures/new">ثبت کسب‌وکار</Link>
              </Button>
            }
          />
        ) : (
          <>
            <p className="text-[13px] text-[var(--fg-tertiary)]">
              {toPersianDigits(total)} کسب‌وکار
            </p>
            <ul className="grid gap-4 md:grid-cols-2">
              {ventures.map((venture) => (
                <li key={venture.id}>
                  <VentureCard venture={venture} />
                </li>
              ))}
            </ul>
          </>
        )}
      </section>
    </div>
  );
}

function VentureCard({ venture }: { venture: VentureSummary }) {
  return (
    <Card variant="interactive" className="flex h-full flex-col gap-3">
      <div className="flex flex-wrap items-center gap-1.5">
        <Badge tone="accent">{venture.stage_fa}</Badge>
        {venture.looking_for_cofounder && <Badge tone="brand">دنبال هم‌بنیان‌گذار</Badge>}
      </div>
      <Link
        href={`/ventures/${venture.id}`}
        className="text-[16.5px] font-semibold text-[var(--fg-primary)] hover:text-[var(--fg-brand)]"
      >
        {venture.name}
      </Link>
      <p className="text-[14px] leading-[1.9] text-[var(--fg-secondary)]">{venture.pitch}</p>
      <StageTrack stage={venture.stage} compact />
      <p className="mt-auto text-[12.5px] text-[var(--fg-tertiary)]">
        {venture.founder?.name ?? 'بنیان‌گذار'} · {toPersianDigits(venture.member_count)} عضو
        {venture.needed_roles.length > 0 && ` · نیاز: ${venture.needed_roles.join('، ')}`}
      </p>
    </Card>
  );
}
