'use client';

import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';

import { MaterialRow } from '@/components/domain/MaterialRow';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card, CardDescription, CardTitle } from '@/components/ui/Card';
import { SkeletonCard } from '@/components/ui/Skeleton';
import { ApiError, NetworkError } from '@/lib/api/client';
import {
  type CourseResource,
  type WeekDetail,
  fetchWeek,
  recordProgress,
  resourceDownloadUrl,
} from '@/lib/api/courses';
import { useSession } from '@/lib/auth/use-session';
import { cn } from '@/lib/cn';
import { toPersianDigits } from '@/lib/format/digits';

/**
 * `/courses/[offeringId]/weeks/[n]` — §3.4.
 *
 * دو دستهٔ محتوا، و تفکیکشان برای کاربر معنا دارد (ADR-0008):
 *
 * * **منابع این هفته** — مخصوص همین ارائه. باز کردنشان پیشرفت ثبت می‌کند.
 * * **از کتابخانهٔ درس** — کتاب و جزوهٔ ماندگار درس، با سطح دسترسی خودشان.
 */

const KIND_LABELS: Record<string, string> = {
  PDF: 'جزوه',
  VIDEO: 'ویدئو',
  LINK: 'پیوند',
  SLIDE: 'اسلاید',
  DATASET: 'مجموعه‌داده',
  CODE: 'کد',
  OTHER: 'سایر',
};

