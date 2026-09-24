'use client';

import type { ReactNode } from 'react';

import { Badge, type BadgeTone } from '@/components/ui/Badge';
import { cn } from '@/lib/cn';
import type { Milestone, MilestoneStatus } from '@/lib/api/workspace';
import { formatDateLong, formatDeadline } from '@/lib/format/date';
import { toPersianDigits } from '@/lib/format/digits';

/**
 * ردیاب مراحل — PRD §10.6 (M2-12).
 *
 * یک ستون عمودی از مراحل، به ترتیب. هر مرحله وضعیتش را با **متن**
 * می‌گوید، نه فقط با رنگ (§10.2): کاربر رنگ‌کور باید همان را بفهمد.
 *
 * «از مهلت گذشته» و «تأیید شده» هر دو حالت پایانی به نظر می‌رسند ولی
 * یکی نیستند: مرحلهٔ گذشته از مهلت هنوز تحویل می‌پذیرد (§7.6)، پس
 * غیرفعال نمایش داده نمی‌شود.
 */

const TONES: Record<MilestoneStatus, BadgeTone> = {
  PENDING: 'neutral',
  IN_PROGRESS: 'info',
  SUBMITTED: 'brand',
  APPROVED: 'success',
  OVERDUE: 'warning',
};

const MARKERS: Record<MilestoneStatus, string> = {
  PENDING: 'border-[var(--border-default)] bg-[var(--bg-surface)]',
  IN_PROGRESS: 'border-[var(--info-500)] bg-[var(--bg-surface)]',
  SUBMITTED: 'border-[var(--brand-500)] bg-[var(--brand-50)]',
  APPROVED: 'border-[var(--success-500)] bg-[var(--success-500)]',
  OVERDUE: 'border-[var(--warning-500)] bg-[var(--bg-surface)]',
};

export interface MilestoneTrackerProps {
  milestones: Milestone[];
  /** محتوای اختیاری زیر هر مرحله — فرم تحویل، تاریخچه، دکمه‌ها. */
  renderExtra?: (milestone: Milestone) => ReactNode;
  className?: string;
}

export function MilestoneTracker({ milestones, renderExtra, className }: MilestoneTrackerProps) {
  return (
    <ol className={cn('flex flex-col', className)}>
      {milestones.map((milestone, index) => {
        const isLast = index === milestones.length - 1;
        const deadline = milestone.due_on ? formatDeadline(milestone.due_on) : null;

        return (
          <li key={milestone.id} className="relative flex gap-4 pb-6 last:pb-0">
            {/* خط اتصال بین نشانگرها */}
            {!isLast && (
              <span
                aria-hidden="true"
                className="absolute bottom-0 start-[11px] top-6 w-px bg-[var(--border-subtle)]"
              />
            )}

            <span
              aria-hidden="true"
              className={cn(
                'relative z-[1] mt-0.5 flex size-6 shrink-0 items-center justify-center',
                'rounded-[var(--radius-full)] border-2',
                MARKERS[milestone.status],
              )}
            >
              {milestone.status === 'APPROVED' && (
                <svg viewBox="0 0 16 16" className="size-3.5 text-[var(--neutral-0)]">
                  <path
                    d="M3 8.5 6.5 12 13 4.5"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              )}
            </span>

            <div className="flex min-w-0 flex-1 flex-col gap-2">
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="text-[15.5px] font-semibold text-[var(--fg-primary)]">
                  {milestone.title_fa}
                </h3>
                <Badge tone={TONES[milestone.status]}>{milestone.status_fa}</Badge>
                {!milestone.is_required && <Badge tone="neutral">اختیاری</Badge>}
                {milestone.points > 0 && (
                  <Badge tone="accent">{toPersianDigits(milestone.points)} امتیاز</Badge>
                )}
              </div>

              {milestone.description && (
                <p className="text-[13.5px] leading-[1.95] text-[var(--fg-secondary)]">
                  {milestone.description}
                </p>
              )}

              <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[12.5px] text-[var(--fg-tertiary)]">
                {milestone.due_on && (
                  <span
                    className={
                      deadline?.isOverdue && milestone.status !== 'APPROVED'
                        ? 'text-[var(--fg-warning)]'
                        : undefined
                    }
                  >
                    مهلت: {formatDateLong(milestone.due_on)}
                    {deadline && ` — ${deadline.label}`}
                  </span>
                )}
                {milestone.output_kind_fa && <span>خروجی: {milestone.output_kind_fa}</span>}
                {milestone.deliverable_count > 0 && (
                  <span>{toPersianDigits(milestone.deliverable_count)} تحویل ثبت شده</span>
                )}
              </div>

              {milestone.checklist.length > 0 && (
                <ul className="flex flex-col gap-1">
                  {milestone.checklist.map((item, itemIndex) => (
                    <li
                      key={itemIndex}
                      className="flex items-start gap-2 text-[13px] text-[var(--fg-secondary)]"
                    >
                      <span
                        aria-hidden="true"
                        className="mt-[7px] size-1.5 shrink-0 rounded-full bg-[var(--border-default)]"
                      />
                      {item}
                    </li>
                  ))}
                </ul>
              )}

              {renderExtra?.(milestone)}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
