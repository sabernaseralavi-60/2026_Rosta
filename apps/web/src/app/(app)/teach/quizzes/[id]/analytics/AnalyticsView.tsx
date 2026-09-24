'use client';

import { useEffect, useState } from 'react';

import { errorText, ErrorLine } from '@/components/admin/common';
import { fa, SectionHeader } from '@/components/teach/common';
import { useQuiz } from '@/components/teach/QuizFrame';
import { Badge } from '@/components/ui/Badge';
import { Card } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { SkeletonRow } from '@/components/ui/Skeleton';
import { fetchQuestionStats, KIND_LABELS, type QuestionStats } from '@/lib/api/teach';
import { toPersianDigits } from '@/lib/format/digits';

/**
 * `/teach/quizzes/[id]/analytics` — تحلیل سؤال (§3.5، M4-13).
 *
 * ضریب دشواری = میانگین نسبت نمره به بارم (بالا یعنی آسان)؛ ضریب تمیز =
 * همبستگی نقطه‌ای دو رشته‌ای با نمرهٔ کل بقیهٔ آزمون. عدد تنها برای استادی
 * که آمار نخوانده کم است؛ جملهٔ سرور می‌گوید با سؤال چه کند.
 */
export function AnalyticsView() {
  const { quiz, token } = useQuiz();
  const [stats, setStats] = useState<QuestionStats[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchQuestionStats(quiz.id, token)
      .then(setStats)
      .catch((cause) => setError(errorText(cause)));
  }, [quiz.id, token]);

  if (error) return <ErrorLine>{error}</ErrorLine>;
  if (!stats) return <SkeletonRow label="در حال محاسبهٔ تحلیل سؤال" />;
  if (stats.every((s) => s.answered === 0)) {
    return (
      <EmptyState
        title="هنوز پاسخی برای تحلیل نیست"
        description="تحلیل پس از اولین تلاش‌های تصحیح‌شده ساخته می‌شود. ضریب تمیز دست‌کم به ۱۰ شرکت‌کننده نیاز دارد."
      />
    );
  }

  return (
    <section className="flex flex-col gap-4">
      <SectionHeader
        title="تحلیل سؤال‌ها"
        description="دشواری: درصد نمرهٔ گرفته‌شده از بارم (۸۵٪ به بالا یعنی خیلی آسان، ۳۰٪ به پایین یعنی خیلی سخت). تمیز: آیا دانشجوی قوی‌تر این سؤال را بهتر جواب داده؟ زیر ۰٫۱۵ یعنی نه."
      />
      <ol className="flex flex-col gap-3">
        {stats.map((row, index) => (
          <li key={row.question_id}>
            <Card className="flex flex-col gap-2">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-[13px] text-[var(--fg-tertiary)]">
                  سؤال {toPersianDigits(index + 1)}
                </span>
                <Badge tone="brand">{KIND_LABELS[row.kind]}</Badge>
                <span className="text-[13px] text-[var(--fg-secondary)]">
                  {fa(row.points)} نمره · {toPersianDigits(row.answered)} پاسخ
                </span>
              </div>
              <p className="line-clamp-2 text-[14px]">{row.body}</p>
              <div className="grid gap-3 sm:grid-cols-2">
                <Meter
                  label="دشواری"
                  value={row.difficulty === null ? null : Number(row.difficulty)}
                  display={
                    row.difficulty === null ? '—' : `${fa(Number(row.difficulty) * 100, 0)}٪`
                  }
                />
                <Meter
                  label="تمیز"
                  value={
                    row.discrimination === null ? null : Math.max(0, Number(row.discrimination))
                  }
                  display={
                    row.discrimination === null ? 'کمتر از ۱۰ شرکت‌کننده' : fa(row.discrimination)
                  }
                />
              </div>
              {row.note_fa && (
                <p className="rounded-[var(--radius-md)] bg-[var(--bg-sunken)] p-2.5 text-[13.5px] text-[var(--fg-warning)]">
                  {row.note_fa}
                </p>
              )}
            </Card>
          </li>
        ))}
      </ol>
    </section>
  );
}

function Meter({
  label,
  value,
  display,
}: {
  label: string;
  value: number | null;
  display: string;
}) {
  return (
    <div className="flex flex-col gap-1">
      <span className="flex justify-between text-[12.5px]">
        <span className="text-[var(--fg-secondary)]">{label}</span>
        <span className="font-semibold tabular-nums">{display}</span>
      </span>
      <div
        className="h-2 overflow-hidden rounded-[var(--radius-full)] bg-[var(--bg-sunken)]"
        aria-hidden="true"
      >
        <div
          className="h-full bg-[var(--brand-500)]"
          style={{ width: `${Math.min(100, Math.round((value ?? 0) * 100))}%` }}
        />
      </div>
    </div>
  );
}
