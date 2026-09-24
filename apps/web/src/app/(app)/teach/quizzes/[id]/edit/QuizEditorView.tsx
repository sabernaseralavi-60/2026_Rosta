'use client';

import dynamic from 'next/dynamic';
import { useRouter } from 'next/navigation';
import { type ReactNode, useEffect, useState } from 'react';

import { errorText, ErrorLine, Field, SELECT_CLASS } from '@/components/admin/common';
import { fa, SectionHeader } from '@/components/teach/common';
import { useQuiz } from '@/components/teach/QuizFrame';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { Input } from '@/components/ui/Input';
import type { QuestionKind } from '@/lib/api/quizzes';
import {
  addBankItem,
  addQuestion,
  type BankItem,
  copyFromBank,
  deleteQuestion,
  deleteQuiz,
  fetchBank,
  fetchTeachQuiz,
  KIND_LABELS,
  pickRandom,
  quizAction,
  reorderQuestions,
  type TeachQuestion,
  updateQuestion,
  updateQuiz,
} from '@/lib/api/teach';
import { toLatinDigits, toPersianDigits } from '@/lib/format/digits';

// فرم سؤال و تنظیمات فقط با «سؤال تازه»، «ویرایش» یا «ویرایش تنظیمات» باز
// می‌شوند؛ بیشتر بازدیدها فهرست سؤال را می‌خوانند (بودجهٔ باندل، ADR-0019).
const QuestionEditor = dynamic(
  () => import('@/components/teach/QuestionEditor').then((m) => m.QuestionEditor),
  { ssr: false },
);
const QuizSettingsForm = dynamic(
  () => import('@/components/teach/QuizSettingsForm').then((m) => m.QuizSettingsForm),
  { ssr: false },
);

/**
 * `/teach/quizzes/[id]/edit` — ویرایشگر آزمون (§3.5، FR-QUIZ-01، M4-02/03).
 *
 * سؤال‌ها فقط تا پیش از اولین تلاش عوض می‌شوند؛ پس از آن ویرایشگر
 * فقط‌خواندنی است و می‌گوید چرا. انتشار آزمون بی‌سؤال را سرور رد می‌کند.
 */
