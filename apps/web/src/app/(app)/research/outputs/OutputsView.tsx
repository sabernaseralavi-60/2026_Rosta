'use client';

import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';

import { Badge, type BadgeTone } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card, CardDescription, CardTitle } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { Input } from '@/components/ui/Input';
import { SkeletonCard } from '@/components/ui/Skeleton';
import { ApiError, NetworkError } from '@/lib/api/client';
import {
  type Output,
  type OutputInput,
  type OutputKind,
  type OutputStatus,
  type Quartile,
  type ReviewStatus,
  createOutput,
  deleteOutput,
  fetchMyOutputs,
  updateOutput,
} from '@/lib/api/research';
import { useSession } from '@/lib/auth/use-session';
import { toPersianDigits } from '@/lib/format/digits';

/**
 * `/research/outputs` — خروجی‌های پژوهشی، FR-RES-02.
 *
 * وضعیت مقاله را نویسنده به‌روز می‌کند؛ هر تغییری که امتیاز را عوض کند
 * (ارسال، پذیرش، انتشار، چارک) به صف راستی‌آزمایی می‌رود. امتیاز فقط پس
 * از تأیید بازبین ثبت می‌شود — این را صفحه صریح می‌گوید، تا «در انتظار
 * راستی‌آزمایی» باگ به نظر نرسد.
 */

const KIND_OPTIONS: { value: OutputKind; label: string }[] = [
  { value: 'JOURNAL', label: 'مقالهٔ مجله' },
  { value: 'CONFERENCE', label: 'مقالهٔ کنفرانس' },
  { value: 'THESIS', label: 'پایان‌نامه' },
  { value: 'REPORT', label: 'گزارش پژوهشی' },
  { value: 'PREPRINT', label: 'پیش‌انتشار' },
];

const STATUS_OPTIONS: { value: OutputStatus; label: string }[] = [
  { value: 'DRAFT', label: 'پیش‌نویس' },
  { value: 'SUBMITTED', label: 'ارسال‌شده' },
  { value: 'UNDER_REVIEW', label: 'در داوری' },
  { value: 'REVISION', label: 'در حال اصلاح' },
  { value: 'ACCEPTED', label: 'پذیرفته‌شده' },
  { value: 'PUBLISHED', label: 'منتشرشده' },
  { value: 'REJECTED', label: 'ردشده' },
];

const REVIEW_TONE: Record<ReviewStatus, BadgeTone> = {
  NONE: 'neutral',
  PENDING: 'warning',
  VERIFIED: 'success',
  REJECTED: 'danger',
};

const EMPTY: OutputInput = {
  kind: 'JOURNAL',
  title: '',
  authors: '',
  status: 'DRAFT',
  venue: null,
  quartile: null,
  doi: null,
  url: null,
  submitted_on: null,
  published_on: null,
};

