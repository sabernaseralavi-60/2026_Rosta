'use client';

import { type FormEvent, useId, useState } from 'react';

import { errorText, ErrorLine, Field, SELECT_CLASS } from '@/components/admin/common';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Textarea } from '@/components/ui/Textarea';
import type { QuestionKind } from '@/lib/api/quizzes';
import { KIND_LABELS, type QuestionInput, type TeachQuestion } from '@/lib/api/teach';
import { toLatinDigits } from '@/lib/format/digits';

import { INPUT_CLASS } from './common';

/**
 * ویرایشگر یک سؤال — هفت نوع FR-QUIZ-01.
 *
 * خروجی همان `payload`ی است که `silp.domain.quiz.payload.parse_question`
 * می‌پذیرد. اعتبارسنجی نهایی با سرور است و پیامش همان‌جا نشان داده
 * می‌شود؛ این فرم فقط کاری می‌کند که ساختن سؤال نیمه‌کاره سخت باشد.
 */

interface Item {
  id: string;
  text: string;
}

interface Draft {
  kind: QuestionKind;
  body: string;
  points: string;
  explanation: string;
  options: Item[];
  correct: string[];
  truth: boolean;
  accepted: string;
  caseSensitive: boolean;
  number: string;
  tolerance: string;
  unit: string;
  minWords: string;
  maxWords: string;
  rubric: string;
  left: Item[];
  right: Item[];
  pairs: Record<string, string>;
}

const LETTERS = 'abcdefghijkl';

function items(count: number, prefix = ''): Item[] {
  return Array.from({ length: count }, (_, i) => ({ id: `${prefix}${LETTERS[i]}`, text: '' }));
}

function asItems(value: unknown): Item[] {
  return Array.isArray(value)
    ? value.map((raw) => ({
        id: String((raw as Item).id),
        text: String((raw as Item).text ?? ''),
      }))
    : [];
}

function initial(kind: QuestionKind, question?: TeachQuestion): Draft {
  const p = question?.payload ?? {};
  const correct = p.correct;
  return {
    kind,
    body: question?.body ?? '',
    points: question?.points ? String(Number(question.points)) : '1',
    explanation: question?.explanation ?? '',
    options: asItems(p.options).length ? asItems(p.options) : items(4),
    correct: Array.isArray(correct) && !Array.isArray(correct[0]) ? correct.map(String) : [],
    truth: typeof correct === 'boolean' ? correct : true,
    accepted: Array.isArray(p.accepted) ? p.accepted.map(String).join('\n') : '',
    caseSensitive: Boolean(p.case_sensitive),
    number: kind === 'NUMERIC' && correct !== undefined ? String(correct) : '',
    tolerance: p.tolerance !== undefined ? String(p.tolerance) : '0',
    unit: typeof p.unit === 'string' ? p.unit : '',
    minWords: typeof p.min_words === 'number' ? String(p.min_words) : '',
    maxWords: typeof p.max_words === 'number' ? String(p.max_words) : '',
    rubric: typeof p.rubric === 'string' ? p.rubric : '',
    left: asItems(p.left).length ? asItems(p.left) : items(3, 'l'),
    right: asItems(p.right).length ? asItems(p.right) : items(3, 'r'),
    pairs:
      kind === 'MATCHING' && Array.isArray(correct)
        ? Object.fromEntries(
            (correct as unknown[][]).map((pair) => [String(pair[0]), String(pair[1])]),
          )
        : {},
  };
}

function num(value: string): string {
  return toLatinDigits(value).replace('٫', '.').trim();
}

