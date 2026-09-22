import type { HTMLAttributes } from 'react';

import { cn } from '@/lib/cn';

/**
 * اسکلت بارگذاری — PRD §10.6، §10.1.
 *
 * «هم‌شکل محتوای نهایی، نه مستطیل خاکستری عمومی.» و «صداقت بصری»:
 * حالت بارگذاری باید شبیه محتوای نهایی باشد، بدون توهم سرعت.
 *
 * به همین دلیل `Skeleton` خام صادر نمی‌شود؛ شکل‌های آماده صادر می‌شوند
 * که هرکدام قالب یک جزء واقعی را تقلید می‌کنند.
 */

interface SkeletonProps extends HTMLAttributes<HTMLDivElement> {
  /** توضیح آنچه در حال بارگذاری است — برای صفحه‌خوان. */
  label?: string;
}

function Bar({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        'rounded-[var(--radius-sm)] bg-[var(--bg-sunken)]',
        'motion-safe:animate-[silp-pulse_1500ms_var(--ease-in-out)_infinite]',
        className,
      )}
      {...props}
    />
  );
}

/** اسکلت یک بند متن. */
export function SkeletonText({ label = 'در حال بارگذاری', className, ...props }: SkeletonProps) {
  return (
    <div
      className={cn('flex flex-col gap-2', className)}
      role="status"
      aria-live="polite"
      {...props}
    >
      <span className="sr-only">{label}</span>
      <Bar className="h-4 w-full" />
      <Bar className="h-4 w-[92%]" />
      <Bar className="h-4 w-[68%]" />
    </div>
  );
}

/** اسکلت یک کارت — با همان ابعاد و فاصله‌های `Card`. */
export function SkeletonCard({ label = 'در حال بارگذاری', className, ...props }: SkeletonProps) {
  return (
    <div
      className={cn(
        'rounded-[var(--radius-lg)] border border-[var(--border-subtle)]',
        'bg-[var(--bg-surface)] p-5',
        className,
      )}
      role="status"
      aria-live="polite"
      {...props}
    >
      <span className="sr-only">{label}</span>
      <Bar className="mb-4 h-5 w-1/2" />
      <Bar className="mb-2 h-4 w-full" />
      <Bar className="mb-5 h-4 w-3/4" />
      <div className="flex gap-2">
        <Bar className="h-6 w-16 rounded-[var(--radius-full)]" />
        <Bar className="h-6 w-20 rounded-[var(--radius-full)]" />
      </div>
    </div>
  );
}

/** اسکلت یک ردیف فهرست، با آواتار. */
export function SkeletonRow({ label = 'در حال بارگذاری', className, ...props }: SkeletonProps) {
  return (
    <div
      className={cn('flex items-center gap-3', className)}
      role="status"
      aria-live="polite"
      {...props}
    >
      <span className="sr-only">{label}</span>
      <Bar className="size-10 rounded-[var(--radius-full)]" />
      <div className="flex flex-1 flex-col gap-2">
        <Bar className="h-4 w-1/3" />
        <Bar className="h-3 w-1/2" />
      </div>
    </div>
  );
}
