'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';

import { errorText } from '@/components/admin/common';
import { Button } from '@/components/ui/Button';
import { EmptyState } from '@/components/ui/EmptyState';
import { SkeletonCard } from '@/components/ui/Skeleton';
import { ApiError } from '@/lib/api/client';
import {
  fetchTeachOffering,
  fetchTeachQuiz,
  type TeachOfferingDetail,
  type TeachQuiz,
} from '@/lib/api/teach';
import { useSession } from '@/lib/auth/use-session';
import { cn } from '@/lib/cn';
import { formatDateTime } from '@/lib/format/date';
import { toPersianDigits } from '@/lib/format/digits';

import { fa, QuizStatusBadge } from './common';

interface QuizContextValue {
  quiz: TeachQuiz;
  offering: TeachOfferingDetail;
  token: string;
  reload: () => Promise<void>;
  replace: (quiz: TeachQuiz) => void;
  /** اعتراض و ابطال تلاش با استاد است، نه دستیار (§6.1). */
  isInstructor: boolean;
}

const QuizContext = createContext<QuizContextValue | null>(null);

export function useQuiz(): QuizContextValue {
  const value = useContext(QuizContext);
  if (!value) throw new Error('useQuiz بیرون از QuizFrame');
  return value;
}

const TABS = [
  { path: '/edit', label: 'سؤال‌ها و تنظیمات' },
  { path: '/grade', label: 'تصحیح و اعتراض' },
  { path: '/analytics', label: 'تحلیل سؤال' },
];

/** قاب آزمون — §3.5 `/teach/quizzes/[id]/…`. */
export function QuizFrame({ quizId, children }: { quizId: string; children: ReactNode }) {
  const pathname = usePathname();
  const { accessToken: token } = useSession();
  const [quiz, setQuiz] = useState<TeachQuiz | null>(null);
  const [offering, setOffering] = useState<TeachOfferingDetail | null>(null);
  const [error, setError] = useState<{ text: string; status: number | null } | null>(null);
  // ارائه فقط بار اول (یا اگر آزمون به ارائهٔ دیگری تعلق داشت) خوانده می‌شود.
  const offeringRef = useRef<TeachOfferingDetail | null>(null);

  const reload = useCallback(async () => {
    if (!token) return;
    try {
      const loaded = await fetchTeachQuiz(quizId, token);
      if (offeringRef.current?.id !== loaded.offering_id) {
        const parent = await fetchTeachOffering(loaded.offering_id, token);
        offeringRef.current = parent;
        setOffering(parent);
      }
      setQuiz(loaded);
      setError(null);
    } catch (cause) {
      setError({
        text: errorText(cause),
        status: cause instanceof ApiError ? cause.status : null,
      });
    }
  }, [quizId, token]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const value = useMemo(
    () =>
      quiz && offering && token
        ? {
            quiz,
            offering,
            token,
            reload,
            replace: setQuiz,
            isInstructor: offering.staff_role !== 'TA',
          }
        : null,
    [quiz, offering, token, reload],
  );

  if (error && !quiz) {
    const missing = error.status === 403 || error.status === 404;
    return (
      <EmptyState
        as="h1"
        title={missing ? 'این آزمون در دسترس تو نیست' : 'آزمون بارگذاری نشد'}
        description={missing ? 'فقط استاد و دستیار همان ارائه آزمونش را می‌بینند.' : error.text}
        action={
          missing ? (
            <Link href="/teach/quizzes" className="text-[14px] font-medium text-[var(--fg-brand)]">
              بازگشت به آزمون‌ها
            </Link>
          ) : (
            <Button onClick={() => void reload()}>تلاش دوباره</Button>
          )
        }
      />
    );
  }
  if (!value) return <SkeletonCard label="در حال بارگذاری آزمون" />;

  const base = `/teach/quizzes/${quizId}`;
  return (
    <QuizContext.Provider value={value}>
      <div className="flex flex-col gap-6">
        <header className="flex flex-col gap-2">
          <nav aria-label="مسیر" className="text-[13px] text-[var(--fg-tertiary)]">
            <Link
              href={`/teach/offerings/${value.offering.id}/quizzes`}
              className="hover:text-[var(--fg-brand)]"
            >
              {value.offering.course_title_fa}
            </Link>{' '}
            ‹ آزمون‌ها
          </nav>
          <div className="flex flex-wrap items-center gap-3">
            <h1>{value.quiz.title_fa}</h1>
            <QuizStatusBadge status={value.quiz.status} label={value.quiz.status_fa} />
          </div>
          <p className="text-[13.5px] text-[var(--fg-secondary)]">
            {formatDateTime(value.quiz.opens_at)} تا {formatDateTime(value.quiz.closes_at)} ·{' '}
            {toPersianDigits(value.quiz.duration_min)} دقیقه · {fa(value.quiz.total_points)} نمره ·{' '}
            {toPersianDigits(value.quiz.attempt_count)} تلاش
          </p>
        </header>
        <nav
          aria-label="بخش‌های آزمون"
          className="flex gap-1 overflow-x-auto border-b border-[var(--border-subtle)]"
        >
          {TABS.map((tab) => {
            const href = `${base}${tab.path}`;
            const current = pathname.startsWith(href);
            return (
              <Link
                key={tab.path}
                href={href}
                aria-current={current ? 'page' : undefined}
                className={cn(
                  '-mb-px whitespace-nowrap border-b-2 px-3 py-2 text-[14px]',
                  current
                    ? 'border-[var(--brand-600)] font-semibold text-[var(--fg-brand)]'
                    : 'border-transparent text-[var(--fg-secondary)] hover:text-[var(--fg-primary)]',
                )}
              >
                {tab.label}
              </Link>
            );
          })}
        </nav>
        {children}
      </div>
    </QuizContext.Provider>
  );
}
