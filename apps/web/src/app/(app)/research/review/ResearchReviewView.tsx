'use client';

import { useCallback, useEffect, useState } from 'react';

import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { SkeletonCard } from '@/components/ui/Skeleton';
import { Textarea } from '@/components/ui/Textarea';
import { ApiError, NetworkError } from '@/lib/api/client';
import {
  type OutputReviewItem,
  type ReviewItem,
  fetchOutputReviewQueue,
  fetchResearchReviewQueue,
  reviewOutput,
  reviewSubmission,
  submissionFileUrl,
} from '@/lib/api/research';
import { useSession } from '@/lib/auth/use-session';
import { formatDateLong } from '@/lib/format/date';
import { toPersianDigits } from '@/lib/format/digits';

const STAGE_FA = { SUBMITTED: 'ارسال', ACCEPTED: 'پذیرش', PUBLISHED: 'انتشار' } as const;

/**
 * `/research/review` — صف بررسی منتور و استاد.
 *
 * دو صف: تحویل سطح‌های مسیر (تأیید یا «اصلاح کن» با بازخورد) و ادعای
 * وضعیت مقاله (راستی‌آزمایی یا رد با یادداشت). هر دو قدیمی‌ترین اول؛
 * تحویل خود بازبین در صف نیست — سرور فیلتر کرده است.
 */
