'use client';

import { useSearchParams } from 'next/navigation';
import { type FormEvent, type ReactNode, useCallback, useEffect, useState } from 'react';

import { errorText, ErrorLine, FactList } from '@/components/admin/common';
import { RequestTimeline } from '@/components/domain/RequestTimeline';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { Input } from '@/components/ui/Input';
import { SkeletonRow } from '@/components/ui/Skeleton';
import { Textarea } from '@/components/ui/Textarea';
import {
  fetchInbox,
  fetchInboxItem,
  INBOX_PAGE_SIZE,
  type InboxDetail,
  type InboxItem,
  type InboxPage,
  type IntakeKind,
  type IntakeStatus,
  KIND_LABELS,
  NEED_TYPE_LABELS,
  STATUS_LABELS,
  STATUS_TONES,
  STATUSES,
  updateInboxItem,
} from '@/lib/api/inbox';
import { useSession } from '@/lib/auth/use-session';
import { cn } from '@/lib/cn';
import { formatDateShort, formatRelative } from '@/lib/format/date';
import { toPersianDigits } from '@/lib/format/digits';

const KINDS: { value: IntakeKind | ''; label: string }[] = [
  { value: '', label: 'همه' },
  { value: 'INTAKE', label: KIND_LABELS.INTAKE },
  { value: 'COLLABORATION', label: KIND_LABELS.COLLABORATION },
];

/** برچسب کلیدهای فرم؛ کلید ناشناخته همان‌طور که هست نشان داده می‌شود (فرم‌ها گسترش می‌یابند). */
const PAYLOAD_LABELS: Record<string, string> = {
  expected_result: 'نتیجهٔ مورد انتظار',
  sector: 'حوزه',
  has_data: 'داده دارد؟',
  timeline: 'بازهٔ زمانی',
  budget: 'بودجه',
  notes: 'توضیح بیشتر',
  specialty: 'تخصص',
  skills: 'مهارت‌ها',
  experience: 'سابقه',
  interests: 'علاقه‌مندی‌ها',
  ways: 'شکل همکاری',
  hours_per_week: 'زمان در هفته',
  portfolio_url: 'نمونه‌کار',
};

const HAS_DATA: Record<string, string> = { YES: 'بله', NO: 'خیر', UNSURE: 'مطمئن نیستم' };

/**
 * `/admin/inbox` — صندوق درخواست‌های ورودی (ADR-0032).
 *
 * «مسئله / نیاز» و «همکاری» بی‌ورود ثبت می‌شوند و اینجا می‌رسند. مالک وضعیت می‌دهد، پیامی
 * برای مشتری می‌نویسد (در داشبورد او دیده می‌شود) و یادداشت خصوصی می‌گذارد (هرگز دیده نمی‌شود).
 * نشان «نیاز به پیگیری» یعنی بیش از سه روز دست‌نخورده.
 */
