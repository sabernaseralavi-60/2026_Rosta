import type { HTMLAttributes, ReactNode } from 'react';

import { cn } from '@/lib/cn';

/**
 * نشان — PRD §10.6، §10.2.
 *
 * «همیشه با آیکن یا متن، نه فقط رنگ.» کاربر رنگ‌کور باید بتواند وضعیت
 * را بخواند — به همین دلیل `children` اجباری است و رنگ تنها سیگنال نیست.
 */

export type BadgeTone =
  | 'neutral'
  | 'brand'
  | 'accent'
  | 'success'
  | 'warning'
  | 'danger'
  | 'info'
  | 'research';

const TONES: Record<BadgeTone, string> = {
  neutral: 'bg-[var(--bg-sunken)] text-[var(--fg-secondary)]',
  brand: 'bg-[var(--brand-50)] text-[var(--brand-700)]',
  accent: 'bg-[var(--accent-50)] text-[var(--accent-700)]',
  success: 'bg-[color-mix(in_oklch,var(--success-500)_14%,transparent)] text-[var(--success-600)]',
  warning: 'bg-[color-mix(in_oklch,var(--warning-500)_18%,transparent)] text-[var(--warning-600)]',
  danger: 'bg-[color-mix(in_oklch,var(--danger-500)_12%,transparent)] text-[var(--danger-600)]',
  info: 'bg-[color-mix(in_oklch,var(--info-500)_12%,transparent)] text-[var(--info-500)]',
  research:
    'bg-[color-mix(in_oklch,var(--cat-research)_12%,transparent)] text-[var(--cat-research)]',
};

export interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  tone?: BadgeTone;
  icon?: ReactNode;
  /** متن نشان — اجباری است تا رنگ تنها حامل معنا نباشد. */
  children: ReactNode;
}

export function Badge({ tone = 'neutral', icon, className, children, ...props }: BadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-[var(--radius-full)]',
        'px-2.5 py-0.5 text-[12.5px] font-medium',
        TONES[tone],
        className,
      )}
      {...props}
    >
      {icon && (
        <span className="shrink-0" aria-hidden="true">
          {icon}
        </span>
      )}
      {children}
    </span>
  );
}