export function ResearchReviewView() {
  const { accessToken, loading: sessionLoading } = useSession();
  const [submissions, setSubmissions] = useState<ReviewItem[] | null>(null);
  const [outputs, setOutputs] = useState<OutputReviewItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    if (sessionLoading || !accessToken) return;
    Promise.all([fetchResearchReviewQueue(accessToken), fetchOutputReviewQueue(accessToken)])
      .then(([levels, papers]) => {
        setSubmissions(levels);
        setOutputs(papers);
      })
      .catch((cause) => setError(messageFor(cause)));
  }, [accessToken, sessionLoading]);

  useEffect(load, [load]);

  return (
    <div className="flex flex-col gap-8">
      <header className="flex flex-col gap-1">
        <h1>صف بررسی پژوهش</h1>
        <p className="text-[15px] text-[var(--fg-secondary)]">
          امتیاز پژوهش دانشجو از همین تأیید می‌آید. اگر شاهد کافی نیست، بگو دقیقاً چه لازم است.
        </p>
      </header>
      {error && (
        <p role="alert" className="text-[13.5px] text-[var(--danger-600)]">
          {error}
        </p>
      )}

      <section className="flex flex-col gap-3" aria-labelledby="levels-title">
        <h2 id="levels-title" className="text-[19px] font-semibold">
          تحویل سطح‌ها
          {submissions && ` (${toPersianDigits(submissions.length)})`}
        </h2>
        {submissions === null ? (
          !error && <SkeletonCard label="در حال بارگذاری صف" />
        ) : submissions.length === 0 ? (
          <EmptyState title="تحویلی منتظر بررسی نیست" />
        ) : (
          <ul className="flex flex-col gap-3">
            {submissions.map((item) => (
              <li key={item.id}>
                {accessToken && (
                  <SubmissionReview item={item} accessToken={accessToken} onDone={load} />
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="flex flex-col gap-3" aria-labelledby="outputs-title">
        <h2 id="outputs-title" className="text-[19px] font-semibold">
          راستی‌آزمایی مقاله
          {outputs && ` (${toPersianDigits(outputs.length)})`}
        </h2>
        {outputs === null ? (
          !error && <SkeletonCard label="در حال بارگذاری صف" />
        ) : outputs.length === 0 ? (
          <EmptyState title="ادعایی منتظر راستی‌آزمایی نیست" />
        ) : (
          <ul className="flex flex-col gap-3">
            {outputs.map((item) => (
              <li key={item.id}>
                {accessToken && (
                  <OutputReview item={item} accessToken={accessToken} onDone={load} />
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function SubmissionReview({
  item,
  accessToken,
  onDone,
}: {
  item: ReviewItem;
  accessToken: string;
  onDone: () => void;
}) {
  const [feedback, setFeedback] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const labels = Object.fromEntries(item.evidence_fields.map((f) => [f.key, f.label_fa]));

  async function decide(decision: 'APPROVED' | 'CHANGES_REQUESTED') {
    setBusy(true);
    setError(null);
    try {
      await reviewSubmission(accessToken, item.id, decision, feedback.trim());
      onDone();
    } catch (cause) {
      setError(messageFor(cause));
    } finally {
      setBusy(false);
    }
  }

  async function open(fileId: string) {
    try {
      const { download_url } = await submissionFileUrl(accessToken, item.id, fileId);
      window.open(download_url, '_blank', 'noopener');
    } catch (cause) {
      setError(messageFor(cause));
    }
  }

  return (
    <Card className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-[15.5px] font-semibold">
          {item.student.name ?? item.student.username} — سطح {toPersianDigits(item.level)}:{' '}
          {item.level_title_fa}
        </p>
        <div className="flex items-center gap-2">
          <Badge tone="neutral">نسخهٔ {toPersianDigits(item.version)}</Badge>
          <span className="text-[12.5px] text-[var(--fg-tertiary)]">
            {formatDateLong(item.submitted_at)}
          </span>
        </div>
      </div>
      {item.topic_title && (
        <p className="text-[13.5px] text-[var(--fg-secondary)]">موضوع: {item.topic_title}</p>
      )}
      <p className="whitespace-pre-line text-[14px] leading-[1.9]">{item.summary}</p>
      <dl className="grid gap-1 text-[13.5px]">
        {Object.entries(item.evidence).map(([key, value]) => (
          <div key={key} className="flex flex-wrap gap-1.5">
            <dt className="text-[var(--fg-tertiary)]">{labels[key] ?? key}:</dt>
            <dd className="break-words">
              {typeof value === 'string' && value.startsWith('http') ? (
                <a
                  href={value}
                  target="_blank"
                  rel="noopener noreferrer"
                  dir="ltr"
                  className="text-[var(--brand-700)] underline"
                >
                  {value}
                </a>
              ) : (
                toPersianDigits(String(value))
              )}
            </dd>
          </div>
        ))}
      </dl>
      {(item.links.length > 0 || item.files.length > 0) && (
        <ul className="flex flex-wrap gap-2 text-[13px]">
          {item.links.map((link) => (
            <li key={link}>
              <a
                href={link}
                target="_blank"
                rel="noopener noreferrer"
                dir="ltr"
                className="text-[var(--brand-700)] underline"
              >
                {link}
              </a>
            </li>
          ))}
          {item.files.map((file) => (
            <li key={file.id}>
              <button
                type="button"
                onClick={() => open(file.id)}
                className="text-[var(--brand-700)] underline"
              >
                {file.original_name}
              </button>
            </li>
          ))}
        </ul>
      )}
      {item.previous.length > 0 && (
        <details className="text-[13.5px]">
          <summary className="cursor-pointer text-[var(--fg-secondary)]">
            بازخوردهای نسخه‌های قبلی
          </summary>
          <ul className="mt-2 flex flex-col gap-1">
            {item.previous.map((prev) => (
              <li key={prev.version}>
                نسخهٔ {toPersianDigits(prev.version)}: {prev.feedback ?? '—'}
              </li>
            ))}
          </ul>
        </details>
      )}
      <details className="text-[13.5px]">
        <summary className="cursor-pointer text-[var(--fg-secondary)]">چک‌لیست کیفیت سطح</summary>
        <ul className="mt-2 list-disc ps-5">
          {item.checklist.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      </details>
      <Textarea
        label="بازخورد"
        hint="برای «اصلاح کن» لازم است؛ برای تأیید اختیاری"
        value={feedback}
        onChange={(event) => setFeedback(event.target.value)}
        maxLength={2000}
        rows={3}
      />
      {error && (
        <p role="alert" className="text-[13px] text-[var(--danger-600)]">
          {error}
        </p>
      )}
      <div className="flex flex-wrap gap-2">
        <Button loading={busy} onClick={() => decide('APPROVED')}>
          تأیید سطح
        </Button>
        <Button
          variant="secondary"
          loading={busy}
          disabled={!feedback.trim()}
          onClick={() => decide('CHANGES_REQUESTED')}
        >
          اصلاح کن
        </Button>
      </div>
    </Card>
  );
}

function OutputReview({
  item,
  accessToken,
  onDone,
}: {
  item: OutputReviewItem;
  accessToken: string;
  onDone: () => void;
}) {
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function decide(decision: 'VERIFIED' | 'REJECTED') {
    setBusy(true);
    setError(null);
    try {
      await reviewOutput(accessToken, item.id, decision, note.trim());
      onDone();
    } catch (cause) {
      setError(messageFor(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-1.5">
        <Badge tone="research">{item.kind_fa}</Badge>
        <Badge tone="warning">ادعا: {item.status_fa}</Badge>
        {item.quartile && <Badge tone="accent">{item.quartile}</Badge>}
        {item.verified_stage && (
          <span className="text-[12.5px] text-[var(--fg-tertiary)]">
            پیش‌تر تأییدشده: {STAGE_FA[item.verified_stage]}
            {item.verified_quartile ? ` · ${item.verified_quartile}` : ''}
          </span>
        )}
      </div>
      <p className="text-[15.5px] font-semibold" dir="auto">
        {item.title}
      </p>
      <p className="text-[13.5px] text-[var(--fg-secondary)]" dir="auto">
        {item.owner.name ?? item.owner.username} · {item.authors}
        {item.venue && ` — ${item.venue}`}
      </p>
      <div className="flex flex-wrap gap-3 text-[13px]">
        {item.doi && (
          <a
            href={`https://doi.org/${item.doi}`}
            target="_blank"
            rel="noopener noreferrer"
            dir="ltr"
            className="text-[var(--brand-700)] underline"
          >
            doi:{item.doi}
          </a>
        )}
        {item.url && (
          <a
            href={item.url}
            target="_blank"
            rel="noopener noreferrer"
            dir="ltr"
            className="text-[var(--brand-700)] underline"
          >
            {item.url}
          </a>
        )}
        {!item.doi && !item.url && (
          <span className="text-[var(--fg-tertiary)]">شاهدی پیوست نشده است.</span>
        )}
      </div>
      <Textarea
        label="یادداشت"
        hint="برای رد لازم است — بگو چه شاهدی کم است"
        value={note}
        onChange={(event) => setNote(event.target.value)}
        maxLength={1000}
        rows={2}
      />
      {error && (
        <p role="alert" className="text-[13px] text-[var(--danger-600)]">
          {error}
        </p>
      )}
      <div className="flex flex-wrap gap-2">
        <Button loading={busy} onClick={() => decide('VERIFIED')}>
          راستی‌آزمایی شد
        </Button>
        <Button
          variant="secondary"
          loading={busy}
          disabled={!note.trim()}
          onClick={() => decide('REJECTED')}
        >
          رد ادعا
        </Button>
      </div>
    </Card>
  );
}

function messageFor(cause: unknown): string {
  if (cause instanceof ApiError || cause instanceof NetworkError) return cause.message;
  return 'کار انجام نشد. کمی بعد دوباره تلاش کن.';
}
