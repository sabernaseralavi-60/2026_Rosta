'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react';

import { ErrorLine, errorText } from '@/components/admin/common';
import { SectionHeader } from '@/components/teach/common';
import { useOffering } from '@/components/teach/OfferingFrame';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { EmptyState } from '@/components/ui/EmptyState';
import { SkeletonRow } from '@/components/ui/Skeleton';
import {
  fetchThreads,
  MESSAGE_MAX,
  openChannel,
  openThread,
  sendToAudience,
  type Thread,
} from '@/lib/api/messaging';
import { toPersianDigits } from '@/lib/format/digits';

type Mode = 'ALL' | 'SELECTED';

/**
 * پیام به دانشجویان یک ارائه.
 *
 * «به همهٔ کلاس» یک پست در کانال درس است (دانشجو فقط می‌خواند). «به منتخب» برای هر نفر یک
 * گفت‌وگوی خصوصی می‌سازد و همان‌جا می‌تواند پاسخ بدهد. دانشجوی بدون حساب (هنوز فعال‌سازی
 * نکرده) پیام نمی‌گیرد؛ با شمارنده نشان داده می‌شود تا ساکت از دست نرود.
 */
export function OfferingMessagesView() {
  const { offering, token } = useOffering();
  const router = useRouter();
  const [threads, setThreads] = useState<Thread[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [mode, setMode] = useState<Mode>('ALL');
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [body, setBody] = useState('');
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    fetchThreads(offering.id, token)
      .then(setThreads)
      .catch((cause) => setError(errorText(cause)));
  }, [offering.id, token]);

  useEffect(load, [load]);

  const withAccount = useMemo(() => (threads ?? []).filter((t) => t.has_account), [threads]);
  const withoutAccount = (threads ?? []).length - withAccount.length;

  function toggle(studentId: string) {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(studentId)) next.delete(studentId);
      else next.add(studentId);
      return next;
    });
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const result = await sendToAudience(
        offering.id,
        { audience: mode, student_ids: mode === 'SELECTED' ? [...selected] : [], body },
        token,
      );
      setBody('');
      setSelected(new Set());
      setNotice(
        `برای ${toPersianDigits(result.sent)} نفر ارسال شد.` +
          (mode === 'ALL' && result.skipped_no_account > 0
            ? ` ${toPersianDigits(result.skipped_no_account)} نفر هنوز حساب فعال ندارند و نمی‌بینند.`
            : ''),
      );
      load();
    } catch (cause) {
      setError(errorText(cause));
    } finally {
      setBusy(false);
    }
  }

  async function openConversation(studentId: string) {
    setError(null);
    try {
      const { id } = await openThread(offering.id, studentId, token);
      router.push(`/messages/${id}`);
    } catch (cause) {
      setError(errorText(cause));
    }
  }

  async function openAnnouncementChannel() {
    setError(null);
    try {
      const { id } = await openChannel(offering.id, token);
      router.push(`/messages/${id}`);
    } catch (cause) {
      setError(errorText(cause));
    }
  }

  const canSend = body.trim().length > 0 && (mode === 'ALL' || selected.size > 0);

  return (
    <div className="flex flex-col gap-8">
      <SectionHeader
        title="پیام‌ها"
        description="جایگزین گروه تلگرام درس: پیام به همه، به چند نفر، یا گفت‌وگوی خصوصی با هر دانشجو."
      />

      <form
        onSubmit={submit}
        className="flex flex-col gap-4 rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-5"
      >
        <fieldset className="flex flex-wrap gap-4 text-[14px]">
          <legend className="sr-only">گیرندگان</legend>
          <label className="flex items-center gap-2">
            <input type="radio" checked={mode === 'ALL'} onChange={() => setMode('ALL')} />
            همهٔ کلاس (کانال درس)
          </label>
          <label className="flex items-center gap-2">
            <input
              type="radio"
              checked={mode === 'SELECTED'}
              onChange={() => setMode('SELECTED')}
            />
            دانشجویان انتخاب‌شده ({toPersianDigits(selected.size)})
          </label>
        </fieldset>
        <label htmlFor="audience-body" className="sr-only">
          متن پیام
        </label>
        <textarea
          id="audience-body"
          value={body}
          onChange={(event) => setBody(event.target.value)}
          maxLength={MESSAGE_MAX}
          rows={4}
          placeholder={
            mode === 'ALL'
              ? 'پیام برای همهٔ کلاس…'
              : 'پیام برای دانشجویان انتخاب‌شده (در گفت‌وگوی خصوصی هرکدام)…'
          }
          className="w-full rounded-[var(--radius-md)] border border-[var(--border-default)] bg-[var(--bg-canvas)] p-3 text-[15px] leading-[1.9]"
        />
        {error && <ErrorLine>{error}</ErrorLine>}
        {notice && (
          <p role="status" className="text-[14px] text-[var(--fg-success)]">
            {notice}
          </p>
        )}
        <div className="flex flex-wrap items-center justify-between gap-3">
          <button
            type="button"
            onClick={() => void openAnnouncementChannel()}
            className="text-[13.5px] text-[var(--fg-brand)] underline"
          >
            دیدن کانال درس
          </button>
          <Button type="submit" loading={busy} loadingLabel="در حال ارسال…" disabled={!canSend}>
            ارسال
          </Button>
        </div>
      </form>

      <section aria-labelledby="threads-title" className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 id="threads-title" className="text-[18px]">
            دانشجویان
          </h2>
          {mode === 'SELECTED' && withAccount.length > 0 && (
            <button
              type="button"
              className="text-[13.5px] text-[var(--fg-brand)] underline"
              onClick={() =>
                setSelected(
                  selected.size === withAccount.length
                    ? new Set()
                    : new Set(withAccount.map((t) => t.student_id as string)),
                )
              }
            >
              {selected.size === withAccount.length ? 'برداشتن همه' : 'انتخاب همه'}
            </button>
          )}
        </div>

        {!threads && !error && <SkeletonRow />}
        {threads && threads.length === 0 && (
          <EmptyState
            title="هنوز دانشجویی در این ارائه نیست"
            description="فهرست دانشجویان را با اسکریپت ورود از اکسل یا از صفحهٔ «دانشجویان» وارد کن."
            action={
              <Link
                href={`/teach/offerings/${offering.id}/students`}
                className="text-[14px] font-medium text-[var(--fg-brand)]"
              >
                صفحهٔ دانشجویان
              </Link>
            }
          />
        )}
        <ul className="flex flex-col divide-y divide-[var(--border-subtle)] rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-surface)]">
          {threads?.map((thread, index) => (
            <li
              key={thread.student_id ?? `no-account-${index}`}
              className="flex items-center gap-3 px-4 py-3"
            >
              {mode === 'SELECTED' && thread.student_id && (
                <input
                  type="checkbox"
                  aria-label={`انتخاب ${thread.name}`}
                  checked={selected.has(thread.student_id)}
                  onChange={() => toggle(thread.student_id as string)}
                />
              )}
              <div className="flex min-w-0 flex-1 flex-col">
                <span className="text-[14.5px] font-medium">{thread.name}</span>
                <span className="truncate text-[13px] text-[var(--fg-secondary)]">
                  {thread.has_account
                    ? (thread.last_preview ?? 'هنوز گفت‌وگویی نیست')
                    : 'هنوز حساب خود را فعال نکرده'}
                </span>
              </div>
              {thread.unread > 0 && (
                <Badge tone="brand">{toPersianDigits(thread.unread)} تازه</Badge>
              )}
              {thread.has_account && thread.student_id ? (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => void openConversation(thread.student_id as string)}
                >
                  گفت‌وگو
                </Button>
              ) : (
                <Badge tone="neutral">بدون حساب</Badge>
              )}
            </li>
          ))}
        </ul>
        {withoutAccount > 0 && (
          <p className="text-[13px] text-[var(--fg-tertiary)]">
            {toPersianDigits(withoutAccount)} نفر از فهرست هنوز با موبایل و شمارهٔ دانشجویی حساب
            فعال نکرده‌اند؛ پیام به آن‌ها نمی‌رسد.
          </p>
        )}
      </section>
    </div>
  );
}
