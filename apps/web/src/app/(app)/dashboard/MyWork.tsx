'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';

import { Badge } from '@/components/ui/Badge';
import { Card } from '@/components/ui/Card';
import { type Application, fetchMyApplications } from '@/lib/api/workspace';
import { useSession } from '@/lib/auth/use-session';
import { formatRelative } from '@/lib/format/date';
import { toPersianDigits } from '@/lib/format/digits';

/**
 * «درخواست‌های در جریان» — §3.4، FR-DASH-01 (بخش M2).
 *
 * از M5 پروژه‌ها، دروس و امتیاز از `GET /me/dashboard` می‌آیند
 * (`DashboardView`). اینجا فقط چیزی مانده که آن پاسخ ندارد: درخواستی که
 * کاربر داده و هنوز جوابی نگرفته — بدون آن، پس از درخواست گم می‌شود.
 */

export function MyWork() {
  const { accessToken, loading: sessionLoading } = useSession({ required: false });
  const [applications, setApplications] = useState<Application[]>([]);

  useEffect(() => {
    if (sessionLoading || !accessToken) return;
    let cancelled = false;

    fetchMyApplications(accessToken)
      .then((rows) => !cancelled && setApplications(rows))
      .catch(() => !cancelled && setApplications([]));

    return () => {
      cancelled = true;
    };
  }, [accessToken, sessionLoading]);

  const openApplications = applications.filter(
    (application) => application.status === 'PENDING' || application.status === 'WAITLISTED',
  );
  if (!accessToken || openApplications.length === 0) return null;

  return (
    <section className="flex flex-col gap-3">
      <h2 className="text-[19px] font-semibold">درخواست‌های در جریان</h2>
      <ul className="flex flex-col gap-2">
        {openApplications.map((application) => (
          <li key={application.id}>
            <Card className="flex flex-wrap items-center justify-between gap-3 p-4">
              <div className="flex flex-col gap-0.5">
                <Link
                  href={`/projects/${application.project_id}`}
                  className="text-[14.5px] font-medium text-[var(--fg-primary)]"
                >
                  {application.project_title_fa ?? 'پروژه'}
                </Link>
                <span className="text-[12.5px] text-[var(--fg-tertiary)]">
                  {formatRelative(application.created_at)}
                </span>
              </div>
              <div className="flex items-center gap-2">
                {application.match_score !== null && (
                  <Badge tone="brand">
                    {toPersianDigits(Math.round(application.match_score))}٪ تطابق
                  </Badge>
                )}
                <Badge tone="info">{application.status_fa}</Badge>
              </div>
            </Card>
          </li>
        ))}
      </ul>
    </section>
  );
}