export function WeekView({ offeringId, weekNumber }: { offeringId: string; weekNumber: number }) {
  const { accessToken, loading: sessionLoading } = useSession();
  const [week, setWeek] = useState<WeekDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!accessToken) return;
    try {
      setWeek(await fetchWeek(offeringId, weekNumber, accessToken));
      setError(null);
    } catch (cause) {
      setError(messageFor(cause));
    }
  }, [accessToken, offeringId, weekNumber]);

  useEffect(() => {
    if (sessionLoading || !accessToken) return;
    void load();
  }, [accessToken, load, sessionLoading]);

  if (error) {
    return (
      <Card className="flex flex-col gap-4">
        <CardTitle>این هفته در دسترس نیست</CardTitle>
        <CardDescription>{error}</CardDescription>
        <div>
          <Button variant="secondary" asChild>
            <Link href={`/courses/${offeringId}`}>بازگشت به درس</Link>
          </Button>
        </div>
      </Card>
    );
  }

  if (!week) return <SkeletonCard />;

  const done = week.resources.filter((r) => r.progress?.status === 'COMPLETED').length;

  return (
    <div className="flex flex-col gap-8">
      <header className="flex flex-col gap-3">
        <Link
          href={`/courses/${offeringId}`}
          className="text-[13px] text-[var(--fg-secondary)] hover:text-[var(--fg-brand)]"
        >
          ← بازگشت به نمای درس
        </Link>
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-[26px] font-bold text-[var(--fg-primary)]">
            هفتهٔ {toPersianDigits(week.week_number)} — {week.title_fa}
          </h1>
          {week.status !== 'PUBLISHED' && <Badge tone="neutral">منتشر نشده</Badge>}
        </div>
        {week.description && (
          <p className="max-w-[70ch] text-[14px] leading-7 text-[var(--fg-secondary)]">
            {week.description}
          </p>
        )}
      </header>

      {week.objectives.length > 0 && (
        <section className="flex flex-col gap-2">
          <h2 className="text-[17px] font-semibold text-[var(--fg-primary)]">
            در پایان این هفته می‌توانید
          </h2>
          <ul className="flex list-disc flex-col gap-1.5 ps-5 text-[14px] leading-7 text-[var(--fg-secondary)]">
            {week.objectives.map((objective) => (
              <li key={objective}>{objective}</li>
            ))}
          </ul>
        </section>
      )}

      <section className="flex flex-col gap-3">
        <div className="flex items-baseline justify-between gap-3">
          <h2 className="text-[19px] font-semibold text-[var(--fg-primary)]">منابع این هفته</h2>
          {week.resources.length > 0 && (
            <span className="text-[13px] tabular-nums text-[var(--fg-tertiary)]">
              {toPersianDigits(done)} از {toPersianDigits(week.resources.length)} مطالعه شده
            </span>
          )}
        </div>

        {week.resources.length === 0 ? (
          <p className="rounded-[var(--radius-lg)] border border-dashed border-[var(--border-default)] px-4 py-6 text-center text-[13.5px] text-[var(--fg-secondary)]">
            برای این هفته منبع اختصاصی گذاشته نشده است.
          </p>
        ) : (
          <ul className="flex flex-col gap-3">
            {week.resources.map((resource) => (
              <ResourceRow
                key={resource.id}
                resource={resource}
                accessToken={accessToken}
                onChanged={load}
              />
            ))}
          </ul>
        )}
      </section>

      {week.materials.length > 0 && (
        <section className="flex flex-col gap-3">
          <div className="flex flex-col gap-1">
            <h2 className="text-[19px] font-semibold text-[var(--fg-primary)]">از کتابخانهٔ درس</h2>
            <p className="text-[13px] text-[var(--fg-secondary)]">
              کتاب‌ها و جزوه‌های ماندگار درس که این هفته به آن‌ها ارجاع می‌دهد.
            </p>
          </div>
          <ul className="flex flex-col gap-3">
            {week.materials.map((material) => (
              <MaterialRow key={material.id} material={material} accessToken={accessToken} />
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

/**
 * یک منبع هفته.
 *
 * ویدئو خودش با ۹۰٪ تمام می‌شود (FR-EDU-04) و همین‌جا فقط «باز کردم» و
 * «خواندم» ثبت می‌شوند؛ درصد واقعی را پخش‌کنندهٔ ویدئو در M4 می‌فرستد.
 */
function ResourceRow({
  resource,
  accessToken,
  onChanged,
}: {
  resource: CourseResource;
  accessToken: string | null;
  onChanged: () => Promise<void>;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const completed = resource.progress?.status === 'COMPLETED';

  async function open() {
    if (!accessToken) return;
    setBusy(true);
    setError(null);
    try {
      // باز کردن ⇒ IN_PROGRESS (FR-EDU-04). ثبت پیش از دانلود انجام
      // می‌شود چون پس از تغییر مکان، کدی اجرا نمی‌شود.
      await recordProgress(resource.id, accessToken);
      const target = resource.has_file
        ? (await resourceDownloadUrl(resource.id, accessToken)).download_url
        : resource.external_url;
      await onChanged();
      if (target) window.open(target, '_blank', 'noopener,noreferrer');
    } catch (cause) {
      setError(messageFor(cause));
    } finally {
      setBusy(false);
    }
  }

  async function markRead() {
    if (!accessToken) return;
    setBusy(true);
    setError(null);
    try {
      await recordProgress(resource.id, accessToken, { completed: true });
      await onChanged();
    } catch (cause) {
      setError(messageFor(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <li
      className={cn(
        'flex flex-col gap-3 rounded-[var(--radius-lg)] border p-4',
        completed
          ? 'border-[var(--success-500)] bg-[color-mix(in_oklch,var(--success-500)_5%,transparent)]'
          : 'border-[var(--border-subtle)] bg-[var(--bg-surface)]',
      )}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 flex-col gap-1.5">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={completed ? 'success' : 'neutral'}>
              {KIND_LABELS[resource.kind] ?? resource.kind}
            </Badge>
            <h3 className="text-[15px] font-semibold text-[var(--fg-primary)]">
              {resource.title_fa}
            </h3>
            {completed && <Badge tone="success">مطالعه شد</Badge>}
            {!resource.is_required && <Badge tone="neutral">اختیاری</Badge>}
          </div>
          {resource.description && (
            <p className="text-[13.5px] leading-6 text-[var(--fg-secondary)]">
              {resource.description}
            </p>
          )}
        </div>

        <div className="flex shrink-0 items-center gap-2">
          <Button size="sm" variant="secondary" onClick={open} disabled={busy || !accessToken}>
            {resource.kind === 'VIDEO' ? 'تماشا' : 'باز کردن'}
          </Button>
          {!completed && resource.kind !== 'VIDEO' && (
            <Button size="sm" variant="ghost" onClick={markRead} disabled={busy || !accessToken}>
              خواندم
            </Button>
          )}
        </div>
      </div>

      {error && (
        <p role="alert" className="text-[12.5px] text-[var(--fg-danger)]">
          {error}
        </p>
      )}
    </li>
  );
}

function messageFor(cause: unknown): string {
  if (cause instanceof ApiError || cause instanceof NetworkError) return cause.message;
  return 'خطای غیرمنتظره‌ای رخ داد.';
}
