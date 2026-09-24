'use client';

import { type FormEvent, useCallback, useEffect, useState } from 'react';

import { errorText, ErrorLine } from '@/components/admin/common';
import { fa, SectionHeader } from '@/components/teach/common';
import { useQuiz } from '@/components/teach/QuizFrame';
import { Badge, type BadgeTone } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { SkeletonRow } from '@/components/ui/Skeleton';
import { Textarea } from '@/components/ui/Textarea';
import type { AnswerResponse, Appeal, AttemptResult, AttemptStatus } from '@/lib/api/quizzes';
import {
  attemptAction,
  type AttemptSummary,
  fetchAttempts,
  fetchGradingQueue,
  fetchQuizAppeals,
  fetchStaffResult,
  gradeAnswer,
  type GradingQueue,
  resolveAppeal,
  type TeachQuestion,
} from '@/lib/api/teach';
import { cn } from '@/lib/cn';
import { formatDateTime } from '@/lib/format/date';
import { toLatinDigits, toPersianDigits } from '@/lib/format/digits';

/**
 * `/teach/quizzes/[id]/grade` — صف تصحیح تشریحی، اعتراض و تلاش‌ها (§3.5، M4-10/12).
 *
 * **تصحیح بر اساس سؤال، نه دانشجو:** یک سؤال انتخاب می‌شود و پاسخ همهٔ
 * دانشجویان به همان سؤال پشت سر هم می‌آید — نمره‌دهی یکنواخت‌تر و سریع‌تر.
 */
export function GradingView() {
  const { quiz, token, reload, isInstructor } = useQuiz();
  const [queue, setQueue] = useState<GradingQueue[] | null>(null);
  const [attempts, setAttempts] = useState<AttemptSummary[] | null>(null);
  const [appeals, setAppeals] = useState<Appeal[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [q, a, ap] = await Promise.all([
        fetchGradingQueue(quiz.id, token),
        fetchAttempts(quiz.id, token),
        isInstructor ? fetchQuizAppeals(quiz.id, token) : Promise.resolve([] as Appeal[]),
      ]);
      setQueue(q);
      setAttempts(a);
      setAppeals(ap);
    } catch (cause) {
      setError(errorText(cause));
    }
  }, [quiz.id, token, isInstructor]);

  useEffect(() => {
    void load();
  }, [load]);

  const refreshAll = useCallback(async () => {
    await Promise.all([load(), reload()]);
  }, [load, reload]);

  if ((!queue || !attempts) && !error) return <SkeletonRow label="در حال بارگذاری صف تصحیح" />;
  if (!queue || !attempts) return <ErrorLine>{error}</ErrorLine>;

  const names = Object.fromEntries(attempts.map((a) => [a.id, a.student_name]));

  return (
    <div className="flex flex-col gap-8">
      {error && <ErrorLine>{error}</ErrorLine>}
      <EssayQueue queue={queue} onGraded={refreshAll} />
      {isInstructor && appeals.length > 0 && (
        <AppealsSection appeals={appeals} names={names} onResolved={refreshAll} />
      )}
      <AttemptsSection attempts={attempts} onChanged={refreshAll} />
    </div>
  );
}

