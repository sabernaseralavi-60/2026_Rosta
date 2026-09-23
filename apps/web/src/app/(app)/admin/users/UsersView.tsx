'use client';

import Link from 'next/link';
import { type FormEvent, useCallback, useEffect, useState } from 'react';

import { errorText, ErrorLine, Field, SELECT_CLASS } from '@/components/admin/common';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { EmptyState } from '@/components/ui/EmptyState';
import { Input } from '@/components/ui/Input';
import { SkeletonRow } from '@/components/ui/Skeleton';
import {
  type AdminUserPage,
  fetchUsers,
  ROLE_LABELS,
  USER_STATUS_LABELS,
  type UserStatus,
} from '@/lib/api/admin';
import { useSession } from '@/lib/auth/use-session';
import { formatDateShort, formatRelative } from '@/lib/format/date';
import { toPersianDigits } from '@/lib/format/digits';

/**
 * `/admin/users` — جستجو با نام، نام کاربری، بخشی از موبایل یا ایمیل.
 *
 * در موبایل جدول به فهرست کارت تبدیل می‌شود (§3.9 «هیچ جدولی در موبایل
 * اسکرول افقی نمی‌گیرد»). پشتیبانی موبایل را پوشانده می‌بیند (NFR-01).
 */

const STATUS_TONE: Record<UserStatus, 'success' | 'warning' | 'danger'> = {
  ACTIVE: 'success',
  SUSPENDED: 'warning',
  DEACTIVATED: 'danger',
};

export function UsersView() {
  const { accessToken } = useSession();
  const [draft, setDraft] = useState('');
  const [filters, setFilters] = useState<{ q: string; role: string; status: string; page: number }>(
    { q: '', role: '', status: '', page: 1 },
  );
  const [data, setData] = useState<AdminUserPage | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    if (!accessToken) return;
    setError(null);
    fetchUsers(accessToken, filters)
      .then(setData)
      .catch((cause) => setError(errorText(cause)));
  }, [accessToken, filters]);

  useEffect(load, [load]);

  function submit(event: FormEvent) {
    event.preventDefault();
    setData(null);
    setFilters((current) => ({ ...current, q: draft.trim(), page: 1 }));
  }

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-1">
        <h1>کاربران و نقش‌ها</h1>
        <p className="text-[14px] text-[var(--fg-secondary)]">
          حساب هرگز حذف نمی‌شود؛ تعلیق و غیرفعال‌سازی با دلیل، و هر تغییر در لاگ حسابرسی.
        </p>
      </header>

      <form onSubmit={submit} className="grid gap-3 md:grid-cols-[1fr_auto_auto_auto] md:items-end">
        <Input
          label="جستجو"
          placeholder="نام، نام کاربری، چهار رقم از موبایل یا ایمیل"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
        />
        <Field label="نقش">
          <select
            className={SELECT_CLASS}
            value={filters.role}
            onChange={(event) => {
              setData(null);
              setFilters((current) => ({ ...current, role: event.target.value, page: 1 }));
            }}
          >
            <option value="">همه</option>
            {Object.entries(ROLE_LABELS)
              .filter(([code]) => !['GUEST', 'PROJECT_MEMBER', 'PROJECT_LEAD'].includes(code))
              .map(([code, label]) => (
                <option key={code} value={code}>
                  {label}
                </option>
              ))}
          </select>
        </Field>
        <Field label="وضعیت">
          <select
            className={SELECT_CLASS}
            value={filters.status}
            onChange={(event) => {
              setData(null);
              setFilters((current) => ({ ...current, status: event.target.value, page: 1 }));
            }}
          >
            <option value="">همه</option>
            {(Object.keys(USER_STATUS_LABELS) as UserStatus[]).map((status) => (
              <option key={status} value={status}>
                {USER_STATUS_LABELS[status]}
              </option>
            ))}
          </select>
        </Field>
        <Button type="submit">جستجو</Button>
      </form>

      {error && <ErrorLine>{error}</ErrorLine>}
      {!data && !error && <SkeletonRow label="در حال بارگذاری کاربران" />}
      {data && data.items.length === 0 && (
        <EmptyState
          title="کاربری با این مشخصات نیست"
          description="بخش کوتاه‌تری از نام یا چهار رقم آخر موبایل را امتحان کن."
        />
      )}
      {data && data.items.length > 0 && (
        <>
          <p className="text-[13px] text-[var(--fg-tertiary)]">
            {toPersianDigits(data.total)} کاربر
          </p>
          <ul className="flex flex-col divide-y divide-[var(--border-subtle)] rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-surface)]">
            {data.items.map((user) => (
              <li key={user.id}>
                <Link
                  href={`/admin/users/${user.id}`}
                  className="grid gap-1 px-4 py-3 hover:bg-[var(--bg-sunken)] md:grid-cols-[1.4fr_1fr_1.2fr_auto] md:items-center md:gap-4"
                >
                  <span className="flex flex-col">
                    <span className="font-medium">{user.name ?? 'بی‌نام (نیمرخ ناقص)'}</span>
                    {user.username && (
                      <span className="text-[12.5px] text-[var(--fg-tertiary)]" dir="ltr">
                        @{user.username}
                      </span>
                    )}
                  </span>
                  <span className="text-[13px] text-[var(--fg-secondary)]" dir="ltr">
                    {user.mobile ?? user.email ?? '—'}
                  </span>
                  <span className="flex flex-wrap gap-1">
                    {user.roles.map((role) => (
                      <Badge
                        key={role}
                        tone={role === 'ADMIN' || role === 'SUPPORT' ? 'accent' : 'neutral'}
                      >
                        {ROLE_LABELS[role] ?? role}
                      </Badge>
                    ))}
                  </span>
                  <span className="flex items-center gap-2 text-[12.5px] text-[var(--fg-tertiary)]">
                    <Badge tone={STATUS_TONE[user.status]}>{USER_STATUS_LABELS[user.status]}</Badge>
                    {user.last_login_at
                      ? `ورود ${formatRelative(user.last_login_at)}`
                      : `ثبت‌نام ${formatDateShort(user.created_at)}`}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
          <div className="flex items-center justify-between">
            <Button
              variant="secondary"
              size="sm"
              disabled={filters.page <= 1}
              onClick={() => setFilters((current) => ({ ...current, page: current.page - 1 }))}
            >
              قبلی
            </Button>
            <span className="text-[13px] text-[var(--fg-tertiary)]">
              صفحهٔ {toPersianDigits(filters.page)}
            </span>
            <Button
              variant="secondary"
              size="sm"
              disabled={!data.has_next}
              onClick={() => setFilters((current) => ({ ...current, page: current.page + 1 }))}
            >
              بعدی
            </Button>
          </div>
        </>
      )}
    </div>
  );
}
