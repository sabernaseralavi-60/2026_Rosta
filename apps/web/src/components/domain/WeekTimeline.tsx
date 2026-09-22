'use client';

import Link from 'next/link';

import { Badge, type BadgeTone } from '@/components/ui/Badge';
import type { WeekSummary } from '@/lib/api/courses';
import { cn } from '@/lib/cn';
import { toPersianDigits } from '@/lib/format/digits';

/**
 * خط زمانی هفته‌ها — PRD §10.6 (M3-11).
 *
 * هفده هفته در یک ستون. سه چیز عمدی است:
 *
 * ۱. **هفتهٔ پیش‌نویس با متن مشخص می‌شود، نه با رنگ کم‌رنگ** (§10.2) —
 *    استاد باید ببیند کدام هنوز منتشر نشده، و کاربر رنگ‌کور هم.
 * ۲. **هفتهٔ بدون محتوا لینک ندارد.** بردن کاربر به صفحه‌ای که می‌گوید
 *    «چیزی اینجا نیست» یک کلیک هدررفته است.
 * ۳. **درصد پیشرفت فقط وقتی نشان داده می‌شود که منبعی باشد** — «۰٪ از
 *    ۰ منبع» اطلاعات نیست، سر و صداست.
 */

const STATUS_TONES: Record<string, BadgeTone> = {
  DRAFT: 'neutral',
  PUBLISHED: 'brand',
  ARCHIVED: 'neutral',
};

const STATUS_LABELS: Record<string, string> = {
  DRAFT: 'منتشر نشده',
  PUBLISHED: 'منتشر شده',
  ARCHIVED: 'بایگانی',
};

export interface WeekTimelineProps {
  weeks: WeekSummary[];
  /** الگوی نشانی هفته — `n` جایگزین می‌شود. */
  hrefFor?: (week: WeekSummary) => string;
  /** شمارهٔ هفته‌ای که «همین حالا» است — با حاشیه مشخص می‌شود. */
  currentWeekNumber?: number | null;
  className?: string;
}

export function WeekTimeline({
  weeks,
  hrefFor,
  currentWeekNumber,
  className,
}: WeekTimelineProps) {
  if (weeks.length === 0) {
    return (
      <p className="rounded-[var(--radius-lg)] border border-dashed border-[var(--border-default)] px-4 py-6 text-center text-[13.5px] text-[var(--fg-secondary)]">
        هنوز هفته‌ای منتشر نشده است.
      </p>
    );
  }

  return (
    <ol className={cn('flex flex-col', className)}>
      {weeks.map((week, index) => {
        const isLast = index === weeks.length - 1;
        const isCurrent = week.week_number === currentWeekNumber;
        const hasContent = week.resource_count + week.material_count > 0;
        const href = hrefFor && week.status === 'PUBLISHED' ? hrefFor(week) : null;

        const body = (
          <div
            className={cn(
              'flex flex-1 flex-col gap-2 rounded-[var(--radius-md)] px-4 py-3',
              isCurrent && 'bg-[var(--brand-50)]',
              href &&
                'transition-colors duration-[var(--dur-fast)] hover:bg-[var(--bg-sunken)]',
            )}
          >
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-[14.5px] font-semibold text-[var(--fg-primary)]">
                هفتهٔ {toPersianDigits(week.week_number)} — {week.title_fa}
              </span>
              {week.status !== 'PUBLISHED' && (
                <Badge tone={STATUS_TONES[week.status] ?? 'neutral'}>
                  {STATUS_LABELS[week.status] ?? week.status}
                </Badge>
              )}
              {isCurrent && <Badge tone="brand">هفتهٔ جاری</Badge>}
            </div>

            {week.description && (
              <p className="text-[13px] leading-6 text-[var(--fg-secondary)]">
                {week.description}
              </p>
            )}

            <div className="flex flex-wrap items-center gap-3 text-[12.5px] text-[var(--fg-tertiary)]">
              {hasContent ? (
                <>
                  <span>
                    {toPersianDigits(week.resource_count)} منبع ·{' '}
                    {toPersianDigits(week.material_count)} محتوای کتابخانه
                  </span>
                  {week.resource_count > 0 && (
                    <span className="tabular-nums">
                      {toPersianDigits(week.progress_percent)}٪ مطالعه شده
                    </span>
                  )}
                </>
              ) : (
                <span>هنوز محتوایی برای این هفته گذاشته نشده.</span>
              )}
            </div>
          </div>
        );

        return (
          <li key={week.id} className="flex gap-3">
            {/* ستون نشانگر */}
            <div className="flex w-5 shrink-0 flex-col items-center pt-4">
              <span
                className={cn(
                  'size-3 shrink-0 rounded-[var(--radius-full)] border-2',
                  week.status === 'PUBLISHED'
                    ? 'border-[var(--brand-500)] bg-[var(--brand-500)]'
                    : 'border-[var(--border-default)] bg-[var(--bg-surface)]',
                )}
                aria-hidden="true"
              />
              {!isLast && (
                <span
                  className="mt-1 w-px flex-1 bg-[var(--border-subtle)]"
                  aria-hidden="true"
                />
              )}
            </div>

            {href ? (
              <Link href={href} className="flex flex-1 focus-visible:outline-none">
                {body}
              </Link>
            ) : (
              body
            )}
          </li>
        );
      })}
    </ol>
  );
}