export function QuizEditorView() {
  const { quiz, offering, token, replace } = useQuiz();
  const router = useRouter();
  const [editing, setEditing] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const editable = quiz.status === 'DRAFT' || quiz.attempt_count === 0;
  const questions = [...quiz.questions].sort((a, b) => a.sort_order - b.sort_order);

  const refresh = async () => replace(await fetchTeachQuiz(quiz.id, token));

  async function run(key: string, action: () => Promise<unknown>): Promise<boolean> {
    setBusy(key);
    setError(null);
    try {
      await action();
      await refresh();
      return true;
    } catch (cause) {
      setError(errorText(cause));
      return false;
    } finally {
      setBusy(null);
    }
  }

  async function move(index: number, delta: number) {
    const order = questions.map((q) => q.id);
    const [moved] = order.splice(index, 1);
    if (moved === undefined) return;
    order.splice(index + delta, 0, moved);
    await run(`move-${index}`, () => reorderQuestions(quiz.id, order, token));
  }

  return (
    <div className="flex flex-col gap-6">
      <Card className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex flex-col gap-0.5">
            <h2 className="text-[16px]">وضعیت آزمون</h2>
            <p className="text-[13px] text-[var(--fg-secondary)]">
              {quiz.status === 'DRAFT' && 'پیش‌نویس — دانشجو نمی‌بیند.'}
              {quiz.status === 'PUBLISHED' &&
                `منتشرشده — نمایش نتیجه: ${quiz.result_visibility_fa}.`}
              {quiz.status === 'CLOSED' && 'بسته — تلاش تازه پذیرفته نمی‌شود.'}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            {quiz.status === 'DRAFT' && (
              <Button
                loading={busy === 'publish'}
                disabled={questions.length === 0}
                onClick={() => run('publish', () => quizAction(quiz.id, 'publish', token))}
              >
                انتشار آزمون
              </Button>
            )}
            {quiz.status === 'PUBLISHED' && (
              <Button
                variant="secondary"
                loading={busy === 'close'}
                onClick={() => run('close', () => quizAction(quiz.id, 'close', token))}
              >
                بستن آزمون
              </Button>
            )}
            {quiz.result_visibility === 'MANUAL' &&
              quiz.status !== 'DRAFT' &&
              !quiz.results_published_at && (
                <Button
                  variant="secondary"
                  loading={busy === 'results'}
                  onClick={() =>
                    run('results', () => quizAction(quiz.id, 'publish-results', token))
                  }
                >
                  انتشار نتیجه‌ها
                </Button>
              )}
            {quiz.attempt_count === 0 && (
              <Button
                variant={confirmDelete ? 'danger' : 'ghost'}
                loading={busy === 'delete'}
                onClick={async () => {
                  if (!confirmDelete) {
                    setConfirmDelete(true);
                    return;
                  }
                  setBusy('delete');
                  try {
                    await deleteQuiz(quiz.id, token);
                    router.push(`/teach/offerings/${offering.id}/quizzes`);
                  } catch (cause) {
                    setError(errorText(cause));
                    setBusy(null);
                  }
                }}
              >
                {confirmDelete ? 'بله، حذف کن' : 'حذف آزمون'}
              </Button>
            )}
          </div>
        </div>
        {quiz.status === 'DRAFT' && questions.length === 0 && (
          <p className="text-[13px] text-[var(--fg-tertiary)]">
            برای انتشار دست‌کم یک سؤال لازم است.
          </p>
        )}
        {error && <ErrorLine>{error}</ErrorLine>}
      </Card>

      <Card className="flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <h2 className="text-[16px]">تنظیمات</h2>
          <Button variant="ghost" size="sm" onClick={() => setSettingsOpen((open) => !open)}>
            {settingsOpen ? 'بستن' : 'ویرایش تنظیمات'}
          </Button>
        </div>
        {settingsOpen && (
          <QuizSettingsForm
            quiz={quiz}
            weeks={offering.weeks}
            submitLabel="ذخیرهٔ تنظیمات"
            onSubmit={async (input) => {
              replace(await updateQuiz(quiz.id, input, token));
              setSettingsOpen(false);
            }}
          />
        )}
      </Card>

      <section className="flex flex-col gap-3">
        <SectionHeader
          title={`سؤال‌ها (${toPersianDigits(questions.length)} سؤال، ${fa(quiz.total_points)} نمره)`}
          description={
            editable
              ? undefined
              : 'این آزمون تلاش ثبت‌شده دارد؛ سؤال‌ها دیگر عوض نمی‌شوند تا نمرهٔ کسی بی‌خبر تغییر نکند.'
          }
          action={
            editable && !adding ? (
              <Button onClick={() => setAdding(true)}>سؤال تازه</Button>
            ) : undefined
          }
        />
        {adding && (
          <Card className="flex flex-col gap-3">
            <h3 className="text-[15px]">سؤال تازه</h3>
            <QuestionEditor
              submitLabel="افزودن سؤال"
              onCancel={() => setAdding(false)}
              onSubmit={async (input) => {
                await addQuestion(quiz.id, input, token);
                await refresh();
                setAdding(false);
              }}
            />
          </Card>
        )}
        {questions.length === 0 && !adding ? (
          <EmptyState
            title="هنوز سؤالی نیست"
            description="سؤال بنویس، یا از بانک سؤالت کپی کن — دستی یا تصادفی."
          />
        ) : (
          <ol className="flex flex-col gap-3">
            {questions.map((question, index) => (
              <li key={question.id}>
                <Card className="flex flex-col gap-3">
                  {editing === question.id ? (
                    <QuestionEditor
                      question={question}
                      submitLabel="ذخیرهٔ سؤال"
                      onCancel={() => setEditing(null)}
                      onSubmit={async (input) => {
                        await updateQuestion(quiz.id, question.id, input, token);
                        await refresh();
                        setEditing(null);
                      }}
                    />
                  ) : (
                    <QuestionSummary
                      index={index}
                      question={question}
                      editable={editable}
                      busy={busy}
                      first={index === 0}
                      last={index === questions.length - 1}
                      onEdit={() => setEditing(question.id)}
                      onMove={(delta) => move(index, delta)}
                      onDelete={() =>
                        run(`del-${question.id}`, () => deleteQuestion(quiz.id, question.id, token))
                      }
                      onBank={() =>
                        run(`bank-${question.id}`, () =>
                          addBankItem(
                            {
                              kind: question.kind,
                              body: question.body,
                              payload: question.payload,
                              explanation: question.explanation,
                              course_id: offering.course_id,
                            },
                            token,
                          ),
                        )
                      }
                    />
                  )}
                </Card>
              </li>
            ))}
          </ol>
        )}
      </section>

      {editable && (
        <BankPicker
          quizId={quiz.id}
          courseId={offering.course_id}
          token={token}
          onAdded={refresh}
        />
      )}
    </div>
  );
}

