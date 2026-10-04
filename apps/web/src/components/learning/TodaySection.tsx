'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';

import { ErrorLine, errorText } from '@/components/admin/common';
import { Badge, type BadgeTone } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { SkeletonCard } from '@/components/ui/Skeleton';
import { ApiError } from '@/lib/api/client';
import {
  type CheckpointCard,
  fetchToday,
  MASTERY_LABELS,
  type Mastery,
  type Today,
  type TodayOffering,
} from '@/lib/api/learning';
import { startAttempt } from '@/lib/api/quizzes';
import { useSession } from '@/lib/auth/use-session';
import { formatDateTime } from '@/lib/format/date';
import { toPersianDigits } from '@/lib/format/digits';

const LEVEL_TONE: Record<Mastery['level'], BadgeTone> = {
  STRONG: 'success',
  MEDIUM: 'warning',
  WEAK: 'danger',
  LOW_DATA: 'neutral',
};

/**
 * «امروز» — ورودی پیش‌فرض دانشجو (ADR-0036 §۳).
 *
 * امروز چه بخوانم ← چالش امروز ← بازخورد ← پیشنهاد بعدی. هیچ‌وقت خالی نیست: بدون
 * درس‌نامه و چالش، نقشهٔ شایستگی یا «به صفحهٔ درس برو» نشان داده می‌شود.
 */
export function TodaySection() {
  const { accessToken } = useSession();
  const [today, setToday] = useState<Today | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!accessToken) return;
    fetchToday(accessToken)
      .then(setToday)
      .catch((cause) => setError(errorText(cause)));
  }, [accessToken]);

  if (error) return <ErrorLine>{error}</ErrorLine>;
  if (!today) return <SkeletonCard label="در حال آماده‌سازی «امروز»" />;
  if (today.offerings.length === 0) return null;

  return (
    <section aria-labelledby="today-title" className="flex flex-col gap-4">
      <h2 id="today-title" className="text-[20px]">
        امروز
      </h2>
      {today.offerings.map((offering) => (
        <OfferingToday key={offering.offering_id} offering={offering} />
      ))}
      <SkillMap mastery={today.mastery} suggestion={today.suggestion} />
    </section>
  );
}

function OfferingToday({ offering }: { offering: TodayOffering }) {
  const { lesson, checkpoint, streak, last_result: last } = offering;
  return (
    <article className="flex flex-col gap-4 rounded-[var(--radius-xl)] border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-5">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-[17px]">{offering.course_title}</h3>
        <div className="flex items-center gap-2 text-[13px] text-[var(--fg-secondary)]">
          {streak.alive && streak.current > 0 ? (
            <Badge tone="brand">🔥 {toPersianDigits(streak.current)} روز پیاپی</Badge>
          ) : (
            <span>امروز را شروع کن تا رشته‌ات بسازی</span>
          )}
          <Link
            href={`/courses/${offering.offering_id}/lessons`}
            className="text-[var(--fg-brand)] underline"
          >
            همهٔ درس‌نامه‌ها
          </Link>
        </div>
      </header>

      <div className="grid gap-4 md:grid-cols-2">
        <Step number={1} title="امروز چه بخوانم؟">
          {lesson ? (
            <>
              <p className="text-[15px] font-medium">{lesson.title}</p>
              <p className="text-[13px] text-[var(--fg-secondary)]">
                حدود {toPersianDigits(lesson.est_minutes)} دقیقه مطالعه
              </p>
              <Link
                href={`/lessons/${lesson.id}`}
                className="inline-flex h-10 w-fit items-center rounded-[var(--radius-md)] border border-[var(--border-strong)] px-4 text-[14px] font-semibold hover:bg-[var(--bg-sunken)]"
              >
                خواندن درس‌نامه
              </Link>
            </>
          ) : (
            <p className="text-[14px] text-[var(--fg-secondary)]">
              هنوز درس‌نامهٔ تازه‌ای منتشر نشده است.
            </p>
          )}
        </Step>

        <Step number={2} title="چالش امروز">
          {checkpoint ? (
            <CheckpointAction checkpoint={checkpoint} />
          ) : (
            <p className="text-[14px] text-[var(--fg-secondary)]">
              امروز چالشی در کار نیست؛ درس‌نامه را بخوان یا ضعیف‌ترین مهارتت را مرور کن.
            </p>
          )}
        </Step>
      </div>

      {last && (
        <Step number={3} title="بازخورد آخرین چالش">
          <p className="text-[14px]">
            {last.quiz_title}: {toPersianDigits(last.correct)} از {toPersianDigits(last.total)} درست
          </p>
          {last.skills.length > 0 && (
            <ul className="flex flex-wrap gap-2 text-[13px]">
              {last.skills.map((skill) => (
                <li key={skill.title}>
                  <Badge tone={skill.correct === skill.total ? 'success' : 'warning'}>
                    {skill.title} · {toPersianDigits(skill.correct)}/{toPersianDigits(skill.total)}
                  </Badge>
                </li>
              ))}
            </ul>
          )}
        </Step>
      )}
    </article>
  );
}

