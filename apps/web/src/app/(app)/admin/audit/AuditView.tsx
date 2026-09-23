'use client';

import Link from 'next/link';
import { type FormEvent, useCallback, useEffect, useState } from 'react';

import {
  ChangeSummary,
  errorText,
  ErrorLine,
  Field,
  SELECT_CLASS,
} from '@/components/admin/common';
import { Button } from '@/components/ui/Button';
import { EmptyState } from '@/components/ui/EmptyState';
import { Input } from '@/components/ui/Input';
import { SkeletonRow } from '@/components/ui/Skeleton';
import { type AuditEntry, type AuditFilters, downloadAuditCsv, fetchAudit } from '@/lib/api/admin';
import { useSession } from '@/lib/auth/use-session';
import { formatDateTime } from '@/lib/format/date';

/**
 * `/admin/audit` — لاگ فقط‌افزودنی (FR-ADM-02): جستجو با کاربر، عمل و بازهٔ
 * زمانی، «بیشتر» با مکان‌نما، و خروجی CSV برای همان فیلترها. هیچ دکمهٔ
 * ویرایش یا حذفی نیست — تریگر دیتابیس هم اجازه‌اش را نمی‌داد.
 */

const ACTIONS: { code: string; label: string }[] = [
  { code: 'ROLE_GRANTED', label: 'اعطای نقش' },
  { code: 'ROLE_REVOKED', label: 'سلب نقش' },
  { code: 'USER_STATUS_CHANGED', label: 'تغییر وضعیت حساب' },
  { code: 'IMPERSONATION_STARTED', label: 'شروع مشاهده به‌عنوان کاربر' },
  { code: 'IMPERSONATION_ENDED', label: 'پایان مشاهده به‌عنوان کاربر' },
  { code: 'IMPERSONATED_REQUEST', label: 'درخواست در حالت مشاهده' },
  { code: 'GRADE_OVERRIDDEN', label: 'بازنویسی نمرهٔ سؤال' },
  { code: 'FINAL_GRADE_SET', label: 'نمرهٔ نهایی درس' },
  { code: 'ATTEMPT_VOIDED', label: 'ابطال تلاش آزمون' },
  { code: 'APPEAL_RESOLVED', label: 'رسیدگی به اعتراض' },
  { code: 'POINT_RULE_UPDATED', label: 'ویرایش قاعدهٔ امتیاز' },
  { code: 'POINTS_RECALCULATED', label: 'بازمحاسبهٔ امتیاز' },
  { code: 'POINT_ENTRY_REVERSED', label: 'اصلاح ردیف امتیاز' },
  { code: 'CERTIFICATE_REVOKED', label: 'ابطال گواهی' },
  { code: 'MESSAGE_TEMPLATE_UPDATED', label: 'ویرایش الگوی پیام' },
];

