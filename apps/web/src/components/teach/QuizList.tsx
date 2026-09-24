'use client';

import Link from 'next/link';

import { Button } from '@/components/ui/Button';
import type { TeachQuiz } from '@/lib/api/teach';
import { formatDateTime } from '@/lib/format/date';
import { toPersianDigits } from '@/lib/format/digits';

import { fa, QuizStatusBadge } from './common';

/** فهرست آزمون با پیوند ویرایش، تصحیح و تحلیل — ارائه و «همهٔ آزمون‌ها». */
export function QuizList({
  quizzes,
  showCourse,
}: {
  quizzes: (TeachQuiz & { course?: string })[];
  showCourse?: boolean;
}) {
  return (
    <ul className="flex flex-col divide-y divide-[var(--border-subtle)] rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-surface)]">
      {quizzes.map((quiz) => (
        <li key={quiz.id} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
          <div className="flex min-w-0 flex-col gap-0.5">
            <span className="flex flex-wrap items-center gap-2">
              <Link
                href={`/teach/quizzes/${quiz.id}/edit`}
                className="font-medium hover:text-[var(--fg-brand)]"
              >
                {quiz.title_fa}
              </Link>
              <QuizStatusBadge status={quiz.status} label={quiz.status_fa} />
            </span>
            <span className="text-[12.5px] text-[var(--fg-tertiary)]">
              {showCourse && quiz.course ? `${quiz.course} · ` : ''}
              {formatDateTime(quiz.opens_at)} تا {formatDateTime(quiz.closes_at)} ·{' '}
              {fa(quiz.total_points)} نمره · {toPersianDigits(quiz.attempt_count)} تلاش
            </span>
          </div>
          <div className="flex gap-1">
            <Button asChild size="sm" variant="ghost">
              <Link href={`/teach/quizzes/${quiz.id}/edit`}>ویرایش</Link>
            </Button>
            {quiz.attempt_count > 0 && (
              <>
                <Button asChild size="sm" variant="ghost">
                  <Link href={`/teach/quizzes/${quiz.id}/grade`}>تصحیح</Link>
                </Button>
                <Button asChild size="sm" variant="ghost">
                  <Link href={`/teach/quizzes/${quiz.id}/analytics`}>تحلیل</Link>
                </Button>
              </>
            )}
          </div>
        </li>
      ))}
    </ul>
  );
}
