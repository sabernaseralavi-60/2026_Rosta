import { Slot } from '@radix-ui/react-slot';
import type { ButtonHTMLAttributes, ReactNode } from 'react';
import { forwardRef } from 'react';

import { cn } from '@/lib/cn';

/**
 * دکمه — PRD §10.6.
 *
 * حالت `loading`: اسپینر **جایگزین متن** می‌شود و عرض دکمه ثابت می‌ماند.
 * اگر دکمه هنگام بارگذاری بپرد، کاربر جای کلیک بعدی‌اش را گم می‌کند.
 */

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger';
export type ButtonSize = 'sm' | 'md' | 'lg';

const VARIANTS: Record<ButtonVariant, string> = {
  primary:
    'bg-[var(--brand-600)] text-[var(--fg-on-brand)] hover:bg-[var(--brand-700)] ' +
    'active:bg-[var(--brand-800)]',
  secondary:
    'bg-[var(--bg-surface)] text-[var(--fg-primary)] border border-[var(--border-default)] ' +
    'hover:bg-[var(--bg-sunken)]',
  ghost: 'bg-transparent text-[var(--fg-secondary)] hover:bg-[var(--bg-sunken)] hover:text-[var(--fg-primary)]',
  danger:
    'bg-[var(--danger-600)] text-[var(--neutral-0)] hover:bg-[var(--danger-500)]',
};

const SIZES: Record<ButtonSize, string> = {
  sm: 'h-9 px-3 text-[13.5px] rounded-[var(--radius-sm)] gap-1.5',
  md: 'h-11 px-5 text-[15px] rounded-[var(--radius-md)] gap-2',
  lg: 'h-13 px-7 text-[17px] rounded-[var(--radius-md)] gap-2.5',
};

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  /** متنی که هنگام بارگذاری به صفحه‌خوان اعلام می‌شود. */
  loadingLabel?: string;
  fullWidth?: boolean;
  asChild?: boolean;
  children?: ReactNode;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  {
    variant = 'primary',
    size = 'md',
    loading = false,
    loadingLabel = 'در حال انجام…',
    fullWidth = false,
    asChild = false,
    className,
    disabled,
    children,
    ...props
  },
  ref,
) {
  const Component = asChild ? Slot : 'button';

  return (
    <Component
      ref={ref}
      // دکمه هنگام بارگذاری غیرفعال است تا ارسال دوباره رخ ندهد.
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={cn(
        'relative inline-flex items-center justify-center font-medium',
        'transition-colors duration-[var(--dur-instant)] ease-[var(--ease-out)]',
        'disabled:cursor-not-allowed disabled:opacity-55',
        VARIANTS[variant],
        SIZES[size],
        fullWidth && 'w-full',
        className,
      )}
      {...props}
    >
      {loading ? (
        <>
          {/* متن نامرئی می‌ماند تا عرض دکمه تکان نخورد. */}
          <span className="invisible" aria-hidden="true">
            {children}
          </span>
          <span className="absolute inset-0 flex items-center justify-center">
            <Spinner />
            <span className="sr-only">{loadingLabel}</span>
          </span>
        </>
      ) : (
        children
      )}
    </Component>
  );
});

function Spinner() {
  return (
    <svg
      className="size-5 animate-spin"
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
    >
      <circle
        cx="12"
        cy="12"
        r="9"
        stroke="currentColor"
        strokeWidth="2.5"
        opacity="0.25"
      />
      <path
        d="M21 12a9 9 0 0 0-9-9"
        stroke="currentColor"
        strokeWidth="2.5"
        strokeLinecap="round"
      />
    </svg>
  );
}
