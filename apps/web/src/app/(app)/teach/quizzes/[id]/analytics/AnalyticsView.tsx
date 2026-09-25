'use client';

import { useEffect, useState } from 'react';

import { errorText, ErrorLine } from '@/components/admin/common';
import { fa, SectionHeader } from '@/components/teach/common';
import { useQuiz } from '@/components/teach/QuizFrame';
import { Badge, type BadgeTone } from '@/components/ui/Badge';
import { Card } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { SkeletonRow } from '@/components/ui/Skeleton';
import {
  fetchQuizAnalytics,
  KIND_LABELS,
  type ItemAnalysis,
  type OptionStat,
  type Reliability,
  type ScoreSummary,
  type QuizAnalytics,
} from '@/lib/api/teach';
import { toPersianDigits } from '@/lib/format/digits';

/**
 * `/teach/quizzes/[id]/analytics` — تحلیل آزمون (§3.5، M4-13، ADR-0028).
 *
 * سه لایه: کل آزمون (توزیع نمره و پایایی)، هر سؤال (دشواری، تمیز، همبستگی با
 * بقیه) و هر گزینه. عدد تنها برای استادی که آمار نخوانده کم است؛ جملهٔ سرور
 * می‌گوید با سؤال یا گزینه چه کند.
 */
