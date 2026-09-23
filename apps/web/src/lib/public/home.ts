/**
 * منطق صفحهٔ اصلی — §10.10. جدا از فایل صفحه تا آزمون‌پذیر باشد (فایل
 * صفحهٔ Next.js فقط خروجی‌های مجاز خودش را می‌پذیرد).
 */

import type { PublicStats } from '@/lib/api/public';
import { formatCompact, formatNumber } from '@/lib/format/digits';

export interface Tile {
  value: string;
  label: string;
}

/**
 * «اگر آمار کم است، به‌جایش "۴ درس فعال" نشان بده، نه "۰ مقاله"» (§10.10).
 * ترتیب، ترتیب اهمیت است؛ صفرها کنار می‌روند و چهار تای اول می‌مانند.
 */
export function statTiles(stats: PublicStats): Tile[] {
  const candidates: [number, (n: number) => string, string][] = [
    [stats.students, formatNumber, 'دانشجو'],
    [stats.active_projects, formatNumber, 'پروژهٔ فعال'],
    [stats.research_outputs, formatNumber, 'مقالهٔ راستی‌آزمایی‌شده'],
    [stats.verified_revenue_rial, formatCompact, 'ریال فروش تأییدشده'],
    [stats.completed_projects, formatNumber, 'پروژهٔ تکمیل‌شده'],
    [stats.completed_milestones, formatNumber, 'مرحلهٔ تأییدشده'],
    [stats.certificates, formatNumber, 'گواهی صادرشده'],
    [stats.active_courses, formatNumber, 'درس فعال'],
  ];
  return candidates
    .filter(([value]) => value > 0)
    .slice(0, 4)
    .map(([value, format, label]) => ({ value: format(value), label }));
}
