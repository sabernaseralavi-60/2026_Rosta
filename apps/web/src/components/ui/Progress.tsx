import { cn } from '@/lib/cn';
import { toPersianDigits } from '@/lib/format/digits';

/**
 * نوار پیشرفت — PRD §10.6.
 *
 * «با برچسب عددی، همیشه.» نوار بدون عدد فقط یک حس مبهم می‌دهد؛ کاربر
 * می‌خواهد بداند دو گام مانده یا چهار.
 */

export interface ProgressProps {
  value: number;
  max?: number;
  label?: string;
  /**
   * نام دسترس‌پذیر وقتی برچسب دیدنی بیرون از نوار است (مثلاً عنوان کارت).
   * نوار پیشرفت بی‌نام برای صفحه‌خوان فقط «نوار پیشرفت، صفر» است (M7-14).
   */
  ariaLabel?: string;
  /** متن سمت چپ — پیش‌فرض «‹value› از ‹max›». */
  valueText?: string;
  className?: string;
}

export function Progress({
  value,
  max = 100,
  label,
  ariaLabel,
  valueText,
  className,
}: ProgressProps) {
  const safeMax = Math.max(1, max);
  const clamped = Math.max(0, Math.min(safeMax, value));
  const percent = (clamped / safeMax) * 100;

  return (
    <div className={cn('flex flex-col gap-1.5', className)}>
      {(label || valueText) && (
        <div className="flex items-baseline justify-between gap-3 text-[13px]">
          {label && <span className="text-[var(--fg-secondary)]">{label}</span>}
          <span className="font-medium tabular-nums text-[var(--fg-primary)]">
            {valueText ?? `${toPersianDigits(clamped)} از ${toPersianDigits(safeMax)}`}
          </span>
        </div>
      )}
      <div
        role="progressbar"
        aria-valuenow={clamped}
        aria-valuemin={0}
        aria-valuemax={safeMax}
        aria-label={label ?? ariaLabel ?? 'پیشرفت'}
        aria-valuetext={valueText}
        className="h-2 w-full overflow-hidden rounded-[var(--radius-full)] bg-[var(--bg-sunken)]"
      >
        <div
          className="h-full rounded-[var(--radius-full)] bg-[var(--brand-600)] transition-[width] duration-[var(--dur-normal)] ease-[var(--ease-out)] motion-reduce:transition-none"
          style={{ width: `${percent}%` }}
        />
      </div>
    </div>
  );
}
