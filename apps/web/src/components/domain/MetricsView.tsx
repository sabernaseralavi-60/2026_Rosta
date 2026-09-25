'use client';

import Link from 'next/link';
import { type FormEvent, useCallback, useEffect, useState } from 'react';

import { Badge, type BadgeTone } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card, CardDescription, CardTitle } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { Input } from '@/components/ui/Input';
import { SkeletonCard } from '@/components/ui/Skeleton';
import { ApiError, NetworkError } from '@/lib/api/client';
import {
  type Metric,
  type MetricKind,
  type MetricOwner,
  type MetricStatus,
  type MetricsPage,
  deleteMetric,
  fetchMetrics,
  recordMetric,
  reviewMetric,
} from '@/lib/api/ventures';
import { useSession } from '@/lib/auth/use-session';
import { formatDateShort } from '@/lib/format/date';
import { formatNumber, formatRial, toLatinDigits } from '@/lib/format/digits';

/**
 * فعالیت و فروش — FR-VEN-02، M7-04.
 *
 * هم برای کسب‌وکار (`/ventures/[id]/metrics`) و هم برای پروژهٔ عملیاتی
 * (زبانهٔ فضای کاری). ثبت با عضو است، تأیید با کس دیگر؛ `can_review` را
 * سرور برای هر ردیف حساب می‌کند. «به تفکیک عضو» همان داشبورد عملکرد
 * هر عضو است که FR-VEN-02 خواسته.
 */

const KINDS: MetricKind[] = [
  'MEETINGS',
  'CALLS',
  'LEADS',
  'SALES_COUNT',
  'SALES_AMOUNT',
  'CONTENT_PIECES',
  'CUSTOMERS',
];

const STATUS_TONE: Record<MetricStatus, BadgeTone> = {
  PENDING: 'warning',
  VERIFIED: 'success',
  REJECTED: 'danger',
};

function today(): string {
  return new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Tehran' });
}

function formatValue(metric: MetricKind, value: number): string {
  return metric === 'SALES_AMOUNT' ? formatRial(value) : formatNumber(value);
}

