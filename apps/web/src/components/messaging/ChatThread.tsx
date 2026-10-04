'use client';

import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react';

import { ErrorLine, errorText } from '@/components/admin/common';
import { Button } from '@/components/ui/Button';
import { SkeletonRow } from '@/components/ui/Skeleton';
import {
  type ChatMessage,
  deleteMessage,
  fetchMessages,
  MESSAGE_MAX,
  markRead,
  sendMessage,
} from '@/lib/api/messaging';
import { cn } from '@/lib/cn';
import { formatDateTime } from '@/lib/format/date';
import { toPersianDigits } from '@/lib/format/digits';

/** هر چند ثانیه یک‌بار پیام‌های تازه را می‌گیرد؛ تب پنهان نمی‌پرسد. */
const POLL_MS = 15_000;

/**
 * یک گفت‌وگو — فهرست پیام و جعبهٔ نوشتن.
 *
 * `canWrite=false` (کانال درس برای دانشجو) جعبهٔ نوشتن را نشان نمی‌دهد و دلیلش را می‌گوید.
 * حذف نرم فقط برای پیام خودم، یا هر پیام وقتی `staff` باشد.
 */
export function ChatThread({
  conversationId,
  token,
  canWrite,
  staff,
  onChanged,
}: {
  conversationId: string;
  token: string;
  canWrite: boolean;
  staff: boolean;
  onChanged?: () => void;
}) {
  const [messages, setMessages] = useState<ChatMessage[] | null>(null);
  const [text, setText] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const bottom = useRef<HTMLDivElement>(null);
  const lastId = useRef<string | null>(null);

  const load = useCallback(async () => {
    try {
      const rows = await fetchMessages(conversationId, token);
      setMessages(rows);
      const newest = rows.at(-1)?.id ?? null;
      if (newest !== lastId.current) {
        lastId.current = newest;
        await markRead(conversationId, token);
        onChanged?.();
      }
    } catch (cause) {
      setError(errorText(cause));
    }
  }, [conversationId, token, onChanged]);

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => {
      if (document.visibilityState === 'visible') void load();
    }, POLL_MS);
    return () => window.clearInterval(timer);
  }, [load]);

  useEffect(() => {
    bottom.current?.scrollIntoView({ block: 'end' });
  }, [messages?.length]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!text.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await sendMessage(conversationId, text, token);
      setText('');
      await load();
    } catch (cause) {
      setError(errorText(cause));
    } finally {
      setBusy(false);
    }
  }

  async function remove(message: ChatMessage) {
    if (!window.confirm('این پیام حذف شود؟')) return;
    try {
      await deleteMessage(message.id, token);
      await load();
    } catch (cause) {
      setError(errorText(cause));
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div
        role="log"
        aria-live="polite"
        aria-label="پیام‌ها"
        className="flex max-h-[60vh] min-h-[240px] flex-col gap-3 overflow-y-auto rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-4"
      >
        {!messages && !error && <SkeletonRow />}
        {messages && messages.length === 0 && (
          <p className="m-auto text-[14px] text-[var(--fg-tertiary)]">هنوز پیامی نیست.</p>
        )}
        {messages?.map((message) => (
          <article
            key={message.id}
            className={cn(
              'flex max-w-[85%] flex-col gap-1 rounded-[var(--radius-lg)] px-4 py-2.5',
              message.mine
                ? 'self-start bg-[var(--brand-50)]'
                : 'self-end bg-[var(--bg-sunken)]',
            )}
          >
            <header className="flex items-center gap-2 text-[12px] text-[var(--fg-tertiary)]">
              <span className="font-semibold text-[var(--fg-secondary)]">
                {message.mine ? 'من' : message.sender_name}
              </span>
              <time dateTime={message.created_at}>
                {toPersianDigits(formatDateTime(message.created_at))}
              </time>
              {(message.mine || staff) && !message.deleted && (
                <button
                  type="button"
                  onClick={() => void remove(message)}
                  className="text-[var(--fg-tertiary)] underline hover:text-[var(--fg-danger)]"
                >
                  حذف
                </button>
              )}
            </header>
            {message.deleted ? (
              <p className="text-[13px] italic text-[var(--fg-tertiary)]">این پیام حذف شد.</p>
            ) : (
              <p className="whitespace-pre-wrap text-[14.5px] leading-[1.9]">{message.body}</p>
            )}
          </article>
        ))}
        <div ref={bottom} />
      </div>

      {error && <ErrorLine>{error}</ErrorLine>}

      {canWrite ? (
        <form onSubmit={submit} className="flex flex-col gap-2">
          <label htmlFor="chat-body" className="sr-only">
            متن پیام
          </label>
          <textarea
            id="chat-body"
            value={text}
            onChange={(event) => setText(event.target.value)}
            maxLength={MESSAGE_MAX}
            rows={3}
            placeholder="پیامت را بنویس…"
            className="w-full rounded-[var(--radius-md)] border border-[var(--border-default)] bg-[var(--bg-surface)] p-3 text-[15px] leading-[1.9]"
          />
          <div className="flex items-center justify-between gap-3">
            <span className="text-[12px] text-[var(--fg-tertiary)]">
              {toPersianDigits(text.length)} از {toPersianDigits(MESSAGE_MAX)}
            </span>
            <Button type="submit" loading={busy} loadingLabel="در حال ارسال…" disabled={!text.trim()}>
              ارسال
            </Button>
          </div>
        </form>
      ) : (
        <p className="rounded-[var(--radius-md)] bg-[var(--bg-sunken)] px-4 py-3 text-[13.5px] text-[var(--fg-secondary)]">
          این کانال یک‌طرفه است؛ فقط استاد و دستیار می‌نویسند. برای پرسش، از «گفت‌وگوی خصوصی با
          استاد» استفاده کن.
        </p>
      )}
    </div>
  );
}
