import { GROWTH_STAGES, type VentureStage } from '@/lib/api/ventures';
import { cn } from '@/lib/cn';

/**
 * مسیر بلوغ کسب‌وکار — §7.7: ایده ← اعتبارسنجی ← محصول کمینه ← اولین درآمد ← رشد.
 *
 * متوقف و بسته‌شده روی مسیر نیستند؛ برای متوقف، مرحلهٔ پیش از توقف
 * (`pausedFrom`) پررنگ می‌ماند تا معلوم باشد به کجا برمی‌گردد.
 */

const LABELS: Record<string, string> = {
  IDEA: 'ایده',
  VALIDATION: 'اعتبارسنجی',
  MVP: 'محصول کمینه',
  FIRST_REVENUE: 'اولین درآمد',
  GROWTH: 'رشد',
};

export function StageTrack({
  stage,
  pausedFrom = null,
  compact = false,
}: {
  stage: VentureStage;
  pausedFrom?: VentureStage | null;
  compact?: boolean;
}) {
  const effective = stage === 'PAUSED' ? pausedFrom : stage;
  const current = effective ? GROWTH_STAGES.indexOf(effective) : -1;
  const muted = stage === 'PAUSED' || stage === 'CLOSED';

  return (
    <ol
      aria-label="مسیر بلوغ کسب‌وکار"
      className={cn('flex items-center gap-1', compact ? 'text-[11px]' : 'text-[12.5px]')}
    >
      {GROWTH_STAGES.map((item, index) => {
        const done = index < current;
        const active = index === current;
        return (
          <li
            key={item}
            aria-current={active ? 'step' : undefined}
            className="flex flex-1 flex-col items-center gap-1"
          >
            <span
              className={cn(
                'h-1.5 w-full rounded-[var(--radius-full)]',
                done || active
                  ? muted
                    ? 'bg-[var(--fg-tertiary)]'
                    : 'bg-[var(--accent-500)]'
                  : 'bg-[var(--bg-sunken)]',
              )}
            />
            {!compact && (
              <span
                className={cn(
                  'text-center',
                  active ? 'font-semibold text-[var(--fg-primary)]' : 'text-[var(--fg-tertiary)]',
                )}
              >
                {LABELS[item]}
              </span>
            )}
          </li>
        );
      })}
    </ol>
  );
}
