'use client';

import { type FormEvent, useCallback, useEffect, useState } from 'react';

import { errorText, ErrorLine, Field, SELECT_CLASS } from '@/components/admin/common';
import { Badge, type BadgeTone } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { Input } from '@/components/ui/Input';
import { SkeletonRow } from '@/components/ui/Skeleton';
import { type AdminUser, fetchUsers } from '@/lib/api/admin';
import { type CourseSummary, fetchCourses } from '@/lib/api/courses';
import {
  activateSubscription,
  type AdminSubscription,
  fetchAdminSubscriptions,
  fetchPlans,
  grantSubscription,
  type Plan,
  rejectSubscription,
  SUBSCRIPTION_STATUS_LABELS,
  type SubscriptionStatus,
} from '@/lib/api/subscriptions';
import { useSession } from '@/lib/auth/use-session';
import { cn } from '@/lib/cn';
import { formatDateShort, formatDateTime } from '@/lib/format/date';
import { toPersianDigits } from '@/lib/format/digits';

const TONES: Record<SubscriptionStatus, BadgeTone> = {
  PENDING: 'warning',
  ACTIVE: 'success',
  EXPIRED: 'neutral',
  CANCELLED: 'danger',
};

const FILTERS: { value: SubscriptionStatus | ''; label: string }[] = [
  { value: 'PENDING', label: 'در انتظار تأیید' },
  { value: 'ACTIVE', label: 'فعال' },
  { value: '', label: 'همه' },
];

function toman(rial: number | null): string {
  if (rial === null) return '—';
  // جداکنندهٔ هزارگان فارسی «٬» — همان قالب `price_fa` سرور.
  return `${toPersianDigits(
    Math.round(rial / 10)
      .toLocaleString('en-US')
      .replace(/,/g, '٬'),
  )} تومان`;
}

/**
 * `/admin/subscriptions` — تأیید پرداخت و فعال‌سازی اشتراک (ADR-0009، ADR-0019).
 *
 * پرداخت بیرون از سامانه است: پشتیبانی فیش را با درخواست تطبیق می‌دهد و
 * با کد پیگیری فعال می‌کند. دوره از لحظهٔ تأیید شمرده می‌شود، نه از لحظهٔ
 * درخواست؛ رد درخواست دلیل می‌خواهد چون به کاربر اعلان می‌شود.
 */
