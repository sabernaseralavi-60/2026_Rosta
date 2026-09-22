import { Progress } from '@/components/ui/Progress';
import type { Badge } from '@/lib/api/points';
import { cn } from '@/lib/cn';
import { formatDateLong } from '@/lib/format/date';
import { toPersianDigits } from '@/lib/format/digits';

/**
 * کاشی نشان — §9.5 «کاربر نشان‌های قفل‌شده را با شرایطشان می‌بیند».
 *
 * نشان قفل پنهان نمی‌شود: شرطش و «۳ از ۵» پیشرفتش دیده می‌شود، چون این
 * خودش راهنمای مسیر است. رنگ تنها حامل «کسب‌شده» نیست — متن وضعیت هم
 * هست (§10.6 Badge).
 *
 * ستون `badges.icon` نام آیکن lucide است. کتابخانهٔ آیکن هنوز وابستگی
 * پروژه نیست (بودجهٔ باندل §10.11)، پس نگاشت به نماد یونی‌کد اینجاست؛
 * افزودن lucide بعداً فقط همین نگاشت را عوض می‌کند.
 */

const ICONS: Record<string, string> = {
  footprints: '👣',
  zap: '⚡',
  target: '🎯',
  brain: '🧠',
  'calendar-check': '📅',
  'package-check': '📦',
  hammer: '🔨',
  'building-2': '🏛️',
  'badge-dollar-sign': '💰',
  'cloud-rain': '🌧️',
  microscope: '🔬',
  'file-text': '📄',
  award: '🏆',
  lightbulb: '💡',
  telescope: '🔭',
  'hand-helping': '🤝',
  compass: '🧭',
  users: '👥',
  shapes: '🧩',
  map: '🗺️',
  moon: '🌙',
};

const TIER_RING: Record<Badge['tier'], string> = {
  BRONZE: 'ring-[oklch(62%_0.09_55)]',
  SILVER: 'ring-[var(--neutral-400)]',
  GOLD: 'ring-[var(--accent-400)]',
  PLATINUM: 'ring-[var(--brand-400)]',
};

export function BadgeIcon({
  icon,
  earned,
  tier,
  size = 'md',
}: {
  icon: string;
  earned: boolean;
  tier?: Badge['tier'];
  size?: 'md' | 'lg';
}) {
  return (
    <span
      aria-hidden="true"
      className={cn(
        'flex shrink-0 items-center justify-center rounded-[var(--radius-full)] ring-2',
        size === 'lg' ? 'size-24 text-[44px]' : 'size-12 text-[22px]',
        earned ? 'bg-[var(--accent-50)]' : 'bg-[var(--bg-sunken)] grayscale opacity-60',
        tier ? TIER_RING[tier] : 'ring-[var(--accent-300)]',
      )}
    >
      {ICONS[icon] ?? '🏅'}
    </span>
  );
}

export function BadgeTile({ badge }: { badge: Badge }) {
  const current = Number(badge.progress_current);
  const target = Number(badge.progress_target);
  return (
    <article
      className={cn(
        'flex h-full gap-3 rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-4',
        !badge.earned && 'bg-[var(--bg-canvas)]',
      )}
    >
      <BadgeIcon icon={badge.icon} earned={badge.earned} tier={badge.tier} />
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <div className="flex flex-wrap items-baseline gap-x-2">
          <h3 className="text-[15px] font-semibold">{badge.title_fa}</h3>
          <span className="text-[12px] text-[var(--fg-tertiary)]">{badge.tier_fa}</span>
        </div>
        <p className="text-[13px] text-[var(--fg-secondary)]">{badge.description}</p>
        {badge.earned ? (
          <p className="text-[12.5px] font-medium text-[var(--success-600)]">
            کسب‌شده{badge.awarded_at && ` — ${formatDateLong(badge.awarded_at)}`}
          </p>
        ) : (
          target > 1 && (
            <Progress
              value={current}
              max={target}
              label="پیشرفت"
              valueText={`${toPersianDigits(current)} از ${toPersianDigits(target)}`}
              className="mt-1"
            />
          )
        )}
      </div>
    </article>
  );
}