function QuestionSummary({
  index,
  question,
  editable,
  busy,
  first,
  last,
  onEdit,
  onMove,
  onDelete,
  onBank,
}: {
  index: number;
  question: TeachQuestion;
  editable: boolean;
  busy: string | null;
  first: boolean;
  last: boolean;
  onEdit: () => void;
  onMove: (delta: number) => void;
  onDelete: () => void;
  onBank: () => Promise<boolean>;
}) {
  const [banked, setBanked] = useState(false);
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <span className="flex flex-wrap items-center gap-2">
          <span className="text-[13px] text-[var(--fg-tertiary)]">
            سؤال {toPersianDigits(index + 1)}
          </span>
          <Badge tone="brand">{KIND_LABELS[question.kind]}</Badge>
          <span className="text-[13px] text-[var(--fg-secondary)]">{fa(question.points)} نمره</span>
          {question.bank_id && <Badge tone="neutral">از بانک</Badge>}
        </span>
        <span className="flex flex-wrap gap-1">
          {editable && (
            <>
              <Button
                size="sm"
                variant="ghost"
                disabled={first || busy !== null}
                aria-label={`بالا بردن سؤال ${index + 1}`}
                onClick={() => onMove(-1)}
              >
                ↑
              </Button>
              <Button
                size="sm"
                variant="ghost"
                disabled={last || busy !== null}
                aria-label={`پایین بردن سؤال ${index + 1}`}
                onClick={() => onMove(1)}
              >
                ↓
              </Button>
              <Button size="sm" variant="ghost" onClick={onEdit}>
                ویرایش
              </Button>
              <Button
                size="sm"
                variant="ghost"
                loading={busy === `del-${question.id}`}
                onClick={onDelete}
              >
                حذف
              </Button>
            </>
          )}
          {!question.bank_id && (
            <Button
              size="sm"
              variant="ghost"
              disabled={banked}
              loading={busy === `bank-${question.id}`}
              onClick={async () => setBanked(await onBank())}
            >
              {banked ? 'در بانک ✓' : 'به بانک'}
            </Button>
          )}
        </span>
      </div>
      <p className="whitespace-pre-line text-[14.5px]">{question.body}</p>
      <AnswerKey question={question} />
    </div>
  );
}

/** کلید پاسخ خوانا — فقط برای کادر آموزشی. */
function AnswerKey({ question }: { question: TeachQuestion }) {
  const p = question.payload as Record<string, unknown>;
  const text = (list: unknown) =>
    Array.isArray(list) ? (list as { id: string; text: string }[]) : [];
  let content: ReactNode = null;
  switch (question.kind) {
    case 'SINGLE_CHOICE':
    case 'MULTI_CHOICE': {
      const correct = new Set((p.correct as string[]) ?? []);
      content = (
        <ul className="flex flex-col gap-0.5">
          {text(p.options).map((o) => (
            <li
              key={o.id}
              className={correct.has(o.id) ? 'font-semibold text-[var(--fg-success)]' : ''}
            >
              {correct.has(o.id) ? '✓ ' : '○ '}
              {o.text}
            </li>
          ))}
        </ul>
      );
      break;
    }
    case 'TRUE_FALSE':
      content = <>پاسخ: {p.correct ? 'درست' : 'نادرست'}</>;
      break;
    case 'SHORT_ANSWER':
      content = <>پذیرفته: {((p.accepted as string[]) ?? []).join('، ')}</>;
      break;
    case 'NUMERIC':
      content = (
        <>
          پاسخ: <span dir="ltr">{String(p.correct)}</span>
          {Number(p.tolerance) > 0 && (
            <>
              {' '}
              ± <span dir="ltr">{String(p.tolerance)}</span>
            </>
          )}
          {typeof p.unit === 'string' && ` ${p.unit}`}
        </>
      );
      break;
    case 'ESSAY':
      content = (
        <>تشریحی — در صف تصحیح نمره می‌گیرد.{p.rubric ? ` معیار: ${String(p.rubric)}` : ''}</>
      );
      break;
    case 'MATCHING': {
      const right = Object.fromEntries(text(p.right).map((r) => [r.id, r.text]));
      content = (
        <ul className="flex flex-col gap-0.5">
          {((p.correct as [string, string][]) ?? []).map(([l, r]) => (
            <li key={l}>
              {text(p.left).find((x) => x.id === l)?.text} ← {right[r]}
            </li>
          ))}
        </ul>
      );
      break;
    }
  }
  return <div className="text-[13px] text-[var(--fg-secondary)]">{content}</div>;
}