export function AuditView({
  initialUserId,
  initialAction,
}: {
  initialUserId: string;
  initialAction: string;
}) {
  const { accessToken } = useSession();
  const [userId, setUserId] = useState(initialUserId);
  const [filters, setFilters] = useState<AuditFilters>({
    user_id: initialUserId || undefined,
    action: initialAction || undefined,
  });
  const [items, setItems] = useState<AuditEntry[] | null>(null);
  const [cursor, setCursor] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(
    async (after: string | null) => {
      if (!accessToken) return;
      setBusy(true);
      setError(null);
      try {
        const page = await fetchAudit(accessToken, filters, after);
        setItems((current) => (after && current ? [...current, ...page.items] : page.items));
        setCursor(page.next_cursor);
      } catch (cause) {
        setError(errorText(cause));
      } finally {
        setBusy(false);
      }
    },
    [accessToken, filters],
  );

  useEffect(() => {
    setItems(null);
    void load(null);
  }, [load]);

  function submit(event: FormEvent) {
    event.preventDefault();
    setFilters((current) => ({ ...current, user_id: userId.trim() || undefined }));
  }

  async function exportCsv() {
    if (!accessToken) return;
    try {
      const blob = await downloadAuditCsv(accessToken, filters);
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = 'silp-audit.csv';
      link.click();
      URL.revokeObjectURL(url);
    } catch (cause) {
      setError(errorText(cause));
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div className="flex flex-col gap-1">
          <h1>لاگ حسابرسی</h1>
          <p className="text-[14px] text-[var(--fg-secondary)]">
            فقط افزودنی — حتی مدیر نمی‌تواند ردیفی را ویرایش یا پاک کند.
          </p>
        </div>
        <Button variant="secondary" size="sm" onClick={() => void exportCsv()}>
          خروجی CSV
        </Button>
      </header>

      <form onSubmit={submit} className="grid gap-3 md:grid-cols-[1fr_1fr_auto] md:items-end">
        <Input
          label="شناسهٔ کاربر"
          hint="هرچه این کاربر کرد یا بر او شد"
          forceLtr
          value={userId}
          onChange={(event) => setUserId(event.target.value)}
        />
        <Field label="عمل">
          <select
            className={SELECT_CLASS}
            value={filters.action ?? ''}
            onChange={(event) =>
              setFilters((current) => ({ ...current, action: event.target.value || undefined }))
            }
          >
            <option value="">همه</option>
            {ACTIONS.map((action) => (
              <option key={action.code} value={action.code}>
                {action.label}
              </option>
            ))}
          </select>
        </Field>
        <Button type="submit">اعمال</Button>
      </form>

      {error && <ErrorLine>{error}</ErrorLine>}
      {items === null && !error && <SkeletonRow label="در حال بارگذاری لاگ" />}
      {items && items.length === 0 && (
        <EmptyState
          title="رویدادی با این فیلتر نیست"
          description="فیلتر عمل یا کاربر را بردار تا همهٔ رویدادها را ببینی."
        />
      )}
      {items && items.length > 0 && (
        <ol className="flex flex-col divide-y divide-[var(--border-subtle)] rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-surface)]">
          {items.map((entry) => (
            <li
              key={entry.id}
              className="grid gap-2 px-4 py-3 md:grid-cols-[14rem_1fr_1.2fr] md:gap-4"
            >
              <div className="flex flex-col text-[12.5px] text-[var(--fg-tertiary)]">
                <span>{formatDateTime(entry.created_at)}</span>
                {entry.ip_address && <span dir="ltr">{entry.ip_address}</span>}
              </div>
              <div className="flex flex-col gap-0.5 text-[13.5px]">
                <strong>{entry.action_fa}</strong>
                <span className="text-[var(--fg-secondary)]">
                  {entry.actor_id ? (
                    <Link
                      href={`/admin/users/${entry.actor_id}`}
                      className="hover:text-[var(--brand-700)]"
                    >
                      {entry.actor_name ?? 'کاربر'}
                    </Link>
                  ) : (
                    'سامانه'
                  )}
                  {entry.impersonator_name && (
                    <span className="text-[var(--danger-600)]">
                      {' '}
                      — به دست {entry.impersonator_name}
                    </span>
                  )}
                </span>
                <span className="text-[12.5px] text-[var(--fg-tertiary)]">
                  {entry.entity_type_fa}
                  {entry.entity_type === 'USER' && entry.entity_id && (
                    <>
                      {' '}
                      <Link
                        href={`/admin/users/${entry.entity_id}`}
                        className="text-[var(--brand-700)]"
                      >
                        (نمایش)
                      </Link>
                    </>
                  )}
                </span>
              </div>
              <ChangeSummary before={entry.before} after={entry.after} />
            </li>
          ))}
        </ol>
      )}
      {cursor && (
        <Button variant="secondary" loading={busy} onClick={() => void load(cursor)}>
          رویدادهای قدیمی‌تر
        </Button>
      )}
    </div>
  );
}