function toInput(d: Draft): QuestionInput {
  const clean = (list: Item[]) => list.filter((o) => o.text.trim());
  let payload: Record<string, unknown>;
  switch (d.kind) {
    case 'SINGLE_CHOICE':
    case 'MULTI_CHOICE': {
      const options = clean(d.options);
      const ids = new Set(options.map((o) => o.id));
      payload = { options, correct: d.correct.filter((id) => ids.has(id)) };
      break;
    }
    case 'TRUE_FALSE':
      payload = { correct: d.truth };
      break;
    case 'SHORT_ANSWER':
      payload = {
        accepted: d.accepted
          .split('\n')
          .map((line) => line.trim())
          .filter(Boolean),
        case_sensitive: d.caseSensitive,
      };
      break;
    case 'NUMERIC':
      payload = {
        correct: num(d.number),
        tolerance: num(d.tolerance) || '0',
        ...(d.unit.trim() ? { unit: d.unit.trim() } : {}),
      };
      break;
    case 'ESSAY':
      payload = {
        ...(d.minWords ? { min_words: Number(num(d.minWords)) } : {}),
        ...(d.maxWords ? { max_words: Number(num(d.maxWords)) } : {}),
        ...(d.rubric.trim() ? { rubric: d.rubric.trim() } : {}),
      };
      break;
    case 'MATCHING': {
      const left = clean(d.left);
      const right = clean(d.right);
      payload = {
        left,
        right,
        correct: left.filter((l) => d.pairs[l.id]).map((l) => [l.id, d.pairs[l.id]]),
      };
      break;
    }
  }
  return {
    kind: d.kind,
    body: d.body.trim(),
    points: num(d.points) || '1',
    explanation: d.explanation.trim() || null,
    payload,
  };
}

