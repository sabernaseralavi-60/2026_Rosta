import { cn } from '@/lib/cn';
import { toPersianDigits } from '@/lib/format/digits';

/**
 * حلقهٔ درصد تطابق — PRD §10.6.
 *
 * «رنگ بر اساس بازه: ≥۸۰ سبز، ۶۰-۸۰ زعفرانی، <۶۰ خاکستری.»
 *
 * عدد **همیشه** داخل حلقه نوشته می‌شود؛ رنگ به‌تنهایی اطلاعات نمی‌رساند
 * (§10.2) و کاربر کوررنگ هم باید بداند ۸۲٪ است یا ۴۲٪.
 */

const STRONG_MATCH = 80;
const MODERATE_MATCH = 60;

const RADIUS = 20;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

export interface MatchRingProps {
  /** ۰ تا ۱۰۰. */
  score: number;
  size?: 'sm' | 'md';
  className?: string;
}

function toneFor(score: number): { stroke: string; text: string; label: string } {
  if (score >= STRONG_MATCH) {
    return {
      stroke: 'var(--success-600)',
      text: 'text-[var(--success-600)]',
      label: 'تطابق بالا',
    };
  }
  if (score >= MODERATE_MATCH) {
    return {
      stroke: 'var(--accent-600)',
      text: 'text-[var(--accent-700)]',
      label: 'تطابق متوسط',
    };
  }
  return {
    stroke: 'var(--neutral-400)',
    text: 'text-[var(--fg-tertiary)]',
    label: 'تطابق کم',
  };
}

export function MatchRing({ score, size = 'md', className }: MatchRingProps) {
  const clamped = Math.max(0, Math.min(100, score));
  const rounded = Math.round(clamped);
  const tone = toneFor(clamped);
  const dimension = size === 'sm' ? 'size-12' : 'size-14';

  return (
    <div
      className={cn('relative shrink-0', dimension, className)}
      role="img"
      aria-label={`${tone.label}: ${toPersianDigits(rounded)} درصد`}
    >
      <svg viewBox="0 0 48 48" className="size-full -rotate-90" aria-hidden="true">
        <circle
          cx="24"
          cy="24"
          r={RADIUS}
          fill="none"
          stroke="var(--border-subtle)"
          strokeWidth="4"
        />
        <circle
          cx="24"
          cy="24"
          r={RADIUS}
          fill="none"
          stroke={tone.stroke}
          strokeWidth="4"
          strokeLinecap="round"
          strokeDasharray={CIRCUMFERENCE}
          strokeDashoffset={CIRCUMFERENCE * (1 - clamped / 100)}
          // §10.7 — حرکت فقط جایی که معنا دارد؛ اینجا پرشدن حلقه.
          className="transition-[stroke-dashoffset] duration-[var(--dur-slow)] ease-[var(--ease-out)] motion-reduce:transition-none"
        />
      </svg>
      <span
        className={cn(
          'absolute inset-0 flex items-center justify-center font-semibold tabular-nums',
          size === 'sm' ? 'text-[12.5px]' : 'text-[14px]',
          tone.text,
        )}
        aria-hidden="true"
      >
        {toPersianDigits(rounded)}٪
      </span>
    </div>
  );
}