// ── صف تشریحی ─────────────────────────────────────────────────────────
function EssayQueue({ queue, onGraded }: { queue: GradingQueue[]; onGraded: () => Promise<void> }) {
  const { quiz, token } = useQuiz();
  const withWork = queue.filter((q) => q.pending.length > 0);
  const pendingTotal = withWork.reduce((sum, q) => sum + q.pending.length, 0);
  const [selected, setSelected] = useState<string | null>(null);
  const current = withWork.find((q) => q.question_id === selected) ?? withWork[0];

  return (
    <section className="flex flex-col gap-3">
      <SectionHeader
        title={`صف تصحیح تشریحی (${toPersianDigits(pendingTotal)} پاسخ)`}
        description="یک سؤال را انتخاب کن؛ پاسخ همهٔ دانشجویان به همان سؤال پشت سر هم می‌آید. Enter در کادر نمره ثبت می‌کند."
      />
      {!current ? (
        <EmptyState
          title="پاسخ تشریحیِ بی‌نمره‌ای نمانده"
          description="نمرهٔ سؤال‌های بسته خودکار ثبت شده است؛ برای بازنویسی نمرهٔ یک سؤال، تلاش را در فهرست پایین باز کن."
        />
      ) : (
        <>
          {withWork.length > 1 && (
            <div className="flex flex-wrap gap-2" aria-label="سؤال‌های منتظر تصحیح">
              {withWork.map((q, index) => {
                const active = current.question_id === q.question_id;
                return (
                  <button
                    key={q.question_id}
                    type="button"
                    aria-pressed={active}
                    onClick={() => setSelected(q.question_id)}
                    className={cn(
                      'rounded-[var(--radius-sm)] border px-3 py-1.5 text-[13px]',
                      active
                        ? 'border-[var(--brand-600)] bg-[var(--brand-50)] font-semibold text-[var(--fg-brand)]'
                        : 'border-[var(--border-default)] text-[var(--fg-secondary)]',
                    )}
                  >
                    سؤال تشریحی {toPersianDigits(index + 1)} · {toPersianDigits(q.pending.length)}{' '}
                    پاسخ
                  </button>
                );
              })}
            </div>
          )}
          <Card className="flex flex-col gap-4">
            <div className="flex flex-col gap-1.5">
              <p className="whitespace-pre-line font-medium">{current.body}</p>
              <span className="text-[13px] text-[var(--fg-secondary)]">
                بارم {fa(current.points)} · {toPersianDigits(current.graded_count)} تصحیح‌شده ·{' '}
                {toPersianDigits(current.pending.length)} مانده
              </span>
              {current.rubric && (
                <p className="rounded-[var(--radius-md)] bg-[var(--bg-sunken)] p-3 text-[13.5px]">
                  <strong>معیار: </strong>
                  {current.rubric}
                </p>
              )}
            </div>
            <ol className="flex flex-col gap-3">
              {current.pending.map((answer) => (
                <li key={`${answer.attempt_id}-${answer.question_id}`}>
                  <ScoreForm
                    who={`${answer.student_name}${
                      answer.attempt_no > 1 ? ` — تلاش ${toPersianDigits(answer.attempt_no)}` : ''
                    }`}
                    answer={
                      <p className="whitespace-pre-line text-[14px]">
                        {answer.response?.text?.trim() || (
                          <span className="text-[var(--fg-tertiary)]">(بی‌پاسخ)</span>
                        )}
                      </p>
                    }
                    max={Number(current.points)}
                    onSubmit={async (score, feedback) => {
                      await gradeAnswer(
                        quiz.id,
                        answer.attempt_id,
                        answer.question_id,
                        { score, feedback },
                        token,
                      );
                      await onGraded();
                    }}
                  />
                </li>
              ))}
            </ol>
          </Card>
        </>
      )}
    </section>
  );
}

function ScoreForm({
  who,
  answer,
  max,
  initialScore = '',
  initialFeedback = '',
  submitLabel = 'ثبت نمره',
  onSubmit,
}: {
  who: string;
  answer: React.ReactNode;
  max: number;
  initialScore?: string;
  initialFeedback?: string;
  submitLabel?: string;
  onSubmit: (score: string, feedback: string | null) => Promise<void>;
}) {
  const [score, setScore] = useState(initialScore);
  const [feedback, setFeedback] = useState(initialFeedback);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const value = Number(toLatinDigits(score).replace('٫', '.'));
  const valid = score.trim() !== '' && !Number.isNaN(value) && value >= 0 && value <= max;

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!valid) return;
    setBusy(true);
    setError(null);
    try {
      await onSubmit(String(value), feedback.trim() || null);
    } catch (cause) {
      setError(errorText(cause));
      setBusy(false);
    }
  }

  return (
    <form
      onSubmit={submit}
      className="flex flex-col gap-2 rounded-[var(--radius-md)] border border-[var(--border-subtle)] p-3"
    >
      <span className="text-[13px] font-semibold text-[var(--fg-secondary)]">{who}</span>
      {answer}
      <div className="flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1 text-[12.5px]">
          نمره (از {fa(max)})
          <input
            inputMode="decimal"
            className="h-10 w-24 rounded-[var(--radius-sm)] border border-[var(--border-default)] bg-[var(--bg-surface)] px-2 text-center tabular-nums"
            value={score}
            onChange={(event) => setScore(event.target.value)}
          />
        </label>
        <label className="flex min-w-[14rem] flex-1 flex-col gap-1 text-[12.5px]">
          بازخورد (اختیاری)
          <input
            className="h-10 rounded-[var(--radius-sm)] border border-[var(--border-default)] bg-[var(--bg-surface)] px-2"
            maxLength={2000}
            value={feedback}
            onChange={(event) => setFeedback(event.target.value)}
          />
        </label>
        <Button type="submit" size="sm" loading={busy} disabled={!valid}>
          {submitLabel}
        </Button>
      </div>
      {score.trim() !== '' && !valid && (
        <span className="text-[12px] text-[var(--fg-danger)]">بین ۰ تا {fa(max)}</span>
      )}
      {error && <ErrorLine>{error}</ErrorLine>}
    </form>
  );
}

