'use client';

import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';

import { errorText } from '@/components/admin/common';
import { OfferingStatusBadge } from '@/components/teach/common';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { SkeletonCard } from '@/components/ui/Skeleton';
import { fetchTeachOfferings, STAFF_ROLE_LABELS, type TeachOffering } from '@/lib/api/teach';
import { useSession } from '@/lib/auth/use-session';
import { toPersianDigits } from '@/lib/format/digits';

/** `/teach/offerings` — §3.5 «ارائه‌های من»: استاد اصلی و دستیار، هر دو. */
export function OfferingsView() {
  const { accessToken } = useSession();
  const [rows, setRows] = useState<TeachOffering[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    if (!accessToken) return;
    setError(null);
    fetchTeachOfferings(accessToken)
      .then(setRows)
      .catch((cause) => setError(errorText(cause)));
  }, [accessToken]);

  useEffect(load, [load]);

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-1">
        <h1>ارائه‌های من</h1>
        <p className="text-[14px] text-[var(--fg-secondary)]">
          درس‌هایی که در آن‌ها استاد یا دستیار آموزشی هستی.
        </p>
      </header>
      {error && !rows && (
        <EmptyState
          title="فهرست ارائه‌ها بارگذاری نشد"
          description={error}
          action={<Button onClick={load}>تلاش دوباره</Button>}
        />
      )}
      {!rows && !error && <SkeletonCard label="در حال بارگذاری ارائه‌ها" />}
      {rows && rows.length === 0 && (
        <EmptyState
          title="هنوز ارائه‌ای به تو سپرده نشده"
          description="ارائهٔ هر درس را مدیر آموزشی برای یک نیم‌سال می‌سازد و استادش را تعیین می‌کند. دستیار آموزشی را هم مدیر سامانه به همان ارائه اضافه می‌کند."
          action={
            <Link
              href="/help/instructor"
              className="text-[14px] font-medium text-[var(--fg-brand)]"
            >
              راهنمای استاد
            </Link>
          }
        />
      )}
      {rows && rows.length > 0 && (
        <ul className="grid gap-3 md:grid-cols-2">
          {rows.map((offering) => (
            <li key={offering.id}>
              <Card variant="interactive" className="h-full p-0">
                <Link
                  href={`/teach/offerings/${offering.id}`}
                  className="flex h-full flex-col gap-3 p-4"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="text-[16px] font-semibold">{offering.course_title_fa}</span>
                    <OfferingStatusBadge status={offering.status} />
                  </div>
                  <span className="text-[13px] text-[var(--fg-secondary)]">
                    {offering.term_title_fa}
                    {offering.staff_role && ` · ${STAFF_ROLE_LABELS[offering.staff_role]}`}
                  </span>
                  <div className="mt-auto flex flex-wrap items-center gap-2 text-[13px]">
                    <Badge tone="neutral">
                      {toPersianDigits(offering.active_students)} دانشجوی فعال
                      {offering.capacity ? ` از ${toPersianDigits(offering.capacity)}` : ''}
                    </Badge>
                    {offering.pending_enrollments > 0 && (
                      <Badge tone="warning">
                        {toPersianDigits(offering.pending_enrollments)} درخواست ثبت‌نام
                      </Badge>
                    )}
                    {offering.has_enrollment_code && <Badge tone="info">با کد ثبت‌نام</Badge>}
                  </div>
                </Link>
              </Card>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
