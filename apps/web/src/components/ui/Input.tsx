'use client';

import type { InputHTMLAttributes, ReactNode } from 'react';
import { forwardRef, useId } from 'react';

import { cn } from '@/lib/cn';

/**
 * ورودی — PRD §10.6، §10.8.
 *
 * «برچسب همیشه بالای ورودی، نه داخل — placeholder برچسب نیست.»
 * کاربری که شروع به تایپ می‌کند، placeholder را از دست می‌دهد و دیگر
 * نمی‌داند این فیلد چه بود.
 *
 * خطا با `aria-describedby` وصل و با `role="alert"` اعلام می‌شود (§10.8).
 */

export interface InputProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'size'> {
  label: string;
  /** توضیح کمکی زیر برچسب — همیشه دیده می‌شود، برخلاف tooltip. */
  hint?: string;
  error?: string;
  /** برای شماره، ایمیل و URL: جهت چپ‌به‌راست اجباری است (§10.5). */
  forceLtr?: boolean;
  leadingIcon?: ReactNode;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { label, hint, error, forceLtr = false, leadingIcon, className, id, ...props },
  ref,
) {
  const generatedId = useId();
  const inputId = id ?? generatedId;
  const hintId = `${inputId}-hint`;
  const errorId = `${inputId}-error`;

  const describedBy =
    [hint ? hintId : null, error ? errorId : null].filter(Boolean).join(' ') || undefined;

  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={inputId} className="text-[13.5px] font-medium text-[var(--fg-primary)]">
        {label}
      </label>

      {hint && (
        <p id={hintId} className="text-[12.5px] text-[var(--fg-tertiary)]">
          {hint}
        </p>
      )}

      <div className="relative flex items-center">
        {leadingIcon && (
          <span
            className="pointer-events-none absolute start-3 text-[var(--fg-tertiary)]"
            aria-hidden="true"
          >
            {leadingIcon}
          </span>
        )}
        <input
          ref={ref}
          id={inputId}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy}
          dir={forceLtr ? 'ltr' : undefined}
          className={cn(
            'h-11 w-full rounded-[var(--radius-md)] border bg-[var(--bg-surface)]',
            'px-3 text-[15px] text-[var(--fg-primary)]',
            'placeholder:text-[var(--fg-tertiary)]',
            'transition-colors duration-[var(--dur-instant)]',
            'disabled:cursor-not-allowed disabled:bg-[var(--bg-sunken)] disabled:opacity-60',
            'read-only:bg-[var(--bg-sunken)]',
            error
              ? 'border-[var(--danger-600)]'
              : 'border-[var(--border-default)] hover:border-[var(--border-strong)]',
            leadingIcon && 'ps-10',
            // متن چپ‌به‌راست در یک فرم RTL باید در ابتدای فیلد بنشیند.
            forceLtr && 'text-start',
            className,
          )}
          {...props}
        />
      </div>

      {error && (
        <p
          id={errorId}
          role="alert"
          className="flex items-center gap-1 text-[12.5px] text-[var(--fg-danger)]"
        >
          {/* §10.2 — رنگ به‌تنهایی کافی نیست؛ آیکن هم لازم است. */}
          <svg
            className="size-4 shrink-0"
            viewBox="0 0 20 20"
            fill="currentColor"
            aria-hidden="true"
          >
            <path
              fillRule="evenodd"
              d="M10 18a8 8 0 1 0 0-16 8 8 0 0 0 0 16Zm0-12a.9.9 0 0 1 .9.9v4.2a.9.9 0 1 1-1.8 0V6.9A.9.9 0 0 1 10 6Zm0 8.4a1 1 0 1 0 0-2 1 1 0 0 0 0 2Z"
              clipRule="evenodd"
            />
          </svg>
          {error}
        </p>
      )}
    </div>
  );
});
