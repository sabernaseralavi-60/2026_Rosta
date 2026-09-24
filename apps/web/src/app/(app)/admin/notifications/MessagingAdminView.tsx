'use client';

import { type FormEvent, useCallback, useEffect, useMemo, useState } from 'react';

import { errorText, ErrorLine, Field, SELECT_CLASS } from '@/components/admin/common';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card, CardTitle } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { SkeletonRow } from '@/components/ui/Skeleton';
import { Textarea } from '@/components/ui/Textarea';
import {
  fetchOutbox,
  fetchTemplates,
  type MessageTemplate,
  type OutboxPage,
  type OutboxStatus,
  previewTemplate,
  retryDead,
  retryMessage,
  saveTemplate,
} from '@/lib/api/admin';
import { useSession } from '@/lib/auth/use-session';
import { formatDateTime } from '@/lib/format/date';
import { toPersianDigits } from '@/lib/format/digits';

/**
 * `/admin/notifications` — صف ارسال (§7.10) و الگوهای پیام (FR-MSG-03).
 *
 * API هر دو از M6 آماده بود و رابطش به پنل مدیریت موکول شد (§13.6).
 * پشتیبانی صف را می‌بیند؛ تلاش دوباره و ویرایش الگو با مدیر است و پاسخ
 * ۴۰۳ سرور با پیام فارسی نشان داده می‌شود.
 */

const STATUSES: {
  value: OutboxStatus;
  label: string;
  tone: 'neutral' | 'info' | 'success' | 'warning' | 'danger';
}[] = [
  { value: 'QUEUED', label: 'در صف', tone: 'info' },
  { value: 'SENDING', label: 'در حال ارسال', tone: 'info' },
  { value: 'SENT', label: 'ارسال‌شده', tone: 'success' },
  { value: 'FAILED', label: 'ناموفق (تلاش دوباره)', tone: 'warning' },
  { value: 'DEAD', label: 'ارسال‌نشدهٔ نهایی', tone: 'danger' },
];
const CHANNEL_LABELS: Record<string, string> = {
  IN_APP: 'داخل سامانه',
  EMAIL: 'ایمیل',
  SMS: 'پیامک',
  TELEGRAM: 'تلگرام',
  EITAA: 'ایتا',
  WHATSAPP: 'واتساپ',
};

export function MessagingAdminView() {
  const [tab, setTab] = useState<'outbox' | 'templates'>('outbox');
  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-1">
        <h1>صف ارسال و الگوهای پیام</h1>
        <p className="text-[14px] text-[var(--fg-secondary)]">
          چرا پیامکی نرسید، و متن هر اعلان در هر کانال.
        </p>
      </header>
      <div role="tablist" aria-label="بخش" className="flex gap-2">
        {(
          [
            ['outbox', 'صف ارسال'],
            ['templates', 'الگوهای پیام'],
          ] as const
        ).map(([key, label]) => (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={tab === key}
            onClick={() => setTab(key)}
            className="rounded-[var(--radius-full)] px-4 py-1.5 text-[14px] aria-selected:bg-[var(--brand-600)] aria-selected:text-[var(--fg-on-brand)] aria-[selected=false]:bg-[var(--bg-sunken)]"
          >
            {label}
          </button>
        ))}
      </div>
      {tab === 'outbox' ? <OutboxPanel /> : <TemplatesPanel />}
    </div>
  );
}

