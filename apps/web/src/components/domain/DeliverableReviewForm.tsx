'use client';

import { useState } from 'react';

import { Button } from '@/components/ui/Button';
import { Card, CardTitle } from '@/components/ui/Card';
import { Textarea } from '@/components/ui/Textarea';
import { ApiError, NetworkError } from '@/lib/api/client';
import { type ReviewDecision, type ReviewResult, reviewDeliverable } from '@/lib/api/workspace';

/**
 * فرم بررسی یک تحویل — §7.6. هم در فضای کاری پروژه و هم در صف واحد بررسی
 * استاد (`/teach/review-queue`) به کار می‌رود؛ دو نسخهٔ جدا یعنی دو قاعدهٔ
 * «بازخورد اجباری است» که روزی از هم دور می‌شوند.
 *
 * «اصلاح کن» و «رد» بدون بازخورد ارسال نمی‌شوند — سرور هم همین را می‌گوید،
 * ولی گرفتن جلوی کلیک بهتر از خطای پس از کلیک است.
 */

const DECISIONS: { value: ReviewDecision; label: string }[] = [
  { value: 'APPROVED', label: 'تأیید' },
  { value: 'CHANGES_REQUESTED', label: 'اصلاح کن' },
  { value: 'REJECTED', label: 'رد' },
];

export function DeliverableReviewForm({
  deliverableId,
  accessToken,
  onReviewed,
}: {
  deliverableId: string;
  accessToken: string;
  onReviewed: (result: ReviewResult) => void;
}) {
  const [decision, setDecision] = useState<ReviewDecision>('APPROVED');
  const [feedback, setFeedback] = useState('');
  const [score, setScore] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [readyToClose, setReadyToClose] = useState(false);

  const feedbackRequired = decision !== 'APPROVED';
  const blocked = feedbackRequired && feedback.trim().length === 0;

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const result = await reviewDeliverable(
        deliverableId,
        {
          decision,
          feedback: feedback.trim() || null,
          score: score.trim() ? Number(score) : null,
        },
        accessToken,
      );
      setReadyToClose(result.project_ready_to_close);
      onReviewed(result);
    } catch (cause) {
      setError(messageFor(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card variant="raised" className="flex flex-col gap-3">
      <CardTitle>بررسی تحویل</CardTitle>

      <form onSubmit={handleSubmit} className="flex flex-col gap-3">
        <fieldset className="flex flex-col gap-2">
          <legend className="text-[13.5px] font-medium text-[var(--fg-primary)]">تصمیم</legend>
          <div className="flex flex-wrap gap-2">
            {DECISIONS.map((option) => (
              <label
                key={option.value}
                className={`cursor-pointer rounded-[var(--radius-sm)] border px-3 py-1.5 text-[13.5px] ${
                  decision === option.value
                    ? 'border-[var(--brand-500)] bg-[var(--brand-50)] text-[var(--fg-brand)]'
                    : 'border-[var(--border-default)] text-[var(--fg-secondary)]'
                }`}
              >
                <input
                  type="radio"
                  name={`decision-${deliverableId}`}
                  value={option.value}
                  checked={decision === option.value}
                  onChange={() => setDecision(option.value)}
                  className="sr-only"
                />
                {option.label}
              </label>
            ))}
          </div>
        </fieldset>

        <Textarea
          label="بازخورد"
          hint={
            feedbackRequired
              ? 'برای «اصلاح کن» و «رد» اجباری است: دانشجو باید بداند چه چیزی را درست کند.'
              : 'اختیاری، ولی یک جملهٔ کوتاه هم بهتر از سکوت است.'
          }
          value={feedback}
          onChange={(event) => setFeedback(event.target.value)}
          maxLength={5000}
          rows={3}
          required={feedbackRequired}
        />

        <label className="flex flex-col gap-1.5">
          <span className="text-[13.5px] font-medium text-[var(--fg-primary)]">نمره (اختیاری)</span>
          <input
            type="number"
            min={0}
            step="0.5"
            value={score}
            onChange={(event) => setScore(event.target.value)}
            className="h-10 w-28 rounded-[var(--radius-md)] border border-[var(--border-default)] bg-[var(--bg-surface)] px-3 text-[14px] tabular-nums"
          />
        </label>

        {error && (
          <p role="alert" className="text-[13px] text-[var(--fg-danger)]">
            {error}
          </p>
        )}

        {readyToClose && (
          <p className="text-[13px] text-[var(--fg-success)]">
            همهٔ مراحل الزامی تأیید شدند — پروژه آمادهٔ بسته شدن است.
          </p>
        )}

        <Button type="submit" size="sm" className="self-start" loading={busy} disabled={blocked}>
          ثبت بررسی
        </Button>
      </form>
    </Card>
  );
}

function messageFor(cause: unknown): string {
  if (cause instanceof ApiError || cause instanceof NetworkError) return cause.message;
  return 'انجام نشد. کمی بعد دوباره تلاش کن.';
}