function Step({
  number,
  title,
  children,
}: {
  number: number;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-2 rounded-[var(--radius-lg)] bg-[var(--bg-canvas)] p-4">
      <p className="flex items-center gap-2 text-[13px] font-semibold text-[var(--fg-secondary)]">
        <span
          aria-hidden="true"
          className="inline-flex size-5 items-center justify-center rounded-full bg-[var(--brand-600)] text-[11px] text-[var(--fg-on-brand)]"
        >
          {toPersianDigits(number)}
        </span>
        {title}
      </p>
      {children}
    </div>
  );
}

function CheckpointAction({ checkpoint }: { checkpoint: CheckpointCard }) {
  const router = useRouter();
  const { accessToken } = useSession();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function begin() {
    if (!accessToken) return;
    if (checkpoint.state === 'IN_PROGRESS' && checkpoint.attempt_id) {
      router.push(`/quiz/${checkpoint.attempt_id}`);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const started = await startAttempt(checkpoint.quiz_id, accessToken);
      router.push(`/quiz/${started.attempt_id}`);
    } catch (cause) {
      if (cause instanceof ApiError && cause.code === 'ACTIVE_ATTEMPT_EXISTS') {
        const id = cause.details.attempt_id;
        if (typeof id === 'string') {
          router.push(`/quiz/${id}`);
          return;
        }
      }
      setError(errorText(cause));
      setBusy(false);
    }
  }

  return (
    <>
      <p className="text-[15px] font-medium">{checkpoint.title}</p>
      <p className="text-[13px] text-[var(--fg-secondary)]">
        {toPersianDigits(checkpoint.question_count)} سؤال ·{' '}
        {toPersianDigits(checkpoint.duration_min)} دقیقه ·{' '}
        {checkpoint.state === 'UPCOMING'
          ? `از ${toPersianDigits(formatDateTime(checkpoint.opens_at))}`
          : `تا ${toPersianDigits(formatDateTime(checkpoint.closes_at))}`}
      </p>
      {error && <ErrorLine>{error}</ErrorLine>}
      {checkpoint.state === 'DONE' && (
        <Badge tone="success">انجام شد ✓ بازخوردش را پایین ببین</Badge>
      )}
      {checkpoint.state === 'UPCOMING' && <Badge tone="neutral">هنوز باز نشده</Badge>}
      {(checkpoint.state === 'AVAILABLE' || checkpoint.state === 'IN_PROGRESS') && (
        <Button size="sm" onClick={() => void begin()} loading={busy} loadingLabel="در حال شروع…">
          {checkpoint.state === 'IN_PROGRESS' ? 'ادامهٔ چالش' : 'شروع چالش'}
        </Button>
      )}
    </>
  );
}

function SkillMap({
  mastery,
  suggestion,
}: {
  mastery: Mastery[];
  suggestion: Today['suggestion'];
}) {
  if (mastery.length === 0) {
    return (
      <p className="rounded-[var(--radius-lg)] bg-[var(--bg-sunken)] px-4 py-3 text-[13.5px] text-[var(--fg-secondary)]">
        بعد از اولین چالش، نقشهٔ مهارتت همین‌جا ساخته می‌شود: کجا قوی هستی و کجا تمرین لازم داری.
      </p>
    );
  }
  return (
    <div className="flex flex-col gap-3 rounded-[var(--radius-xl)] border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-5">
      <h3 className="text-[17px]">نقشهٔ مهارت من</h3>
      {suggestion?.kind === 'REVIEW' && suggestion.title && (
        <p className="rounded-[var(--radius-md)] bg-[var(--brand-50)] px-3 py-2 text-[14px]">
          پیشنهاد بعدی: «{suggestion.title}» را مرور کن؛ نیازمند تمرین است.
        </p>
      )}
      {suggestion?.kind === 'KEEP_GOING' && (
        <p className="rounded-[var(--radius-md)] bg-[var(--brand-50)] px-3 py-2 text-[14px]">
          همه‌چیز خوب پیش می‌رود؛ با چالش‌های روزانه ادامه بده.
        </p>
      )}
      <ul className="flex flex-col gap-2">
        {mastery.map((row) => (
          <li key={row.competency_id} className="flex items-center gap-3">
            <span className="w-40 shrink-0 truncate text-[14px]">{row.title}</span>
            <div
              role="img"
              aria-label={`${row.title}: ${MASTERY_LABELS[row.level]}`}
              className="h-2 flex-1 overflow-hidden rounded-full bg-[var(--bg-sunken)]"
            >
              <div
                className="h-full rounded-full bg-[var(--brand-600)]"
                style={{ width: `${Math.round(row.score * 100)}%` }}
              />
            </div>
            <Badge tone={LEVEL_TONE[row.level]}>{MASTERY_LABELS[row.level]}</Badge>
          </li>
        ))}
      </ul>
      <p className="text-[12px] text-[var(--fg-tertiary)]">
        «کم‌داده» یعنی هنوز سؤال کافی نداده‌ای تا سطحت معلوم شود.
      </p>
    </div>
  );
}