// ── اعتراض — M4-12 ────────────────────────────────────────────────────
function AppealsSection({
  appeals,
  names,
  onResolved,
}: {
  appeals: Appeal[];
  names: Record<string, string>;
  onResolved: () => Promise<void>;
}) {
  const { quiz } = useQuiz();
  const questionOf = (id: string | null) => quiz.questions.find((q) => q.id === id);

  return (
    <section className="flex flex-col gap-3">
      <SectionHeader
        title={`اعتراض‌های باز (${toPersianDigits(appeals.length)})`}
        description="پذیرش با نمرهٔ تازه، یا رد با پاسخ مکتوب — هر دو به دانشجو اعلان می‌شوند و در لاگ حسابرسی می‌مانند."
      />
      <ul className="flex flex-col gap-3">
        {appeals.map((appeal) => (
          <li key={appeal.id}>
            <AppealCard
              appeal={appeal}
              student={names[appeal.attempt_id] ?? 'دانشجو'}
              question={questionOf(appeal.question_id)}
              onResolved={onResolved}
            />
          </li>
        ))}
      </ul>
    </section>
  );
}

function AppealCard({
  appeal,
  student,
  question,
  onResolved,
}: {
  appeal: Appeal;
  student: string;
  question: TeachQuestion | undefined;
  onResolved: () => Promise<void>;
}) {
  const { token } = useQuiz();
  const [response, setResponse] = useState('');
  const [newScore, setNewScore] = useState('');
  const [busy, setBusy] = useState<'accept' | 'reject' | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function decide(accept: boolean) {
    setBusy(accept ? 'accept' : 'reject');
    setError(null);
    try {
      await resolveAppeal(
        appeal.id,
        {
          accept,
          response: response.trim(),
          new_score: accept && newScore ? toLatinDigits(newScore).replace('٫', '.') : null,
        },
        token,
      );
      await onResolved();
    } catch (cause) {
      setError(errorText(cause));
      setBusy(null);
    }
  }

  return (
    <Card className="flex flex-col gap-3">
      <div className="flex flex-col gap-1">
        <span className="font-semibold">{student}</span>
        <span className="text-[12.5px] text-[var(--fg-tertiary)]">
          {formatDateTime(appeal.created_at)}
          {question ? ` · دربارهٔ: ${question.body.slice(0, 80)}` : ' · دربارهٔ کل آزمون'}
        </span>
        <p className="whitespace-pre-line text-[14px]">{appeal.reason}</p>
      </div>
      <Textarea
        label="پاسخ به دانشجو"
        rows={2}
        maxLength={2000}
        value={response}
        onChange={(event) => setResponse(event.target.value)}
      />
      <div className="flex flex-wrap items-end gap-2">
        {question && (
          <label className="flex flex-col gap-1 text-[12.5px]">
            نمرهٔ تازهٔ سؤال (از {fa(question.points)})
            <input
              inputMode="decimal"
              className="h-10 w-28 rounded-[var(--radius-sm)] border border-[var(--border-default)] bg-[var(--bg-surface)] px-2 text-center"
              value={newScore}
              onChange={(event) => setNewScore(event.target.value)}
            />
          </label>
        )}
        <Button
          size="sm"
          loading={busy === 'accept'}
          disabled={!response.trim() || busy !== null}
          onClick={() => decide(true)}
        >
          پذیرش
        </Button>
        <Button
          size="sm"
          variant="ghost"
          loading={busy === 'reject'}
          disabled={!response.trim() || busy !== null}
          onClick={() => decide(false)}
        >
          رد
        </Button>
      </div>
      {error && <ErrorLine>{error}</ErrorLine>}
    </Card>
  );
}

