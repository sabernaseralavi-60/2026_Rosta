'use client';

import type { TextareaHTMLAttributes } from 'react';
import { forwardRef, useId } from 'react';

import { cn } from '@/lib/cn';
import { toPersianDigits } from '@/lib/format/digits';

/**
 * ناحیهٔ متن — PRD §10.6، §10.8.
 *
 * همان قواعد `Input`: برچسب بالای فیلد، خطا با `role="alert"`.
 *
 * شمارندهٔ نویسه وقتی `maxLength` داده شود نمایش داده می‌شود و **پیش از
 * رسیدن به سقف** هشدار می‌دهد. انگیزه‌نامهٔ ۵۰۰ نویسه‌ای که در نویسهٔ
 * ۵۰۱ بی‌صدا قطع شود، بدترین حالت است.
 */

export interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label: string;
  hint?: string;
  error?: string;
  /** تعداد نویسهٔ فعلی — برای نمایش شمارنده لازم است. */
  value?: string;
}

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(function Textarea(
  { label, hint, error, className, id, maxLength, value, rows = 4, ...props },
  ref,
) {
  const generatedId = useId();
  const fieldId = id ?? generatedId;
  const hintId = `${fieldId}-hint`;
  const errorId = `${fieldId}-error`;
  const countId = `${fieldId}-count`;

  const used = typeof value === 'string' ? value.length : 0;
  const showCount = typeof maxLength === 'number';
  const nearLimit = showCount && used > maxLength * 0.9;

  const describedBy =
    [hint ? hintId : null, error ? errorId : null, showCount ? countId : null]
      .filter(Boolean)
      .join(' ') || undefined;

  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={fieldId} className="text-[13.5px] font-medium text-[var(--fg-primary)]">
        {label}
      </label>

      {hint && (
        <p id={hintId} className="text-[12.5px] text-[var(--fg-tertiary)]">
          {hint}
        </p>
      )}

      <textarea
        ref={ref}
        id={fieldId}
        rows={rows}
        maxLength={maxLength}
        value={value}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy}
        className={cn(
          'w-full resize-y rounded-[var(--radius-md)] border bg-[var(--bg-surface)]',
          'px-3 py-2.5 text-[15px] leading-[1.9] text-[var(--fg-primary)]',
          'placeholder:text-[var(--fg-tertiary)]',
          'transition-[border-color,box-shadow] duration-[var(--dur-instant)]',
          'focus:outline-none focus:ring-2 focus:ring-[var(--border-focus)]',
          'disabled:cursor-not-allowed disabled:opacity-55',
          error ? 'border-[var(--danger-600)]' : 'border-[var(--border-default)]',
          className,
        )}
        {...props}
      />

      <div className="flex items-start justify-between gap-3">
        {error ? (
          <p id={errorId} role="alert" className="text-[12.5px] text-[var(--danger-600)]">
            {error}
          </p>
        ) : (
          <span />
        )}
        {showCount && (
          <span
            id={countId}
            className={cn(
              'shrink-0 text-[12px] tabular-nums',
              nearLimit ? 'text-[var(--warning-600)]' : 'text-[var(--fg-tertiary)]',
            )}
          >
            {toPersianDigits(used)}/{toPersianDigits(maxLength)}
          </span>
        )}
      </div>
    </div>
  );
});
