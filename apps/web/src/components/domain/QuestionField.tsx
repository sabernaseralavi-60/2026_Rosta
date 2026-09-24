'use client';

import { useId } from 'react';

import { Textarea } from '@/components/ui/Textarea';
import type { AnswerResponse, VisibleQuestion } from '@/lib/api/quizzes';
import { cn } from '@/lib/cn';
import { toPersianDigits } from '@/lib/format/digits';

/**
 * ورودی پاسخ، به‌ازای هر نوع سؤال — §3.4، FR-QUIZ-01.
 *
 * `payload` از سرور می‌آید و **کلید پاسخ ندارد** (§5.6). این کامپوننت
 * هیچ‌جا دنبال `correct` نمی‌گردد؛ اگر روزی سرور اشتباهاً بفرستدش،
 * اینجا هم استفاده نمی‌شود.
 *
 * ترتیب گزینه‌ها همان است که سرور داده — درهم‌سازی سمت سرور انجام شده
 * و قطعی است (ADR-0011). مرتب‌سازی دوباره در کلاینت، پاسخ ذخیره‌شده را
 * از گزینه‌اش جدا می‌کرد.
 */

interface Option {
  id: string;
  text: string;
}

function options(payload: Record<string, unknown>, key = 'options'): Option[] {
  const raw = payload[key];
  if (!Array.isArray(raw)) return [];
  return raw.filter(
    (item): item is Option =>
      typeof item === 'object' && item !== null && 'id' in item && 'text' in item,
  );
}

export interface QuestionFieldProps {
  question: VisibleQuestion;
  value: AnswerResponse | null;
  onChange: (value: AnswerResponse | null) => void;
  disabled?: boolean;
}

export function QuestionField({ question, value, onChange, disabled }: QuestionFieldProps) {
  switch (question.kind) {
    case 'SINGLE_CHOICE':
      return (
        <ChoiceGroup
          question={question}
          value={value}
          onChange={onChange}
          disabled={disabled}
          multiple={false}
        />
      );
    case 'MULTI_CHOICE':
      return (
        <ChoiceGroup
          question={question}
          value={value}
          onChange={onChange}
          disabled={disabled}
          multiple
        />
      );
    case 'TRUE_FALSE':
      return <TrueFalse value={value} onChange={onChange} disabled={disabled} />;
    case 'SHORT_ANSWER':
      return <ShortAnswer value={value} onChange={onChange} disabled={disabled} />;
    case 'NUMERIC':
      return (
        <Numeric
          value={value}
          onChange={onChange}
          disabled={disabled}
          unit={typeof question.payload.unit === 'string' ? question.payload.unit : null}
        />
      );
    case 'ESSAY':
      return <Essay question={question} value={value} onChange={onChange} disabled={disabled} />;
    case 'MATCHING':
      return <Matching question={question} value={value} onChange={onChange} disabled={disabled} />;
    default:
      return null;
  }
}

// ── چندگزینه‌ای ───────────────────────────────────────────────────────
function ChoiceGroup({
  question,
  value,
  onChange,
  disabled,
  multiple,
}: QuestionFieldProps & { multiple: boolean }) {
  const name = useId();
  const items = options(question.payload);
  const selected = value && 'selected' in value ? value.selected : [];

  function toggle(optionId: string) {
    if (!multiple) {
      onChange({ selected: [optionId] });
      return;
    }
    const next = selected.includes(optionId)
      ? selected.filter((id) => id !== optionId)
      : [...selected, optionId];
    onChange(next.length ? { selected: next } : null);
  }

  return (
    <fieldset className="space-y-2" disabled={disabled}>
      <legend className="sr-only">
        {multiple ? 'همهٔ گزینه‌های درست را انتخاب کنید' : 'یک گزینه را انتخاب کنید'}
      </legend>
      {multiple ? (
        <p className="text-[13px] text-[var(--fg-secondary)]">
          می‌توانید بیش از یک گزینه انتخاب کنید.
        </p>
      ) : null}
      {items.map((option) => {
        const isSelected = selected.includes(option.id);
        return (
          <label
            key={option.id}
            className={cn(
              'flex cursor-pointer items-start gap-3 rounded-[var(--radius-md)] border p-3',
              'transition-colors',
              isSelected
                ? 'border-[var(--brand-600)] bg-[var(--brand-50)]'
                : 'border-[var(--border-default)] hover:bg-[var(--bg-sunken)]',
              disabled && 'cursor-not-allowed opacity-60',
            )}
          >
            <input
              type={multiple ? 'checkbox' : 'radio'}
              name={name}
              value={option.id}
              checked={isSelected}
              onChange={() => toggle(option.id)}
              disabled={disabled}
              className="mt-1 size-4 accent-[var(--brand-600)]"
            />
            <span className="text-[15px] leading-7 text-[var(--fg-primary)]">{option.text}</span>
          </label>
        );
      })}
    </fieldset>
  );
}

// ── درست/نادرست ──────────────────────────────────────────────────────
function TrueFalse({
  value,
  onChange,
  disabled,
}: Pick<QuestionFieldProps, 'value' | 'onChange' | 'disabled'>) {
  const name = useId();
  const current = value && 'value' in value ? value.value : null;

  return (
    <fieldset className="flex gap-3" disabled={disabled}>
      <legend className="sr-only">درست یا نادرست</legend>
      {[
        { label: 'درست', flag: true },
        { label: 'نادرست', flag: false },
      ].map((option) => (
        <label
          key={option.label}
          className={cn(
            'flex flex-1 cursor-pointer items-center justify-center gap-2 rounded-[var(--radius-md)]',
            'border p-3 text-[15px] transition-colors',
            current === option.flag
              ? 'border-[var(--brand-600)] bg-[var(--brand-50)] text-[var(--fg-brand)]'
              : 'border-[var(--border-default)] hover:bg-[var(--bg-sunken)]',
            disabled && 'cursor-not-allowed opacity-60',
          )}
        >
          <input
            type="radio"
            name={name}
            checked={current === option.flag}
            onChange={() => onChange({ value: option.flag })}
            disabled={disabled}
            className="size-4 accent-[var(--brand-600)]"
          />
          {option.label}
        </label>
      ))}
    </fieldset>
  );
}

