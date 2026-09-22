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
        'rounded-[var(--radius-lg)] bg-[var(--bg-surface)]',
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

export function CardTitle({ className, children, ...props }: HTMLAttributes<HTMLHeadingElement>) {
  return (
    <h3 className={cn('text-[18px] font-semibold text-[var(--fg-primary)]', className)} {...props}>
      {children}
    </h3>
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
