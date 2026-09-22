'use client';

import { type ReactNode, useEffect, useState } from 'react';

import { CategoryDot } from '@/components/domain/CategoryTiles';
import { Card } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { SkeletonCard } from '@/components/ui/Skeleton';
import { ApiError } from '@/lib/api/client';
import { fetchMyOfferings, type OfferingSummary } from '@/lib/api/courses';
import {
  CATEGORIES,
  CATEGORY_LABELS,
  fetchLeaderboard,
  type Leaderboard,
  type LeaderboardScope,
  type LeaderRow,
  type PointCategory,
  points,
} from '@/lib/api/points';
import { useSession } from '@/lib/auth/use-session';
import { cn } from '@/lib/cn';
import { formatNumber, toPersianDigits } from '@/lib/format/digits';

/**
 * رتبه‌بندی — §9.7، FR-GAM-04، M5-07.
 *
 * قواعد انصاف §9.7 در سرورند؛ این صفحه فقط آن‌ها را آشکار می‌کند:
 * * فقط ۱۰ نفر برتر و **جایگاه خودت** — نه فهرست کامل.
 * * صدک همیشه به زبان رشد گفته می‌شود («بالاتر از ۶۲٪»)، هرگز «عقب‌تر از»
 *   (§9.10 «بدون تحقیر»).
 * * جدول «بیشترین رشد» کنار جدول اصلی، تا دانشجوی کوشای متوسط هم دیده شود.
 * * کاربری که انصراف داده، می‌داند که دیگران او را نمی‌بینند.
 */

type ScopeChoice = { scope: LeaderboardScope; scopeId?: string; label: string };

export function LeaderboardView() {
  const { accessToken, loading } = useSession({ required: false });
  const [offerings, setOfferings] = useState<OfferingSummary[]>([]);
  const [choice, setChoice] = useState<ScopeChoice>({ scope: 'GLOBAL', label: 'کل سامانه' });
  const [category, setCategory] = useState<PointCategory | null>(null);
  const [board, setBoard] = useState<Leaderboard | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (loading || !accessToken) return;
    fetchMyOfferings(accessToken)
      .then(setOfferings)
      .catch(() => setOfferings([]));
  }, [accessToken, loading]);

  useEffect(() => {
    if (loading || !accessToken) return;
    let cancelled = false;
    setBoard(null);
    setError(null);
    fetchLeaderboard(accessToken, {
      scope: choice.scope,
      scope_id: choice.scopeId,
      category: category ?? undefined,
    })
      .then((value) => !cancelled && setBoard(value))
      .catch((cause: unknown) => {
        if (!cancelled) setError(cause instanceof ApiError ? cause.message : 'رتبه‌بندی بارگذاری نشد.');
      });
    return () => {
      cancelled = true;
    };
  }, [accessToken, loading, choice, category]);

  const scopes: ScopeChoice[] = [
    { scope: 'GLOBAL', label: 'کل سامانه' },
    { scope: 'UNIVERSITY', label: 'دانشگاه من' },
    ...offerings.map((o) => ({
      scope: 'OFFERING' as const,
      scopeId: o.id,
      label: o.course_title_fa,
    })),
  ];

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h1>رتبه‌بندی</h1>
        <p className="text-[15px] text-[var(--fg-secondary)]">
          {board?.term_title_fa ? `نیم‌سال ${board.term_title_fa}. ` : ''}
          هر نیم‌سال از صفر شروع می‌شود و هر دسته جدولی جدا دارد.
        </p>
      </div>

      <div className="flex flex-col gap-3">
        <Chips label="دامنه">
          {scopes.map((s) => (
            <Chip
              key={`${s.scope}-${s.scopeId ?? ''}`}
              active={s.scope === choice.scope && s.scopeId === choice.scopeId}
              onClick={() => setChoice(s)}
            >
              {s.label}
            </Chip>
          ))}
        </Chips>
        <Chips label="دستهٔ امتیاز">
          <Chip active={category === null} onClick={() => setCategory(null)}>
            همهٔ دسته‌ها
          </Chip>
          {CATEGORIES.map((c) => (
            <Chip key={c} active={category === c} onClick={() => setCategory(c)}>
              <CategoryDot category={c} />
              {CATEGORY_LABELS[c]}
            </Chip>
          ))}
        </Chips>
      </div>

      {error ? (
        <EmptyState title="رتبه‌بندی بارگذاری نشد" description={error} />
      ) : !board ? (
        <SkeletonCard label="در حال بارگذاری رتبه‌بندی" />
      ) : (
        <>
          <MyStanding board={board} />
          <div className="grid gap-6 lg:grid-cols-2">
            <Board title="ده نفر برتر" rows={board.entries} empty="هنوز کسی در این جدول امتیاز ندارد." />
            <Board
              title="بیشترین رشد در ۳۰ روز"
              rows={board.growth}
              empty="در ۳۰ روز اخیر رشدی ثبت نشده."
              growth
            />
          </div>
        </>
      )}
    </div>
  );
}

