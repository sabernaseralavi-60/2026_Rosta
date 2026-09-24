import Link from 'next/link';

import { Button } from '@/components/ui/Button';
import type { NextStep } from '@/lib/api/points';
import { formatDeadline } from '@/lib/format/date';

/**
 * «قدم بعدی تو» — FR-DASH-01، §10.6 `NextStepCard`.
 *
 * بزرگ‌ترین عنصر داشبورد و فقط **یک** اقدام. اینکه کدام اقدام، تصمیم
 * سرور است (`silp.domain.next_step`)؛ کارت فقط نمایش می‌دهد. وقتی هیچ
 * کاری نمانده، کارت هم خالی نمی‌ماند — «داشبورد خالی ممنوع است» (§00).
 */

const ACTION_LABEL: Record<string, string> = {
  QUIZ_OPEN: 'برو به آزمون',
  MILESTONE_OVERDUE: 'برو به فضای کاری',
  MILESTONE_DUE: 'برو به فضای کاری',
  PROFILE_INCOMPLETE: 'ادامهٔ نیمرخ',
  STUDY: 'شروع مطالعه',
  FIND_PROJECT: 'دیدن پروژه‌ها',
  ENROLL: 'دیدن دروس',
};

export function NextStepCard({ step, now }: { step: NextStep | null; now?: Date }) {
  if (!step) {
    return (
      <section
        aria-labelledby="next-step-title"
        className="flex flex-col gap-2 rounded-[var(--radius-xl)] border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-6"
      >
        <p className="text-[13px] font-medium text-[var(--fg-tertiary)]">قدم بعدی تو</p>
        <h2 id="next-step-title" className="text-[22px] font-bold">
          فعلاً کار عقب‌افتاده‌ای نداری
        </h2>
        <p className="text-[15px] text-[var(--fg-secondary)]">
          وقت خوبی است برای یک ایدهٔ تازه یا نگاهی به جدول رتبه‌بندی.
        </p>
      </section>
    );
  }

  const deadline = step.due_at ? formatDeadline(step.due_at, now) : null;
  return (
    <section
      aria-labelledby="next-step-title"
      className="flex flex-col gap-3 rounded-[var(--radius-xl)] border border-[var(--brand-200)] bg-[var(--brand-50)] p-6 sm:p-8"
    >
      <p className="text-[13px] font-medium text-[var(--fg-brand)]">قدم بعدی تو</p>
      <h2
        id="next-step-title"
        className="text-[22px] font-bold text-[var(--fg-primary)] sm:text-[26px]"
      >
        {step.title}
      </h2>
      <p className="text-[15px] text-[var(--fg-secondary)]">{step.description}</p>
      <div className="mt-1 flex flex-wrap items-center gap-3">
        <Button asChild size="lg">
          <Link href={step.href}>{ACTION_LABEL[step.kind] ?? 'ادامه'}</Link>
        </Button>
        {deadline && (
          <span
            className={
              deadline.isOverdue
                ? 'text-[14px] font-medium text-[var(--fg-danger)]'
                : 'text-[14px] text-[var(--fg-secondary)]'
            }
          >
            {deadline.label}
          </span>
        )}
      </div>
    </section>
  );
}
