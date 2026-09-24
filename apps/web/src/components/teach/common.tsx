'use client';

import type { ReactNode } from 'react';

import { Badge, type BadgeTone } from '@/components/ui/Badge';
import { OFFERING_STATUS_LABELS, type OfferingStatus, type QuizStatus } from '@/lib/api/teach';
import { formatDateTime } from '@/lib/format/date';
import { toPersianDigits } from '@/lib/format/digits';

/** بخش‌های مشترک ناحیهٔ استاد — §3.5، ADR-0019. */

const OFFERING_TONES: Record<OfferingStatus, BadgeTone> = {
  DRAFT: 'neutral',
  OPEN: 'success',
  IN_PROGRESS: 'brand',
  CLOSED: 'info',
  ARCHIVED: 'neutral',
};

export function OfferingStatusBadge({ status }: { status: OfferingStatus }) {
  return <Badge tone={OFFERING_TONES[status]}>{OFFERING_STATUS_LABELS[status]}</Badge>;
}

const QUIZ_TONES: Record<QuizStatus, BadgeTone> = {
  DRAFT: 'neutral',
  PUBLISHED: 'success',
  CLOSED: 'info',
};

export function QuizStatusBadge({ status, label }: { status: QuizStatus; label: string }) {
  return <Badge tone={QUIZ_TONES[status]}>{label}</Badge>;
}

/** عدد اعشاری سرور («17.50») به فارسی خوانا («۱۷٫۵»). */
export function fa(value: string | number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || value === '') return '—';
  const number = typeof value === 'number' ? value : Number(value);
  if (Number.isNaN(number)) return '—';
  const rounded = Number(number.toFixed(digits));
  return toPersianDigits(String(rounded)).replace('.', '٫');
}

/** ISO ← مقدار `datetime-local` (به وقت مرورگر، که برای استاد همان تهران است). */
export function fromLocalInput(value: string): string {
  return new Date(value).toISOString();
}

/** مقدار `datetime-local` ← ISO. */
export function toLocalInput(iso: string | null | undefined): string {
  if (!iso) return '';
  const date = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(
    date.getHours(),
  )}:${pad(date.getMinutes())}`;
}

/** امروز به شکل `YYYY-MM-DD` به وقت مرورگر — برای `input[type=date]`. */
export function todayInput(): string {
  return toLocalInput(new Date().toISOString()).slice(0, 10);
}

export const INPUT_CLASS =
  'h-11 w-full rounded-[var(--radius-md)] border border-[var(--border-default)] bg-[var(--bg-surface)] px-3 text-[14px]';

/**
 * ورودی تاریخ و ساعت با پیش‌نمایش شمسی — ورودی بومی مرورگر میلادی است،
 * پس تاریخ خوانا برای استاد زیرش می‌آید.
 */
export function DateTimeField({
  label,
  value,
  onChange,
  hint,
  required,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  hint?: string;
  required?: boolean;
}) {
  return (
    <label className="flex flex-col gap-1.5 text-[13.5px] font-medium">
      {label}
      <input
        type="datetime-local"
        className={INPUT_CLASS}
        value={value}
        required={required}
        onChange={(event) => onChange(event.target.value)}
      />
      <span className="text-[12px] font-normal text-[var(--fg-tertiary)]">
        {value ? formatDateTime(fromLocalInput(value)) : (hint ?? 'تاریخ را انتخاب کن')}
      </span>
    </label>
  );
}

/** یک CSV با BOM تا Excel فارسی را درست باز کند — §3.5 «خروجی Excel». */
export function downloadCsv(filename: string, rows: (string | number | null)[][]): void {
  const escape = (cell: string | number | null) => {
    const text = cell === null ? '' : String(cell);
    return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
  };
  const body = rows.map((row) => row.map(escape).join(',')).join('\r\n');
  const blob = new Blob([String.fromCharCode(0xfeff) + body], {
    type: 'text/csv;charset=utf-8',
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

export function SectionHeader({
  title,
  description,
  action,
}: {
  title: string;
  description?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-3">
      <div className="flex flex-col gap-1">
        <h2 className="text-[18px]">{title}</h2>
        {description && (
          <p className="max-w-[70ch] text-[13.5px] text-[var(--fg-secondary)]">{description}</p>
        )}
      </div>
      {action}
    </div>
  );
}
