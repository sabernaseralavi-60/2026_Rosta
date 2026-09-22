'use client';

import Link from 'next/link';

import { points } from '@/lib/api/points';
import { formatNumber, toPersianDigits } from '@/lib/format/digits';

import { usePoints } from './PointsProvider';

/**
 * امتیاز و سطح در هدر — §10.6 `PointsBadge`، §9.10 «پیشرفت».
 *
 * «نوار سطح همیشه در هدر، با «۱۳۰ امتیاز تا سطح بعد»» — عدد خام بدون
 * فاصله تا هدف، انگیزه نمی‌سازد. کل کاشی پیوندی است به `/me/points`
 * (§9.10 شفافیت: هر عدد قابل کلیک و منتهی به دفتر کل).
 *
 * متن «تا سطح بعد» در موبایل پنهان است ولی برای صفحه‌خوان در برچسب
 * پیوند می‌ماند؛ اطلاعات مهم هرگز فقط در tooltip نیست (§10.6).
 */
export function PointsBadge() {
  const { summary } = usePoints();
  if (!summary) return null;

  const { level } = summary;
  const toNext = Math.ceil(points(level.to_next));
  const ratio = Math.max(0, Math.min(1, points(level.ratio)));
  const hint =
    level.next_at === null ? 'بالاترین سطح' : `${formatNumber(toNext)} امتیاز تا سطح بعد`;

  return (
    <Link
      href="/me/points"
      aria-label={`سطح ${toPersianDigits(level.level)}، ${level.title_fa}، ${formatNumber(points(summary.total))} امتیاز — ${hint}`}
      className="flex items-center gap-2.5 rounded-[var(--radius-md)] px-2 py-1 transition-colors hover:bg-[var(--bg-sunken)]"
    >
      <span
        aria-hidden="true"
        className="flex size-8 items-center justify-center rounded-[var(--radius-full)] bg-[var(--brand-50)] text-[14px] font-bold text-[var(--brand-700)]"
      >
        {toPersianDigits(level.level)}
      </span>
      <span aria-hidden="true" className="flex flex-col gap-1">
        <span className="flex items-baseline gap-1.5 text-[13px]">
          <span className="font-semibold text-[var(--fg-primary)]">
            {formatNumber(points(summary.total))}
          </span>
          <span className="hidden text-[12px] text-[var(--fg-tertiary)] md:inline">{hint}</span>
        </span>
        <span className="block h-1.5 w-20 overflow-hidden rounded-[var(--radius-full)] bg-[var(--brand-100)]">
          <span
            className="block h-full rounded-[var(--radius-full)] bg-[var(--brand-600)] transition-[width] duration-[var(--dur-normal)]"
            style={{ width: `${ratio * 100}%` }}
          />
        </span>
      </span>
    </Link>
  );
}