// ── تلاش‌ها ────────────────────────────────────────────────────────────
const ATTEMPT_TONES: Record<AttemptStatus, BadgeTone> = {
  IN_PROGRESS: 'info',
  SUBMITTED: 'warning',
  AUTO_SUBMITTED: 'warning',
  GRADED: 'success',
  VOIDED: 'neutral',
};

function AttemptsSection({
  attempts,
  onChanged,
}: {
  attempts: AttemptSummary[];
  onChanged: () => Promise<void>;
}) {
  const [open, setOpen] = useState<string | null>(null);
  return (
    <section className="flex flex-col gap-3">
      <SectionHeader
        title={`تلاش‌ها (${toPersianDigits(attempts.length)})`}
        description="برای دیدن پاسخ‌ها و بازنویسی نمرهٔ یک سؤال (با استاد)، تلاش را باز کن. ستاره یعنی نمره هنوز موقت است."
      />
      {attempts.length === 0 ? (
        <p className="text-[14px] text-[var(--fg-secondary)]">هنوز کسی آزمون را شروع نکرده.</p>
      ) : (
        <ul className="flex flex-col divide-y divide-[var(--border-subtle)] rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-surface)]">
          {attempts.map((attempt) => (
            <li key={attempt.id} className="flex flex-col gap-3 px-4 py-3">
              <AttemptRow
                attempt={attempt}
                expanded={open === attempt.id}
                onToggle={() => setOpen((o) => (o === attempt.id ? null : attempt.id))}
                onChanged={onChanged}
              />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function AttemptRow({
  attempt,
  expanded,
  onToggle,
  onChanged,
}: {
  attempt: AttemptSummary;
  expanded: boolean;
  onToggle: () => void;
  onChanged: () => Promise<void>;
}) {
  const { quiz, token, isInstructor } = useQuiz();
  const [busy, setBusy] = useState<string | null>(null);
  const [confirmVoid, setConfirmVoid] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function act(action: 'finalize' | 'void') {
    if (action === 'void' && !confirmVoid) {
      setConfirmVoid(true);
      return;
    }
    setBusy(action);
    setError(null);
    try {
      await attemptAction(quiz.id, attempt.id, action, token);
      setConfirmVoid(false);
      await onChanged();
    } catch (cause) {
      setError(errorText(cause));
    } finally {
      setBusy(null);
    }
  }

  const submitted = attempt.status === 'SUBMITTED' || attempt.status === 'AUTO_SUBMITTED';

  return (
    <>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-col">
          <span className="flex flex-wrap items-center gap-2 font-medium">
            {attempt.student_name}
            {attempt.attempt_no > 1 && (
              <span className="text-[12.5px] text-[var(--fg-tertiary)]">
                تلاش {toPersianDigits(attempt.attempt_no)}
              </span>
            )}
            <Badge tone={ATTEMPT_TONES[attempt.status]}>{attempt.status_fa}</Badge>
            {attempt.auto_closed && <Badge tone="neutral">بسته‌شده با پایان وقت</Badge>}
            {attempt.integrity_event_count > 0 && (
              <Badge tone="warning">
                {toPersianDigits(attempt.integrity_event_count)} رویداد تمامیت
              </Badge>
            )}
          </span>
          <span className="text-[12.5px] text-[var(--fg-tertiary)]">
            {attempt.submitted_at ? formatDateTime(attempt.submitted_at) : 'هنوز ارسال نشده'}
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="tabular-nums">
            {attempt.total_score === null ? '—' : fa(attempt.total_score)}
            {attempt.is_provisional && attempt.total_score !== null && (
              <span className="text-[var(--fg-warning)]" title="موقت">
                *
              </span>
            )}{' '}
            <span className="text-[12.5px] text-[var(--fg-tertiary)]">
              از {fa(quiz.total_points)}
            </span>
          </span>
          {attempt.status !== 'IN_PROGRESS' && attempt.status !== 'VOIDED' && (
            <Button size="sm" variant="ghost" aria-expanded={expanded} onClick={onToggle}>
              {expanded ? 'بستن' : 'پاسخ‌ها'}
            </Button>
          )}
          {submitted && (
            <Button
              size="sm"
              variant="secondary"
              loading={busy === 'finalize'}
              onClick={() => act('finalize')}
            >
              پایان تصحیح
            </Button>
          )}
          {isInstructor && attempt.status !== 'VOIDED' && (
            <Button
              size="sm"
              variant={confirmVoid ? 'danger' : 'ghost'}
              loading={busy === 'void'}
              onClick={() => act('void')}
            >
              {confirmVoid ? 'بله، ابطال کن' : 'ابطال'}
            </Button>
          )}
        </div>
      </div>
      {confirmVoid && (
        <p role="alert" className="text-[13px] text-[var(--fg-warning)]">
          ابطال نمرهٔ این تلاش را کنار می‌گذارد و در لاگ حسابرسی ثبت می‌شود؛ یک فرصت تلاش به دانشجو
          برمی‌گردد.
        </p>
      )}
      {error && <ErrorLine>{error}</ErrorLine>}
      {expanded && <AttemptDetail attemptId={attempt.id} onChanged={onChanged} />}
    </>
  );
}

function AttemptDetail({
  attemptId,
  onChanged,
}: {
  attemptId: string;
  onChanged: () => Promise<void>;
}) {
  const { quiz, token, isInstructor } = useQuiz();
  const [result, setResult] = useState<AttemptResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [overriding, setOverriding] = useState<string | null>(null);

  const load = useCallback(() => {
    fetchStaffResult(quiz.id, attemptId, token)
      .then(setResult)
      .catch((cause) => setError(errorText(cause)));
  }, [quiz.id, attemptId, token]);

  useEffect(load, [load]);

  if (error) return <ErrorLine>{error}</ErrorLine>;
  if (!result) return <SkeletonRow label="در حال بارگذاری پاسخ‌ها" />;

  return (
    <ol className="flex flex-col gap-2 rounded-[var(--radius-md)] bg-[var(--bg-sunken)] p-3">
      {result.questions.map((question, index) => {
        const source = quiz.questions.find((q) => q.id === question.id);
        return (
          <li key={question.id} className="flex flex-col gap-1.5 text-[13.5px]">
            <span className="flex flex-wrap items-center justify-between gap-2">
              <span className="font-medium">
                {toPersianDigits(index + 1)}. {question.body.slice(0, 120)}
              </span>
              <span className="flex items-center gap-2 tabular-nums">
                {question.score === null ? '—' : fa(question.score)} از {fa(question.points)}
                {/* عوض کردن نمرهٔ ثبت‌شده فقط با استاد است (§6.2، ADR-0019). */}
                {isInstructor && (
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => setOverriding((o) => (o === question.id ? null : question.id))}
                  >
                    بازنویسی
                  </Button>
                )}
              </span>
            </span>
            <span className="text-[var(--fg-secondary)]">
              پاسخ: {describeAnswer(question.my_answer, source)}
            </span>
            {question.feedback && (
              <span className="text-[var(--fg-tertiary)]">بازخورد: {question.feedback}</span>
            )}
            {overriding === question.id && (
              <ScoreForm
                who="نمرهٔ تازهٔ این سؤال — در لاگ حسابرسی ثبت می‌شود"
                answer={null}
                max={Number(question.points)}
                initialScore={question.score === null ? '' : String(Number(question.score))}
                initialFeedback={question.feedback ?? ''}
                submitLabel="ثبت نمرهٔ تازه"
                onSubmit={async (score, feedback) => {
                  await gradeAnswer(quiz.id, attemptId, question.id, { score, feedback }, token);
                  setOverriding(null);
                  load();
                  await onChanged();
                }}
              />
            )}
          </li>
        );
      })}
    </ol>
  );
}

/** پاسخ دانشجو خوانا — شناسهٔ گزینه به متن گزینه. */
function describeAnswer(
  answer: AnswerResponse | null,
  question: TeachQuestion | undefined,
): string {
  if (!answer) return 'بی‌پاسخ';
  const payload = (question?.payload ?? {}) as Record<string, unknown>;
  const label = (list: unknown, id: string) =>
    (Array.isArray(list) ? (list as { id: string; text: string }[]) : []).find((o) => o.id === id)
      ?.text ?? id;
  if ('selected' in answer)
    return answer.selected.map((id) => label(payload.options, id)).join('، ');
  if ('text' in answer) return answer.text || 'بی‌پاسخ';
  if ('pairs' in answer) {
    return answer.pairs
      .map(([l, r]) => `${label(payload.left, l)} ← ${label(payload.right, r)}`)
      .join('؛ ');
  }
  if (typeof answer.value === 'boolean') return answer.value ? 'درست' : 'نادرست';
  return String(answer.value);
}
