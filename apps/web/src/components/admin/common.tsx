'use client';

import type { ReactNode } from 'react';

import { Card } from '@/components/ui/Card';
import { ApiError, NetworkError } from '@/lib/api/client';
import { cn } from '@/lib/cn';
import { toPersianDigits } from '@/lib/format/digits';

/** پیام خطای فارسیِ آمادهٔ نمایش — §3.8 «پیام قابل فهم + کد برای پشتیبانی». */
export function errorText(cause: unknown, fallback = 'درخواست انجام نشد. کمی بعد دوباره تلاش کن.') {
  if (cause instanceof ApiError) {
    return cause.traceId
      ? `${cause.message} (کد پیگیری: ${cause.traceId.slice(0, 8)})`
      : cause.message;
  }
  if (cause instanceof NetworkError) return cause.message;
  return fallback;
}

export function ErrorLine({ children }: { children: ReactNode }) {
  return (
    <p role="alert" className="text-[13.5px] text-[var(--fg-danger)]">
      {children}
    </p>
  );
}

export function StatTile({
  label,
  value,
  hint,
  tone = 'neutral',
}: {
  label: string;
  value: number;
  hint?: string;
  tone?: 'neutral' | 'warning' | 'danger';
}) {
  return (
    <Card className="flex flex-col gap-1 p-4">
      <span className="text-[12.5px] text-[var(--fg-secondary)]">{label}</span>
      <span
        className={cn(
          'text-[26px] font-bold tabular-nums leading-tight',
          tone === 'warning' && value > 0 && 'text-[var(--fg-warning)]',
          tone === 'danger' && value > 0 && 'text-[var(--fg-danger)]',
        )}
      >
        {toPersianDigits(value.toLocaleString('en-US').replace(/,/g, '٬'))}
      </span>
      {hint && <span className="text-[12px] text-[var(--fg-tertiary)]">{hint}</span>}
    </Card>
  );
}

/** «قبل ← بعد» یک ردیف لاگ حسابرسی، خوانا برای انسان. */
export function ChangeSummary({
  before,
  after,
}: {
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
}) {
  const keys = Array.from(new Set([...Object.keys(before ?? {}), ...Object.keys(after ?? {})]));
  if (keys.length === 0) return <span className="text-[var(--fg-tertiary)]">—</span>;
  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-2 text-[12.5px]" dir="auto">
      {keys.map((key) => {
        const was = before?.[key];
        const now = after?.[key];
        return (
          <div key={key} className="contents">
            <dt className="font-mono text-[var(--fg-tertiary)]" dir="ltr">
              {key}
            </dt>
            <dd className="break-words">
              {before && key in before && (
                <span className="text-[var(--fg-tertiary)] line-through">{show(was)}</span>
              )}
              {before && key in before && after && key in after && ' ← '}
              {after && key in after && <span>{show(now)}</span>}
            </dd>
          </div>
        );
      })}
    </dl>
  );
}

function show(value: unknown): string {
  if (value === null || value === undefined) return 'خالی';
  if (typeof value === 'boolean') return value ? 'بله' : 'خیر';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

export const SELECT_CLASS =
  'h-11 rounded-[var(--radius-md)] border border-[var(--border-default)] bg-[var(--bg-surface)] px-3 text-[14px]';

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="flex flex-col gap-1.5 text-[13.5px] font-medium">
      {label}
      {children}
    </label>
  );
}
