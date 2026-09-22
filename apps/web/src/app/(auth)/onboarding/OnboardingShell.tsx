import type { ReactNode } from 'react';

import { Progress } from '@/components/ui/Progress';
import { toPersianDigits } from '@/lib/format/digits';

/**
 * پوستهٔ مشترک گام‌های ورود اولیه — §3.3.
 *
 * الزامات ناحیه: نوار پیشرفت در همهٔ گام‌ها، حداکثر ۷ فیلد در هر صفحه،
 * و دکمهٔ «بعداً» در گام‌های غیر الزامی.
 */

export interface OnboardingShellProps {
  title: string;
  description?: string;
  /** شمارهٔ گام جاری، از ۱. */
  step: number;
  totalSteps: number;
  estimatedSeconds?: number;
  children: ReactNode;
  footer?: ReactNode;
}

export function OnboardingShell({
  title,
  description,
  step,
  totalSteps,
  estimatedSeconds,
  children,
  footer,
}: OnboardingShellProps) {
  return (
    <div className="flex w-full max-w-[32rem] flex-col gap-6">
      <Progress
        value={step}
        max={totalSteps}
        label="پیشرفت"
        valueText={`گام ${toPersianDigits(step)} از ${toPersianDigits(totalSteps)}`}
      />

      <header className="flex flex-col gap-1.5">
        <h1 className="text-[24px] font-bold text-[var(--fg-primary)]">{title}</h1>
        {description && (
          <p className="text-[14px] leading-[1.9] text-[var(--fg-secondary)]">{description}</p>
        )}
        {estimatedSeconds && (
          <p className="text-[12.5px] text-[var(--fg-tertiary)]">
            حدود {toPersianDigits(estimatedSeconds)} ثانیه وقت می‌گیرد.
          </p>
        )}
      </header>

      {children}

      {footer && <div className="flex flex-col gap-3">{footer}</div>}
    </div>
  );
}