// ── پاسخ کوتاه ───────────────────────────────────────────────────────
function ShortAnswer({
  value,
  onChange,
  disabled,
}: Pick<QuestionFieldProps, 'value' | 'onChange' | 'disabled'>) {
  const text = value && 'text' in value ? value.text : '';
  return (
    <input
      type="text"
      value={text}
      onChange={(event) => onChange(event.target.value ? { text: event.target.value } : null)}
      disabled={disabled}
      placeholder="پاسخ کوتاه"
      className={cn(
        'h-11 w-full rounded-[var(--radius-md)] border border-[var(--border-default)]',
        'bg-[var(--bg-surface)] px-3 text-[15px] text-[var(--fg-primary)]',
        'focus:border-[var(--brand-600)] focus:outline-none',
        disabled && 'opacity-60',
      )}
    />
  );
}

// ── عددی ─────────────────────────────────────────────────────────────
function Numeric({
  value,
  onChange,
  disabled,
  unit,
}: Pick<QuestionFieldProps, 'value' | 'onChange' | 'disabled'> & { unit: string | null }) {
  const current = value && 'value' in value ? String(value.value) : '';
  return (
    <div className="flex items-center gap-2">
      <input
        type="text"
        inputMode="decimal"
        value={current}
        onChange={(event) => onChange(event.target.value ? { value: event.target.value } : null)}
        disabled={disabled}
        placeholder="عدد"
        dir="ltr"
        className={cn(
          'h-11 w-40 rounded-[var(--radius-md)] border border-[var(--border-default)]',
          'bg-[var(--bg-surface)] px-3 text-center text-[15px] text-[var(--fg-primary)]',
          'focus:border-[var(--brand-600)] focus:outline-none',
          disabled && 'opacity-60',
        )}
      />
      {unit ? <span className="text-[14px] text-[var(--fg-secondary)]">{unit}</span> : null}
    </div>
  );
}

// ── تشریحی ───────────────────────────────────────────────────────────
function Essay({ question, value, onChange, disabled }: QuestionFieldProps) {
  const text = value && 'text' in value ? value.text : '';
  const min = typeof question.payload.min_words === 'number' ? question.payload.min_words : null;
  const max = typeof question.payload.max_words === 'number' ? question.payload.max_words : null;
  const words = text.trim() ? text.trim().split(/\s+/).length : 0;

  return (
    <div className="space-y-2">
      {typeof question.payload.rubric === 'string' && question.payload.rubric ? (
        <p className="rounded-[var(--radius-sm)] bg-[var(--bg-sunken)] p-3 text-[13.5px] text-[var(--fg-secondary)]">
          معیار نمره‌دهی: {question.payload.rubric}
        </p>
      ) : null}
      <Textarea
        label="پاسخ تشریحی"
        value={text}
        onChange={(event) => onChange(event.target.value ? { text: event.target.value } : null)}
        disabled={disabled}
        rows={8}
        placeholder="پاسخ خود را بنویسید…"
      />
      <p className="text-[13px] text-[var(--fg-secondary)]">
        {toPersianDigits(words)} واژه
        {min ? ` · دست‌کم ${toPersianDigits(min)}` : ''}
        {max ? ` · حداکثر ${toPersianDigits(max)}` : ''}
      </p>
    </div>
  );
}

// ── جورکردنی ─────────────────────────────────────────────────────────
function Matching({ question, value, onChange, disabled }: QuestionFieldProps) {
  const left = options(question.payload, 'left');
  const right = options(question.payload, 'right');
  const pairs = value && 'pairs' in value ? value.pairs : [];
  const byLeft = new Map(pairs.map(([l, r]) => [l, r]));

  function pick(leftId: string, rightId: string) {
    const next = new Map(byLeft);
    if (rightId) next.set(leftId, rightId);
    else next.delete(leftId);
    const list = [...next.entries()] as [string, string][];
    onChange(list.length ? { pairs: list } : null);
  }

  return (
    <div className="space-y-2">
      <p className="text-[13px] text-[var(--fg-secondary)]">
        برای هر مورد، گزینهٔ متناظرش را انتخاب کنید.
      </p>
      {left.map((item) => (
        <div
          key={item.id}
          className="flex flex-wrap items-center gap-3 rounded-[var(--radius-md)] border border-[var(--border-default)] p-3"
        >
          <span className="flex-1 text-[15px] text-[var(--fg-primary)]">{item.text}</span>
          <select
            value={byLeft.get(item.id) ?? ''}
            onChange={(event) => pick(item.id, event.target.value)}
            disabled={disabled}
            aria-label={`پاسخ متناظر با «${item.text}»`}
            className={cn(
              'h-10 min-w-44 rounded-[var(--radius-sm)] border border-[var(--border-default)]',
              'bg-[var(--bg-surface)] px-2 text-[14px] text-[var(--fg-primary)]',
              disabled && 'opacity-60',
            )}
          >
            <option value="">— انتخاب کنید —</option>
            {right.map((option) => (
              <option key={option.id} value={option.id}>
                {option.text}
              </option>
            ))}
          </select>
        </div>
      ))}
    </div>
  );
}