function OutboxPanel() {
  const { accessToken } = useSession();
  const [status, setStatus] = useState<OutboxStatus | ''>('DEAD');
  const [channel, setChannel] = useState('');
  const [page, setPage] = useState(1);
  const [data, setData] = useState<OutboxPage | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(() => {
    if (!accessToken) return;
    fetchOutbox(accessToken, { status: status || undefined, channel: channel || undefined, page })
      .then(setData)
      .catch((cause) => setError(errorText(cause)));
  }, [accessToken, status, channel, page]);

  useEffect(load, [load]);

  async function retry(id: string) {
    if (!accessToken) return;
    setError(null);
    try {
      await retryMessage(accessToken, id);
      setNotice('پیام دوباره در صف قرار گرفت.');
      load();
    } catch (cause) {
      setError(errorText(cause));
    }
  }

  async function retryAll() {
    if (!accessToken) return;
    if (
      !window.confirm(
        'همهٔ پیام‌های ارسال‌نشدهٔ نهایی دوباره در صف قرار بگیرند؟ فقط پس از رفع قطعی کانال.',
      )
    )
      return;
    setError(null);
    try {
      const result = await retryDead(accessToken, channel || undefined);
      setNotice(`${toPersianDigits(result.retried)} پیام دوباره در صف قرار گرفت.`);
      load();
    } catch (cause) {
      setError(errorText(cause));
    }
  }

  return (
    <div className="flex flex-col gap-4">
      {data && (
        <ul className="flex flex-wrap gap-2">
          {STATUSES.map((item) => (
            <li key={item.value}>
              <button
                type="button"
                onClick={() => {
                  setStatus(item.value);
                  setPage(1);
                }}
                aria-pressed={status === item.value}
                className="rounded-[var(--radius-md)] border border-[var(--border-subtle)] px-3 py-1.5 text-[13px] aria-pressed:border-[var(--brand-600)]"
              >
                {item.label}: {toPersianDigits(data.counts[item.value] ?? 0)}
              </button>
            </li>
          ))}
        </ul>
      )}
      <div className="flex flex-wrap items-end gap-3">
        <Field label="وضعیت">
          <select
            className={SELECT_CLASS}
            value={status}
            onChange={(event) => {
              setStatus(event.target.value as OutboxStatus | '');
              setPage(1);
            }}
          >
            <option value="">همه</option>
            {STATUSES.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>
        </Field>
        <Field label="کانال">
          <select
            className={SELECT_CLASS}
            value={channel}
            onChange={(event) => {
              setChannel(event.target.value);
              setPage(1);
            }}
          >
            <option value="">همه</option>
            {['SMS', 'EMAIL', 'TELEGRAM', 'EITAA'].map((value) => (
              <option key={value} value={value}>
                {CHANNEL_LABELS[value]}
              </option>
            ))}
          </select>
        </Field>
        <Button variant="secondary" onClick={() => void retryAll()}>
          تلاش دوباره برای همهٔ ارسال‌نشده‌ها
        </Button>
      </div>
      {notice && (
        <p role="status" className="text-[13.5px] text-[var(--fg-success)]">
          {notice}
        </p>
      )}
      {error && <ErrorLine>{error}</ErrorLine>}
      {!data && !error && <SkeletonRow label="در حال بارگذاری صف" />}
      {data && data.items.length === 0 && (
        <EmptyState
          title="پیامی با این فیلتر نیست"
          description="صف در این وضعیت خالی است — خبر خوبی است."
        />
      )}
      {data && data.items.length > 0 && (
        <ul className="flex flex-col divide-y divide-[var(--border-subtle)] rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-surface)]">
          {data.items.map((message) => {
            const meta = STATUSES.find((item) => item.value === message.status);
            return (
              <li
                key={message.id}
                className="flex flex-wrap items-start justify-between gap-3 px-4 py-3"
              >
                <div className="flex min-w-0 flex-col gap-0.5 text-[13.5px]">
                  <span className="flex flex-wrap items-center gap-2">
                    <Badge tone={meta?.tone ?? 'neutral'}>{message.status_fa}</Badge>
                    <span>{CHANNEL_LABELS[message.channel] ?? message.channel}</span>
                    <span className="font-mono text-[12px] text-[var(--fg-tertiary)]" dir="ltr">
                      {message.template}
                    </span>
                  </span>
                  <span className="text-[12.5px] text-[var(--fg-tertiary)]">
                    <span dir="ltr">{message.recipient_masked}</span> ·{' '}
                    {toPersianDigits(message.attempts)} تلاش · {formatDateTime(message.created_at)}
                  </span>
                  {message.last_error && (
                    <span className="break-words text-[12.5px] text-[var(--fg-danger)]" dir="auto">
                      {message.last_error}
                    </span>
                  )}
                </div>
                {(message.status === 'DEAD' || message.status === 'FAILED') && (
                  <Button variant="ghost" size="sm" onClick={() => void retry(message.id)}>
                    تلاش دوباره
                  </Button>
                )}
              </li>
            );
          })}
        </ul>
      )}
      {data && (data.has_next || page > 1) && (
        <div className="flex justify-between">
          <Button
            variant="secondary"
            size="sm"
            disabled={page <= 1}
            onClick={() => setPage(page - 1)}
          >
            قبلی
          </Button>
          <Button
            variant="secondary"
            size="sm"
            disabled={!data.has_next}
            onClick={() => setPage(page + 1)}
          >
            بعدی
          </Button>
        </div>
      )}
    </div>
  );
}

function TemplatesPanel() {
  const { accessToken } = useSession();
  const [templates, setTemplates] = useState<MessageTemplate[] | null>(null);
  const [selected, setSelected] = useState<string>('');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!accessToken) return;
    fetchTemplates(accessToken)
      .then((rows) => {
        setTemplates(rows);
        setSelected((current) => current || (rows[0] ? `${rows[0].code}/${rows[0].channel}` : ''));
      })
      .catch((cause) => setError(errorText(cause)));
  }, [accessToken]);

  const current = useMemo(
    () => templates?.find((t) => `${t.code}/${t.channel}` === selected) ?? null,
    [templates, selected],
  );

  if (error && !templates) return <ErrorLine>{error}</ErrorLine>;
  if (!templates || !accessToken) return <SkeletonRow label="در حال بارگذاری الگوها" />;

  return (
    <div className="grid gap-6 lg:grid-cols-[18rem_1fr]">
      <Field label="الگو">
        <select
          className={`${SELECT_CLASS} lg:h-auto`}
          size={12}
          value={selected}
          onChange={(event) => setSelected(event.target.value)}
        >
          {templates.map((t) => (
            <option key={`${t.code}/${t.channel}`} value={`${t.code}/${t.channel}`}>
              {(t.kind_title_fa ?? t.code) + ' — ' + (CHANNEL_LABELS[t.channel] ?? t.channel)}
            </option>
          ))}
        </select>
      </Field>
      {current && (
        <TemplateEditor
          key={selected}
          template={current}
          token={accessToken}
          onSaved={(saved) =>
            setTemplates((rows) =>
              (rows ?? []).map((t) =>
                t.code === saved.code && t.channel === saved.channel ? saved : t,
              ),
            )
          }
        />
      )}
    </div>
  );
}