export function AnalyticsView() {
  const { quiz, token } = useQuiz();
  const [data, setData] = useState<QuizAnalytics | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchQuizAnalytics(quiz.id, token)
      .then(setData)
      .catch((cause) => setError(errorText(cause)));
  }, [quiz.id, token]);

  if (error) return <ErrorLine>{error}</ErrorLine>;
  if (!data) return <SkeletonRow label="در حال محاسبهٔ تحلیل آزمون" />;
  if (data.items.every((s) => s.answered === 0)) {
    return (
      <EmptyState
        title="هنوز پاسخی برای تحلیل نیست"
        description="تحلیل پس از اولین تلاش‌های تصحیح‌شده ساخته می‌شود. ضریب تمیز، پایایی و مقایسهٔ گروه‌ها دست‌کم به ۱۰ شرکت‌کننده نیاز دارد."
      />
    );
  }

  return (
    <section className="flex flex-col gap-6">
      <div className="flex flex-col gap-3">
        <SectionHeader
          title="کل آزمون"
          description="توزیع نمرهٔ تلاش‌های تصحیح‌شده، به درصد بارم. پایایی می‌گوید نمرهٔ هر دانشجو چقدر قابل‌اتکاست."
        />
        {data.summary && <SummaryCard summary={data.summary} />}
        <ReliabilityCard reliability={data.reliability} />
      </div>

      <div className="flex flex-col gap-3">
        <SectionHeader
          title="تحلیل سؤال‌ها"
          description="دشواری: درصد نمرهٔ گرفته‌شده از بارم (۸۵٪ به بالا یعنی خیلی آسان، ۳۰٪ به پایین یعنی خیلی سخت). تمیز: آیا دانشجوی قوی‌تر این سؤال را بهتر جواب داده؟ زیر ۰٫۱۵ یعنی نه. همبستگی با بقیه: مثل تمیز، ولی با کل نمرهٔ بقیهٔ آزمون سنجیده می‌شود؛ منفی یعنی قوی‌ها این سؤال را بدتر زده‌اند."
        />
        <ol className="flex flex-col gap-3">
          {data.items.map((row, index) => (
            <li key={row.question_id}>
              <ItemCard row={row} index={index} />
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}

function percent(value: number, digits = 0): string {
  return `${fa(value, digits)}٪`;
}

/** علامت منفی در متن راست‌به‌چپ جابه‌جا می‌شود («۰٫۳-»)؛ با کلمه می‌گوییم. */
function signed(value: string | number): string {
  const number = Number(value);
  return number < 0 ? `منفی ${fa(-number)}` : fa(number);
}

function SummaryCard({ summary }: { summary: ScoreSummary }) {
  const peak = Math.max(1, ...summary.histogram);
  const bins = summary.histogram.length;
  const width = 100 / bins;
  const description = summary.histogram
    .map(
      (count, i) =>
        `از ${toPersianDigits(Math.round(i * width))} تا ${toPersianDigits(Math.round((i + 1) * width))} درصد: ${toPersianDigits(count)} نفر`,
    )
    .join('، ');

  return (
    <Card className="flex flex-col gap-4">
      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-5">
        <Fact label="تعداد تلاش" value={toPersianDigits(summary.n)} />
        <Fact label="میانگین" value={percent(summary.mean_percent)} />
        <Fact label="میانه" value={percent(summary.median_percent)} />
        <Fact
          label="انحراف معیار"
          value={summary.sd_percent === null ? '—' : percent(summary.sd_percent)}
        />
        <Fact
          label="کمینه تا بیشینه"
          value={`${percent(summary.min_percent)} تا ${percent(summary.max_percent)}`}
        />
      </dl>
      {/* محور عددی از کم به زیاد، چپ به راست — قرارداد نمودارهای عددی. */}
      <div dir="ltr" role="img" aria-label={`توزیع نمره: ${description}`}>
        <div className="flex h-28 items-end gap-1" aria-hidden="true">
          {summary.histogram.map((count, i) => (
            <div key={i} className="flex h-full flex-1 flex-col items-center justify-end gap-1">
              <span className="text-[11.5px] tabular-nums text-[var(--fg-secondary)]">
                {count > 0 ? toPersianDigits(count) : ''}
              </span>
              <div
                className="w-full rounded-t-[var(--radius-sm)] bg-[var(--brand-500)]"
                style={{ height: `${Math.max(count > 0 ? 4 : 0, (count / peak) * 80)}%` }}
              />
            </div>
          ))}
        </div>
        <div className="mt-1 flex gap-1" aria-hidden="true">
          {summary.histogram.map((_, i) => (
            <span
              key={i}
              className="flex-1 text-center text-[10.5px] tabular-nums text-[var(--fg-tertiary)]"
            >
              {toPersianDigits(Math.round(i * width))}
            </span>
          ))}
        </div>
      </div>
      <p className="text-[12.5px] text-[var(--fg-tertiary)]">
        محور افقی: درصد نمره، در بازه‌های ۱۰٪ی؛ ارتفاع ستون: تعداد تلاش.
      </p>
    </Card>
  );
}

function ReliabilityCard({ reliability }: { reliability: Reliability | null }) {
  if (!reliability) {
    return (
      <Card>
        <p className="text-[13.5px] text-[var(--fg-secondary)]">
          پایایی هنوز محاسبه نمی‌شود: دست‌کم ۱۰ تلاش و ۲ سؤال مشترک بین همهٔ تلاش‌ها لازم است، و
          نمرهٔ همهٔ دانشجویان نباید یکسان باشد.
        </p>
      </Card>
    );
  }
  const tone: BadgeTone =
    reliability.alpha >= 0.7 ? 'success' : reliability.alpha >= 0.6 ? 'warning' : 'danger';
  return (
    <Card className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[13.5px] text-[var(--fg-secondary)]">پایایی (آلفای کرونباخ)</span>
        <Badge tone={tone}>{reliability.label_fa}</Badge>
        <span className="text-[13.5px] font-semibold tabular-nums">
          {signed(reliability.alpha)}
        </span>
      </div>
      <p className="text-[13.5px] text-[var(--fg-secondary)]">
        خطای معیار اندازه‌گیری: حدود {percent(reliability.sem_percent, 1)} از بارم کل. یعنی نمرهٔ
        واقعی هر دانشجو با احتمال حدود ۶۸٪ در همین فاصله از نمرهٔ ثبت‌شده‌اش است.
      </p>
      {reliability.advice_fa && (
        <p className="rounded-[var(--radius-md)] bg-[var(--bg-sunken)] p-2.5 text-[13.5px] text-[var(--fg-warning)]">
          {reliability.advice_fa}
        </p>
      )}
    </Card>
  );
}

function ItemCard({ row, index }: { row: ItemAnalysis; index: number }) {
  return (
    <Card className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[13px] text-[var(--fg-tertiary)]">
          سؤال {toPersianDigits(index + 1)}
        </span>
        <Badge tone="brand">{KIND_LABELS[row.kind]}</Badge>
        <span className="text-[13px] text-[var(--fg-secondary)]">
          {fa(row.points)} نمره، {toPersianDigits(row.answered)} پاسخ
        </span>
      </div>
      <p className="line-clamp-2 text-[14px]">{row.body}</p>
      <div className="grid gap-3 sm:grid-cols-3">
        <Meter
          label="دشواری"
          value={row.difficulty === null ? null : Number(row.difficulty)}
          display={row.difficulty === null ? '—' : percent(Number(row.difficulty) * 100)}
        />
        <Meter
          label="تمیز"
          value={row.discrimination === null ? null : Math.max(0, Number(row.discrimination))}
          display={
            row.discrimination === null ? 'کمتر از ۱۰ شرکت‌کننده' : signed(row.discrimination)
          }
        />
        <Meter
          label="همبستگی با بقیه"
          value={row.item_rest === null ? null : Math.max(0, row.item_rest)}
          display={row.item_rest === null ? '—' : signed(row.item_rest)}
        />
      </div>
      {row.note_fa && (
        <p className="rounded-[var(--radius-md)] bg-[var(--bg-sunken)] p-2.5 text-[13.5px] text-[var(--fg-warning)]">
          {row.note_fa}
        </p>
      )}
      {row.options.length > 0 && <OptionList options={row.options} />}
    </Card>
  );
}

function OptionList({ options }: { options: OptionStat[] }) {
  return (
    <div className="mt-1 flex flex-col gap-2 border-t border-[var(--border-subtle)] pt-3">
      <span className="text-[12.5px] font-semibold text-[var(--fg-secondary)]">
        توزیع گزینه‌ها (سهم از همهٔ تلاش‌ها)
      </span>
      <ul className="flex flex-col gap-2.5">
        {options.map((option) => (
          <li key={option.option_id} className="flex flex-col gap-1">
            <div className="flex flex-wrap items-center gap-2 text-[13.5px]">
              <span>{option.text}</span>
              {option.is_correct && <Badge tone="success">پاسخ درست</Badge>}
              <span className="text-[12.5px] text-[var(--fg-tertiary)]">
                انتخاب‌شده: {toPersianDigits(option.chosen)} نفر
              </span>
            </div>
            <Meter label="سهم" value={option.share} display={percent(option.share * 100)} />
            {option.top_share !== null && option.bottom_share !== null && (
              <span className="text-[12.5px] text-[var(--fg-secondary)]">
                گروه قوی: {percent(option.top_share * 100)} و گروه ضعیف:{' '}
                {percent(option.bottom_share * 100)}
              </span>
            )}
            {option.note_fa && (
              <p className="text-[13px] text-[var(--fg-warning)]">{option.note_fa}</p>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <dt className="text-[12.5px] text-[var(--fg-secondary)]">{label}</dt>
      <dd className="text-[15px] font-semibold tabular-nums">{value}</dd>
    </div>
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
