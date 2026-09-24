'use client';

import { useEffect, useState } from 'react';

import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card, CardDescription, CardTitle } from '@/components/ui/Card';
import { SkeletonCard } from '@/components/ui/Skeleton';
import { Textarea } from '@/components/ui/Textarea';
import { ApiError, NetworkError } from '@/lib/api/client';
import {
  type AnswerResponse,
  type AttemptResult,
  type ResultQuestion,
  fetchResult,
  openAppeal,
} from '@/lib/api/quizzes';
import { useSession } from '@/lib/auth/use-session';
import { cn } from '@/lib/cn';
import { toPersianDigits } from '@/lib/format/digits';

/**
 * صفحهٔ نتیجه — FR-QUIZ-04، وظیفه‌های M4-11 و M4-12.
 *
 * سه تصمیم که این صفحه را صادق نگه می‌دارد:
 *
 * ۱. **نمرهٔ موقت، موقت نشان داده می‌شود.** تا وقتی سؤال تشریحی تصحیح
 *    نشده، عدد با برچسب «موقت» می‌آید؛ وگرنه دانشجو روی عددی حساب
 *    می‌کند که قرار است عوض شود.
 *
 * ۲. **«زمان تمام شد» را می‌گوید.** تلاشی که کار پس‌زمینه بسته با
 *    تلاشی که خود دانشجو فرستاده یکی نیست (ADR-0011).
 *
 * ۳. **میانگین کلاس وقتی نباشد، جایش خالی نمی‌ماند.** دلیلش گفته
 *    می‌شود، تا «چرا من نمی‌بینم؟» پیش نیاید.
 */

export function ResultView({ attemptId }: { attemptId: string }) {
  const { accessToken, loading: sessionLoading } = useSession();
  const [result, setResult] = useState<AttemptResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (sessionLoading || !accessToken) return;
    let cancelled = false;
    fetchResult(attemptId, accessToken)
      .then((data) => !cancelled && setResult(data))
      .catch((cause) => !cancelled && setError(messageOf(cause)));
    return () => {
      cancelled = true;
    };
  }, [attemptId, accessToken, sessionLoading]);

  if (sessionLoading || (!result && !error)) return <SkeletonCard />;

  if (error) {
    return (
      <Card className="p-6">
        <p className="text-[15px] text-[var(--fg-danger)]">{error}</p>
      </Card>
    );
  }
  if (!result) return null;

  const score = result.total_score ? Number(result.total_score) : 0;
  const total = Number(result.total_points) || 1;
  const percent = Math.round((score / total) * 100);

  return (
    <div className="space-y-4">
      <Card className="space-y-4 p-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <CardTitle>{result.quiz_title_fa}</CardTitle>
            <CardDescription>
              تلاش {toPersianDigits(result.attempt_no)}
              {result.auto_closed ? ' — زمان آزمون تمام شد و پاسخ‌های ذخیره‌شده تصحیح شدند' : ''}
            </CardDescription>
          </div>
          <div className="flex flex-wrap gap-2">
            {result.is_provisional ? (
              <Badge tone="warning">نمرهٔ موقت — سؤال تشریحی هنوز تصحیح نشده</Badge>
            ) : null}
            {result.passed === true ? <Badge tone="success">قبول</Badge> : null}
            {result.passed === false ? <Badge tone="danger">مردود</Badge> : null}
          </div>
        </div>

        <div className="flex flex-wrap items-end gap-6">
          <div>
            <p className="text-[13px] text-[var(--fg-secondary)]">نمرهٔ شما</p>
            <p className="text-[32px] font-semibold tabular-nums text-[var(--fg-primary)]">
              {toPersianDigits(score)}{' '}
              <span className="text-[18px] text-[var(--fg-secondary)]">
                از {toPersianDigits(result.total_points)}
              </span>
            </p>
          </div>
          <ClassComparison result={result} percent={percent} />
        </div>
      </Card>

      <ol className="space-y-3">
        {result.questions.map((question, index) => (
          <li key={question.id}>
            <QuestionResult
              question={question}
              index={index}
              attemptId={attemptId}
              accessToken={accessToken}
            />
          </li>
        ))}
      </ol>
    </div>
  );
}

function ClassComparison({ result, percent }: { result: AttemptResult; percent: number }) {
  if (result.class_average === null) {
    return (
      <p className="max-w-xs text-[13px] text-[var(--fg-secondary)]">
        میانگین کلاس وقتی نشان داده می‌شود که دست‌کم سه نفر آزمون داده باشند — با تعداد کمتر، نمرهٔ
        بقیه از روی میانگین قابل حدس است.
      </p>
    );
  }
  const average = Number(result.class_average);
  const total = Number(result.total_points) || 1;
  const averagePercent = Math.round((average / total) * 100);

  return (
    <div className="min-w-56 flex-1">
      <p className="text-[13px] text-[var(--fg-secondary)]">
        میانگین کلاس: {toPersianDigits(average)} ({toPersianDigits(result.cohort_size)} نفر)
      </p>
      <div className="mt-2 space-y-1.5">
        <Bar label="شما" percent={percent} tone="brand" />
        <Bar label="میانگین" percent={averagePercent} tone="neutral" />
      </div>
    </div>
  );
}

