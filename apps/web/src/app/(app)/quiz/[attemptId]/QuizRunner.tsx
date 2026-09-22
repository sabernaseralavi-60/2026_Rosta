'use client';

import { useRouter } from 'next/navigation';
import { useCallback, useEffect, useRef, useState } from 'react';

import { QuestionField } from '@/components/domain/QuestionField';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card, CardTitle } from '@/components/ui/Card';
import { SkeletonCard } from '@/components/ui/Skeleton';
import { ApiError, NetworkError } from '@/lib/api/client';
import {
  type AnswerResponse,
  type AttemptView,
  fetchAttempt,
  recordIntegrityEvent,
  saveAnswer,
  submitAttempt,
  syncAnswers,
} from '@/lib/api/quizzes';
import { useSession } from '@/lib/auth/use-session';
import { cn } from '@/lib/cn';
import { toPersianDigits } from '@/lib/format/digits';
import {
  type PendingMap,
  clearAnswer,
  clearAttempt,
  isAnswered,
  pendingCount,
  queueAnswer,
  readPending,
  toSyncPayload,
} from '@/lib/quiz/offline-store';
import {
  type TimerAnchor,
  anchor,
  crossedWarning,
  formatClock,
  levelFor,
  remainingAt,
} from '@/lib/quiz/timer';

/**
 * محیط آزمون — §3.4، وظیفه‌های M4-06 و M4-15.
 *
 * سه چیز که این صفحه را از یک فرم معمولی جدا می‌کند:
 *
 * ۱. **زمان‌سنج به سرور لنگر دارد.** هر پاسخ سرور `seconds_remaining`
 *    می‌دهد و لنگر تازه می‌شود؛ ساعت مرورگر فقط «چند ثانیه گذشت» را
 *    می‌گوید. دستکاری ساعت سیستم اثری ندارد.
 *
 * ۲. **هر پاسخ اول روی دیسک می‌نشیند، بعد فرستاده می‌شود.** قطع
 *    اینترنت یا بستن تب، کار انجام‌شده را نمی‌برد.
 *
 * ۳. **نشانگر همگام‌سازی دروغ نمی‌گوید.** تا وقتی چیزی در صف مانده،
 *    «ذخیره شد» نشان داده نمی‌شود.
 */

const AUTOSAVE_MS = 10_000;
const TICK_MS = 1_000;
const LONG_PASTE_CHARS = 200;

type SyncState = 'saved' | 'pending' | 'offline' | 'saving';

const SYNC_LABEL: Record<SyncState, string> = {
  saved: 'همهٔ پاسخ‌ها ذخیره شد',
  saving: 'در حال ذخیره…',
  pending: 'ذخیرهٔ محلی — در انتظار ارسال',
  offline: 'اینترنت قطع است — پاسخ‌ها محلی نگه داشته می‌شوند',
};

const SYNC_TONE: Record<SyncState, 'success' | 'neutral' | 'warning'> = {
  saved: 'success',
  saving: 'neutral',
  pending: 'warning',
  offline: 'warning',
};