function MyStanding({ board }: { board: Leaderboard }) {
  const { me } = board;
  if (me.excluded_reason === 'STAFF') {
    return (
      <Card className="text-[14px] text-[var(--fg-secondary)]">
        جدول رتبه‌بندی رقابت دانشجویان است؛ کادر آموزشی در آن رتبه ندارد.
      </Card>
    );
  }
  return (
    <Card className="flex flex-wrap items-center justify-between gap-4">
      <div className="flex flex-col gap-1">
        <span className="text-[13px] text-[var(--fg-secondary)]">جایگاه تو</span>
        <span className="text-[26px] font-bold">
          {me.rank === null ? 'هنوز در جدول نیستی' : `رتبهٔ ${toPersianDigits(me.rank)}`}
        </span>
        {me.rank === null && (
          <span className="text-[13px] text-[var(--fg-secondary)]">
            با اولین امتیاز این نیم‌سال وارد جدول می‌شوی.
          </span>
        )}
      </div>
      <div className="flex flex-col items-end gap-1 text-[14px]">
        <span>
          {formatNumber(points(me.total))} امتیاز · سطح {toPersianDigits(me.level)}
        </span>
        {me.percentile !== null && me.percentile > 0 && (
          <span className="text-[var(--fg-secondary)]">
            بالاتر از {toPersianDigits(me.percentile)}٪ شرکت‌کنندگان
          </span>
        )}
        {me.excluded_reason === 'OPTED_OUT' && (
          <span className="text-[12.5px] text-[var(--fg-tertiary)]">
            از جدول عمومی انصراف داده‌ای؛ دیگران تو را نمی‌بینند.
          </span>
        )}
      </div>
    </Card>
  );
}

function Board({
  title,
  rows,
  empty,
  growth = false,
}: {
  title: string;
  rows: LeaderRow[];
  empty: string;
  growth?: boolean;
}) {
  return (
    <section className="flex flex-col gap-3">
      <h2 className="text-[19px] font-semibold">{title}</h2>
      {rows.length === 0 ? (
        <p className="text-[14px] text-[var(--fg-secondary)]">{empty}</p>
      ) : (
        <ol className="flex flex-col divide-y divide-[var(--border-subtle)] rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-surface)]">
          {rows.map((row) => (
            <li
              key={row.user.user_id}
              aria-current={row.is_me ? 'true' : undefined}
              className={cn(
                'flex items-center gap-3 px-4 py-2.5',
                row.is_me && 'bg-[var(--brand-50)]',
              )}
            >
              <span className="w-7 text-center text-[15px] font-semibold text-[var(--fg-secondary)] tabular-nums">
                {toPersianDigits(row.rank)}
              </span>
              <span className="flex min-w-0 flex-1 flex-col">
                <span className="truncate text-[14.5px] font-medium">
                  {row.user.display_name ?? row.user.username ?? 'کاربر'}
                  {row.is_me && ' (تو)'}
                </span>
                <span className="text-[12px] text-[var(--fg-tertiary)]">
                  سطح {toPersianDigits(row.level)}
                </span>
              </span>
              <span className="text-[14.5px] font-semibold tabular-nums" dir="ltr">
                {growth ? '+' : ''}
                {formatNumber(points(row.total))}
              </span>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

function Chips({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div role="group" aria-label={label} className="flex flex-wrap gap-2">
      {children}
    </div>
  );
}

function Chip({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={cn(
        'inline-flex items-center gap-1.5 rounded-[var(--radius-full)] border px-3 py-1.5 text-[13px]',
        active
          ? 'border-[var(--brand-600)] bg-[var(--brand-50)] font-medium text-[var(--brand-700)]'
          : 'border-[var(--border-subtle)] text-[var(--fg-secondary)] hover:border-[var(--border-default)]',
      )}
    >
      {children}
    </button>
  );
}