function Bar({
  label,
  percent,
  tone,
}: {
  label: string;
  percent: number;
  tone: 'brand' | 'neutral';
}) {
  return (
    <div className="flex items-center gap-2">
      <span className="w-14 text-[12.5px] text-[var(--fg-secondary)]">{label}</span>
      <div
        className="h-2.5 flex-1 overflow-hidden rounded-[var(--radius-full)] bg-[var(--bg-sunken)]"
        role="img"
        aria-label={`${label}: ${percent} درصد`}
      >
        <div
          className={cn(
            'h-full rounded-[var(--radius-full)]',
            tone === 'brand' ? 'bg-[var(--brand-600)]' : 'bg-[var(--fg-muted)]',
          )}
          style={{ width: `${Math.min(100, Math.max(0, percent))}%` }}
        />
      </div>
      <span className="w-10 text-end text-[12.5px] tabular-nums text-[var(--fg-secondary)]">
        {toPersianDigits(percent)}٪
      </span>
    </div>
  );
}

function QuestionResult({
  question,
  index,
  attemptId,
  accessToken,
}: {
  question: ResultQuestion;
  index: number;
  attemptId: string;
  accessToken: string | null;
}) {
  const [appealing, setAppealing] = useState(false);
  const [reason, setReason] = useState('');
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submitAppeal() {
    if (!accessToken) return;
    setBusy(true);
    setError(null);
    try {
      await openAppeal(attemptId, { reason, question_id: question.id }, accessToken);
      setSent(true);
      setAppealing(false);
    } catch (cause) {
      setError(messageOf(cause));
    } finally {
      setBusy(false);
    }
  }

  const tone =
    question.is_correct === true ? 'success' : question.is_correct === false ? 'danger' : 'warning';
  const verdict =
    question.is_correct === true ? 'درست' : question.is_correct === false ? 'نادرست' : 'نمرهٔ جزئی';

  return (
    <Card className="space-y-3 p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex-1">
          <p className="text-[13px] text-[var(--fg-secondary)]">
            سؤال {toPersianDigits(index + 1)} · {question.kind_fa}
          </p>
          <p className="mt-1.5 text-[15.5px] leading-7 text-[var(--fg-primary)]">{question.body}</p>
        </div>
        <div className="flex items-center gap-2">
          <Badge tone={tone}>{verdict}</Badge>
          <span className="text-[15px] tabular-nums text-[var(--fg-primary)]">
            {toPersianDigits(question.score ?? 0)} / {toPersianDigits(question.points)}
          </span>
        </div>
      </div>

      <dl className="space-y-1.5 text-[14px]">
        <div className="flex gap-2">
          <dt className="text-[var(--fg-secondary)]">پاسخ شما:</dt>
          <dd className="text-[var(--fg-primary)]">{describe(question.my_answer)}</dd>
        </div>
        {question.review ? (
          <div className="flex gap-2">
            <dt className="text-[var(--fg-secondary)]">پاسخ درست:</dt>
            <dd className="text-[var(--fg-primary)]">
              {question.review.accepted
                ? question.review.accepted.join(' · ')
                : describeCorrect(question.review.correct)}
            </dd>
          </div>
        ) : null}
      </dl>

      {question.review?.explanation ? (
        <p className="rounded-[var(--radius-sm)] bg-[var(--bg-sunken)] p-3 text-[13.5px] leading-6 text-[var(--fg-secondary)]">
          {question.review.explanation}
        </p>
      ) : null}

      {question.feedback ? (
        <p className="rounded-[var(--radius-sm)] border-e-2 border-[var(--brand-600)] bg-[var(--brand-50)] p-3 text-[13.5px] leading-6 text-[var(--fg-brand)]">
          بازخورد استاد: {question.feedback}
        </p>
      ) : null}

      {sent ? (
        <p className="text-[13.5px] text-[var(--fg-success)]">
          اعتراض شما ثبت شد و به استاد ارجاع شد.
        </p>
      ) : appealing ? (
        <div className="space-y-2">
          <Textarea
            label="دلیل اعتراض"
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            rows={3}
            placeholder="چرا فکر می‌کنید نمرهٔ این سؤال درست نیست؟"
          />
          {error ? <p className="text-[13px] text-[var(--fg-danger)]">{error}</p> : null}
          <div className="flex gap-2">
            <Button
              size="sm"
              onClick={() => void submitAppeal()}
              loading={busy}
              disabled={!reason.trim()}
            >
              ثبت اعتراض
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setAppealing(false)}>
              انصراف
            </Button>
          </div>
        </div>
      ) : (
        <Button size="sm" variant="ghost" onClick={() => setAppealing(true)}>
          اعتراض به نمرهٔ این سؤال
        </Button>
      )}
    </Card>
  );
}

function describe(answer: AnswerResponse | null): string {
  if (!answer) return 'بی‌پاسخ';
  if ('selected' in answer) return answer.selected.join('، ') || 'بی‌پاسخ';
  if ('pairs' in answer) return answer.pairs.map(([l, r]) => `${l} ← ${r}`).join('، ');
  if ('text' in answer) return answer.text || 'بی‌پاسخ';
  if ('value' in answer) {
    if (typeof answer.value === 'boolean') return answer.value ? 'درست' : 'نادرست';
    return toPersianDigits(String(answer.value));
  }
  return 'بی‌پاسخ';
}

function describeCorrect(correct: unknown): string {
  if (correct === null || correct === undefined) return '—';
  if (typeof correct === 'boolean') return correct ? 'درست' : 'نادرست';
  if (Array.isArray(correct)) {
    return correct
      .map((item) => (Array.isArray(item) ? `${item[0]} ← ${item[1]}` : String(item)))
      .join('، ');
  }
  return toPersianDigits(String(correct));
}

function messageOf(cause: unknown): string {
  if (cause instanceof ApiError || cause instanceof NetworkError) return cause.message;
  return 'خطای غیرمنتظره‌ای رخ داد.';
}
