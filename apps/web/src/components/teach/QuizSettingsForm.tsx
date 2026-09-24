'use client';

import { type FormEvent, useState } from 'react';

import { errorText, ErrorLine, Field, SELECT_CLASS } from '@/components/admin/common';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Textarea } from '@/components/ui/Textarea';
import type { WeekSummary } from '@/lib/api/courses';
import {
  type QuizInput,
  RESULT_VISIBILITY_LABELS,
  type ResultVisibility,
  type TeachQuiz,
} from '@/lib/api/teach';
import { toLatinDigits, toPersianDigits } from '@/lib/format/digits';

import { DateTimeField, fromLocalInput, toLocalInput } from './common';

/**
 * تنظیمات آزمون — همان فرم برای ساخت و ویرایش (FR-QUIZ-01).
 *
 * مدت آزمون پس از اولین تلاش قفل است (سرور می‌گوید چرا)؛ این فرم فقط
 * پیشاپیش همان را غیرفعال نشان می‌دهد.
 */
export function QuizSettingsForm({
  quiz,
  weeks,
  submitLabel,
  onSubmit,
}: {
  quiz?: TeachQuiz;
  weeks: WeekSummary[];
  submitLabel: string;
  onSubmit: (input: QuizInput) => Promise<void>;
}) {
  const now = new Date();
  const defaultOpen = new Date(now.getTime() + 24 * 3600 * 1000);
  defaultOpen.setMinutes(0, 0, 0);
  const defaultClose = new Date(defaultOpen.getTime() + 7 * 24 * 3600 * 1000);

  const [title, setTitle] = useState(quiz?.title_fa ?? '');
  const [description, setDescription] = useState(quiz?.description ?? '');
  const [weekId, setWeekId] = useState(quiz?.week_id ?? '');
  const [opensAt, setOpensAt] = useState(toLocalInput(quiz?.opens_at ?? defaultOpen.toISOString()));
  const [closesAt, setClosesAt] = useState(
    toLocalInput(quiz?.closes_at ?? defaultClose.toISOString()),
  );
  const [duration, setDuration] = useState(String(quiz?.duration_min ?? 30));
  const [attempts, setAttempts] = useState(String(quiz?.max_attempts ?? 1));
  const [passing, setPassing] = useState(quiz?.passing_score ?? '');
  const [visibility, setVisibility] = useState<ResultVisibility>(
    quiz?.result_visibility ?? 'AFTER_CLOSE',
  );
  const [showAnswers, setShowAnswers] = useState(quiz?.show_correct_answers ?? true);
  const [shuffleQuestions, setShuffleQuestions] = useState(quiz?.shuffle_questions ?? true);
  const [shuffleOptions, setShuffleOptions] = useState(quiz?.shuffle_options ?? true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const durationLocked = Boolean(quiz && quiz.attempt_count > 0);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await onSubmit({
        title_fa: title.trim(),
        description: description.trim() || null,
        week_id: weekId || null,
        opens_at: fromLocalInput(opensAt),
        closes_at: fromLocalInput(closesAt),
        duration_min: Number(toLatinDigits(duration)),
        max_attempts: Number(toLatinDigits(attempts)),
        passing_score: passing ? toLatinDigits(String(passing)) : null,
        result_visibility: visibility,
        show_correct_answers: showAnswers,
        shuffle_questions: shuffleQuestions,
        shuffle_options: shuffleOptions,
      });
    } catch (cause) {
      setError(errorText(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="grid gap-4 md:grid-cols-2">
      <div className="md:col-span-2">
        <Input
          label="عنوان آزمون"
          value={title}
          required
          maxLength={200}
          placeholder="مثلاً آزمون هفتهٔ ۴"
          onChange={(event) => setTitle(event.target.value)}
        />
      </div>
      <div className="md:col-span-2">
        <Textarea
          label="توضیح برای دانشجو (اختیاری)"
          rows={2}
          maxLength={4000}
          value={description}
          onChange={(event) => setDescription(event.target.value)}
        />
      </div>
      <Field label="هفته">
        <select className={SELECT_CLASS} value={weekId} onChange={(e) => setWeekId(e.target.value)}>
          <option value="">بدون هفته</option>
          {weeks.map((week) => (
            <option key={week.id} value={week.id}>
              هفتهٔ {toPersianDigits(week.week_number)} — {week.title_fa}
            </option>
          ))}
        </select>
      </Field>
      <Input
        label="مدت (دقیقه)"
        inputMode="numeric"
        required
        disabled={durationLocked}
        hint={durationLocked ? 'پس از اولین تلاش مدت عوض نمی‌شود.' : '۱ تا ۳۰۰ دقیقه'}
        value={duration}
        onChange={(event) => setDuration(event.target.value.replace(/[^\d۰-۹]/g, ''))}
      />
      <DateTimeField label="باز شدن" value={opensAt} onChange={setOpensAt} required />
      <DateTimeField label="بسته شدن" value={closesAt} onChange={setClosesAt} required />
      <Input
        label="تعداد تلاش مجاز"
        inputMode="numeric"
        required
        hint="۱ تا ۱۰ — بهترین تلاش شمرده می‌شود."
        value={attempts}
        onChange={(event) => setAttempts(event.target.value.replace(/[^\d۰-۹]/g, ''))}
      />
      <Input
        label="نمرهٔ قبولی (اختیاری)"
        inputMode="decimal"
        value={String(passing)}
        onChange={(event) => setPassing(event.target.value)}
      />
      <Field label="نمایش نتیجه به دانشجو">
        <select
          className={SELECT_CLASS}
          value={visibility}
          onChange={(event) => setVisibility(event.target.value as ResultVisibility)}
        >
          {(Object.keys(RESULT_VISIBILITY_LABELS) as ResultVisibility[]).map((key) => (
            <option key={key} value={key}>
              {RESULT_VISIBILITY_LABELS[key]}
            </option>
          ))}
        </select>
      </Field>
      <fieldset className="flex flex-col gap-2 text-[13.5px]">
        <legend className="mb-1 font-medium">گزینه‌ها</legend>
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={shuffleQuestions}
            onChange={(event) => setShuffleQuestions(event.target.checked)}
          />
          ترتیب سؤال‌ها برای هر دانشجو درهم
        </label>
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={shuffleOptions}
            onChange={(event) => setShuffleOptions(event.target.checked)}
          />
          ترتیب گزینه‌ها درهم
        </label>
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={showAnswers}
            onChange={(event) => setShowAnswers(event.target.checked)}
          />
          پاسخ درست همراه نتیجه دیده شود
        </label>
      </fieldset>
      {error && (
        <div className="md:col-span-2">
          <ErrorLine>{error}</ErrorLine>
        </div>
      )}
      <div className="md:col-span-2">
        <Button type="submit" loading={busy} disabled={!title.trim() || !opensAt || !closesAt}>
          {submitLabel}
        </Button>
      </div>
    </form>
  );
}
