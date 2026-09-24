'use client';

import Link from 'next/link';
import { useCallback, useEffect, useMemo, useState } from 'react';

import { errorText, ErrorLine } from '@/components/admin/common';
import { fa, SectionHeader } from '@/components/teach/common';
import { useOffering } from '@/components/teach/OfferingFrame';
import { Badge, type BadgeTone } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { EmptyState } from '@/components/ui/EmptyState';
import { SkeletonRow } from '@/components/ui/Skeleton';
import type { EnrollmentStatus } from '@/lib/api/courses';
import {
  decideEnrollment,
  ENROLLMENT_STATUS_LABELS,
  fetchRoster,
  type RosterEntry,
} from '@/lib/api/teach';
import { formatDateShort } from '@/lib/format/date';
import { toPersianDigits } from '@/lib/format/digits';

const TONES: Record<EnrollmentStatus, BadgeTone> = {
  PENDING: 'warning',
  ACTIVE: 'success',
  COMPLETED: 'brand',
  DROPPED: 'neutral',
  REJECTED: 'danger',
};

/**
 * `/teach/offerings/[id]/students` — §3.5: درخواست‌های ثبت‌نام بالای صفحه،
 * سپس کلاس. دستیار فهرست را می‌بیند ولی تصمیم ثبت‌نام و نمره با استاد است.
 */
export function StudentsView() {
  const { offering, token, reload } = useOffering();
  const [rows, setRows] = useState<RosterEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(() => {
    fetchRoster(offering.id, token)
      .then(setRows)
      .catch((cause) => setError(errorText(cause)));
  }, [offering.id, token]);

  useEffect(load, [load]);

  const groups = useMemo(() => {
    const all = rows ?? [];
    return {
      pending: all.filter((r) => r.status === 'PENDING'),
      enrolled: all.filter((r) => r.status === 'ACTIVE' || r.status === 'COMPLETED'),
      gone: all.filter((r) => r.status === 'DROPPED' || r.status === 'REJECTED'),
    };
  }, [rows]);

  async function decide(entry: RosterEntry, approve: boolean) {
    setBusy(entry.enrollment_id);
    setError(null);
    try {
      await decideEnrollment(entry.enrollment_id, approve, token);
      load();
      await reload();
    } catch (cause) {
      setError(errorText(cause));
    } finally {
      setBusy(null);
    }
  }

  if (!rows && !error) return <SkeletonRow label="در حال بارگذاری دانشجویان" />;
  if (!rows) return <ErrorLine>{error}</ErrorLine>;

  const canDecide = offering.permissions.approve_enrollments;

  return (
    <div className="flex flex-col gap-8">
      {error && <ErrorLine>{error}</ErrorLine>}
      {groups.pending.length > 0 && (
        <section className="flex flex-col gap-3">
          <SectionHeader
            title={`درخواست‌های ثبت‌نام (${toPersianDigits(groups.pending.length)})`}
            description={
              canDecide
                ? 'با تأیید، دانشجو به کلاس می‌پیوندد و اعلان می‌گیرد.'
                : 'تصمیم دربارهٔ ثبت‌نام با استاد درس است.'
            }
          />
          <ul className="flex flex-col divide-y divide-[var(--border-subtle)] rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-surface)]">
            {groups.pending.map((entry) => (
              <li
                key={entry.enrollment_id}
                className="flex flex-wrap items-center justify-between gap-3 px-4 py-3"
              >
                <div className="flex flex-col">
                  <span className="font-medium">{entry.student_name ?? 'بی‌نام'}</span>
                  <span className="text-[12.5px] text-[var(--fg-tertiary)]">
                    درخواست: {formatDateShort(entry.enrolled_at)}
                  </span>
                </div>
                {canDecide && (
                  <div className="flex gap-2">
                    <Button
                      size="sm"
                      loading={busy === entry.enrollment_id}
                      onClick={() => decide(entry, true)}
                    >
                      تأیید
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      disabled={busy === entry.enrollment_id}
                      onClick={() => decide(entry, false)}
                    >
                      رد
                    </Button>
                  </div>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="flex flex-col gap-3">
        <SectionHeader
          title={`کلاس (${toPersianDigits(groups.enrolled.length)})`}
          action={
            offering.permissions.manage ? (
              <Button asChild size="sm" variant="secondary">
                <Link href={`/teach/offerings/${offering.id}/grades`}>دفتر نمره</Link>
              </Button>
            ) : undefined
          }
        />
        {groups.enrolled.length === 0 ? (
          <EmptyState
            title="هنوز دانشجویی در کلاس نیست"
            description={
              offering.status === 'OPEN'
                ? offering.has_enrollment_code
                  ? 'کد ثبت‌نام را در کلاس اعلام کن تا دانشجویان از صفحهٔ درس ثبت‌نام کنند.'
                  : 'ارائه برای ثبت‌نام باز است؛ دانشجویان از صفحهٔ درس ثبت‌نام می‌کنند.'
                : 'برای پذیرش ثبت‌نام، وضعیت ارائه را در «تنظیمات» روی «باز برای ثبت‌نام» بگذار.'
            }
          />
        ) : (
          <RosterList rows={groups.enrolled} showGrade={offering.permissions.manage} />
        )}
      </section>

      {groups.gone.length > 0 && (
        <section className="flex flex-col gap-3">
          <SectionHeader title="انصراف و ردشده" />
          <RosterList rows={groups.gone} showGrade={false} />
        </section>
      )}
    </div>
  );
}

function RosterList({ rows, showGrade }: { rows: RosterEntry[]; showGrade: boolean }) {
  return (
    <ul className="flex flex-col divide-y divide-[var(--border-subtle)] rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-surface)]">
      {rows.map((entry) => (
        <li
          key={entry.enrollment_id}
          className="flex flex-wrap items-center justify-between gap-2 px-4 py-3"
        >
          <span className="font-medium">{entry.student_name ?? 'بی‌نام'}</span>
          <span className="flex items-center gap-3 text-[13px] text-[var(--fg-secondary)]">
            {showGrade && entry.final_grade !== null && (
              <span>
                نمرهٔ نهایی: <strong className="tabular-nums">{fa(entry.final_grade)}</strong>
              </span>
            )}
            <Badge tone={TONES[entry.status]}>{ENROLLMENT_STATUS_LABELS[entry.status]}</Badge>
          </span>
        </li>
      ))}
    </ul>
  );
}