function TemplateEditor({
  template,
  token,
  onSaved,
}: {
  template: MessageTemplate;
  token: string;
  onSaved: (template: MessageTemplate) => void;
}) {
  const [subject, setSubject] = useState(template.subject ?? '');
  const [body, setBody] = useState(template.body);
  const [active, setActive] = useState(template.is_active);
  const [preview, setPreview] = useState<{
    subject: string | null;
    body: string;
    sms_parts: number | null;
  } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  async function showPreview() {
    setError(null);
    try {
      setPreview(
        await previewTemplate(token, {
          code: template.code,
          channel: template.channel,
          subject: subject || null,
          body,
        }),
      );
    } catch (cause) {
      setError(errorText(cause));
    }
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setSaved(false);
    try {
      onSaved(
        await saveTemplate(token, {
          code: template.code,
          channel: template.channel,
          subject: subject || null,
          body,
          is_active: active,
        }),
      );
      setSaved(true);
    } catch (cause) {
      setError(errorText(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="flex flex-col gap-4">
      <CardTitle className="text-[16px]">
        {template.kind_title_fa ?? template.code} —{' '}
        {CHANNEL_LABELS[template.channel] ?? template.channel}
      </CardTitle>
      <p className="text-[12.5px] text-[var(--fg-tertiary)]">
        متغیرهای مجاز:{' '}
        {template.variables.map((name) => (
          <code key={name} className="mx-0.5 rounded bg-[var(--bg-sunken)] px-1" dir="ltr">
            {`{{${name}}}`}
          </code>
        ))}
      </p>
      <form onSubmit={save} className="flex flex-col gap-3">
        {template.channel !== 'SMS' && (
          <Textarea
            label="عنوان"
            rows={1}
            value={subject}
            onChange={(event) => setSubject(event.target.value)}
          />
        )}
        <Textarea
          label="متن"
          rows={5}
          value={body}
          onChange={(event) => setBody(event.target.value)}
        />
        <label className="flex items-center gap-2 text-[14px]">
          <input
            type="checkbox"
            checked={active}
            onChange={(event) => setActive(event.target.checked)}
          />
          فعال
        </label>
        {error && <ErrorLine>{error}</ErrorLine>}
        {saved && (
          <p role="status" className="text-[13.5px] text-[var(--fg-success)]">
            ذخیره شد و در لاگ حسابرسی ثبت شد.
          </p>
        )}
        <div className="flex flex-wrap gap-2">
          <Button type="button" variant="secondary" onClick={() => void showPreview()}>
            پیش‌نمایش
          </Button>
          <Button type="submit" loading={busy}>
            ذخیره
          </Button>
        </div>
      </form>
      {preview && (
        <div className="rounded-[var(--radius-md)] border border-dashed border-[var(--border-default)] p-3 text-[14px]">
          {preview.subject && <p className="font-semibold">{preview.subject}</p>}
          <p className="whitespace-pre-line">{preview.body}</p>
          {preview.sms_parts !== null && (
            <p className="mt-2 text-[12.5px] text-[var(--fg-tertiary)]">
              {toPersianDigits(preview.sms_parts)} بخش پیامک
            </p>
          )}
        </div>
      )}
    </Card>
  );
}