export function QuestionEditor({
  question,
  kind: initialKind = 'SINGLE_CHOICE',
  submitLabel,
  withPoints = true,
  onSubmit,
  onCancel,
}: {
  question?: TeachQuestion;
  kind?: QuestionKind;
  submitLabel: string;
  withPoints?: boolean;
  onSubmit: (input: QuestionInput) => Promise<void>;
  onCancel?: () => void;
}) {
  const [draft, setDraft] = useState<Draft>(() => initial(question?.kind ?? initialKind, question));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const uid = useId();

  const set = <K extends keyof Draft>(key: K, value: Draft[K]) =>
    setDraft((d) => ({ ...d, [key]: value }));

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await onSubmit(toInput(draft));
    } catch (cause) {
      setError(errorText(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-4">
      <div className="grid gap-3 sm:grid-cols-[1fr_8rem]">
        <Field label="نوع سؤال">
          <select
            className={SELECT_CLASS}
            value={draft.kind}
            disabled={Boolean(question)}
            onChange={(event) =>
              setDraft((d) => ({
                ...initial(event.target.value as QuestionKind),
                body: d.body,
                points: d.points,
              }))
            }
          >
            {(Object.keys(KIND_LABELS) as QuestionKind[]).map((key) => (
              <option key={key} value={key}>
                {KIND_LABELS[key]}
              </option>
            ))}
          </select>
        </Field>
        {withPoints && (
          <Input
            label="بارم"
            inputMode="decimal"
            required
            value={draft.points}
            onChange={(event) => set('points', event.target.value)}
          />
        )}
      </div>
      <Textarea
        label="متن سؤال"
        rows={3}
        required
        maxLength={4000}
        value={draft.body}
        onChange={(event) => set('body', event.target.value)}
      />

      {(draft.kind === 'SINGLE_CHOICE' || draft.kind === 'MULTI_CHOICE') && (
        <ChoiceEditor name={`${uid}-correct`} draft={draft} setDraft={setDraft} />
      )}

      {draft.kind === 'TRUE_FALSE' && (
        <fieldset className="flex gap-4 text-[14px]">
          <legend className="mb-1 text-[13.5px] font-medium">پاسخ درست</legend>
          {[true, false].map((value) => (
            <label key={String(value)} className="flex items-center gap-2">
              <input
                type="radio"
                name={`${uid}-truth`}
                checked={draft.truth === value}
                onChange={() => set('truth', value)}
              />
              {value ? 'درست' : 'نادرست'}
            </label>
          ))}
        </fieldset>
      )}

      {draft.kind === 'SHORT_ANSWER' && (
        <>
          <Textarea
            label="پاسخ‌های پذیرفته"
            hint="هر پاسخ در یک سطر. «ي» و «ك» عربی، نیم‌فاصله و فاصلهٔ اضافه یکسان حساب می‌شوند."
            rows={3}
            required
            value={draft.accepted}
            onChange={(event) => set('accepted', event.target.value)}
          />
          <label className="flex items-center gap-2 text-[13.5px]">
            <input
              type="checkbox"
              checked={draft.caseSensitive}
              onChange={(event) => set('caseSensitive', event.target.checked)}
            />
            حروف بزرگ و کوچک لاتین فرق دارند
          </label>
        </>
      )}

      {draft.kind === 'NUMERIC' && (
        <div className="grid gap-3 sm:grid-cols-3">
          <Input
            label="پاسخ درست"
            inputMode="decimal"
            forceLtr
            required
            value={draft.number}
            onChange={(event) => set('number', event.target.value)}
          />
          <Input
            label="خطای مجاز (±)"
            inputMode="decimal"
            forceLtr
            value={draft.tolerance}
            onChange={(event) => set('tolerance', event.target.value)}
          />
          <Input
            label="واحد (اختیاری)"
            value={draft.unit}
            onChange={(event) => set('unit', event.target.value)}
          />
        </div>
      )}

      {draft.kind === 'ESSAY' && (
        <>
          <div className="grid gap-3 sm:grid-cols-2">
            <Input
              label="کمینهٔ واژه"
              inputMode="numeric"
              value={draft.minWords}
              onChange={(event) => set('minWords', event.target.value.replace(/[^\d۰-۹]/g, ''))}
            />
            <Input
              label="بیشینهٔ واژه"
              inputMode="numeric"
              value={draft.maxWords}
              onChange={(event) => set('maxWords', event.target.value.replace(/[^\d۰-۹]/g, ''))}
            />
          </div>
          <Textarea
            label="معیار نمره‌دهی (روبریک)"
            hint="در صف تصحیح کنار هر پاسخ دیده می‌شود؛ دانشجو هم هنگام پاسخ آن را می‌بیند."
            rows={3}
            value={draft.rubric}
            onChange={(event) => set('rubric', event.target.value)}
          />
        </>
      )}

      {draft.kind === 'MATCHING' && <MatchingEditor draft={draft} setDraft={setDraft} />}

      <Textarea
        label="توضیح پس از نتیجه (اختیاری)"
        rows={2}
        maxLength={4000}
        value={draft.explanation}
        onChange={(event) => set('explanation', event.target.value)}
      />
      {error && <ErrorLine>{error}</ErrorLine>}
      <div className="flex gap-2">
        <Button type="submit" loading={busy} disabled={!draft.body.trim()}>
          {submitLabel}
        </Button>
        {onCancel && (
          <Button type="button" variant="ghost" onClick={onCancel}>
            انصراف
          </Button>
        )}
      </div>
    </form>
  );
}

function ChoiceEditor({
  name,
  draft,
  setDraft,
}: {
  name: string;
  draft: Draft;
  setDraft: (update: (d: Draft) => Draft) => void;
}) {
  const single = draft.kind === 'SINGLE_CHOICE';
  const unused = LETTERS.split('').find((l) => !draft.options.some((o) => o.id === l));

  function toggle(id: string) {
    setDraft((d) => ({
      ...d,
      correct: single
        ? [id]
        : d.correct.includes(id)
          ? d.correct.filter((c) => c !== id)
          : [...d.correct, id],
    }));
  }

  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="mb-1 text-[13.5px] font-medium">
        گزینه‌ها — {single ? 'گزینهٔ درست را علامت بزن' : 'همهٔ گزینه‌های درست را علامت بزن'}
      </legend>
      {draft.options.map((option, index) => (
        <div key={option.id} className="flex items-center gap-2">
          <input
            type={single ? 'radio' : 'checkbox'}
            name={name}
            aria-label={`گزینهٔ ${index + 1} درست است`}
            checked={draft.correct.includes(option.id)}
            onChange={() => toggle(option.id)}
          />
          <input
            aria-label={`متن گزینهٔ ${index + 1}`}
            className={INPUT_CLASS}
            value={option.text}
            onChange={(event) =>
              setDraft((d) => ({
                ...d,
                options: d.options.map((o) =>
                  o.id === option.id ? { ...o, text: event.target.value } : o,
                ),
              }))
            }
          />
          {draft.options.length > 2 && (
            <Button
              type="button"
              size="sm"
              variant="ghost"
              aria-label={`حذف گزینهٔ ${index + 1}`}
              onClick={() =>
                setDraft((d) => ({
                  ...d,
                  options: d.options.filter((o) => o.id !== option.id),
                  correct: d.correct.filter((c) => c !== option.id),
                }))
              }
            >
              حذف
            </Button>
          )}
        </div>
      ))}
      {unused && (
        <div>
          <Button
            type="button"
            size="sm"
            variant="secondary"
            onClick={() =>
              setDraft((d) => ({ ...d, options: [...d.options, { id: unused, text: '' }] }))
            }
          >
            گزینهٔ تازه
          </Button>
        </div>
      )}
    </fieldset>
  );
}

