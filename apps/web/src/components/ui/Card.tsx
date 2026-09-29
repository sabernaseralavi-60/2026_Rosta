import type { HTMLAttributes, ReactNode } from 'react';

import { cn } from '@/lib/cn';

/**
 * کارت — PRD §10.6.
 *
 * «سلسله‌مراتب با فضا، نه خط» (§10.1): کارت پیش‌فرض تخت است و فقط یک
 * مرز ظریف دارد. سایه فقط وقتی که واقعاً لایه‌بندی لازم است.
 */

export type CardVariant = 'flat' | 'raised' | 'interactive';

const VARIANTS: Record<CardVariant, string> = {
  flat: 'border border-[var(--border-subtle)]',
  raised: 'border border-[var(--border-subtle)] shadow-[var(--shadow-md)]',
  interactive:
    'border border-[var(--border-subtle)] cursor-pointer ' +
    'transition-[box-shadow,border-color] duration-[var(--dur-fast)] ease-[var(--ease-out)] ' +
    'hover:border-[var(--border-default)] hover:shadow-[var(--shadow-md)] ' +
    'focus-within:border-[var(--border-focus)]',
};

export interface CardProps extends HTMLAttributes<HTMLDivElement> {
  variant?: CardVariant;
  children?: ReactNode;
}

export function Card({ variant = 'flat', className, children, ...props }: CardProps) {
  return (
    <div
      className={cn(
        // `relative`: لنگر موقعیت‌دهی برای پوشش «کل کارت کلیک‌پذیر» (ProjectCard) —
        // بدون آن، `after:absolute after:inset-0` به‌جای خود کارت کل صفحه را
        // می‌گیرد و کلیک روی هر چیز دیگری (مثلاً دکمهٔ منو در هدر) را می‌رباید.
        'relative rounded-[var(--radius-lg)] bg-[var(--bg-surface)]',
        // §10.4 — فاصلهٔ درون کارت ۲۰px
        'p-5',
        VARIANTS[variant],
        className,
      )}
      {...props}
    >
      {children}
    </div>
  );
}

export function CardHeader({ className, children, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cn('mb-4 flex flex-col gap-1', className)} {...props}>
      {children}
    </div>
  );
}

export interface CardTitleProps extends HTMLAttributes<HTMLHeadingElement> {
  /**
   * سطح عنوان. پیش‌فرض `h3` برای کارت زیر یک بخش `h2`؛ کارتی که مستقیم زیر
   * `h1` صفحه است باید `h2` باشد، وگرنه ترتیب عنوان‌ها می‌پرد؛ کارتی که خودش
   * تمام صفحه است (مثلاً «دسترسی نداری») `h1` (M7-14).
   */
  as?: 'h1' | 'h2' | 'h3' | 'h4';
}

export function CardTitle({ as: Tag = 'h3', className, children, ...props }: CardTitleProps) {
  return (
    <Tag className={cn('text-[18px] font-semibold text-[var(--fg-primary)]', className)} {...props}>
      {children}
    </Tag>
  );
}

export function CardDescription({
  className,
  children,
  ...props
}: HTMLAttributes<HTMLParagraphElement>) {
  return (
    <p className={cn('text-[13.5px] text-[var(--fg-secondary)]', className)} {...props}>
      {children}
    </p>
  );
}
