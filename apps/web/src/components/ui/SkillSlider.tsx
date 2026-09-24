'use client';

import { useId } from 'react';

import { cn } from '@/lib/cn';
import { toPersianDigits } from '@/lib/format/digits';

/**
 * اسلایدر مهارت — PRD §10.6، FR-PROF-01.
 *
 * «اسلایدر ۱-۵ با متن توصیفی زیر آن.»
 *
 * چرا متن توصیفی اجباری است: «سطح ۳» برای دو دانشجو دو معنا دارد و
 * موتور توصیه‌گر روی همین عدد حساب می‌کند. متن‌ها از سرور می‌آیند
 * (`/taxonomy/skills`) تا تعریف سطح در فرم و در دلیل پیشنهاد یکی باشد.
 *
 * حالت «پاسخ‌نداده» با `value = null` نمایش داده می‌شود و با سطح ۱
 * یکی نیست: §8.8 مهارت پاسخ‌نداده را در محاسبهٔ کامل بودن نیمرخ به حساب
 * نمی‌آورد.
 */

const MIN = 1;
const MAX = 5;
const LEVELS = [1, 2, 3, 4, 5] as const;

export interface SkillSliderProps {
  label: string;
  /** `null` یعنی هنوز پاسخ نداده. */
  value: number | null;
  onChange: (level: number) => void;
  /** متن هر سطح، از سرور. */
  levelLabels: Record<number, string>;
  hint?: string;
  disabled?: boolean;
  className?: string;
}

export function SkillSlider({
  label,
  value,
  onChange,
  levelLabels,
  hint,
  disabled = false,
  className,
}: SkillSliderProps) {
  const id = useId();
  const descriptionId = `${id}-description`;
  const answered = value !== null;
  const level = value ?? MIN;

  return (
    <div className={cn('flex flex-col gap-2 py-3', className)}>
      <div className="flex items-baseline justify-between gap-3">
        <label htmlFor={id} className="text-[15px] font-medium text-[var(--fg-primary)]">
          {label}
        </label>
        <span
          id={descriptionId}
          className={cn(
            'text-[13px]',
            answered ? 'text-[var(--fg-brand)]' : 'text-[var(--fg-tertiary)]',
          )}
        >
          {answered ? levelLabels[level] : 'هنوز پاسخ نداده‌ای'}
        </span>
      </div>

      {hint && <p className="text-[12.5px] text-[var(--fg-tertiary)]">{hint}</p>}

      {/* دکمه‌های مجزا به‌جای <input type=range>: ناحیهٔ لمس ≥۴۴px و
          حالت «پاسخ‌نداده» با اسلایدر بومی قابل بیان نیست (§10.6). */}
      <div
        role="radiogroup"
        aria-labelledby={id}
        aria-describedby={descriptionId}
        className="flex gap-1.5"
      >
        {LEVELS.map((candidate) => {
          const active = answered && candidate <= level;
          const selected = answered && candidate === level;
          return (
            <button
              key={candidate}
              type="button"
              role="radio"
              aria-checked={selected}
              aria-label={`${candidate} — ${levelLabels[candidate] ?? ''}`}
              disabled={disabled}
              onClick={() => onChange(candidate)}
              className={cn(
                'h-11 flex-1 rounded-[var(--radius-md)] border text-[14px] font-medium tabular-nums',
                'transition-colors duration-[var(--dur-instant)]',
                'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--border-focus)]',
                'disabled:cursor-not-allowed disabled:opacity-55',
                selected
                  ? 'border-[var(--brand-600)] bg-[var(--brand-600)] text-[var(--fg-on-brand)]'
                  : active
                    ? 'border-[var(--brand-200)] bg-[var(--brand-50)] text-[var(--fg-brand)]'
                    : 'border-[var(--border-default)] bg-[var(--bg-surface)] text-[var(--fg-tertiary)] hover:border-[var(--border-strong)]',
              )}
            >
              {toPersianDigits(candidate)}
            </button>
          );
        })}
      </div>
    </div>
  );
}

export { MAX as SKILL_MAX_LEVEL, MIN as SKILL_MIN_LEVEL };
