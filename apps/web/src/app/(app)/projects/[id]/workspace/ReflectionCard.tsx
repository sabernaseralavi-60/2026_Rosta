'use client';

import { type FormEvent, useCallback, useEffect, useState } from 'react';

import { Button } from '@/components/ui/Button';
import { Card, CardDescription, CardTitle } from '@/components/ui/Card';
import { SkeletonText } from '@/components/ui/Skeleton';
import { Textarea } from '@/components/ui/Textarea';
import { ApiError, NetworkError } from '@/lib/api/client';
import { type ReflectionState, fetchReflection, submitReflection } from '@/lib/api/workspace';
import { cn } from '@/lib/cn';
import { toPersianDigits } from '@/lib/format/digits';

/**
 * بازتاب پایان پروژه — FR-PRJ-08، ADR-0024.
 *
 * فقط برای پروژهٔ بسته‌شده و عضو فعال تیم. یک‌بار نوشته می‌شود و ویرایش
 * ندارد؛ خصوصی است (مدیر و استاد نمی‌خوانند). پس از ثبت، همان متن فقط‌خواندنی
 * نشان داده می‌شود تا کاربر بداند ثبت شده است. Toast امتیاز را پوستهٔ
 * اپلیکیشن پس از هر نوشتن خودش نشان می‌دهد (`PointsProvider`).
 *
 * سرور تنها مرجع «می‌شود یا نمی‌شود» است (`can_submit`)؛ آستانهٔ نویسه هم از
 * سرور می‌آید تا عدد در دو جا نماند.
 */

const MAX_FIELD = 4000;
const SATISFACTION_LABELS = ['اصلاً', 'کم', 'متوسط', 'خوب', 'عالی'];

export function ReflectionCard({
  projectId,
  accessToken,
}: {
  projectId: string;
  accessToken: string;
}) {
  const [state, setState] = useState<ReflectionState | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setState(await fetchReflection(projectId, accessToken));
      setLoadError(null);
    } catch (cause) {
      setLoadError(messageFor(cause));
    }
  }, [projectId, accessToken]);

  useEffect(() => {
    void load();
  }, [load]);

  if (loadError) {
    return (
      <Card>
        <p role="alert" className="text-[13.5px] text-[var(--fg-danger)]">
          {loadError}
        </p>
      </Card>
    );
  }
  if (!state) {
    return (
      <Card>
        <SkeletonText label="در حال بارگذاری بازتاب" />
      </Card>
    );
  }

  if (state.reflection) {
    const { reflection } = state;
    return (
      <Card className="flex flex-col gap-3" aria-labelledby="reflection-title">
        <CardTitle as="h2" id="reflection-title">
          بازتاب تو ثبت شد
        </CardTitle>
        <CardDescription>فقط خودت آن را می‌بینی و ویرایش‌پذیر نیست.</CardDescription>
        <dl className="flex flex-col gap-3 text-[14.5px] leading-[1.9]">
          <Answer term="چه آموختم" value={reflection.learned} />
          <Answer term="چه چیزش سخت بود" value={reflection.challenges} />
          <Answer term="اگر دوباره بود چه می‌کردم" value={reflection.would_do_differently} />
          {reflection.satisfaction !== null && (
            <Answer
              term="رضایت"
              value={`${toPersianDigits(reflection.satisfaction)} از ${toPersianDigits(5)} — ${
                SATISFACTION_LABELS[reflection.satisfaction - 1]
              }`}
            />
          )}
        </dl>
      </Card>
    );
  }

  if (!state.can_submit) return null;

  return (
    <ReflectionForm
      projectId={projectId}
      accessToken={accessToken}
      minChars={state.min_learned_chars}
      points={state.points}
      onSaved={load}
    />
  );
}

function Answer({ term, value }: { term: string; value: string | null }) {
  if (!value) return null;
  return (
    <div className="flex flex-col gap-0.5">
      <dt className="text-[12.5px] text-[var(--fg-tertiary)]">{term}</dt>
      <dd className="whitespace-pre-wrap text-[var(--fg-primary)]">{value}</dd>
    </div>
  );
}

