'use client';

import type { ReactNode } from 'react';

import { cn } from '@/lib/cn';

/**
 * کارت انتخاب (چندانتخابی و تک‌انتخابی) — PRD §10.6.
 *
 * «ناحیهٔ کلیک ≥ ۴۴×۴۴px» و «رنگ به‌تنهایی حامل معنا نیست»: وضعیت
 * انتخاب‌شده هم رنگ دارد، هم مرز ضخیم‌تر، هم علامت تیک.
 *
 * ورودی بومی پنهان نمی‌شود بلکه `sr-only` است تا کیبورد و صفحه‌خوان
 * همان رفتار استاندارد رادیو/چک‌باکس را بگیرند.
 */

export interface ChoiceCardProps {
  name: string;
  value: string;
  checked: boolean;
  onChange: (value: string) => void;
  label: string;
  hint?: string;
  icon?: ReactNode;
  type?: 'checkbox' | 'radio';
  className?: string;
}

export function ChoiceCard({
  name,
  value,
  checked,
  onChange,
  label,
  hint,
  icon,
  type = 'checkbox',
  className,
}: ChoiceCardProps) {
  return (
    <label
      className={cn(
        'relative flex min-h-[3.25rem] cursor-pointer items-center gap-3',
        'rounded-[var(--radius-md)] border px-4 py-3',
        'transition-colors duration-[var(--dur-instant)]',
        'has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2',
        'has-[:focus-visible]:outline-[var(--border-focus)]',
        checked
          ? 'border-2 border-[var(--brand-600)] bg-[var(--brand-50)] px-[15px]'
          : 'border-[var(--border-default)] bg-[var(--bg-surface)] hover:border-[var(--border-strong)]',
        className,
      )}
    >
      <input
        type={type}
        name={name}
        value={value}
        checked={checked}
        onChange={() => onChange(value)}
        className="sr-only"
      />

      {icon && (
        <span className="shrink-0 text-[var(--fg-tertiary)]" aria-hidden="true">
          {icon}
        </span>
      )}

      <span className="flex min-w-0 flex-1 flex-col">
        <span
          className={cn(
            'text-[15px] font-medium',
            checked ? 'text-[var(--brand-800)]' : 'text-[var(--fg-primary)]',
          )}
        >
          {label}
        </span>
        {hint && <span className="text-[12.5px] text-[var(--fg-tertiary)]">{hint}</span>}
      </span>

      <span
        className={cn(
          'flex size-5 shrink-0 items-center justify-center rounded-[var(--radius-full)] border',
          checked
            ? 'border-[var(--brand-600)] bg-[var(--brand-600)] text-[var(--fg-on-brand)]'
            : 'border-[var(--border-strong)]',
        )}
        aria-hidden="true"
      >
        {checked && (
          <svg className="size-3" viewBox="0 0 16 16" fill="none">
            <path
              d="M3.5 8.5l3 3 6-7"
              stroke="currentColor"
              strokeWidth="2.2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        )}
      </span>
    </label>
  );
}
