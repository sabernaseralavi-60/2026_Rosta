import type { ReactNode } from 'react';

import { cn } from '@/lib/cn';

/**
 * حالت خالی — PRD §10.6.
 *
 * «با تصویرسازی + اقدام. هرگز فقط متن.» یک صفحهٔ خالی که فقط می‌گوید
 * «موردی یافت نشد» کاربر را به بن‌بست می‌رساند؛ باید بگوید قدم بعدی چیست.
 *
 * به همین دلیل `title` و `action` هر دو در امضا هستند و تصویرسازی
 * پیش‌فرض دارد.
 */

export interface EmptyStateProps {
  title: string;
  description?: string;
  /** اقدام پیشنهادی — دکمه یا لینک. */
  action?: ReactNode;
  illustration?: ReactNode;
  className?: string;
}

export function EmptyState({
  title,
  description,
  action,
  illustration,
  className,
}: EmptyStateProps) {
  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center gap-4 rounded-[var(--radius-lg)]',
        'border border-dashed border-[var(--border-default)] bg-[var(--bg-surface)]',
        'px-6 py-12 text-center',
        className,
      )}
    >
      <div aria-hidden="true">{illustration ?? <DefaultIllustration />}</div>

      <div className="flex flex-col gap-1.5">
        {/* `h2`: حالت خالی جای محتوای اصلی زیر `h1` صفحه می‌نشیند؛ `h3` سطح
            عنوان را می‌پراند (M7-14). */}
        <h2 className="text-[18px] font-semibold text-[var(--fg-primary)]">{title}</h2>
        {description && (
          <p className="max-w-[46ch] text-[13.5px] text-[var(--fg-secondary)]">{description}</p>
        )}
      </div>

      {action && <div className="mt-1">{action}</div>}
    </div>
  );
}

/**
 * تصویرسازی پیش‌فرض: یک میز کار خالی.
 *
 * هویت بصری «کارگاه، نه کلاس درس» است (§10.1)، پس حتی حالت خالی هم
 * باید بوی کار بدهد، نه بوی خطا.
 */
function DefaultIllustration() {
  return (
    <svg
      width="96"
      height="72"
      viewBox="0 0 96 72"
      fill="none"
      className="text-[var(--border-default)]"
    >
      {/* سطح میز */}
      <path d="M10 50h76" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
      {/* پایه‌ها */}
      <path d="M20 50v12M76 50v12" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
      {/* دو ورق روی میز */}
      <rect x="30" y="22" width="26" height="28" rx="3" stroke="currentColor" strokeWidth="2.5" />
      <rect
        x="40"
        y="14"
        width="26"
        height="28"
        rx="3"
        stroke="currentColor"
        strokeWidth="2.5"
        className="text-[var(--brand-300)]"
      />
    </svg>
  );
}
