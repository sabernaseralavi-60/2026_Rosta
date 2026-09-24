'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useState } from 'react';

import { errorText, ErrorLine } from '@/components/admin/common';
import { SectionHeader } from '@/components/teach/common';
import { useOffering } from '@/components/teach/OfferingFrame';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { EmptyState } from '@/components/ui/EmptyState';
import type { WeekSummary } from '@/lib/api/courses';
import { publishWeek, saveWeek } from '@/lib/api/teach';
import { formatDateTime } from '@/lib/format/date';
import { toPersianDigits } from '@/lib/format/digits';

const MAX_WEEK = 17;

/**
 * `/teach/offerings/[id]` — هفته‌ها (§3.5 «مدیریت ارائه»، FR-EDU-02).
 *
 * هفتهٔ پیش‌نویس فقط برای کادر آموزشی دیده می‌شود. انتشار فوری یا
 * زمان‌بندی‌شده از ویرایشگر هفته است؛ اینجا فقط «همین حالا منتشر کن».
 */
export function WeeksView() {
  const { offering, token, reload } = useOffering();
  const router = useRouter();
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const weeks = [...offering.weeks].sort((a, b) => a.week_number - b.week_number);
  const taken = new Set(weeks.map((w) => w.week_number));
  const next = Array.from({ length: MAX_WEEK }, (_, i) => i + 1).find((n) => !taken.has(n));
  const can = offering.permissions;

  async function createNext() {
    if (!next) return;
    setBusy('new');
    setError(null);
    try {
      await saveWeek(
        offering.id,
        { week_number: next, title_fa: `هفتهٔ ${toPersianDigits(next)}` },
        token,
      );
      router.push(`/teach/offerings/${offering.id}/weeks/${next}`);
    } catch (cause) {
      setError(errorText(cause));
      setBusy(null);
    }
  }

  async function publishNow(week: WeekSummary) {
    setBusy(week.id);
    setError(null);
    try {
      await publishWeek(week.id, null, token);
      await reload();
    } catch (cause) {
      setError(errorText(cause));
    } finally {
      setBusy(null);
    }
  }

  return (
    <section className="flex flex-col gap-4">
      <SectionHeader
        title="هفته‌ها"
        description="هفتهٔ پیش‌نویس را دانشجو نمی‌بیند. با انتشار هر هفته، به دانشجویان اعلان می‌رود."
        action={
          can.edit_weeks && next ? (
            <Button onClick={createNext} loading={busy === 'new'}>
              ساخت هفتهٔ {toPersianDigits(next)}
            </Button>
          ) : undefined
        }
      />
      {error && <ErrorLine>{error}</ErrorLine>}
      {weeks.length === 0 ? (
        <EmptyState
          title="هنوز هفته‌ای ساخته نشده"
          description={
            can.manage
              ? 'هفتهٔ اول را بساز، یا از «تنظیمات» محتوای ارائهٔ نیم‌سال قبل را کپی کن.'
              : 'استاد درس هنوز هفته‌ای نساخته است.'
          }
        />
      ) : (
        <ol className="flex flex-col divide-y divide-[var(--border-subtle)] rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-surface)]">
          {weeks.map((week) => (
            <li
              key={week.id}
              className="flex flex-wrap items-center justify-between gap-3 px-4 py-3"
            >
              <div className="flex min-w-0 flex-col gap-0.5">
                <span className="flex flex-wrap items-center gap-2">
                  <span className="text-[13px] text-[var(--fg-tertiary)]">
                    هفتهٔ {toPersianDigits(week.week_number)}
                  </span>
                  <span className="font-medium">{week.title_fa}</span>
                  <WeekStatus week={week} />
                </span>
                <span className="text-[12.5px] text-[var(--fg-tertiary)]">
                  {toPersianDigits(week.resource_count)} منبع ·{' '}
                  {toPersianDigits(week.material_count)} محتوای کتابخانه
                </span>
              </div>
              <div className="flex items-center gap-2">
                {can.publish_weeks && week.status === 'DRAFT' && (
                  <Button
                    size="sm"
                    variant="secondary"
                    loading={busy === week.id}
                    onClick={() => publishNow(week)}
                  >
                    انتشار الان
                  </Button>
                )}
                <Button asChild size="sm" variant="ghost">
                  <Link href={`/teach/offerings/${offering.id}/weeks/${week.week_number}`}>
                    {can.edit_weeks ? 'ویرایش' : 'مشاهده'}
                  </Link>
                </Button>
              </div>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

function WeekStatus({ week }: { week: WeekSummary }) {
  if (week.status === 'PUBLISHED') return <Badge tone="success">منتشرشده</Badge>;
  if (week.status === 'ARCHIVED') return <Badge tone="neutral">بایگانی</Badge>;
  if (week.publish_at && new Date(week.publish_at) > new Date()) {
    return <Badge tone="info">انتشار: {formatDateTime(week.publish_at)}</Badge>;
  }
  return <Badge tone="neutral">پیش‌نویس</Badge>;
}