export function InboxView() {
  const { accessToken } = useSession();
  // پیوند از داشبورد مالک: `?q=Q-1001` — کد را جست‌وجو می‌کند و روی «همه» می‌ماند.
  const initialQuery = useSearchParams().get('q') ?? '';
  const [kind, setKind] = useState<IntakeKind | ''>('');
  const [status, setStatus] = useState<IntakeStatus | ''>(initialQuery ? '' : 'NEW');
  const [query, setQuery] = useState(initialQuery);
  const [debounced, setDebounced] = useState(initialQuery);
  const [offset, setOffset] = useState(0);
  const [page, setPage] = useState<InboxPage | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(query), 300);
    return () => clearTimeout(timer);
  }, [query]);

  useEffect(() => setOffset(0), [kind, status, debounced]);

  const load = useCallback(() => {
    if (!accessToken) return;
    setError(null);
    fetchInbox(accessToken, {
      kind: kind || undefined,
      status: status || undefined,
      q: debounced,
      offset,
    })
      .then(setPage)
      .catch((cause) => setError(errorText(cause)));
  }, [accessToken, kind, status, debounced, offset]);

  useEffect(load, [load]);

  const counts = page?.counts;
  const total = page?.total ?? 0;

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-1">
        <h1>صندوق درخواست‌ها</h1>
        <p className="max-w-[70ch] text-[14px] text-[var(--fg-secondary)]">
          مسئله و نیازِ بازدیدکنندگان و درخواست‌های همکاری. هر درخواست یک کد پیگیری دارد که مشتری با
          آن (و راه تماسش) وضعیت را می‌بیند.
        </p>
      </header>

      <div className="flex flex-wrap items-end gap-4">
        <div className="flex flex-wrap gap-2" role="group" aria-label="نوع درخواست">
          {KINDS.map((item) => (
            <Chip
              key={item.label}
              pressed={kind === item.value}
              onClick={() => setKind(item.value)}
            >
              {item.label}
            </Chip>
          ))}
        </div>
        <div className="w-full sm:w-72">
          <Input
            label="جست‌وجو"
            type="search"
            placeholder="نام، سازمان، کد، شماره یا متن"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </div>
      </div>

      <div className="flex flex-wrap gap-2" role="group" aria-label="وضعیت">
        <Chip pressed={status === ''} onClick={() => setStatus('')}>
          همه
        </Chip>
        {STATUSES.map((value) => (
          <Chip key={value} pressed={status === value} onClick={() => setStatus(value)}>
            {STATUS_LABELS[value]}
            {counts && (
              <span className="ms-1.5 tabular-nums">{toPersianDigits(counts[value])}</span>
            )}
          </Chip>
        ))}
      </div>

      {error && <ErrorLine>{error}</ErrorLine>}
      {!page && !error && <SkeletonRow label="در حال بارگذاری درخواست‌ها" />}
      {page && page.items.length === 0 && (
        <EmptyState
          title={status === 'NEW' ? 'درخواست تازه‌ای نیست' : 'موردی پیدا نشد'}
          description={
            status === 'NEW'
              ? 'درخواست‌های تازه از صفحهٔ «طرح مسئله / نیاز» و «همکاری با ما» اینجا می‌آید.'
              : 'فیلتر یا جست‌وجو را عوض کن.'
          }
        />
      )}
      {page && page.items.length > 0 && accessToken && (
        <ul className="flex flex-col gap-3">
          {page.items.map((item) => (
            <li key={item.id}>
              <Row
                item={item}
                token={accessToken}
                open={openId === item.id}
                onToggle={() => setOpenId(openId === item.id ? null : item.id)}
                onChanged={load}
              />
            </li>
          ))}
        </ul>
      )}
      {page && total > INBOX_PAGE_SIZE && (
        <nav aria-label="صفحه‌بندی" className="flex items-center justify-between gap-3">
          <Button
            variant="secondary"
            size="sm"
            disabled={offset === 0}
            onClick={() => setOffset(Math.max(0, offset - INBOX_PAGE_SIZE))}
          >
            قبلی
          </Button>
          <span className="text-[13px] text-[var(--fg-secondary)]">
            {toPersianDigits(offset + 1)} تا{' '}
            {toPersianDigits(Math.min(offset + INBOX_PAGE_SIZE, total))} از {toPersianDigits(total)}
          </span>
          <Button
            variant="secondary"
            size="sm"
            disabled={offset + INBOX_PAGE_SIZE >= total}
            onClick={() => setOffset(offset + INBOX_PAGE_SIZE)}
          >
            بعدی
          </Button>
        </nav>
      )}
    </div>
  );
}

function Chip({
  pressed,
  onClick,
  children,
}: {
  pressed: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      aria-pressed={pressed}
      onClick={onClick}
      className={cn(
        'rounded-[var(--radius-sm)] border px-3 py-1.5 text-[13.5px]',
        pressed
          ? 'border-[var(--brand-600)] bg-[var(--brand-50)] font-semibold text-[var(--fg-brand)]'
          : 'border-[var(--border-default)] text-[var(--fg-secondary)]',
      )}
    >
      {children}
    </button>
  );
}

