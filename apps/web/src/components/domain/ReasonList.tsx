import type { Reason } from '@/lib/api/projects';
import { cn } from '@/lib/cn';

/**
 * فهرست دلایل تطابق — PRD §10.6، §8.10.
 *
 * متن دلیل **از سرور** می‌آید و همان‌طور که هست نمایش داده می‌شود؛ منطق
 * توضیح در بک‌اند است تا وب و اپلیکیشن موبایل آینده دو روایت متفاوت از
 * یک عدد ندهند.
 *
 * آیکن ✓ و ⚠ کنار رنگ می‌نشیند، چون رنگ به‌تنهایی معنا نمی‌رساند (§10.2).
 */

export interface ReasonListProps {
  reasons: Reason[];
  className?: string;
}

export function ReasonList({ reasons, className }: ReasonListProps) {
  if (reasons.length === 0) return null;

  return (
    <ul className={cn('flex flex-col gap-1.5', className)}>
      {reasons.map((reason, index) => {
        const isWarning = reason.polarity === 'WARNING';
        return (
          <li
            key={`${reason.type}-${index}`}
            className="flex items-start gap-2 text-[13.5px] leading-[1.75]"
          >
            <span
              className={cn(
                'mt-[3px] shrink-0',
                isWarning ? 'text-[var(--warning-600)]' : 'text-[var(--success-600)]',
              )}
              aria-hidden="true"
            >
              {isWarning ? <WarningIcon /> : <CheckIcon />}
            </span>
            <span
              className={cn(
                isWarning ? 'text-[var(--fg-secondary)]' : 'text-[var(--fg-primary)]',
              )}
            >
              <span className="sr-only">{isWarning ? 'هشدار: ' : 'نقطهٔ قوت: '}</span>
              {reason.text}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

function CheckIcon() {
  return (
    <svg className="size-4" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <path
        d="M3.5 8.5l3 3 6-7"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function WarningIcon() {
  return (
    <svg className="size-4" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
      <path
        fillRule="evenodd"
        d="M8 1.5a.9.9 0 0 1 .78.45l6 10.4A.9.9 0 0 1 14 13.7H2a.9.9 0 0 1-.78-1.35l6-10.4A.9.9 0 0 1 8 1.5Zm0 3.6a.75.75 0 0 0-.75.75v3a.75.75 0 0 0 1.5 0v-3A.75.75 0 0 0 8 5.1Zm0 6.6a.85.85 0 1 0 0-1.7.85.85 0 0 0 0 1.7Z"
        clipRule="evenodd"
      />
    </svg>
  );
}
