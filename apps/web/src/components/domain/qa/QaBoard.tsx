'use client';

import { type FormEvent, useCallback, useEffect, useState } from 'react';

import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { ChipGroup } from '@/components/ui/ChipGroup';
import { EmptyState } from '@/components/ui/EmptyState';
import { Input } from '@/components/ui/Input';
import { SkeletonCard } from '@/components/ui/Skeleton';
import { Textarea } from '@/components/ui/Textarea';
import { ApiError, NetworkError } from '@/lib/api/client';
import {
  type QaAuthor,
  type QaFilter,
  type QaReply,
  type QaThreadDetail,
  type QaThreadSummary,
  createQaThread,
  deleteQaReply,
  deleteQaThread,
  endorseQaReply,
  fetchQaThread,
  fetchQaThreads,
  postQaReply,
  setQaResolved,
  voteQaReply,
} from '@/lib/api/qa';
import { useSession } from '@/lib/auth/use-session';
import { cn } from '@/lib/cn';
import { formatRelative } from '@/lib/format/date';
import { toPersianDigits } from '@/lib/format/digits';

/**
 * پرسش‌وپاسخ درس — FR-EDU-07، ADR-0024 برش ج.
 *
 * دو جا سوار می‌شود: صفحهٔ `/courses/[offeringId]/qa` (همهٔ درس، با انتخاب هفته
 * هنگام پرسیدن) و برگهٔ «پرسش‌وپاسخ» صفحهٔ هفته (`weekNumber` ثابت). هر پرسش
 * همان‌جا در فهرست باز می‌شود، نه صفحهٔ جدا — روی موبایل هم دو ستون لازم نیست.
 *
 * «چه کسی چه می‌تواند بکند» را سرور می‌گوید (`can_*`، `is_manager`)؛ این‌جا
 * بازسازی نمی‌شود. ترتیب پاسخ‌ها هم از سرور می‌آید (رسمی، تأییدشده، پررأی)،
 * پس پس از هر رأی یا تأیید پرسش دوباره خوانده می‌شود، نه اینکه محلی جابه‌جا شود.
 */

const PAGE_SIZE = 20;
const MAX_TEXT = 4000;

const FILTERS: { value: QaFilter; label: string }[] = [
  { value: 'all', label: 'همه' },
  { value: 'unanswered', label: 'بی‌پاسخ' },
  { value: 'unresolved', label: 'حل‌نشده' },
  { value: 'mine', label: 'پرسش‌های من' },
];

export interface QaWeekOption {
  week_number: number;
  title_fa: string;
}