export function OutputsView() {
  const { accessToken, loading: sessionLoading } = useSession();
  const [outputs, setOutputs] = useState<Output[] | null>(null);
  const [editing, setEditing] = useState<Output | 'new' | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    if (sessionLoading || !accessToken) return;
    fetchMyOutputs(accessToken)
      .then(setOutputs)
      .catch((cause) => setError(messageFor(cause)));
  }, [accessToken, sessionLoading]);

  useEffect(load, [load]);

  async function remove(output: Output) {
    if (!accessToken) return;
    try {
      await deleteOutput(accessToken, output.id);
      load();
    } catch (cause) {
      setError(messageFor(cause));
    }
  }

  return (
    <div className="flex flex-col gap-8">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="flex flex-col gap-1">
          <Link href="/research" className="text-[13px] text-[var(--fg-tertiary)] hover:underline">
            ← مسیر پژوهش
          </Link>
          <h1>مقاله‌های من</h1>
          <p className="text-[15px] text-[var(--fg-secondary)]">
            امتیاز ارسال، پذیرش و انتشار مقاله پس از راستی‌آزمایی منتور یا استاد ثبت می‌شود.
          </p>
        </div>
        {editing === null && <Button onClick={() => setEditing('new')}>ثبت خروجی تازه</Button>}
      </header>

      {editing !== null && accessToken && (
        <OutputForm
          accessToken={accessToken}
          output={editing === 'new' ? null : editing}
          onDone={() => {
            setEditing(null);
            load();
          }}
          onCancel={() => setEditing(null)}
        />
      )}

      {error && (
        <p role="alert" className="text-[13.5px] text-[var(--danger-600)]">
          {error}
        </p>
      )}
      {outputs === null ? (
        !error && <SkeletonCard label="در حال بارگذاری خروجی‌ها" />
      ) : outputs.length === 0 ? (
        <EmptyState
          title="هنوز خروجی‌ای ثبت نکرده‌ای"
          description="مقالهٔ در دست نوشتن را هم می‌توانی به‌صورت پیش‌نویس ثبت کنی."
        />
      ) : (
        <ul className="flex flex-col gap-3">
          {outputs.map((output) => (
            <li key={output.id}>
              <Card className="flex flex-col gap-2">
                <div className="flex flex-wrap items-center gap-1.5">
                  <Badge tone="research">{output.kind_fa}</Badge>
                  <Badge tone="neutral">{output.status_fa}</Badge>
                  {output.quartile && output.quartile !== 'NA' && (
                    <Badge tone="accent">{output.quartile}</Badge>
                  )}
                  {output.is_scored && (
                    <Badge tone={REVIEW_TONE[output.review_status]}>
                      {output.review_status_fa}
                    </Badge>
                  )}
                </div>
                <p className="text-[16px] font-semibold" dir="auto">
                  {output.title}
                </p>
                <p className="text-[13.5px] text-[var(--fg-secondary)]" dir="auto">
                  {output.authors}
                  {output.venue && ` — ${output.venue}`}
                </p>
                {output.doi && (
                  <a
                    href={`https://doi.org/${output.doi}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    dir="ltr"
                    className="self-start text-[13px] text-[var(--brand-700)] underline"
                  >
                    doi:{output.doi}
                  </a>
                )}
                {output.review_status === 'REJECTED' && output.review_note && (
                  <p className="rounded-[var(--radius-md)] bg-[var(--bg-sunken)] p-3 text-[13.5px]">
                    <span className="font-semibold">بازبین: </span>
                    {output.review_note}
                  </p>
                )}
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="text-[13px] text-[var(--fg-tertiary)]">
                    {output.is_scored
                      ? `${toPersianDigits(Number(output.points))} امتیاز پژوهش`
                      : 'این نوع خروجی امتیاز مقاله ندارد'}
                  </span>
                  <div className="flex gap-2">
                    <Button size="sm" variant="secondary" onClick={() => setEditing(output)}>
                      به‌روزرسانی
                    </Button>
                    {output.can_delete && (
                      <Button size="sm" variant="ghost" onClick={() => remove(output)}>
                        حذف
                      </Button>
                    )}
                  </div>
                </div>
              </Card>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function OutputForm({
  accessToken,
  output,
  onDone,
  onCancel,
}: {
  accessToken: string;
  output: Output | null;
  onDone: () => void;
  onCancel: () => void;
}) {
  const [form, setForm] = useState<OutputInput>(
    output
      ? {
          kind: output.kind,
          title: output.title,
          authors: output.authors,
          status: output.status,
          venue: output.venue,
          quartile: output.quartile,
          doi: output.doi,
          url: output.url,
          submitted_on: output.submitted_on,
          published_on: output.published_on,
        }
      : EMPTY,
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function set<K extends keyof OutputInput>(key: K, value: OutputInput[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (output) await updateOutput(accessToken, output.id, form);
      else await createOutput(accessToken, form);
      onDone();
    } catch (cause) {
      setError(messageFor(cause));
    } finally {
      setBusy(false);
    }
  }

  const selectClass =
    'h-10 rounded-[var(--radius-md)] border border-[var(--border-default)] bg-[var(--bg-surface)] px-3 text-[14px]';

  return (
    <Card variant="raised" className="flex flex-col gap-4">
      <CardTitle>{output ? 'به‌روزرسانی خروجی' : 'ثبت خروجی پژوهشی'}</CardTitle>
      <CardDescription>
        برای راستی‌آزمایی سریع، DOI یا پیوند صفحهٔ مقاله یا ایمیل پذیرش را بگذار.
      </CardDescription>
      <form onSubmit={handleSubmit} className="grid gap-3 md:grid-cols-2">
        <div className="flex flex-col gap-1.5">
          <label htmlFor="output-kind" className="text-[13.5px] font-medium">
            نوع
          </label>
          <select
            id="output-kind"
            value={form.kind}
            onChange={(event) => set('kind', event.target.value as OutputKind)}
            className={selectClass}
          >
            {KIND_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
        <div className="flex flex-col gap-1.5">
          <label htmlFor="output-status" className="text-[13.5px] font-medium">
            وضعیت
          </label>
          <select
            id="output-status"
            value={form.status}
            onChange={(event) => set('status', event.target.value as OutputStatus)}
            className={selectClass}
          >
            {STATUS_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
        <div className="md:col-span-2">
          <Input
            label="عنوان"
            value={form.title}
            onChange={(event) => set('title', event.target.value)}
            dir="auto"
            required
          />
        </div>
        <div className="md:col-span-2">
          <Input
            label="نویسندگان"
            hint="به همان ترتیبی که در مقاله آمده"
            value={form.authors}
            onChange={(event) => set('authors', event.target.value)}
            dir="auto"
            required
          />
        </div>
        <Input
          label="مجله یا کنفرانس"
          value={form.venue ?? ''}
          onChange={(event) => set('venue', event.target.value || null)}
          dir="auto"
        />
        {form.kind === 'JOURNAL' && (
          <div className="flex flex-col gap-1.5">
            <label htmlFor="output-quartile" className="text-[13.5px] font-medium">
              چارک مجله
            </label>
            <select
              id="output-quartile"
              value={form.quartile ?? ''}
              onChange={(event) => set('quartile', (event.target.value || null) as Quartile | null)}
              className={selectClass}
            >
              <option value="">نمی‌دانم</option>
              <option value="Q1">Q1</option>
              <option value="Q2">Q2</option>
              <option value="Q3">Q3</option>
              <option value="Q4">Q4</option>
              <option value="NA">نمایه‌نشده</option>
            </select>
          </div>
        )}
        <Input
          label="DOI"
          hint="مثل 10.1016/j.aap.2024.107512"
          value={form.doi ?? ''}
          onChange={(event) => set('doi', event.target.value || null)}
          forceLtr
        />
        <Input
          label="پیوند"
          value={form.url ?? ''}
          onChange={(event) => set('url', event.target.value || null)}
          type="url"
          forceLtr
        />
        <Input
          label="تاریخ ارسال"
          type="date"
          value={form.submitted_on ?? ''}
          onChange={(event) => set('submitted_on', event.target.value || null)}
          forceLtr
        />
        <Input
          label="تاریخ انتشار"
          type="date"
          value={form.published_on ?? ''}
          onChange={(event) => set('published_on', event.target.value || null)}
          forceLtr
        />
        {error && (
          <p role="alert" className="text-[13.5px] text-[var(--danger-600)] md:col-span-2">
            {error}
          </p>
        )}
        <div className="flex gap-2 md:col-span-2">
          <Button type="submit" loading={busy}>
            ذخیره
          </Button>
          <Button type="button" variant="ghost" onClick={onCancel}>
            انصراف
          </Button>
        </div>
      </form>
    </Card>
  );
}

function messageFor(cause: unknown): string {
  if (cause instanceof ApiError || cause instanceof NetworkError) return cause.message;
  return 'کار انجام نشد. کمی بعد دوباره تلاش کن.';
}