export function QuizRunner({ attemptId }: { attemptId: string }) {
  const router = useRouter();
  const { accessToken, loading: sessionLoading } = useSession();

  const [attempt, setAttempt] = useState<AttemptView | null>(null);
  const [answers, setAnswers] = useState<Record<string, AnswerResponse | null>>({});
  const [flagged, setFlagged] = useState<Record<string, boolean>>({});
  const [current, setCurrent] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [confirming, setConfirming] = useState(false);

  const [timer, setTimer] = useState<TimerAnchor | null>(null);
  const [seconds, setSeconds] = useState(0);
  const [pending, setPending] = useState<PendingMap>({});
  const [syncState, setSyncState] = useState<SyncState>('saved');

  // آخرین ثانیهٔ دیده‌شده — برای اینکه هشدار آستانه یک بار ساخته شود.
  const previousSeconds = useRef<number>(Number.POSITIVE_INFINITY);
  const submittedRef = useRef(false);

  // ── بارگذاری اولیه ──────────────────────────────────────────────────
  useEffect(() => {
    if (sessionLoading || !accessToken) return;
    let cancelled = false;

    fetchAttempt(attemptId, accessToken)
      .then((data) => {
        if (cancelled) return;
        setAttempt(data);
        setTimer(anchor(data.seconds_remaining));
        setSeconds(data.seconds_remaining);
        previousSeconds.current = data.seconds_remaining;

        const stored = readPending(attemptId);
        setPending(stored);

        // پاسخ سرور پایه است؛ صف محلی رویش می‌نشیند چون تازه‌تر است.
        const initial: Record<string, AnswerResponse | null> = {};
        const initialFlags: Record<string, boolean> = {};
        for (const question of data.questions) {
          initial[question.id] = question.my_answer;
          initialFlags[question.id] = question.is_flagged;
        }
        for (const [questionId, entry] of Object.entries(stored)) {
          initial[questionId] = entry.response;
          initialFlags[questionId] = entry.is_flagged;
        }
        setAnswers(initial);
        setFlagged(initialFlags);
        setSyncState(pendingCount(stored) > 0 ? 'pending' : 'saved');
      })
      .catch((cause) => {
        if (cancelled) return;
        setError(messageOf(cause));
      });

    return () => {
      cancelled = true;
    };
  }, [attemptId, accessToken, sessionLoading]);

  // ── تیک زمان‌سنج ────────────────────────────────────────────────────
  useEffect(() => {
    if (!timer) return;
    const id = window.setInterval(() => {
      const left = remainingAt(timer);
      setSeconds(left);
      const warning = crossedWarning(previousSeconds.current, left);
      if (warning) setNotice(warning);
      previousSeconds.current = left;
    }, TICK_MS);
    return () => window.clearInterval(id);
  }, [timer]);

  // ── ارسال خودکار در پایان زمان ─────────────────────────────────────
  //
  // سرور هم خودش می‌بندد (کار پس‌زمینه، §7.3 قاعدهٔ ۲)؛ این فقط دانشجو
  // را زودتر به صفحهٔ نتیجه می‌برد، نه اینکه جایگزین آن باشد.
  useEffect(() => {
    if (seconds > 0 || !attempt || submittedRef.current) return;
    submittedRef.current = true;
    void finish(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [seconds, attempt]);

  // ── ذخیرهٔ دوره‌ای صف ──────────────────────────────────────────────
  useEffect(() => {
    if (!accessToken || !attempt) return;
    const id = window.setInterval(() => {
      void flushPending();
    }, AUTOSAVE_MS);
    return () => window.clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accessToken, attempt, pending]);

  // ── رویدادهای تمامیت — FR-QUIZ-05 ─────────────────────────────────
  //
  // «فقط گزارش می‌شوند، خودکار تقلب تلقی نمی‌شوند.» پس شکستشان هم
  // بی‌صداست: ثبت‌نشدن یک رویداد نباید آزمون کسی را مختل کند.
  useEffect(() => {
    if (!accessToken || !attempt) return;
    function onBlur() {
      void recordIntegrityEvent(attemptId, 'TAB_BLUR', accessToken!).catch(() => {});
    }
    function onPaste(event: ClipboardEvent) {
      const text = event.clipboardData?.getData('text') ?? '';
      if (text.length >= LONG_PASTE_CHARS) {
        void recordIntegrityEvent(attemptId, 'LONG_PASTE', accessToken!, {
          length: text.length,
        }).catch(() => {});
      }
    }
    function onOnline() {
      setSyncState('pending');
      void flushPending();
      void recordIntegrityEvent(attemptId, 'RECONNECT', accessToken!).catch(() => {});
    }
    function onOffline() {
      setSyncState('offline');
    }

    window.addEventListener('blur', onBlur);
    window.addEventListener('paste', onPaste);
    window.addEventListener('online', onOnline);
    window.addEventListener('offline', onOffline);
    return () => {
      window.removeEventListener('blur', onBlur);
      window.removeEventListener('paste', onPaste);
      window.removeEventListener('online', onOnline);
      window.removeEventListener('offline', onOffline);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [attemptId, accessToken, attempt]);

  // ── نوشتن پاسخ ─────────────────────────────────────────────────────
  const change = useCallback(
    (questionId: string, value: AnswerResponse | null) => {
      setAnswers((prev) => ({ ...prev, [questionId]: value }));
      const queued = queueAnswer(attemptId, questionId, {
        response: value,
        is_flagged: flagged[questionId] ?? false,
      });
      setPending(queued);
      setSyncState(navigator.onLine === false ? 'offline' : 'pending');
      void sendOne(questionId, queued);
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [attemptId, flagged, accessToken],
  );

  const toggleFlag = useCallback(
    (questionId: string) => {
      const next = !(flagged[questionId] ?? false);
      setFlagged((prev) => ({ ...prev, [questionId]: next }));
      const queued = queueAnswer(attemptId, questionId, {
        response: answers[questionId] ?? null,
        is_flagged: next,
      });
      setPending(queued);
      void sendOne(questionId, queued);
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [attemptId, answers, flagged, accessToken],
  );

  async function sendOne(questionId: string, queued: PendingMap) {
    if (!accessToken) return;
    const entry = queued[questionId];
    if (!entry) return;
    setSyncState('saving');
    try {
      const result = await saveAnswer(
        attemptId,
        questionId,
        {
          response: entry.response,
          is_flagged: entry.is_flagged,
          client_ts: entry.client_ts,
        },
        accessToken,
      );
      const left = clearAnswer(attemptId, questionId, entry.client_ts);
      setPending(left);
      setTimer(anchor(result.seconds_remaining));
      setSyncState(pendingCount(left) > 0 ? 'pending' : 'saved');
    } catch (cause) {
      // پاسخ در صف ماند؛ `flushPending` بعداً می‌بردش.
      setSyncState(cause instanceof NetworkError ? 'offline' : 'pending');
      if (cause instanceof ApiError && cause.code === 'ATTEMPT_EXPIRED') {
        setError(cause.message);
      }
    }
  }

  async function flushPending() {
    if (!accessToken) return;
    const queued = readPending(attemptId);
    if (pendingCount(queued) === 0) {
      setSyncState('saved');
      return;
    }
    setSyncState('saving');
    try {
      const result = await syncAnswers(attemptId, toSyncPayload(queued), accessToken);
      for (const questionId of result.accepted) {
        clearAnswer(attemptId, questionId, queued[questionId]?.client_ts ?? '');
      }
      // پاسخ ردشده هم از صف می‌رود: تکرارش همان نتیجه را می‌دهد و
      // صفِ همیشه‌پر، نشانگر را برای همیشه زرد نگه می‌دارد.
      for (const questionId of result.rejected) {
        clearAnswer(attemptId, questionId, queued[questionId]?.client_ts ?? '');
      }
      const left = readPending(attemptId);
      setPending(left);
      setTimer(anchor(result.seconds_remaining));
      setSyncState(pendingCount(left) > 0 ? 'pending' : 'saved');
      if (result.rejected.length > 0) {
        setNotice(
          `${toPersianDigits(result.rejected.length)} پاسخ پس از پایان زمان نوشته شده بود و ثبت نشد.`,
        );
      }
    } catch (cause) {
      setSyncState(cause instanceof NetworkError ? 'offline' : 'pending');
    }
  }

  // ── ارسال نهایی ────────────────────────────────────────────────────
  async function finish(auto = false) {
    if (!accessToken || !attempt) return;
    setSubmitting(true);
    setError(null);
    try {
      await flushPending();
      await submitAttempt(attemptId, unansweredCount, accessToken);
      clearAttempt(attemptId);
      router.push(`/quiz/${attemptId}/result`);
    } catch (cause) {
      if (cause instanceof ApiError && cause.code === 'ATTEMPT_ALREADY_SUBMITTED') {
        // زمان تمام شده و کار پس‌زمینهٔ سرور زودتر بسته‌اش — نتیجه هست.
        clearAttempt(attemptId);
        router.push(`/quiz/${attemptId}/result`);
        return;
      }
      setError(messageOf(cause));
      if (auto) submittedRef.current = false;
    } finally {
      setSubmitting(false);
      setConfirming(false);
    }
  }

  // ── نمایش ──────────────────────────────────────────────────────────
  if (sessionLoading || (!attempt && !error)) {
    return <SkeletonCard />;
  }
  if (error && !attempt) {
    return (
      <Card className="p-6">
        <p className="text-[15px] text-[var(--danger-600)]">{error}</p>
      </Card>
    );
  }
  if (!attempt) return null;

  const question = attempt.questions[current];
  const answeredCount = attempt.questions.filter((q) => isAnswered(answers[q.id])).length;
  const unansweredCount = attempt.questions.length - answeredCount;
  const level = levelFor(seconds);
  const readOnly = attempt.status !== 'IN_PROGRESS' || seconds <= 0;

  return (
    <div className="space-y-4">
      {/* ── سربرگ: زمان‌سنج و نشانگر همگام‌سازی ── */}
      <Card className="flex flex-wrap items-center justify-between gap-3 p-4">
        <div>
          <CardTitle className="text-[17px]">{attempt.quiz_title_fa}</CardTitle>
          <p className="mt-1 text-[13px] text-[var(--fg-secondary)]">
            {toPersianDigits(answeredCount)} از {toPersianDigits(attempt.questions.length)} سؤال
            پاسخ داده شده
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Badge tone={SYNC_TONE[syncState]}>{SYNC_LABEL[syncState]}</Badge>
          <div
            role="timer"
            aria-live={level === 'danger' ? 'assertive' : 'off'}
            aria-label="زمان باقی‌مانده"
            className={cn(
              'rounded-[var(--radius-md)] px-4 py-2 font-mono text-[20px] tabular-nums',
              level === 'normal' && 'bg-[var(--bg-sunken)] text-[var(--fg-primary)]',
              level === 'warn' &&
                'bg-[color-mix(in_oklch,var(--warning-500)_18%,transparent)] text-[var(--warning-600)]',
              (level === 'danger' || level === 'expired') &&
                'bg-[color-mix(in_oklch,var(--danger-500)_14%,transparent)] text-[var(--danger-600)]',
            )}
          >
            {formatClock(seconds)}
          </div>
        </div>
      </Card>

      {notice ? (
        <div
          role="status"
          className="rounded-[var(--radius-md)] bg-[color-mix(in_oklch,var(--warning-500)_14%,transparent)] p-3 text-[14px] text-[var(--warning-600)]"
        >
          {notice}
        </div>
      ) : null}
      {error ? (
        <div role="alert" className="rounded-[var(--radius-md)] bg-[color-mix(in_oklch,var(--danger-500)_12%,transparent)] p-3 text-[14px] text-[var(--danger-600)]">
          {error}
        </div>
      ) : null}

      <div className="grid gap-4 lg:grid-cols-[1fr_260px]">
        {/* ── سؤال جاری ── */}
        <Card className="space-y-4 p-5">
          {question ? (
            <>
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-[13px] text-[var(--fg-secondary)]">
                    سؤال {toPersianDigits(current + 1)} · {question.kind_fa} ·{' '}
                    {toPersianDigits(question.points)} نمره
                  </p>
                  <h2 className="mt-2 text-[17px] leading-8 text-[var(--fg-primary)]">
                    {question.body}
                  </h2>
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => toggleFlag(question.id)}
                  aria-pressed={flagged[question.id] ?? false}
                >
                  {flagged[question.id] ? '★ نشان‌شده' : '☆ نشان برای مرور'}
                </Button>
              </div>

              <QuestionField
                question={question}
                value={answers[question.id] ?? null}
                onChange={(value) => change(question.id, value)}
                disabled={readOnly}
              />

              <div className="flex items-center justify-between gap-3 border-t border-[var(--border-subtle)] pt-4">
                <Button
                  variant="secondary"
                  onClick={() => setCurrent((index) => Math.max(0, index - 1))}
                  disabled={current === 0}
                >
                  سؤال قبلی
                </Button>
                <Button
                  variant="secondary"
                  onClick={() =>
                    setCurrent((index) => Math.min(attempt.questions.length - 1, index + 1))
                  }
                  disabled={current === attempt.questions.length - 1}
                >
                  سؤال بعدی
                </Button>
              </div>
            </>
          ) : (
            <p className="text-[15px] text-[var(--fg-secondary)]">این آزمون سؤالی ندارد.</p>
          )}
        </Card>

        {/* ── ناوبر سؤالات ── */}
        <div className="space-y-3">
          <Card className="p-4">
            <h3 className="mb-3 text-[14px] font-medium text-[var(--fg-primary)]">
              ناوبری سؤالات
            </h3>
            <ol className="grid grid-cols-6 gap-2 lg:grid-cols-5">
              {attempt.questions.map((item, index) => {
                const done = isAnswered(answers[item.id]);
                const mark = flagged[item.id];
                return (
                  <li key={item.id}>
                    <button
                      type="button"
                      onClick={() => setCurrent(index)}
                      aria-current={index === current ? 'true' : undefined}
                      aria-label={`سؤال ${index + 1}${done ? '، پاسخ داده شده' : '، بی‌پاسخ'}${mark ? '، نشان‌شده' : ''}`}
                      className={cn(
                        'relative flex size-9 items-center justify-center rounded-[var(--radius-sm)]',
                        'text-[13px] transition-colors',
                        index === current && 'ring-2 ring-[var(--brand-600)]',
                        done
                          ? 'bg-[var(--brand-600)] text-[var(--fg-on-brand)]'
                          : 'bg-[var(--bg-sunken)] text-[var(--fg-secondary)]',
                      )}
                    >
                      {toPersianDigits(index + 1)}
                      {mark ? (
                        <span
                          aria-hidden
                          className="absolute -top-1 -start-1 text-[11px] text-[var(--warning-600)]"
                        >
                          ★
                        </span>
                      ) : null}
                    </button>
                  </li>
                );
              })}
            </ol>
          </Card>

          <Card className="space-y-3 p-4">
            {unansweredCount > 0 ? (
              <p className="text-[13.5px] text-[var(--warning-600)]">
                {toPersianDigits(unansweredCount)} سؤال بی‌پاسخ مانده است.
              </p>
            ) : (
              <p className="text-[13.5px] text-[var(--success-600)]">
                به همهٔ سؤال‌ها پاسخ داده‌اید.
              </p>
            )}

            {confirming ? (
              <div className="space-y-2">
                <p className="text-[13.5px] text-[var(--fg-secondary)]">
                  پس از ارسال، امکان تغییر پاسخ‌ها نیست.
                </p>
                <div className="flex gap-2">
                  <Button onClick={() => void finish()} loading={submitting} fullWidth>
                    ارسال نهایی
                  </Button>
                  <Button variant="ghost" onClick={() => setConfirming(false)}>
                    انصراف
                  </Button>
                </div>
              </div>
            ) : (
              <Button onClick={() => setConfirming(true)} disabled={readOnly} fullWidth>
                پایان و ارسال آزمون
              </Button>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}

function messageOf(cause: unknown): string {
  if (cause instanceof ApiError || cause instanceof NetworkError) return cause.message;
  return 'خطای غیرمنتظره‌ای رخ داد.';
}