export function SubscriptionsAdminView() {
  const { accessToken } = useSession();
  const [status, setStatus] = useState<SubscriptionStatus | ''>('PENDING');
  const [rows, setRows] = useState<AdminSubscription[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    if (!accessToken) return;
    setRows(null);
    setError(null);
    fetchAdminSubscriptions(accessToken, status ? { status } : {})
      .then(setRows)
      .catch((cause) => setError(errorText(cause)));
  }, [accessToken, status]);

  useEffect(load, [load]);

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-1">
        <h1>اشتراک‌ها</h1>
        <p className="max-w-[70ch] text-[14px] text-[var(--fg-secondary)]">
          فیش را با درخواست تطبیق بده و با کد پیگیری فعال کن. دوره از لحظهٔ تأیید شمرده می‌شود؛
          کاربر اعلان و پیامک می‌گیرد.
        </p>
      </header>

      {accessToken && <GrantCard token={accessToken} onGranted={load} />}

      <div className="flex flex-wrap gap-2" role="group" aria-label="فیلتر وضعیت">
        {FILTERS.map((filter) => (
          <button
            key={filter.label}
            type="button"
            aria-pressed={status === filter.value}
            onClick={() => setStatus(filter.value)}
            className={cn(
              'rounded-[var(--radius-sm)] border px-3 py-1.5 text-[13.5px]',
              status === filter.value
                ? 'border-[var(--brand-600)] bg-[var(--brand-50)] font-semibold text-[var(--fg-brand)]'
                : 'border-[var(--border-default)] text-[var(--fg-secondary)]',
            )}
          >
            {filter.label}
          </button>
        ))}
      </div>

      {error && <ErrorLine>{error}</ErrorLine>}
      {!rows && !error && <SkeletonRow label="در حال بارگذاری اشتراک‌ها" />}
      {rows && rows.length === 0 && (
        <EmptyState
          title={status === 'PENDING' ? 'درخواستی در انتظار نیست' : 'اشتراکی پیدا نشد'}
          description={
            status === 'PENDING'
              ? 'درخواست تازه از صفحهٔ اشتراک کاربران اینجا می‌آید، قدیمی‌ترین اول.'
              : undefined
          }
        />
      )}
      {rows && rows.length > 0 && accessToken && (
        <ul className="flex flex-col gap-3">
          {rows.map((row) => (
            <li key={row.id}>
              <SubscriptionRow row={row} token={accessToken} onChanged={load} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function SubscriptionRow({
  row,
  token,
  onChanged,
}: {
  row: AdminSubscription;
  token: string;
  onChanged: () => void;
}) {
  const [mode, setMode] = useState<'activate' | 'reject' | null>(null);
  const [value, setValue] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (mode === 'activate') await activateSubscription(row.id, value.trim(), token);
      else await rejectSubscription(row.id, value.trim(), token);
      onChanged();
    } catch (cause) {
      setError(errorText(cause));
      setBusy(false);
    }
  }

  const name = row.user_name ?? row.username ?? 'بی‌نام';

  return (
    <Card className="flex flex-col gap-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex flex-col gap-0.5">
          <span className="flex flex-wrap items-center gap-2 font-semibold">
            {name}
            <Badge tone={TONES[row.status]}>{SUBSCRIPTION_STATUS_LABELS[row.status]}</Badge>
          </span>
          <span className="text-[12.5px] text-[var(--fg-tertiary)]">
            {row.user_mobile && (
              <span dir="ltr" className="font-mono">
                {row.user_mobile}
              </span>
            )}
            {row.username && <> · @{row.username}</>} · درخواست {formatDateTime(row.created_at)}
          </span>
        </div>
        <div className="flex flex-col items-end gap-0.5 text-[13px]">
          <span className="font-medium">
            {row.plan_title_fa}
            {row.course_title_fa && ` — ${row.course_title_fa}`}
          </span>
          <span className="tabular-nums text-[var(--fg-secondary)]">{toman(row.amount_irr)}</span>
        </div>
      </div>
      {row.note && (
        <p className="rounded-[var(--radius-md)] bg-[var(--bg-sunken)] p-2.5 text-[13.5px]">
          <strong>یادداشت کاربر: </strong>
          {row.note}
        </p>
      )}
      {row.status === 'ACTIVE' && (
        <p className="text-[13px] text-[var(--fg-secondary)]">
          {formatDateShort(row.starts_at)} تا {formatDateShort(row.ends_at)} ·{' '}
          {toPersianDigits(row.days_remaining)} روز مانده
          {row.payment_ref && (
            <>
              {' '}
              · کد پیگیری <span dir="ltr">{row.payment_ref}</span>
            </>
          )}
          {row.granted_by_name && <> · تأیید: {row.granted_by_name}</>}
        </p>
      )}
      {row.status === 'PENDING' && !mode && (
        <div className="flex gap-2">
          <Button size="sm" onClick={() => setMode('activate')}>
            تأیید پرداخت
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setMode('reject')}>
            رد
          </Button>
        </div>
      )}
      {mode && (
        <form onSubmit={submit} className="flex flex-wrap items-end gap-2">
          <div className="min-w-[16rem] flex-1">
            <Input
              label={
                mode === 'activate'
                  ? 'کد پیگیری یا شمارهٔ فیش'
                  : 'دلیل رد (در اعلان به کاربر نشان داده می‌شود)'
              }
              forceLtr={mode === 'activate'}
              autoFocus
              maxLength={mode === 'activate' ? 200 : 500}
              value={value}
              onChange={(event) => setValue(event.target.value)}
            />
          </div>
          <Button
            type="submit"
            size="sm"
            variant={mode === 'reject' ? 'danger' : 'primary'}
            loading={busy}
            disabled={value.trim().length < (mode === 'activate' ? 3 : 5)}
          >
            {mode === 'activate' ? 'فعال کن' : 'رد درخواست'}
          </Button>
          <Button
            type="button"
            size="sm"
            variant="ghost"
            onClick={() => {
              setMode(null);
              setValue('');
            }}
          >
            انصراف
          </Button>
        </form>
      )}
      {error && <ErrorLine>{error}</ErrorLine>}
    </Card>
  );
}

function GrantCard({ token, onGranted }: { token: string; onGranted: () => void }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [found, setFound] = useState<AdminUser[] | null>(null);
  const [user, setUser] = useState<AdminUser | null>(null);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [courses, setCourses] = useState<CourseSummary[]>([]);
  const [planCode, setPlanCode] = useState('');
  const [courseSlug, setCourseSlug] = useState('');
  const [paymentRef, setPaymentRef] = useState('');
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    fetchPlans(token)
      .then((list) => {
        setPlans(list);
        setPlanCode((code) => code || list[0]?.code || '');
      })
      .catch(() => setPlans([]));
    fetchCourses({ page_size: 100 }, token)
      .then((page) => setCourses(page.items))
      .catch(() => setCourses([]));
  }, [open, token]);

  const plan = plans.find((p) => p.code === planCode);

  async function search(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      setFound((await fetchUsers(token, { q: query.trim() })).items.slice(0, 8));
    } catch (cause) {
      setError(errorText(cause));
    }
  }

  async function grant(event: FormEvent) {
    event.preventDefault();
    if (!user) return;
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      await grantSubscription(token, {
        user_id: user.id,
        plan_code: planCode,
        ...(plan?.scope === 'SINGLE_COURSE' ? { course_slug: courseSlug } : {}),
        ...(paymentRef.trim() ? { payment_ref: paymentRef.trim() } : {}),
        ...(note.trim() ? { note: note.trim() } : {}),
      });
      setMessage(`اشتراک ${user.name ?? user.username ?? ''} فعال شد.`);
      setUser(null);
      setFound(null);
      setQuery('');
      setPaymentRef('');
      setNote('');
      onGranted();
    } catch (cause) {
      setError(errorText(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="flex flex-col gap-3">
      <div className="flex items-center justify-between gap-2">
        <div className="flex flex-col gap-0.5">
          <h2 className="text-[16px]">فعال‌سازی مستقیم</h2>
          <p className="text-[13px] text-[var(--fg-secondary)]">
            برای فیشی که کاربر بی‌درخواست فرستاده، یا اشتراک هدیه.
          </p>
        </div>
        <Button variant="ghost" size="sm" onClick={() => setOpen((o) => !o)}>
          {open ? 'بستن' : 'باز کردن'}
        </Button>
      </div>
      {open && (
        <>
          {!user ? (
            <form onSubmit={search} className="flex flex-wrap items-end gap-2">
              <div className="min-w-[16rem] flex-1">
                <Input
                  label="جستجوی کاربر (نام، نام کاربری یا موبایل)"
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                />
              </div>
              <Button type="submit" variant="secondary" disabled={query.trim().length < 2}>
                جستجو
              </Button>
            </form>
          ) : (
            <p className="flex flex-wrap items-center gap-2 text-[14px]">
              کاربر: <strong>{user.name ?? user.username}</strong>
              <span dir="ltr" className="font-mono text-[12.5px] text-[var(--fg-tertiary)]">
                {user.mobile}
              </span>
              <Button size="sm" variant="ghost" onClick={() => setUser(null)}>
                تغییر
              </Button>
            </p>
          )}
          {!user && found && (
            <ul className="flex flex-col divide-y divide-[var(--border-subtle)] rounded-[var(--radius-md)] border border-[var(--border-subtle)]">
              {found.length === 0 && (
                <li className="px-3 py-2 text-[13.5px] text-[var(--fg-secondary)]">
                  کسی پیدا نشد.
                </li>
              )}
              {found.map((candidate) => (
                <li key={candidate.id}>
                  <button
                    type="button"
                    onClick={() => setUser(candidate)}
                    className="flex w-full items-center justify-between gap-2 px-3 py-2 text-start text-[13.5px] hover:bg-[var(--bg-sunken)]"
                  >
                    <span>{candidate.name ?? candidate.username ?? 'بی‌نام'}</span>
                    <span dir="ltr" className="font-mono text-[12.5px] text-[var(--fg-tertiary)]">
                      {candidate.mobile}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
          {user && (
            <form onSubmit={grant} className="grid gap-3 md:grid-cols-2">
              <Field label="طرح">
                <select
                  className={SELECT_CLASS}
                  value={planCode}
                  onChange={(event) => setPlanCode(event.target.value)}
                >
                  {plans.map((p) => (
                    <option key={p.code} value={p.code}>
                      {p.title_fa} — {p.price_fa}
                    </option>
                  ))}
                </select>
              </Field>
              {plan?.scope === 'SINGLE_COURSE' && (
                <Field label="درس">
                  <select
                    className={SELECT_CLASS}
                    value={courseSlug}
                    onChange={(event) => setCourseSlug(event.target.value)}
                  >
                    <option value="">انتخاب کن…</option>
                    {courses.map((c) => (
                      <option key={c.slug} value={c.slug}>
                        {c.title_fa}
                      </option>
                    ))}
                  </select>
                </Field>
              )}
              <Input
                label="کد پیگیری یا شمارهٔ فیش"
                forceLtr
                maxLength={200}
                value={paymentRef}
                onChange={(event) => setPaymentRef(event.target.value)}
              />
              <Input
                label="یادداشت"
                hint="بی کد پیگیری لازم است — مثلاً «هدیهٔ برندهٔ مسابقه»."
                maxLength={500}
                value={note}
                onChange={(event) => setNote(event.target.value)}
              />
              <div className="md:col-span-2">
                <Button
                  type="submit"
                  loading={busy}
                  disabled={
                    !planCode ||
                    (!paymentRef.trim() && !note.trim()) ||
                    (plan?.scope === 'SINGLE_COURSE' && !courseSlug)
                  }
                >
                  فعال کن
                </Button>
              </div>
            </form>
          )}
        </>
      )}
      {message && (
        <p role="status" className="text-[13.5px] text-[var(--fg-success)]">
          {message}
        </p>
      )}
      {error && <ErrorLine>{error}</ErrorLine>}
    </Card>
  );
}