function Row({
  item,
  token,
  open,
  onToggle,
  onChanged,
}: {
  item: InboxItem;
  token: string;
  open: boolean;
  onToggle: () => void;
  onChanged: () => void;
}) {
  const panelId = `intake-${item.id}`;
  return (
    <Card className="flex flex-col gap-3 p-4">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={onToggle}
        className="flex flex-col gap-2 text-start"
      >
        <span className="flex flex-wrap items-center gap-2">
          <Badge tone={STATUS_TONES[item.status]}>{STATUS_LABELS[item.status]}</Badge>
          <Badge tone={item.kind === 'INTAKE' ? 'brand' : 'accent'}>{KIND_LABELS[item.kind]}</Badge>
          {item.stale && <Badge tone="danger">نیاز به پیگیری</Badge>}
          <span className="font-mono text-[13px] text-[var(--fg-tertiary)]" dir="ltr">
            {item.tracking_code}
          </span>
        </span>
        <span className="text-[15px] font-semibold">
          {item.contact_name}
          {item.organization && (
            <span className="ms-2 text-[13.5px] font-normal text-[var(--fg-secondary)]">
              {item.organization}
            </span>
          )}
        </span>
        <span className="line-clamp-2 max-w-[80ch] text-[14px] text-[var(--fg-secondary)]">
          {item.summary}
        </span>
        <FactList
          className="text-[var(--fg-tertiary)]"
          items={[
            <span key="d">ثبت: {formatDateShort(item.created_at)}</span>,
            <span key="u">آخرین رسیدگی: {formatRelative(item.updated_at)}</span>,
            item.need_type && (
              <span key="n">نوع: {NEED_TYPE_LABELS[item.need_type] ?? item.need_type}</span>
            ),
          ]}
        />
      </button>
      {open && (
        <div id={panelId}>
          <Detail id={item.id} token={token} onChanged={onChanged} />
        </div>
      )}
    </Card>
  );
}

