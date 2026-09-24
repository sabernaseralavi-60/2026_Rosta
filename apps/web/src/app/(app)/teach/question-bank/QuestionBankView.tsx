'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';

import { errorText, ErrorLine, Field, SELECT_CLASS } from '@/components/admin/common';
import { SectionHeader } from '@/components/teach/common';
import { QuestionEditor } from '@/components/teach/QuestionEditor';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { Input } from '@/components/ui/Input';
import { SkeletonRow } from '@/components/ui/Skeleton';
import type { QuestionKind } from '@/lib/api/quizzes';
import {
  KIND_LABELS,
  addBankItem,
  type BankItem,
  fetchBank,
  fetchTeachOfferings,
  type TeachOffering,
} from '@/lib/api/teach';
import { useSession } from '@/lib/auth/use-session';
import { toPersianDigits } from '@/lib/format/digits';

/**
 * `/teach/question-bank` — بانک سؤال شخصی (M4-03).
 *
 * بانک مال استاد است، نه ارائه: سؤال خوب نیم‌سال قبل برای نیم‌سال بعد
 * می‌ماند. در آزمون کپی می‌شود، نه ارجاع — ویرایش بانک آزمون گذشته را
 * عوض نمی‌کند.
 */
export function QuestionBankView() {
  const { accessToken } = useSession();
  const [offerings, setOfferings] = useState<TeachOffering[]>([]);
  const [items, setItems] = useState<BankItem[] | null>(null);
  const [courseId, setCourseId] = useState('');
  const [kind, setKind] = useState<QuestionKind | ''>('');
  const [difficulty, setDifficulty] = useState('');
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const courses = useMemo(() => {
    const seen = new Map<string, string>();
    for (const offering of offerings) seen.set(offering.course_id, offering.course_title_fa);
    return [...seen.entries()];
  }, [offerings]);

  const load = useCallback(() => {
    if (!accessToken) return;
    setItems(null);
    fetchBank(
      {
        course_id: courseId || undefined,
        kind: kind || undefined,
        difficulty: difficulty ? Number(difficulty) : undefined,
      },
      accessToken,
    )
      .then(setItems)
      .catch((cause) => setError(errorText(cause)));
  }, [accessToken, courseId, kind, difficulty]);

  useEffect(load, [load]);
  useEffect(() => {
    if (!accessToken) return;
    fetchTeachOfferings(accessToken)
      .then(setOfferings)
      .catch(() => setOfferings([]));
  }, [accessToken]);

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div className="flex flex-col gap-1">
          <h1>بانک سؤال</h1>
          <p className="text-[14px] text-[var(--fg-secondary)]">
            سؤال‌هایی که بارها به کار می‌آیند. در آزمون کپی می‌شوند؛ ویرایش اینجا آزمون‌های گذشته را
            عوض نمی‌کند.
          </p>
        </div>
        {!adding && <Button onClick={() => setAdding(true)}>سؤال تازه در بانک</Button>}
      </header>

      {adding && accessToken && (
        <NewBankItem
          token={accessToken}
          courses={courses}
          onCancel={() => setAdding(false)}
          onAdded={() => {
            setAdding(false);
            load();
          }}
        />
      )}

      <div className="grid gap-3 sm:grid-cols-3">
        <Field label="درس">
          <select
            className={SELECT_CLASS}
            value={courseId}
            onChange={(e) => setCourseId(e.target.value)}
          >
            <option value="">همهٔ دروس</option>
            {courses.map(([id, title]) => (
              <option key={id} value={id}>
                {title}
              </option>
            ))}
          </select>
        </Field>
        <Field label="نوع">
          <select
            className={SELECT_CLASS}
            value={kind}
            onChange={(e) => setKind(e.target.value as QuestionKind | '')}
          >
            <option value="">همه</option>
            {(Object.keys(KIND_LABELS) as QuestionKind[]).map((key) => (
              <option key={key} value={key}>
                {KIND_LABELS[key]}
              </option>
            ))}
          </select>
        </Field>
        <Field label="دشواری">
          <select
            className={SELECT_CLASS}
            value={difficulty}
            onChange={(e) => setDifficulty(e.target.value)}
          >
            <option value="">همه</option>
            {[1, 2, 3, 4, 5].map((n) => (
              <option key={n} value={n}>
                {toPersianDigits(n)}
              </option>
            ))}
          </select>
        </Field>
      </div>

      {error && <ErrorLine>{error}</ErrorLine>}
      {!items && !error && <SkeletonRow label="در حال بارگذاری بانک سؤال" />}
      {items && items.length === 0 && (
        <EmptyState
          title="بانک خالی است"
          description="سؤال را همین‌جا بنویس، یا در ویرایشگر آزمون کنار هر سؤال «به بانک» را بزن."
        />
      )}
      {items && items.length > 0 && (
        <section className="flex flex-col gap-3">
          <SectionHeader title={`${toPersianDigits(items.length)} سؤال`} />
          <ul className="flex flex-col divide-y divide-[var(--border-subtle)] rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-surface)]">
            {items.map((item) => (
              <li key={item.id} className="flex flex-col gap-1.5 px-4 py-3">
                <span className="flex flex-wrap items-center gap-2 text-[13px]">
                  <Badge tone="brand">{item.kind_fa}</Badge>
                  {item.category && <Badge tone="neutral">{item.category}</Badge>}
                  {item.difficulty && (
                    <span className="text-[var(--fg-secondary)]">
                      دشواری {toPersianDigits(item.difficulty)} از ۵
                    </span>
                  )}
                  <span className="text-[var(--fg-tertiary)]">
                    {toPersianDigits(item.usage_count)} بار در آزمون
                  </span>
                </span>
                <p className="whitespace-pre-line text-[14px]">{item.body}</p>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

function NewBankItem({
  token,
  courses,
  onCancel,
  onAdded,
}: {
  token: string;
  courses: [string, string][];
  onCancel: () => void;
  onAdded: () => void;
}) {
  const [courseId, setCourseId] = useState(courses[0]?.[0] ?? '');
  const [category, setCategory] = useState('');
  const [difficulty, setDifficulty] = useState('3');

  return (
    <Card className="flex flex-col gap-4">
      <h2 className="text-[16px]">سؤال تازه در بانک</h2>
      <div className="grid gap-3 sm:grid-cols-3">
        <Field label="درس">
          <select
            className={SELECT_CLASS}
            value={courseId}
            onChange={(e) => setCourseId(e.target.value)}
          >
            <option value="">بی‌درس</option>
            {courses.map(([id, title]) => (
              <option key={id} value={id}>
                {title}
              </option>
            ))}
          </select>
        </Field>
        <Input
          label="دسته (اختیاری)"
          placeholder="مثلاً تخمین تقاضا"
          maxLength={200}
          value={category}
          onChange={(event) => setCategory(event.target.value)}
        />
        <Field label="دشواری">
          <select
            className={SELECT_CLASS}
            value={difficulty}
            onChange={(e) => setDifficulty(e.target.value)}
          >
            {[1, 2, 3, 4, 5].map((n) => (
              <option key={n} value={n}>
                {toPersianDigits(n)}
              </option>
            ))}
          </select>
        </Field>
      </div>
      <QuestionEditor
        withPoints={false}
        submitLabel="افزودن به بانک"
        onCancel={onCancel}
        onSubmit={async (input) => {
          await addBankItem(
            {
              kind: input.kind,
              body: input.body,
              payload: input.payload,
              explanation: input.explanation,
              course_id: courseId || null,
              category: category.trim() || null,
              difficulty: Number(difficulty),
            },
            token,
          );
          onAdded();
        }}
      />
    </Card>
  );
}