function ReflectionForm({
  projectId,
  accessToken,
  minChars,
  points,
  onSaved,
}: {
  projectId: string;
  accessToken: string;
  minChars: number;
  points: number | null;
  onSaved: () => void;
}) {
  const [learned, setLearned] = useState('');
  const [challenges, setChallenges] = useState('');
  const [different, setDifferent] = useState('');
  const [satisfaction, setSatisfaction] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const enough = learned.trim().length >= minChars;

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!enough) return;
    setBusy(true);
    setError(null);
    try {
      await submitReflection(
        projectId,
        {
          learned: learned.trim(),
          challenges: challenges.trim() || null,
          would_do_differently: different.trim() || null,
          satisfaction,
        },
        accessToken,
      );
      onSaved();
    } catch (cause) {
      setError(messageFor(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="flex flex-col gap-4" aria-labelledby="reflection-title">
      <div className="flex flex-col gap-1">
        <CardTitle as="h2" id="reflection-title">
          بازتاب پروژه را بنویس
        </CardTitle>
        <CardDescription>
          پروژه بسته شد. چند جمله از آنچه آموختی بنویس؛ فقط خودت می‌بینی و بعد از ثبت ویرایش
          نمی‌شود.
          {points !== null && ` ثبتش ${toPersianDigits(points)} امتیاز یادگیری دارد.`}
        </CardDescription>
      </div>

      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        <Textarea
          label="چه آموختم"
          hint={`دست‌کم ${toPersianDigits(minChars)} نویسه — یک جملهٔ کامل.`}
          value={learned}
          onChange={(event) => setLearned(event.target.value)}
          maxLength={MAX_FIELD}
          rows={4}
          required
        />
        <Textarea
          label="چه چیزش سخت بود (اختیاری)"
          value={challenges}
          onChange={(event) => setChallenges(event.target.value)}
          maxLength={MAX_FIELD}
          rows={3}
        />
        <Textarea
          label="اگر دوباره بود چه می‌کردم (اختیاری)"
          value={different}
          onChange={(event) => setDifferent(event.target.value)}
          maxLength={MAX_FIELD}
          rows={3}
        />

        <fieldset className="flex flex-col gap-2">
          <legend className="text-[13.5px] font-medium text-[var(--fg-primary)]">
            از این پروژه چقدر راضی بودی؟ (اختیاری)
          </legend>
          <div className="flex flex-wrap gap-2">
            {SATISFACTION_LABELS.map((label, index) => {
              const value = index + 1;
              const selected = satisfaction === value;
              return (
                <button
                  key={value}
                  type="button"
                  aria-pressed={selected}
                  aria-label={`${toPersianDigits(value)} از ${toPersianDigits(5)}: ${label}`}
                  onClick={() => setSatisfaction(selected ? null : value)}
                  className={cn(
                    'h-9 rounded-[var(--radius-full)] border px-4 text-[13.5px] font-medium',
                    'transition-colors duration-[var(--dur-instant)]',
                    selected
                      ? 'border-[var(--brand-600)] bg-[var(--brand-600)] text-[var(--fg-on-brand)]'
                      : 'border-[var(--border-default)] bg-[var(--bg-surface)] text-[var(--fg-secondary)] hover:border-[var(--border-strong)]',
                  )}
                >
                  {label}
                </button>
              );
            })}
          </div>
        </fieldset>

        {error && (
          <p role="alert" className="text-[13px] text-[var(--fg-danger)]">
            {error}
          </p>
        )}
        <div className="flex items-center gap-3">
          <Button type="submit" loading={busy} disabled={!enough}>
            ثبت بازتاب
          </Button>
          {!enough && learned.trim().length > 0 && (
            <span className="text-[12.5px] text-[var(--fg-tertiary)]">
              {toPersianDigits(minChars - learned.trim().length)} نویسهٔ دیگر
            </span>
          )}
        </div>
      </form>
    </Card>
  );
}

function messageFor(cause: unknown): string {
  if (cause instanceof ApiError || cause instanceof NetworkError) return cause.message;
  return 'بازتاب بارگذاری نشد. کمی بعد دوباره تلاش کن.';
}
