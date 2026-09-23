'use client';

import { cn } from '@/lib/cn';

/**
 * گروه تراشه‌های انتخاب تکی — فیلتر نوع، دسته، مرتب‌سازی.
 *
 * `aria-pressed` روی هر دکمه، نه `role="radio"`: این‌ها فیلترند و با هر
 * کلیک فهرست را عوض می‌کنند، نه بخشی از یک فرم.
 */
export interface ChipOption<T extends string> {
  value: T;
  label: string;
}

export function ChipGroup<T extends string>({
  options,
  value,
  onChange,
  label,
  className,
}: {
  options: ChipOption<T>[];
  value: T;
  onChange: (value: T) => void;
  /** برچسب دسترس‌پذیر گروه. */
  label: string;
  className?: string;
}) {
  return (
    <div className={cn('flex flex-wrap gap-2', className)} role="group" aria-label={label}>
      {options.map((option) => (
        <button
          key={option.value || 'all'}
          type="button"
          aria-pressed={value === option.value}
          onClick={() => onChange(option.value)}
          className={cn(
            'h-9 rounded-[var(--radius-full)] border px-4 text-[13.5px] font-medium',
            'transition-colors duration-[var(--dur-instant)]',
            value === option.value
              ? 'border-[var(--brand-600)] bg-[var(--brand-600)] text-[var(--fg-on-brand)]'
              : 'border-[var(--border-default)] bg-[var(--bg-surface)] text-[var(--fg-secondary)] hover:border-[var(--border-strong)]',
          )}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}