function BankPicker({
  quizId,
  courseId,
  token,
  onAdded,
}: {
  quizId: string;
  courseId: string;
  token: string;
  onAdded: () => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<BankItem[] | null>(null);
  const [kind, setKind] = useState<QuestionKind | ''>('');
  const [chosen, setChosen] = useState<Set<string>>(new Set());
  const [points, setPoints] = useState('1');
  const [count, setCount] = useState('5');
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    fetchBank({ course_id: courseId, kind: kind || undefined }, token)
      .then(setItems)
      .catch((cause) => setError(errorText(cause)));
  }, [open, courseId, kind, token]);

  const pts = toLatinDigits(points).replace('٫', '.') || '1';

  async function act(key: string, action: () => Promise<{ length: number }>) {
    setBusy(key);
    setError(null);
    setMessage(null);
    try {
      const added = await action();
      setMessage(`${toPersianDigits(added.length)} سؤال به آزمون اضافه شد.`);
      setChosen(new Set());
      await onAdded();
    } catch (cause) {
      setError(errorText(cause));
    } finally {
      setBusy(null);
    }
  }

  return (
    <Card className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <h2 className="text-[16px]">از بانک سؤال</h2>
        <Button variant="ghost" size="sm" onClick={() => setOpen((o) => !o)}>
          {open ? 'بستن' : 'باز کردن بانک این درس'}
        </Button>
      </div>
      {open && (
        <>
          <div className="grid gap-3 sm:grid-cols-3">
            <Field label="نوع">
              <select
                className={SELECT_CLASS}
                value={kind}
                onChange={(event) => setKind(event.target.value as QuestionKind | '')}
              >
                <option value="">همه</option>
                {(Object.keys(KIND_LABELS) as QuestionKind[]).map((key) => (
                  <option key={key} value={key}>
                    {KIND_LABELS[key]}
                  </option>
                ))}
              </select>
            </Field>
            <Input
              label="بارم هر سؤال"
              inputMode="decimal"
              value={points}
              onChange={(e) => setPoints(e.target.value)}
            />
          </div>
          {!items ? (
            <p className="text-[13.5px] text-[var(--fg-tertiary)]">در حال بارگذاری…</p>
          ) : items.length === 0 ? (
            <p className="text-[13.5px] text-[var(--fg-secondary)]">
              بانک این درس خالی است. سؤال‌های خوب را با «به بانک» نگه دار، یا از صفحهٔ «بانک سؤال»
              بنویس.
            </p>
          ) : (
            <>
              <ul className="flex max-h-80 flex-col divide-y divide-[var(--border-subtle)] overflow-y-auto rounded-[var(--radius-md)] border border-[var(--border-subtle)]">
                {items.map((item) => (
                  <li key={item.id}>
                    <label className="flex cursor-pointer items-start gap-2 px-3 py-2 text-[13.5px]">
                      <input
                        type="checkbox"
                        className="mt-1"
                        checked={chosen.has(item.id)}
                        onChange={() =>
                          setChosen((set) => {
                            const next = new Set(set);
                            if (next.has(item.id)) next.delete(item.id);
                            else next.add(item.id);
                            return next;
                          })
                        }
                      />
                      <span className="flex flex-col">
                        <span className="line-clamp-2">{item.body}</span>
                        <span className="text-[12px] text-[var(--fg-tertiary)]">
                          {item.kind_fa}
                          {item.difficulty
                            ? ` · دشواری ${toPersianDigits(item.difficulty)}`
                            : ''} · {toPersianDigits(item.usage_count)} بار استفاده
                        </span>
                      </span>
                    </label>
                  </li>
                ))}
              </ul>
              <div className="flex flex-wrap items-end gap-3">
                <Button
                  variant="secondary"
                  disabled={chosen.size === 0}
                  loading={busy === 'copy'}
                  onClick={() => act('copy', () => copyFromBank(quizId, [...chosen], pts, token))}
                >
                  افزودن {toPersianDigits(chosen.size)} سؤال انتخابی
                </Button>
                <span className="text-[13px] text-[var(--fg-tertiary)]">یا</span>
                <div className="w-24">
                  <Input
                    label="تعداد تصادفی"
                    inputMode="numeric"
                    value={count}
                    onChange={(e) => setCount(e.target.value.replace(/[^\d۰-۹]/g, ''))}
                  />
                </div>
                <Button
                  variant="secondary"
                  disabled={!count}
                  loading={busy === 'random'}
                  onClick={() =>
                    act('random', () =>
                      pickRandom(
                        quizId,
                        {
                          count: Number(toLatinDigits(count)),
                          course_id: courseId,
                          points: pts,
                        },
                        token,
                      ),
                    )
                  }
                >
                  انتخاب تصادفی
                </Button>
              </div>
            </>
          )}
          {message && (
            <p role="status" className="text-[13.5px] text-[var(--fg-success)]">
              {message}
            </p>
          )}
          {error && <ErrorLine>{error}</ErrorLine>}
        </>
      )}
    </Card>
  );
}
