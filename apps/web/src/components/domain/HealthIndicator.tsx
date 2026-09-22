import { Badge } from '@/components/ui/Badge';
import type { Health } from '@/lib/api/points';

/**
 * وضعیت سلامت پروژه — §10.6 `HealthIndicator`، §7.4.
 *
 * رنگ وضعیت همیشه با آیکن و متن — «هرگز فقط رنگ» (§10.6 Badge). متن
 * فارسی از سرور می‌آید (`health_fa`) تا قاعدهٔ نام‌گذاری یک جا بماند.
 */

const TONE = { HEALTHY: 'success', AT_RISK: 'warning', STALLED: 'danger' } as const;
const ICON: Record<Health, string> = { HEALTHY: '●', AT_RISK: '▲', STALLED: '■' };

export function HealthIndicator({ health, label }: { health: Health; label: string }) {
  return (
    <Badge tone={TONE[health]} icon={ICON[health]}>
      {label}
    </Badge>
  );
}