function MatchingEditor({
  draft,
  setDraft,
}: {
  draft: Draft;
  setDraft: (update: (d: Draft) => Draft) => void;
}) {
  const edit = (side: 'left' | 'right', id: string, text: string) =>
    setDraft((d) => ({ ...d, [side]: d[side].map((o) => (o.id === id ? { ...o, text } : o)) }));
  const add = (side: 'left' | 'right') =>
    setDraft((d) => {
      const prefix = side === 'left' ? 'l' : 'r';
      const letter = LETTERS.split('').find((l) => !d[side].some((o) => o.id === `${prefix}${l}`));
      return letter ? { ...d, [side]: [...d[side], { id: `${prefix}${letter}`, text: '' }] } : d;
    });

  return (
    <div className="grid gap-4 md:grid-cols-2">
      <fieldset className="flex flex-col gap-2">
        <legend className="mb-1 text-[13.5px] font-medium">ستون راست — و جفت درست هرکدام</legend>
        {draft.left.map((item, index) => (
          <div
            key={item.id}
            className="flex flex-col gap-1.5 rounded-[var(--radius-md)] border border-[var(--border-subtle)] p-2"
          >
            <input
              aria-label={`مورد ${index + 1} ستون راست`}
              className={INPUT_CLASS}
              value={item.text}
              onChange={(event) => edit('left', item.id, event.target.value)}
            />
            <select
              aria-label={`جفت درست مورد ${index + 1}`}
              className={SELECT_CLASS}
              value={draft.pairs[item.id] ?? ''}
              onChange={(event) =>
                setDraft((d) => ({ ...d, pairs: { ...d.pairs, [item.id]: event.target.value } }))
              }
            >
              <option value="">جفت درست…</option>
              {draft.right
                .filter((r) => r.text.trim())
                .map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.text}
                  </option>
                ))}
            </select>
          </div>
        ))}
        <div>
          <Button type="button" size="sm" variant="secondary" onClick={() => add('left')}>
            مورد تازه
          </Button>
        </div>
      </fieldset>
      <fieldset className="flex flex-col gap-2">
        <legend className="mb-1 text-[13.5px] font-medium">ستون چپ (گزینه‌ها)</legend>
        {draft.right.map((item, index) => (
          <input
            key={item.id}
            aria-label={`گزینهٔ ${index + 1} ستون چپ`}
            className={INPUT_CLASS}
            value={item.text}
            onChange={(event) => edit('right', item.id, event.target.value)}
          />
        ))}
        <div>
          <Button type="button" size="sm" variant="secondary" onClick={() => add('right')}>
            گزینهٔ تازه
          </Button>
        </div>
      </fieldset>
    </div>
  );
}
