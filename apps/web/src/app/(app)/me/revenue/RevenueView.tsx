'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';

import { Button } from '@/components/ui/Button';
import { Card, CardTitle } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { SkeletonCard } from '@/components/ui/Skeleton';
import { ApiError } from '@/lib/api/client';
import {
  fetchRevenue,
  type RevenueLine,
  type RevenueMonth,
  type RevenueReport,
} from '@/lib/api/ventures';
import { useSession } from '@/lib/auth/use-session';
import { formatDateShort } from '@/lib/format/date';
import { formatNumber, formatRial } from '@/lib/format/digits';

/**
 * درآمد و سهم من — FR-VEN-03، ADR-0025.
 *
 * فقط ثبت و گزارش: پرداخت بیرون از سامانه انجام می‌شود، پس هیچ وضعیتی مثل
 * «پرداخت‌شده» اینجا نیست. سهم هر ردیف همان عددی است که هنگام تأیید ثبت شد؛
 * تغییر بعدی درصد پروژه ماه‌های گذشته را جابه‌جا نمی‌کند.
 *
 * هر عدد برچسب خودش را دارد (`dl`) و میان دو عدد نقطهٔ وسط نمی‌آید — «·»
 * کنار رقم فارسی «۰» خوانده می‌شود.
 */

export function RevenueView() {
  const { accessToken, loading } = useSession();
  const [report, setReport] = useState<RevenueReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (loading || !accessToken) return;
    let cancelled = false;
    fetchRevenue(accessToken)
      .then((result) => {
        if (!cancelled) setReport(result);
      })
      .catch((cause: unknown) => {
        if (!cancelled)
          setError(cause instanceof ApiError ? cause.message : 'گزارش درآمد بارگذاری نشد.');
      });
    return () => {
      cancelled = true;
    };
  }, [accessToken, loading]);

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-1">
        <h1>درآمد و سهم من</h1>
        <p className="text-[15px] text-[var(--fg-secondary)]">
          فروش‌هایی که تو در پروژه‌های کارآفرینی ثبت کرده‌ای و مدیر یا منتور تأییدشان کرده، با سهمت
          از هر کدام. اینجا فقط گزارش است؛ پرداخت بیرون از سامانه و با هماهنگی مدیر پروژه انجام
          می‌شود.
        </p>
      </header>

      {error ? (
        <EmptyState title="گزارش درآمد بارگذاری نشد" description={error} />
      ) : report === null ? (
        <SkeletonCard label="در حال بارگذاری گزارش درآمد" />
      ) : (
        <>
          <Summary report={report} />
          {report.months.length === 0 ? (
            <EmptyState
              title="هنوز فروش تأییدشده‌ای نداری"
              description="فروش را در زبانهٔ «فعالیت و فروش» فضای کاری پروژه ثبت کن؛ بعد از تأیید مدیر یا منتور، سهمت اینجا می‌آید."
              action={
                <Button asChild>
                  <Link href="/projects">دیدن پروژه‌ها</Link>
                </Button>
              }
            />
          ) : (
            <div className="flex flex-col gap-4">
              {report.months.map((month) => (
                <MonthCard key={`${month.year}-${month.month}`} month={month} />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}

function Summary({ report }: { report: RevenueReport }) {
  return (
    <dl className="grid gap-3 sm:grid-cols-3">
      <Figure label="سهم من از فروش تأییدشده" value={formatRial(report.total_share_rial)} strong />
      <Figure label="کل فروش تأییدشده" value={formatRial(report.total_sales_rial)} />
      <Figure
        label="در انتظار تأیید"
        value={formatRial(report.pending_sales_rial)}
        hint={
          report.pending_count > 0
            ? `${formatNumber(report.pending_count)} ثبت هنوز بررسی نشده؛ سهمش بعد از تأیید معلوم می‌شود.`
            : undefined
        }
      />
    </dl>
  );
}

function Figure({
  label,
  value,
  hint,
  strong = false,
}: {
  label: string;
  value: string;
  hint?: string;
  strong?: boolean;
}) {
  return (
    <Card className="flex flex-col gap-1">
      <dt className="text-[13px] text-[var(--fg-secondary)]">{label}</dt>
      <dd
        className={
          strong ? 'text-[22px] font-bold tabular-nums' : 'text-[18px] font-semibold tabular-nums'
        }
      >
        {value}
      </dd>
      {hint && <dd className="text-[12.5px] text-[var(--fg-tertiary)]">{hint}</dd>}
    </Card>
  );
}

function MonthCard({ month }: { month: RevenueMonth }) {
  return (
    <Card className="flex flex-col gap-4">
      <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1">
        <CardTitle as="h2">{month.title}</CardTitle>
        <dl className="flex flex-wrap gap-x-6 gap-y-1 text-[13.5px]">
          <div className="flex gap-1.5">
            <dt className="text-[var(--fg-secondary)]">فروش:</dt>
            <dd className="tabular-nums">{formatRial(month.sales_rial)}</dd>
          </div>
          <div className="flex gap-1.5">
            <dt className="text-[var(--fg-secondary)]">سهم من:</dt>
            <dd className="font-semibold tabular-nums">{formatRial(month.share_rial)}</dd>
          </div>
        </dl>
      </div>
      <ul className="flex flex-col divide-y divide-[var(--border-subtle)]">
        {month.lines.map((line) => (
          <LineRow key={line.metric_id} line={line} />
        ))}
      </ul>
    </Card>
  );
}

function LineRow({ line }: { line: RevenueLine }) {
  return (
    <li className="flex flex-col gap-1 py-3 first:pt-0 last:pb-0">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <Link
          href={`/projects/${line.project_id}/workspace`}
          className="font-medium text-[var(--fg-brand)] hover:underline"
        >
          {line.project_title}
        </Link>
        <span className="text-[12.5px] text-[var(--fg-tertiary)]">
          تاریخ فروش: {formatDateShort(line.occurred_on)}
        </span>
      </div>
      <dl className="flex flex-wrap gap-x-6 gap-y-1 text-[13.5px]">
        <div className="flex gap-1.5">
          <dt className="text-[var(--fg-secondary)]">مبلغ فروش:</dt>
          <dd className="tabular-nums">{formatRial(line.value)}</dd>
        </div>
        <div className="flex gap-1.5">
          <dt className="text-[var(--fg-secondary)]">درصد سهم:</dt>
          <dd className="tabular-nums">{formatNumber(line.share_percent)}٪</dd>
        </div>
        <div className="flex gap-1.5">
          <dt className="text-[var(--fg-secondary)]">سهم من:</dt>
          <dd className="font-semibold tabular-nums">{formatRial(line.share_rial)}</dd>
        </div>
      </dl>
      {line.note && <p className="text-[13px] text-[var(--fg-secondary)]">{line.note}</p>}
    </li>
  );
}