export function QaBoard({
  offeringId,
  weekNumber = null,
  weeks = [],
  initialThreadId = null,
}: {
  offeringId: string;
  /** برگهٔ هفته: فهرست و پرسش تازه به همین هفته بسته است. */
  weekNumber?: number | null;
  /** صفحهٔ درس: هفته‌هایی که می‌شود پرسش را به آن‌ها بست. */
  weeks?: QaWeekOption[];
  /** پیوند اعلان — این پرسش باز و به آن اسکرول می‌شود. */
  initialThreadId?: string | null;
}) {
  const { accessToken, loading: sessionLoading } = useSession();
  const [filter, setFilter] = useState<QaFilter>('all');
  const [threads, setThreads] = useState<QaThreadSummary[] | null>(null);
  const [total, setTotal] = useState(0);
  const [hasNext, setHasNext] = useState(false);
  const [page, setPage] = useState(1);
  const [error, setError] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [asking, setAsking] = useState(false);
  const [openId, setOpenId] = useState<string | null>(initialThreadId);

  useEffect(() => {
    if (sessionLoading || !accessToken) return;
    let cancelled = false;
    setThreads(null);
    fetchQaThreads(offeringId, accessToken, { filter, weekNumber, page: 1, pageSize: PAGE_SIZE })
      .then((result) => {
        if (cancelled) return;
        setThreads(result.items);
        setTotal(result.total);
        setHasNext(result.has_next);
        setPage(1);
        setError(null);
      })
      .catch((cause) => !cancelled && setError(messageFor(cause)));
    return () => {
      cancelled = true;
    };
  }, [offeringId, accessToken, sessionLoading, filter, weekNumber]);

  async function loadMore() {
    if (!accessToken) return;
    setLoadingMore(true);
    try {
      const result = await fetchQaThreads(offeringId, accessToken, {
        filter,
        weekNumber,
        page: page + 1,
        pageSize: PAGE_SIZE,
      });
      setThreads((current) => [...(current ?? []), ...result.items]);
      setHasNext(result.has_next);
      setPage(result.page);
    } catch (cause) {
      setError(messageFor(cause));
    } finally {
      setLoadingMore(false);
    }
  }

  const patchThread = useCallback((detail: QaThreadDetail) => {
    setThreads(
      (current) =>
        current?.map((item) =>
          item.id === detail.id
            ? {
                ...item,
                reply_count: detail.reply_count,
                is_resolved: detail.is_resolved,
                has_official_answer: detail.has_official_answer,
              }
            : item,
        ) ?? current,
    );
  }, []);

  const removeThread = useCallback((id: string) => {
    setThreads((current) => current?.filter((item) => item.id !== id) ?? current);
    setTotal((count) => Math.max(0, count - 1));
    setOpenId((current) => (current === id ? null : current));
  }, []);

  function created(detail: QaThreadDetail) {
    setAsking(false);
    setThreads((current) => [detail, ...(current ?? [])]);
    setTotal((count) => count + 1);
    setOpenId(detail.id);
  }

  if (error && !threads) {
    return (
      <Card>
        <p role="alert" className="text-[14px] text-[var(--fg-danger)]">
          {error}
        </p>
      </Card>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <ChipGroup
          label="فیلتر پرسش‌ها"
          options={FILTERS}
          value={filter}
          onChange={(value) => setFilter(value)}
        />
        {!asking && (
          <Button size="sm" onClick={() => setAsking(true)} disabled={!accessToken}>
            پرسش تازه
          </Button>
        )}
      </div>

      {asking && accessToken && (
        <AskForm
          offeringId={offeringId}
          accessToken={accessToken}
          fixedWeek={weekNumber}
          weeks={weeks}
          onCreated={created}
          onCancel={() => setAsking(false)}
        />
      )}

      {error && (
        <p role="alert" className="text-[13px] text-[var(--fg-danger)]">
          {error}
        </p>
      )}

      {sessionLoading || !threads ? (
        <SkeletonCard />
      ) : threads.length === 0 ? (
        <EmptyState
          title={filter === 'all' ? 'هنوز پرسشی نیست' : 'پرسشی با این فیلتر نیست'}
          description={
            filter === 'all'
              ? 'اولین پرسش را بپرس؛ همکلاسی‌ها و استاد پاسخ می‌دهند.'
              : 'فیلتر را عوض کن یا پرسش تازه‌ای بپرس.'
          }
        />
      ) : (
        <>
          <p className="text-[12.5px] text-[var(--fg-tertiary)]" aria-live="polite">
            {toPersianDigits(total)} پرسش — بی‌پاسخ‌ها بالاتر می‌آیند
          </p>
          <ul className="flex flex-col gap-3">
            {threads.map((thread) => (
              <ThreadItem
                key={thread.id}
                thread={thread}
                open={openId === thread.id}
                onToggle={() => setOpenId((current) => (current === thread.id ? null : thread.id))}
                accessToken={accessToken}
                showWeek={weekNumber === null}
                autoScroll={thread.id === initialThreadId}
                onChanged={patchThread}
                onDeleted={removeThread}
              />
            ))}
          </ul>
          {hasNext && (
            <div className="flex justify-center">
              <Button variant="secondary" onClick={() => void loadMore()} loading={loadingMore}>
                پرسش‌های بیشتر
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  );
}

// ── پرسیدن ────────────────────────────────────────────────────────────
function AskForm({
  offeringId,
  accessToken,
  fixedWeek,
  weeks,
  onCreated,
  onCancel,
}: {
  offeringId: string;
  accessToken: string;
  fixedWeek: number | null;
  weeks: QaWeekOption[];
  onCreated: (thread: QaThreadDetail) => void;
  onCancel: () => void;
}) {
  const [title, setTitle] = useState('');
  const [body, setBody] = useState('');
  const [week, setWeek] = useState<string>('');
  const [anonymous, setAnonymous] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const weekNumber = fixedWeek ?? (week ? Number(week) : null);
      onCreated(
        await createQaThread(
          offeringId,
          {
            title: title.trim(),
            body: body.trim(),
            week_number: weekNumber,
            is_anonymous: anonymous,
          },
          accessToken,
        ),
      );
    } catch (cause) {
      setError(messageFor(cause));
      setBusy(false);
    }
  }

  return (
    <Card className="flex flex-col gap-4" aria-labelledby="qa-ask-title">
      <h2 id="qa-ask-title" className="text-[16.5px] font-semibold text-[var(--fg-primary)]">
        پرسش تازه
      </h2>
      <form onSubmit={submit} className="flex flex-col gap-4">
        <Input
          label="عنوان پرسش"
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          maxLength={150}
          required
        />
        <Textarea
          label="شرح پرسش"
          hint="بگو کجا گیر کرده‌ای و تا کجا فهمیده‌ای؛ پاسخ دقیق‌تر می‌گیری."
          value={body}
          onChange={(event) => setBody(event.target.value)}
          maxLength={MAX_TEXT}
          rows={4}
          required
        />
        {fixedWeek === null && weeks.length > 0 && (
          <div className="flex flex-col gap-1.5">
            <label htmlFor="qa-week" className="text-[13.5px] font-medium text-[var(--fg-primary)]">
              مربوط به کدام هفته؟ (اختیاری)
            </label>
            <select
              id="qa-week"
              value={week}
              onChange={(event) => setWeek(event.target.value)}
              className="h-11 rounded-[var(--radius-md)] border border-[var(--border-default)] bg-[var(--bg-surface)] px-3 text-[14.5px] text-[var(--fg-primary)]"
            >
              <option value="">کل درس</option>
              {weeks.map((item) => (
                <option key={item.week_number} value={item.week_number}>
                  هفتهٔ {toPersianDigits(item.week_number)} — {item.title_fa}
                </option>
              ))}
            </select>
          </div>
        )}
        <label className="flex items-start gap-2 text-[13.5px] text-[var(--fg-secondary)]">
          <input
            type="checkbox"
            checked={anonymous}
            onChange={(event) => setAnonymous(event.target.checked)}
            className="mt-1"
          />
          <span>
            ناشناس بپرس
            <span className="block text-[12.5px] text-[var(--fg-tertiary)]">
              نامت برای همکلاسی‌ها پنهان می‌ماند؛ استاد و خودت می‌بینی.
            </span>
          </span>
        </label>
        {error && (
          <p role="alert" className="text-[13px] text-[var(--fg-danger)]">
            {error}
          </p>
        )}
        <div className="flex items-center gap-3">
          <Button type="submit" loading={busy} disabled={!title.trim() || !body.trim()}>
            ثبت پرسش
          </Button>
          <Button type="button" variant="ghost" onClick={onCancel} disabled={busy}>
            انصراف
          </Button>
        </div>
      </form>
    </Card>
  );
}

// ── یک پرسش در فهرست ───────────────────────────────────────────────────
function ThreadItem({
  thread,
  open,
  onToggle,
  accessToken,
  showWeek,
  autoScroll,
  onChanged,
  onDeleted,
}: {
  thread: QaThreadSummary;
  open: boolean;
  onToggle: () => void;
  accessToken: string | null;
  showWeek: boolean;
  autoScroll: boolean;
  onChanged: (detail: QaThreadDetail) => void;
  onDeleted: (id: string) => void;
}) {
  const panelId = `qa-thread-${thread.id}`;
  return (
    <li
      ref={(node) => {
        if (node && autoScroll) node.scrollIntoView({ block: 'start' });
      }}
      className="rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-surface)]"
    >
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        aria-controls={panelId}
        className="flex w-full flex-col gap-2 rounded-[var(--radius-lg)] p-4 text-start hover:bg-[var(--bg-sunken)]"
      >
        <span className="flex flex-wrap items-center gap-2">
          <span className="text-[15.5px] font-semibold text-[var(--fg-primary)]">
            {thread.title}
          </span>
          {thread.is_resolved && <Badge tone="success">حل‌شده</Badge>}
          {thread.reply_count === 0 ? (
            <Badge tone="warning">بی‌پاسخ</Badge>
          ) : (
            <Badge tone="neutral">{toPersianDigits(thread.reply_count)} پاسخ</Badge>
          )}
          {thread.has_official_answer && <Badge tone="brand">پاسخ تأییدشده</Badge>}
          {showWeek && thread.week_number !== null && (
            <Badge tone="neutral">هفتهٔ {toPersianDigits(thread.week_number)}</Badge>
          )}
        </span>
        {!open && (
          <span className="text-[13.5px] leading-6 text-[var(--fg-secondary)]">
            {thread.excerpt}
          </span>
        )}
        <span className="text-[12px] text-[var(--fg-tertiary)]">
          {authorLine(thread.author, thread.is_anonymous, thread.is_mine)} ·{' '}
          {formatRelative(thread.created_at)}
        </span>
      </button>
      {open && (
        <div id={panelId} className="border-t border-[var(--border-subtle)] p-4">
          <ThreadPanel
            threadId={thread.id}
            accessToken={accessToken}
            onChanged={onChanged}
            onDeleted={onDeleted}
          />
        </div>
      )}
    </li>
  );
}

// ── پرسش باز: پاسخ‌ها، رأی، تأیید ──────────────────────────────────────
function ThreadPanel({
  threadId,
  accessToken,
  onChanged,
  onDeleted,
}: {
  threadId: string;
  accessToken: string | null;
  onChanged: (detail: QaThreadDetail) => void;
  onDeleted: (id: string) => void;
}) {
  const [detail, setDetail] = useState<QaThreadDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const load = useCallback(async () => {
    if (!accessToken) return;
    try {
      const fresh = await fetchQaThread(threadId, accessToken);
      setDetail(fresh);
      onChanged(fresh);
      setError(null);
    } catch (cause) {
      setError(messageFor(cause));
    }
  }, [threadId, accessToken, onChanged]);

  useEffect(() => {
    void load();
    // فقط با عوض‌شدن پرسش یا نشست؛ `onChanged` پایدار است.
  }, [load]);

  async function act(work: () => Promise<unknown>, reload = true) {
    setBusy(true);
    setError(null);
    try {
      await work();
      if (reload) await load();
    } catch (cause) {
      setError(messageFor(cause));
    } finally {
      setBusy(false);
    }
  }

  if (!detail) {
    return error ? (
      <p role="alert" className="text-[13px] text-[var(--fg-danger)]">
        {error}
      </p>
    ) : (
      <SkeletonCard />
    );
  }

  return (
    <div className="flex flex-col gap-5">
      <p className="whitespace-pre-wrap text-[14.5px] leading-[1.9] text-[var(--fg-primary)]">
        {detail.body}
      </p>

      <div className="flex flex-wrap items-center gap-2">
        {detail.can_resolve && accessToken && (
          <Button
            size="sm"
            variant="secondary"
            disabled={busy}
            onClick={() =>
              void act(() => setQaResolved(detail.id, !detail.is_resolved, accessToken))
            }
          >
            {detail.is_resolved ? 'دوباره باز کن' : 'حل شد'}
          </Button>
        )}
        {detail.can_delete &&
          accessToken &&
          (confirmDelete ? (
            <>
              <span className="text-[13px] text-[var(--fg-secondary)]">این پرسش حذف شود؟</span>
              <Button
                size="sm"
                variant="danger"
                disabled={busy}
                onClick={() =>
                  void act(async () => {
                    await deleteQaThread(detail.id, accessToken);
                    onDeleted(detail.id);
                  }, false)
                }
              >
                حذف
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setConfirmDelete(false)}>
                انصراف
              </Button>
            </>
          ) : (
            <Button size="sm" variant="ghost" onClick={() => setConfirmDelete(true)}>
              حذف پرسش
            </Button>
          ))}
      </div>

      {error && (
        <p role="alert" className="text-[13px] text-[var(--fg-danger)]">
          {error}
        </p>
      )}

      <section aria-label="پاسخ‌ها" className="flex flex-col gap-3">
        {detail.replies.length === 0 ? (
          <p className="text-[13.5px] text-[var(--fg-secondary)]">هنوز کسی پاسخ نداده است.</p>
        ) : (
          <>
            <p className="text-[12.5px] text-[var(--fg-tertiary)]">
              پاسخی که همکلاسی‌ها مفید بدانند یا استاد تأیید کند، امتیاز جامعه می‌گیرد.
            </p>
            <ul className="flex flex-col gap-3">
              {detail.replies.map((reply) => (
                <ReplyItem
                  key={reply.id}
                  reply={reply}
                  isManager={detail.is_manager}
                  busy={busy}
                  accessToken={accessToken}
                  act={act}
                />
              ))}
            </ul>
          </>
        )}
      </section>

      {accessToken && (
        <ReplyForm
          onSubmit={(text) => act(() => postQaReply(detail.id, text, accessToken))}
          busy={busy}
        />
      )}
    </div>
  );
}

function ReplyItem({
  reply,
  isManager,
  busy,
  accessToken,
  act,
}: {
  reply: QaReply;
  isManager: boolean;
  busy: boolean;
  accessToken: string | null;
  act: (work: () => Promise<unknown>) => Promise<void>;
}) {
  return (
    <li
      className={cn(
        'flex flex-col gap-2 rounded-[var(--radius-md)] border p-3',
        reply.is_official || reply.is_endorsed
          ? 'border-[var(--brand-600)] bg-[var(--brand-50)]'
          : 'border-[var(--border-subtle)] bg-[var(--bg-surface)]',
      )}
    >
      <div className="flex flex-wrap items-center gap-2 text-[12.5px] text-[var(--fg-tertiary)]">
        <span className="font-medium text-[var(--fg-secondary)]">
          {reply.is_mine ? 'تو' : authorName(reply.author)}
        </span>
        {reply.is_official && <Badge tone="brand">پاسخ استاد</Badge>}
        {reply.is_endorsed && <Badge tone="success">تأییدشده توسط استاد</Badge>}
        <span>{formatRelative(reply.created_at)}</span>
      </div>
      <p className="whitespace-pre-wrap text-[14px] leading-[1.9] text-[var(--fg-primary)]">
        {reply.body}
      </p>
      {accessToken && (
        <div className="flex flex-wrap items-center gap-2">
          <Button
            size="sm"
            variant={reply.voted_by_me ? 'primary' : 'secondary'}
            aria-pressed={reply.voted_by_me}
            disabled={busy || !reply.can_vote}
            title={reply.can_vote ? undefined : 'به پاسخ خودت رأی نمی‌دهی'}
            onClick={() => void act(() => voteQaReply(reply.id, !reply.voted_by_me, accessToken))}
          >
            مفید بود{reply.helpful_count > 0 && ` · ${toPersianDigits(reply.helpful_count)}`}
          </Button>
          {isManager && reply.can_endorse && (
            <Button
              size="sm"
              variant="secondary"
              disabled={busy}
              onClick={() =>
                void act(() => endorseQaReply(reply.id, !reply.is_endorsed, accessToken))
              }
            >
              {reply.is_endorsed ? 'برداشتن تأیید' : 'تأیید پاسخ'}
            </Button>
          )}
          {reply.can_delete && (
            <Button
              size="sm"
              variant="ghost"
              disabled={busy}
              onClick={() => void act(() => deleteQaReply(reply.id, accessToken))}
            >
              حذف
            </Button>
          )}
        </div>
      )}
    </li>
  );
}

function ReplyForm({
  onSubmit,
  busy,
}: {
  onSubmit: (text: string) => Promise<void>;
  busy: boolean;
}) {
  const [text, setText] = useState('');

  async function submit(event: FormEvent) {
    event.preventDefault();
    const value = text.trim();
    if (!value) return;
    await onSubmit(value);
    setText('');
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-3">
      <Textarea
        label="پاسخ تو"
        value={text}
        onChange={(event) => setText(event.target.value)}
        maxLength={MAX_TEXT}
        rows={3}
      />
      <div>
        <Button type="submit" size="sm" loading={busy} disabled={!text.trim()}>
          ارسال پاسخ
        </Button>
      </div>
    </form>
  );
}

// ── کمکی ───────────────────────────────────────────────────────────────
function authorName(author: QaAuthor | null): string {
  return author?.name ?? author?.username ?? 'کاربر';
}

/** «مریم رضایی»، «تو (ناشناس برای همکلاسی‌ها)»، یا «پرسندهٔ ناشناس». */
function authorLine(author: QaAuthor | null, anonymous: boolean, mine: boolean): string {
  if (mine) return anonymous ? 'تو (ناشناس برای همکلاسی‌ها)' : 'تو';
  if (!author) return 'پرسندهٔ ناشناس';
  return anonymous ? `${authorName(author)} (ناشناس برای همکلاسی‌ها)` : authorName(author);
}

function messageFor(cause: unknown): string {
  if (cause instanceof ApiError || cause instanceof NetworkError) return cause.message;
  return 'پرسش‌وپاسخ بارگذاری نشد. کمی بعد دوباره تلاش کن.';
}
