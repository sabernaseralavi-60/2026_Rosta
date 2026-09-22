'use client';

import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';

import { Badge, type BadgeTone } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card, CardDescription, CardTitle } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { SkeletonCard } from '@/components/ui/Skeleton';
import { ApiError, NetworkError } from '@/lib/api/client';
import {
  type QuizAvailability,
  type QuizSummary,
  fetchOfferingQuizzes,
  startAttempt,
} from '@/lib/api/quizzes';
import { useSession } from '@/lib/auth/use-session';
import { formatDateTime } from '@/lib/format/date';
import { toPersianDigits } from '@/lib/format/digits';
import { formatClock } from '@/lib/quiz/timer';

/**
 * `/courses/[offeringId]/quizzes` — §3.4.
 *
 * وضعیت هر آزمون و متن فارسی‌اش از سرور می‌آید (`state` و `state_fa`)؛
 * این صفحه جدول §7.3 را بازنمی‌سازد، فقط نمایشش می‌دهد. وگرنه قاعدهٔ
 * «کِی می‌شود شروع کرد» دو جا نوشته می‌شد و یکی‌شان کهنه می‌ماند.
 */

const TONES: Record<QuizAvailability, BadgeTone> = {
  NOT_OPEN: 'neutral',
  AVAILABLE: 'success',
  IN_PROGRESS: 'warning',
  EXHAUSTED: 'neutral',
  CLOSED: 'danger',
};

export function QuizListView({ offeringId }: { offeringId: string }) {
  const router = useRouter();
  const { accessToken, loading: sessionLoading } = useSession();
  const [quizzes, setQuizzes] = useState<QuizSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState<string | null>(null);

  useEffect(() => {
    if (sessionLoading || !accessToken) return;
    let cancelled = false;
    fetchOfferingQuizzes(offeringId, accessToken)
      .then((data) => !cancelled && setQuizzes(data))
      .catch((cause) => !cancelled && setError(messageOf(cause)));
    return () => {
      cancelled = true;
    };
  }, [offeringId, accessToken, sessionLoading]);

  async function begin(quiz: QuizSummary) {
    if (!accessToken) return;
    // تلاش نیمه‌تمام ادامه داده می‌شود، نه اینکه تلاش تازه بسازد —
    // سرور هم همین را با `ACTIVE_ATTEMPT_EXISTS` تحمیل می‌کند.
    if (quiz.active_attempt_id) {
      router.push(`/quiz/${quiz.active_attempt_id}`);
      return;
    }
    setStarting(quiz.id);
    setError(null);
    try {
      const started = await startAttempt(quiz.id, accessToken);
      router.push(`/quiz/${started.attempt_id}`);
    } catch (cause) {
      if (cause instanceof ApiError && cause.code === 'ACTIVE_ATTEMPT_EXISTS') {
        const id = cause.details.attempt_id;
        if (typeof id === 'string') {
          router.push(`/quiz/${id}`);
          return;
        }
      }
      setError(messageOf(cause));
    } finally {
      setStarting(null);
    }
  }

  if (sessionLoading || (!quizzes && !error)) return <SkeletonCard />;

  if (error && !quizzes) {
    return (
      <Card className="p-6">
        <p className="text-[15px] text-[var(--danger-600)]">{error}</p>
      </Card>
    );
  }

  if (!quizzes?.length) {
    return (
      <EmptyState
        title="هنوز آزمونی منتشر نشده"
        description="وقتی استاد آزمونی منتشر کند، اینجا دیده می‌شود."
      />
    );
  }

  return (
    <div className="space-y-4">
      <h1 className="text-[20px] font-semibold text-[var(--fg-primary)]">آزمون‌های این درس</h1>
      {error ? (
        <div role="alert" className="rounded-[var(--radius-md)] bg-[color-mix(in_oklch,var(--danger-500)_12%,transparent)] p-3 text-[14px] text-[var(--danger-600)]">
          {error}
        </div>
      ) : null}

      <ul className="space-y-3">
        {quizzes.map((quiz) => (
          <li key={quiz.id}>
            <Card className="flex flex-wrap items-start justify-between gap-4 p-5">
              <div className="flex-1 space-y-2">
                <div className="flex flex-wrap items-center gap-2">
                  <CardTitle className="text-[16.5px]">{quiz.title_fa}</CardTitle>
                  <Badge tone={TONES[quiz.state]}>{quiz.state_fa}</Badge>
                  {quiz.week_number ? (
                    <Badge tone="neutral">هفتهٔ {toPersianDigits(quiz.week_number)}</Badge>
                  ) : null}
                </div>
                {quiz.description ? (
                  <CardDescription>{quiz.description}</CardDescription>
                ) : null}
                <p className="text-[13px] text-[var(--fg-secondary)]">
                  {toPersianDigits(quiz.question_count)} سؤال ·{' '}
                  {toPersianDigits(quiz.total_points)} نمره ·{' '}
                  {toPersianDigits(quiz.duration_min)} دقیقه · تلاش{' '}
                  {toPersianDigits(quiz.used_attempts)} از{' '}
                  {toPersianDigits(quiz.max_attempts)}
                </p>
                <p className="text-[13px] text-[var(--fg-secondary)]">
                  مهلت: {formatDateTime(quiz.closes_at)}
                </p>
                {/*
                  شروع دیرهنگام یعنی وقت کمتر (ADR-0011 مسئلهٔ ۳). این
                  هشدار پیش از شروع می‌آید، نه بعد از آن — غافلگیری وسط
                  آزمون، همان چیزی است که باید حذف شود.
                */}
                {quiz.state === 'AVAILABLE' &&
                quiz.effective_duration_sec !== null &&
                quiz.effective_duration_sec < quiz.duration_min * 60 ? (
                  <p className="text-[13px] text-[var(--warning-600)]">
                    اگر همین حالا شروع کنید، {formatClock(quiz.effective_duration_sec)} وقت
                    دارید — چون مهلت آزمون زودتر از مدت آن تمام می‌شود.
                  </p>
                ) : null}
              </div>

              <div className="flex items-center">
                {quiz.state === 'AVAILABLE' || quiz.state === 'IN_PROGRESS' ? (
                  <Button
                    onClick={() => void begin(quiz)}
                    loading={starting === quiz.id}
                  >
                    {quiz.state === 'IN_PROGRESS' ? 'ادامهٔ آزمون' : 'شروع آزمون'}
                  </Button>
                ) : (
                  <Button variant="secondary" disabled>
                    {quiz.state_fa}
                  </Button>
                )}
              </div>
            </Card>
          </li>
        ))}
      </ul>
    </div>
  );
}

function messageOf(cause: unknown): string {
  if (cause instanceof ApiError || cause instanceof NetworkError) return cause.message;
  return 'خطای غیرمنتظره‌ای رخ داد.';
}
