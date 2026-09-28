'use client';

import Link from 'next/link';
import type { ReactNode } from 'react';

import { toPersianDigits } from '@/lib/format/digits';
import { cn } from '@/lib/cn';
import type { Submission } from '@/lib/api/intake';

/** تراشهٔ چندانتخابی — خدمات و انواع همکاری. */
export function ChipMulti<T extends string>({
  options,
  value,
  onChange,
  label,
}: {
  options: readonly { value: T; label: string }[];
  value: T[];
  onChange: (next: T[]) => void;
  label: string;
}) {
  return (
    <div role="group" aria-label={label} className="flex flex-wrap gap-2">
      {options.map((option) => {
        const on = value.includes(option.value);
        return (
          <button
            key={option.value}
            type="button"
            aria-pressed={on}
            onClick={() =>
              onChange(on ? value.filter((v) => v !== option.value) : [...value, option.value])
            }
            className={cn(
              'min-h-10 rounded-full border px-4 text-[14px] font-medium transition-colors',
              on
                ? 'border-[var(--brand-600)] bg-[var(--brand-600)] text-[var(--fg-on-brand)]'
                : 'border-[var(--border-default)] bg-[var(--bg-surface)] text-[var(--fg-secondary)] hover:border-[var(--border-strong)]',
            )}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}

/** نوار گام‌ها: «گام ۲ از ۴ — جزئیات». */
export function StepBar({ steps, current }: { steps: readonly string[]; current: number }) {
  return (
    <div className="flex flex-col gap-2" role="group" aria-label="پیشرفت فرم">
      <p className="text-[13px] text-[var(--fg-secondary)]">
        گام {toPersianDigits(current + 1)} از {toPersianDigits(steps.length)} — {steps[current]}
      </p>
      <div
        role="progressbar"
        aria-label="پیشرفت فرم"
        aria-valuetext={`گام ${toPersianDigits(current + 1)} از ${toPersianDigits(steps.length)}`}
        aria-valuemin={1}
        aria-valuemax={steps.length}
        aria-valuenow={current + 1}
        className="h-1.5 overflow-hidden rounded-full bg-[var(--bg-sunken)]"
      >
        <div
          className="h-full rounded-full bg-[var(--brand-600)] transition-[width] duration-[var(--dur-normal)]"
          style={{ width: `${((current + 1) / steps.length) * 100}%` }}
        />
      </div>
    </div>
  );
}

export function Field({
  label,
  hint,
  error,
  children,
}: {
  label: string;
  hint?: string;
  error?: string;
  children: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-[13.5px] font-medium">{label}</span>
      {hint && <span className="text-[12.5px] text-[var(--fg-tertiary)]">{hint}</span>}
      {children}
      {error && (
        <p role="alert" className="text-[13px] text-[var(--fg-danger)]">
          {error}
        </p>
      )}
    </div>
  );
}

export const SELECT_CLASS =
  'h-11 w-full rounded-[var(--radius-md)] border border-[var(--border-default)] bg-[var(--bg-surface)] px-3 text-[15px]';

/** فیلد تلهٔ ربات: برای آدم نامرئی و بیرون از ترتیب Tab. */
export function Honeypot({
  value,
  onChange,
}: {
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <div aria-hidden="true" className="absolute -start-[9999px] h-0 w-0 overflow-hidden">
      <label>
        وب‌سایت
        <input
          type="text"
          name="website"
          tabIndex={-1}
          autoComplete="off"
          value={value}
          onChange={(event) => onChange(event.target.value)}
        />
      </label>
    </div>
  );
}

export function SuccessCard({
  icon,
  title,
  result,
}: {
  icon: string;
  title: string;
  result: Submission;
}) {
  return (
    <div className="mx-auto flex max-w-[560px] flex-col items-center gap-4 rounded-[var(--radius-xl)] border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-10 text-center shadow-[var(--shadow-md)]">
      <div className="text-[40px]" aria-hidden="true">
        {icon}
      </div>
      <h2 className="text-[24px]">{title}</h2>
      <p className="text-[15px] leading-[2] text-[var(--fg-secondary)]">{result.message}</p>
      <p className="rounded-[var(--radius-md)] bg-[var(--bg-sunken)] px-5 py-3 text-[15px]">
        کد پیگیری: <b dir="ltr">{result.tracking_code}</b>
      </p>
      {result.person_code && result.account_linked ? (
        <p className="text-[14px] leading-[1.9] text-[var(--fg-secondary)]">
          این درخواست به حساب شما با کد شخصی <b dir="ltr">{result.person_code}</b> وصل شد.
        </p>
      ) : result.person_code ? (
        <p className="text-[14px] leading-[1.9] text-[var(--fg-secondary)]">
          کد شخصی شما: <b dir="ltr">{result.person_code}</b>. اگر بعداً با همین شماره (یا ایمیل)
          حساب رایگان بسازید، این کد و درخواست‌هایتان به حساب شما وصل می‌شود.
        </p>
      ) : (
        <p className="text-[14px] leading-[1.9] text-[var(--fg-secondary)]">
          برای پیگیری راحت‌تر می‌توانید حساب رایگان بسازید؛ اگر با همین شماره وارد شوید، درخواست به
          کد شخصی شما وصل می‌شود.
        </p>
      )}
      <div className="flex flex-wrap justify-center gap-3">
        <Link
          href="/login"
          className="inline-flex h-11 items-center rounded-[var(--radius-md)] bg-[var(--brand-600)] px-6 text-[15px] font-semibold text-[var(--fg-on-brand)] hover:bg-[var(--brand-700)]"
        >
          ورود و ثبت‌نام
        </Link>
        <Link
          href="/track"
          className="inline-flex h-11 items-center rounded-[var(--radius-md)] border border-[var(--border-default)] px-6 text-[15px] font-medium hover:bg-[var(--bg-sunken)]"
        >
          پیگیری با کد
        </Link>
        <Link
          href="/"
          className="inline-flex h-11 items-center rounded-[var(--radius-md)] border border-[var(--border-default)] px-6 text-[15px] font-medium hover:bg-[var(--bg-sunken)]"
        >
          بازگشت به خانه
        </Link>
      </div>
    </div>
  );
}