function Detail({ id, token, onChanged }: { id: string; token: string; onChanged: () => void }) {
  const [detail, setDetail] = useState<InboxDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<IntakeStatus>('NEW');
  const [publicNote, setPublicNote] = useState('');
  const [ownerNote, setOwnerNote] = useState('');
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  const apply = useCallback((next: InboxDetail) => {
    setDetail(next);
    setStatus(next.status);
    setOwnerNote(next.owner_note ?? '');
    setPublicNote('');
  }, []);

  useEffect(() => {
    fetchInboxItem(token, id)
      .then(apply)
      .catch((cause) => setError(errorText(cause)));
  }, [token, id, apply]);

  if (error) return <ErrorLine>{error}</ErrorLine>;
  if (!detail) return <SkeletonRow label="در حال بارگذاری جزئیات" />;

  const dirty =
    status !== detail.status ||
    publicNote.trim().length > 0 ||
    ownerNote.trim() !== (detail.owner_note ?? '');

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!detail) return;
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      const next = await updateInboxItem(token, id, {
        ...(status !== detail.status ? { status } : {}),
        ...(ownerNote.trim() !== (detail.owner_note ?? '') ? { owner_note: ownerNote.trim() } : {}),
        ...(publicNote.trim() ? { public_note: publicNote.trim() } : {}),
      });
      apply(next);
      setSaved(true);
      onChanged();
    } catch (cause) {
      setError(errorText(cause));
    } finally {
      setSaving(false);
    }
  }

  const payload = Object.entries(detail.payload).filter(
    ([, value]) => value !== '' && value != null,
  );

  return (
    <div className="flex flex-col gap-5 border-t border-[var(--border-subtle)] pt-4">
      <dl className="grid grid-cols-1 gap-x-6 gap-y-2 text-[14px] sm:grid-cols-[auto_1fr]">
        <dt className="text-[var(--fg-secondary)]">تماس</dt>
        <dd className="flex flex-wrap gap-x-4">
          {detail.contact_mobile && (
            <a href={`tel:${detail.contact_mobile}`} dir="ltr" className="text-[var(--fg-brand)]">
              {detail.contact_mobile}
            </a>
          )}
          {detail.contact_email && (
            <a href={`mailto:${detail.contact_email}`} dir="ltr" className="text-[var(--fg-brand)]">
              {detail.contact_email}
            </a>
          )}
        </dd>
        {detail.person_code && (
          <>
            <dt className="text-[var(--fg-secondary)]">کد شخصی</dt>
            <dd dir="ltr" className="text-start font-mono">
              {detail.person_code}
            </dd>
          </>
        )}
        {detail.services.length > 0 && (
          <>
            <dt className="text-[var(--fg-secondary)]">خدمات</dt>
            <dd>{detail.services.join('، ')}</dd>
          </>
        )}
        <dt className="text-[var(--fg-secondary)]">شرح</dt>
        <dd className="max-w-[80ch] whitespace-pre-line leading-[1.9]">{detail.summary}</dd>
        {payload.map(([key, value]) => (
          <div key={key} className="contents">
            <dt className="text-[var(--fg-secondary)]">{PAYLOAD_LABELS[key] ?? key}</dt>
            <dd className="max-w-[80ch] whitespace-pre-line leading-[1.9]">
              {payloadText(key, value)}
            </dd>
          </div>
        ))}
      </dl>

      <section aria-label="تاریخچه" className="flex flex-col gap-2">
        <h3 className="text-[15px] font-semibold">تاریخچهٔ رسیدگی</h3>
        <RequestTimeline
          createdAt={detail.created_at}
          events={detail.events}
          labels={STATUS_LABELS}
        />
      </section>

      <form onSubmit={save} className="flex flex-col gap-4">
        <fieldset className="flex flex-col gap-2">
          <legend className="text-[13.5px] font-medium">وضعیت</legend>
          <div className="flex flex-wrap gap-2">
            {STATUSES.map((value) => (
              <label
                key={value}
                className={cn(
                  'cursor-pointer rounded-[var(--radius-sm)] border px-3 py-1.5 text-[13.5px]',
                  'has-[:focus-visible]:outline has-[:focus-visible]:outline-2',
                  status === value
                    ? 'border-[var(--brand-600)] bg-[var(--brand-50)] font-semibold text-[var(--fg-brand)]'
                    : 'border-[var(--border-default)] text-[var(--fg-secondary)]',
                )}
              >
                <input
                  type="radio"
                  name={`status-${id}`}
                  value={value}
                  checked={status === value}
                  onChange={() => setStatus(value)}
                  className="sr-only"
                />
                {STATUS_LABELS[value]}
              </label>
            ))}
          </div>
        </fieldset>
        <Textarea
          label="پیام برای مشتری"
          hint="در داشبورد و صفحهٔ پیگیریِ مشتری دیده می‌شود. کوتاه و روشن بنویس."
          value={publicNote}
          onChange={(event) => setPublicNote(event.target.value)}
          maxLength={1000}
          rows={3}
        />
        <Textarea
          label="یادداشت خصوصی"
          hint="فقط تو می‌بینی؛ به مشتری هرگز نمی‌رسد."
          value={ownerNote}
          onChange={(event) => setOwnerNote(event.target.value)}
          maxLength={4000}
          rows={3}
        />
        <div className="flex flex-wrap items-center gap-3">
          <Button type="submit" loading={saving} disabled={!dirty}>
            ذخیره
          </Button>
          {saved && (
            <span role="status" className="text-[13.5px] text-[var(--fg-success)]">
              ذخیره شد.
            </span>
          )}
        </div>
      </form>
    </div>
  );
}

function payloadText(key: string, value: unknown): string {
  if (key === 'has_data' && typeof value === 'string') return HAS_DATA[value] ?? value;
  if (Array.isArray(value)) return value.join('، ');
  return String(value);
}
