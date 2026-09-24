'use client';

import { useCallback, useEffect, useState } from 'react';

import { errorText, ErrorLine } from '@/components/admin/common';
import { downloadCsv, fa, SectionHeader } from '@/components/teach/common';
import { useOffering } from '@/components/teach/OfferingFrame';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { SkeletonRow } from '@/components/ui/Skeleton';
import { fetchGradebook, type Gradebook, type GradebookRow, setFinalGrade } from '@/lib/api/teach';
import { toLatinDigits, toPersianDigits } from '@/lib/format/digits';

/**
 * `/teach/offerings/[id]/grades` — «دفتر نمره با ویرایش درجا و خروجی Excel» (§3.5).
 *
 * ستون «پیشنهاد» همان `LS × ۰٫۲` است (§9.6) و **فقط پیشنهاد** است: نمرهٔ
 * نهایی را استاد می‌نویسد، یا با یک کلیک پیشنهاد را می‌پذیرد. ثبت نمره درس
 * را برای آن دانشجو «پایان‌یافته» می‌کند و در لاگ حسابرسی می‌نشیند.
 */
export function GradebookView() {
  const { offering, token } = useOffering();
  const [book, setBook] = useState<Gradebook | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    fetchGradebook(offering.id, token)
      .then(setBook)
      .catch((cause) => setError(errorText(cause)));
  }, [offering.id, token]);

  useEffect(load, [load]);

  if (!book && !error) return <SkeletonRow label="در حال بارگذاری دفتر نمره" />;
  if (!book) return <ErrorLine>{error}</ErrorLine>;

  const editable = offering.permissions.submit_final_grades;

  function exportCsv() {
    if (!book) return;
    const header = [
      'دانشجو',
      ...book.quizzes.map((q) => `${q.title_fa} (از ${Number(q.total_points)})`),
      'حاضر',
      'تأخیر',
      'غایب',
      'موجه',
      'نمرهٔ یادگیری',
      'پیشنهاد (از ۲۰)',
      'نمرهٔ نهایی',
    ];
    const rows = book.rows.map((row) => [
      row.student_name ?? '',
      ...row.quizzes.map((cell) => (cell.score === null ? '' : Number(cell.score))),
      row.attendance.present,
      row.attendance.late,
      row.attendance.absent,
      row.attendance.excused,
      row.learning_score === null ? '' : Number(row.learning_score),
      row.suggested_grade === null ? '' : Number(row.suggested_grade),
      row.final_grade ?? '',
    ]);
    downloadCsv(`gradebook-${offering.course_slug}-${offering.term_code}.csv`, [header, ...rows]);
  }

  const replaceRow = (updated: GradebookRow) =>
    setBook((current) =>
      current
        ? {
            ...current,
            rows: current.rows.map((r) =>
              r.enrollment_id === updated.enrollment_id ? updated : r,
            ),
          }
        : current,
    );

  return (
    <div className="flex flex-col gap-4">
      <SectionHeader
        title="دفتر نمره"
        description={
          <>
            ستون آزمون بهترین تلاش تصحیح‌شده است، حتی اگر نتیجه هنوز به دانشجو نشان داده نشده.
            «پیشنهاد» از نمرهٔ یادگیری می‌آید و فقط پیشنهاد است. جلسه‌های ثبت‌شده:{' '}
            {toPersianDigits(book.sessions_held)}.
          </>
        }
        action={
          book.rows.length > 0 ? (
            <Button variant="secondary" size="sm" onClick={exportCsv}>
              خروجی Excel (CSV)
            </Button>
          ) : undefined
        }
      />
      {error && <ErrorLine>{error}</ErrorLine>}
      {book.rows.length === 0 ? (
        <EmptyState
          title="هنوز دانشجوی فعالی نیست"
          description="دفتر نمره فقط دانشجویان تأییدشده را نشان می‌دهد."
        />
      ) : (
        <>
          {/* دسکتاپ: جدول؛ با آزمون‌های زیاد، خود جدول افقی می‌لغزد نه صفحه. */}
          <div className="hidden overflow-x-auto rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-surface)] md:block">
            <table className="w-full border-collapse text-[13px]">
              <caption className="sr-only">دفتر نمرهٔ {offering.course_title_fa}</caption>
              <thead className="bg-[var(--bg-sunken)] text-[var(--fg-secondary)]">
                <tr>
                  <th
                    scope="col"
                    className="sticky start-0 bg-[var(--bg-sunken)] px-3 py-2 text-start"
                  >
                    دانشجو
                  </th>
                  {book.quizzes.map((quiz) => (
                    <th key={quiz.id} scope="col" className="px-3 py-2 text-center font-medium">
                      <span className="block max-w-[10ch] truncate" title={quiz.title_fa}>
                        {quiz.title_fa}
                      </span>
                      <span className="text-[11px] text-[var(--fg-tertiary)]">
                        از {fa(quiz.total_points)}
                      </span>
                    </th>
                  ))}
                  <th scope="col" className="px-3 py-2 text-center">
                    حضور
                  </th>
                  <th scope="col" className="px-3 py-2 text-center">
                    یادگیری
                  </th>
                  <th scope="col" className="px-3 py-2 text-center">
                    پیشنهاد
                  </th>
                  <th scope="col" className="px-3 py-2 text-center">
                    نمرهٔ نهایی
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--border-subtle)]">
                {book.rows.map((row) => (
                  <tr key={row.enrollment_id}>
                    <th
                      scope="row"
                      className="sticky start-0 bg-[var(--bg-surface)] px-3 py-2 text-start font-medium"
                    >
                      {row.student_name ?? 'بی‌نام'}
                    </th>
                    {row.quizzes.map((cell) => (
                      <td key={cell.quiz_id} className="px-3 py-2 text-center tabular-nums">
                        <QuizCell
                          score={cell.score}
                          provisional={cell.is_provisional}
                          attempts={cell.attempts}
                        />
                      </td>
                    ))}
                    <td className="px-3 py-2 text-center">
                      <AttendanceCell row={row} />
                    </td>
                    <td className="px-3 py-2 text-center tabular-nums">
                      {fa(row.learning_score, 0)}
                    </td>
                    <td className="px-3 py-2 text-center tabular-nums">
                      {fa(row.suggested_grade)}
                    </td>
                    <td className="px-3 py-2">
                      <FinalGradeEditor
                        row={row}
                        editable={editable}
                        token={token}
                        onSaved={replaceRow}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* موبایل: هر دانشجو یک کارت برچسب/مقدار — §3.9. */}
          <ul className="flex flex-col gap-3 md:hidden">
            {book.rows.map((row) => (
              <li key={row.enrollment_id}>
                <Card className="flex flex-col gap-3">
                  <span className="font-semibold">{row.student_name ?? 'بی‌نام'}</span>
                  <dl className="grid grid-cols-2 gap-x-3 gap-y-1.5 text-[13px]">
                    {book.quizzes.map((quiz, index) => (
                      <div key={quiz.id} className="contents">
                        <dt className="truncate text-[var(--fg-tertiary)]">{quiz.title_fa}</dt>
                        <dd className="tabular-nums">
                          <QuizCell
                            score={row.quizzes[index]?.score ?? null}
                            provisional={row.quizzes[index]?.is_provisional ?? false}
                            attempts={row.quizzes[index]?.attempts ?? 0}
                          />{' '}
                          <span className="text-[var(--fg-tertiary)]">
                            از {fa(quiz.total_points)}
                          </span>
                        </dd>
                      </div>
                    ))}
                    <dt className="text-[var(--fg-tertiary)]">حضور</dt>
                    <dd>
                      <AttendanceCell row={row} />
                    </dd>
                    <dt className="text-[var(--fg-tertiary)]">نمرهٔ یادگیری</dt>
                    <dd className="tabular-nums">{fa(row.learning_score, 0)}</dd>
                    <dt className="text-[var(--fg-tertiary)]">پیشنهاد (از ۲۰)</dt>
                    <dd className="tabular-nums">{fa(row.suggested_grade)}</dd>
                  </dl>
                  <FinalGradeEditor
                    row={row}
                    editable={editable}
                    token={token}
                    onSaved={replaceRow}
                  />
                </Card>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

function QuizCell({
  score,
  provisional,
  attempts,
}: {
  score: string | null;
  provisional: boolean;
  attempts: number;
}) {
  if (score === null) {
    return attempts > 0 ? (
      <Badge tone="warning">در انتظار تصحیح</Badge>
    ) : (
      <span className="text-[var(--fg-tertiary)]">—</span>
    );
  }
  return (
    <span>
      {fa(score)}
      {provisional && (
        <span className="text-[var(--fg-warning)]" title="تشریحی هنوز تصحیح نشده">
          {' '}
          *<span className="sr-only">موقت</span>
        </span>
      )}
    </span>
  );
}

function AttendanceCell({ row }: { row: GradebookRow }) {
  const { present, late, absent, excused } = row.attendance;
  return (
    <span className="whitespace-nowrap text-[12.5px]">
      {toPersianDigits(present)}
      <span className="text-[var(--fg-tertiary)]"> حاضر</span>
      {late > 0 && (
        <>
          {' '}
          · {toPersianDigits(late)}
          <span className="text-[var(--fg-tertiary)]"> تأخیر</span>
        </>
      )}
      {absent > 0 && (
        <span className="text-[var(--fg-danger)]"> · {toPersianDigits(absent)} غایب</span>
      )}
      {excused > 0 && (
        <>
          {' '}
          · {toPersianDigits(excused)}
          <span className="text-[var(--fg-tertiary)]"> موجه</span>
        </>
      )}
    </span>
  );
}

function FinalGradeEditor({
  row,
  editable,
  token,
  onSaved,
}: {
  row: GradebookRow;
  editable: boolean;
  token: string;
  onSaved: (row: GradebookRow) => void;
}) {
  const [value, setValue] = useState(row.final_grade === null ? '' : fa(row.final_grade));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const name = row.student_name ?? 'دانشجو';

  if (!editable) {
    return (
      <span className="block text-center tabular-nums">
        {row.final_grade === null ? '—' : fa(row.final_grade)}
      </span>
    );
  }

  const parsed = Number(toLatinDigits(value).replace('٫', '.'));
  // مقدار نمایشی فارسی است؛ «تغییر» با عدد سنجیده می‌شود، نه با متن.
  const valid = value.trim() !== '' && !Number.isNaN(parsed) && parsed >= 0 && parsed <= 20;
  const changed = valid && parsed !== row.final_grade;

  async function save(grade: number) {
    setBusy(true);
    setError(null);
    try {
      const updated = await setFinalGrade(row.enrollment_id, grade, token);
      setValue(fa(updated.final_grade ?? grade));
      onSaved({ ...row, final_grade: updated.final_grade, status: updated.status });
    } catch (cause) {
      setError(errorText(cause));
    } finally {
      setBusy(false);
    }
  }

  const suggested =
    row.suggested_grade === null ? null : Number(Number(row.suggested_grade).toFixed(2));

  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center gap-1.5">
        <input
          aria-label={`نمرهٔ نهایی ${name}`}
          inputMode="decimal"
          className="h-9 w-20 rounded-[var(--radius-sm)] border border-[var(--border-default)] bg-[var(--bg-surface)] px-2 text-center tabular-nums"
          value={value}
          placeholder="—"
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && changed) void save(parsed);
          }}
        />
        {changed && (
          <Button size="sm" loading={busy} onClick={() => save(parsed)}>
            ثبت
          </Button>
        )}
        {!changed && suggested !== null && row.final_grade === null && (
          <Button
            size="sm"
            variant="ghost"
            loading={busy}
            onClick={() => save(suggested)}
            aria-label={`ثبت پیشنهاد ${fa(suggested)} برای ${name}`}
          >
            پیشنهاد
          </Button>
        )}
      </div>
      {value.trim() !== '' && !valid && (
        <span className="text-[12px] text-[var(--fg-danger)]">بین ۰ تا ۲۰</span>
      )}
      {error && (
        <span role="alert" className="text-[12px] text-[var(--fg-danger)]">
          {error}
        </span>
      )}
    </div>
  );
}