export function MetricsView({
  owner,
  backHref,
  embedded = false,
}: {
  owner: MetricOwner;
  backHref?: string;
  /** داخل زبانهٔ فضای کاری — بدون سرتیتر صفحه. */
  embedded?: boolean;
}) {
  const { accessToken, loading: sessionLoading } = useSession();
  const [page, setPage] = useState<MetricsPage | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    if (sessionLoading || !accessToken) return;
    fetchMetrics(accessToken, owner)
      .then((result) => {
        setPage(result);
        setError(null);
      })
      .catch((cause) => setError(messageFor(cause)));
    // `owner` شیء تازه در هر رندر است؛ شناسه‌اش کافی است.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accessToken, sessionLoading, owner.kind, owner.id]);

  useEffect(load, [load]);

  return (
    <div className="flex flex-col gap-6">
      {!embedded && (
        <header className="flex flex-col gap-1">
          {backHref && (
            <Link href={backHref} className="text-[13px] text-[var(--fg-brand)] hover:underline">
              → بازگشت
            </Link>
          )}
          <h1>فعالیت و فروش</h1>
          <p className="text-[15px] text-[var(--fg-secondary)]">
            هر ردیف را منتور یا مدیر پروژه تأیید می‌کند؛ امتیاز کارآفرینی فقط از ثبت تأییدشده
            می‌آید.
          </p>
        </header>
      )}

      {error && (
        <p role="alert" className="text-[13.5px] text-[var(--fg-danger)]">
          {error}
        </p>
      )}

      {accessToken && (
        <RecordForm
          owner={owner}
          accessToken={accessToken}
          titles={page?.metric_titles}
          onSaved={load}
          onError={setError}
        />
      )}

      {page === null ? (
        !error && <SkeletonCard label="در حال بارگذاری فعالیت‌ها" />
      ) : (
        <>
          {page.by_member.length > 1 && (
            <Card className="flex flex-col gap-3">
              <CardTitle as="h2">عملکرد هر عضو (تأییدشده)</CardTitle>
              {page.share_percent !== null && (
                <CardDescription>
                  سهم فروشنده در این پروژه {formatNumber(page.share_percent)}٪ از فروش تأییدشدهٔ
                  خودش است؛ هر کس سهم خودش را در{' '}
                  <Link href="/me/revenue" className="text-[var(--fg-brand)] hover:underline">
                    درآمد و سهم من
                  </Link>{' '}
                  می‌بیند.
                </CardDescription>
              )}
              <div className="flex flex-col gap-2">
                {page.by_member.map((member) => (
                  <div
                    key={member.user_id}
                    className="flex flex-wrap items-baseline gap-x-4 gap-y-1 text-[13.5px]"
                  >
                    <span className="min-w-28 font-medium">{member.name ?? 'عضو'}</span>
                    {Object.entries(member.verified).map(([metric, value]) => (
                      <span key={metric} className="text-[var(--fg-secondary)]">
                        {page.metric_titles[metric as MetricKind]}:{' '}
                        <span className="tabular-nums">
                          {formatValue(metric as MetricKind, value ?? 0)}
                        </span>
                      </span>
                    ))}
                    {member.share_rial > 0 && (
                      <span className="text-[var(--fg-secondary)]">
                        سهم فروشنده:{' '}
                        <span className="tabular-nums">{formatRial(member.share_rial)}</span>
                      </span>
                    )}
                    {Object.keys(member.verified).length === 0 && (
                      <span className="text-[var(--fg-tertiary)]">هنوز چیزی تأیید نشده</span>
                    )}
                  </div>
                ))}
              </div>
            </Card>
          )}

          {page.items.length === 0 ? (
            <EmptyState
              title="هنوز فعالیتی ثبت نشده"
              description="اولین تماس، جلسه یا فروش را ثبت کن؛ هر ردیف پس از تأیید امتیاز کارآفرینی می‌دهد."
            />
          ) : (
            <ul className="flex flex-col gap-3">
              {page.items.map((item) => (
                <li key={item.id}>
                  <MetricRow
                    item={item}
                    accessToken={accessToken}
                    onChanged={load}
                    onError={setError}
                  />
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  );
}

function RecordForm({
  owner,
  accessToken,
  titles,
  onSaved,
  onError,
}: {
  owner: MetricOwner;
  accessToken: string;
  titles?: Record<MetricKind, string>;
  onSaved: () => void;
  onError: (message: string) => void;
}) {
  const [metric, setMetric] = useState<MetricKind>('MEETINGS');
  const [value, setValue] = useState('1');
  const [occurredOn, setOccurredOn] = useState(today());
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const amount = Number(toLatinDigits(value).replace(/[,٬]/g, ''));
    if (!Number.isFinite(amount) || amount <= 0) {
      onError('مقدار باید عددی مثبت باشد.');
      return;
    }
    setBusy(true);
    try {
      await recordMetric(accessToken, owner, {
        metric,
        value: Math.round(amount),
        occurred_on: occurredOn,
        note: note.trim() || null,
      });
      setValue('1');
      setNote('');
      onSaved();
    } catch (cause) {
      onError(messageFor(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <form onSubmit={submit} className="flex flex-col gap-4">
        <div className="flex flex-col gap-1">
          <CardTitle as="h2">ثبت فعالیت یا فروش</CardTitle>
          <CardDescription>
            مبلغ فروش را به ریال بنویس. رسید یا مستند را در توضیح ذکر کن.
          </CardDescription>
        </div>
        <div className="grid gap-4 sm:grid-cols-3">
          <label className="flex flex-col gap-1.5">
            <span className="text-[13.5px] font-medium">نوع</span>
            <select
              value={metric}
              onChange={(event) => setMetric(event.target.value as MetricKind)}
              className="h-11 rounded-[var(--radius-md)] border border-[var(--border-default)] bg-[var(--bg-surface)] px-3 text-[14px]"
            >
              {KINDS.map((kind) => (
                <option key={kind} value={kind}>
                  {titles?.[kind] ?? kind}
                </option>
              ))}
            </select>
          </label>
          <Input
            label={metric === 'SALES_AMOUNT' ? 'مبلغ (ریال)' : 'تعداد'}
            inputMode="numeric"
            forceLtr
            required
            value={value}
            onChange={(event) => setValue(event.target.value)}
          />
          <Input
            label="تاریخ"
            type="date"
            forceLtr
            required
            max={today()}
            value={occurredOn}
            onChange={(event) => setOccurredOn(event.target.value)}
          />
        </div>
        <Input
          label="توضیح"
          hint="اختیاری"
          maxLength={500}
          value={note}
          onChange={(event) => setNote(event.target.value)}
        />
        <Button type="submit" size="sm" loading={busy} className="self-start">
          ثبت
        </Button>
      </form>
    </Card>
  );
}

function MetricRow({
  item,
  accessToken,
  onChanged,
  onError,
  showOwner = false,
}: {
  item: Metric;
  accessToken: string | null;
  onChanged: () => void;
  onError: (message: string) => void;
  showOwner?: boolean;
}) {
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState<'VERIFIED' | 'REJECTED' | 'DELETE' | null>(null);

  async function act(action: 'VERIFIED' | 'REJECTED' | 'DELETE') {
    if (!accessToken) return;
    setBusy(action);
    try {
      if (action === 'DELETE') await deleteMetric(accessToken, item.id);
      else await reviewMetric(accessToken, item.id, action, note.trim());
      onChanged();
    } catch (cause) {
      onError(messageFor(cause));
    } finally {
      setBusy(null);
    }
  }

  return (
    <Card className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-semibold">{item.metric_fa}</span>
        <span className="tabular-nums">{formatValue(item.metric, item.value)}</span>
        <Badge tone={STATUS_TONE[item.status]}>{item.status_fa}</Badge>
      </div>
      <p className="text-[12.5px] text-[var(--fg-tertiary)]">
        {showOwner && item.owner_title && `${item.owner_title} · `}
        {item.user_name ?? 'عضو'} · {formatDateShort(item.occurred_on)}
        {item.reviewed_by_name && ` · بررسی: ${item.reviewed_by_name}`}
      </p>
      {item.share_rial !== null && item.share_percent !== null && (
        <p className="text-[13.5px] text-[var(--fg-secondary)]">
          سهم فروشنده ({formatNumber(item.share_percent)}٪):{' '}
          <span className="tabular-nums">{formatRial(item.share_rial)}</span>
        </p>
      )}
      {item.note && <p className="text-[14px] leading-[1.9]">{item.note}</p>}
      {item.review_note && (
        <p className="text-[13.5px] text-[var(--fg-secondary)]">
          یادداشت بررسی: {item.review_note}
        </p>
      )}
      {item.can_review && (
        <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
          <Input
            label="یادداشت بررسی"
            hint="برای رد کردن الزامی است"
            value={note}
            onChange={(event) => setNote(event.target.value)}
            className="flex-1"
          />
          <div className="flex gap-2">
            <Button size="sm" loading={busy === 'VERIFIED'} onClick={() => act('VERIFIED')}>
              تأیید
            </Button>
            <Button
              size="sm"
              variant="danger"
              loading={busy === 'REJECTED'}
              disabled={!note.trim()}
              onClick={() => act('REJECTED')}
            >
              رد
            </Button>
          </div>
        </div>
      )}
      {item.is_mine && item.status === 'PENDING' && (
        <button
          type="button"
          onClick={() => act('DELETE')}
          className="self-start text-[12.5px] font-medium text-[var(--fg-danger)] hover:underline"
        >
          حذف این ثبت
        </button>
      )}
    </Card>
  );
}

export { MetricRow };

function messageFor(cause: unknown): string {
  if (cause instanceof ApiError || cause instanceof NetworkError) return cause.message;
  return 'کار انجام نشد. کمی بعد دوباره تلاش کن.';
}
