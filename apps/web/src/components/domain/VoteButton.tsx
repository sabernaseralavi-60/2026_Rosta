'use client';

import { useState } from 'react';

import { ApiError } from '@/lib/api/client';
import { voteIdea } from '@/lib/api/ideas';
import { cn } from '@/lib/cn';
import { toPersianDigits } from '@/lib/format/digits';

/**
 * رأی مثبت ایده — FR-IDEA-02. «بدون رأی منفی — فرهنگ سازنده».
 *
 * خوش‌بینانه: شمارنده بی‌درنگ عوض می‌شود و اگر سرور رد کرد، برمی‌گردد.
 * ۴۰۹ `DUPLICATE_VOTE` یعنی رأی در تب دیگری ثبت شده؛ آن را حالت درست
 * می‌گیریم، نه خطا.
 */
export function VoteButton({
  ideaId,
  count,
  voted,
  accessToken,
  disabledReason,
  onError,
}: {
  ideaId: string;
  count: number;
  voted: boolean;
  accessToken: string | null;
  /** اگر پر باشد، دکمه غیرفعال است و این متن توضیح آن است. */
  disabledReason?: string | null;
  onError?: (message: string) => void;
}) {
  const [state, setState] = useState({ count, voted });
  const [busy, setBusy] = useState(false);
  const disabled = busy || !accessToken || Boolean(disabledReason);

  async function toggle() {
    if (!accessToken || disabled) return;
    const next = !state.voted;
    const previous = state;
    setState({ voted: next, count: state.count + (next ? 1 : -1) });
    setBusy(true);
    try {
      const result = await voteIdea(accessToken, ideaId, next);
      setState({ voted: result.voted_by_me, count: result.vote_count });
    } catch (cause) {
      if (cause instanceof ApiError && cause.code === 'DUPLICATE_VOTE') {
        setState({ voted: true, count: previous.count });
      } else {
        setState(previous);
        onError?.(cause instanceof Error ? cause.message : 'رأی ثبت نشد.');
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <button
      type="button"
      onClick={toggle}
      disabled={disabled}
      aria-pressed={state.voted}
      title={disabledReason ?? (accessToken ? undefined : 'برای رأی دادن وارد شو.')}
      aria-label={`${state.voted ? 'پس گرفتن رأی' : 'رأی مثبت'} — ${toPersianDigits(state.count)} رأی`}
      className={cn(
        'flex min-w-14 flex-col items-center gap-0.5 rounded-[var(--radius-md)] border px-2 py-2',
        'text-[13px] font-semibold tabular-nums transition-colors duration-[var(--dur-instant)]',
        'disabled:cursor-not-allowed disabled:opacity-60',
        state.voted
          ? 'border-[var(--brand-600)] bg-[var(--brand-50)] text-[var(--brand-700)]'
          : 'border-[var(--border-default)] bg-[var(--bg-surface)] text-[var(--fg-secondary)] hover:border-[var(--brand-500)]',
      )}
    >
      <svg
        aria-hidden="true"
        viewBox="0 0 24 24"
        className="size-4"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.2"
      >
        <path d="M12 5l7 8h-4v6H9v-6H5z" strokeLinejoin="round" />
      </svg>
      {toPersianDigits(state.count)}
    </button>
  );
}
