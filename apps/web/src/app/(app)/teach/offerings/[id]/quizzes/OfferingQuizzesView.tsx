'use client';

import { useRouter } from 'next/navigation';
import { useCallback, useEffect, useState } from 'react';

import { errorText, ErrorLine } from '@/components/admin/common';
import { SectionHeader } from '@/components/teach/common';
import { useOffering } from '@/components/teach/OfferingFrame';
import { QuizList } from '@/components/teach/QuizList';
import { QuizSettingsForm } from '@/components/teach/QuizSettingsForm';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { SkeletonRow } from '@/components/ui/Skeleton';
import { createQuiz, fetchOfferingQuizzesForStaff, type TeachQuiz } from '@/lib/api/teach';

/** `/teach/offerings/[id]/quizzes` — آزمون‌های یک ارائه و ساخت آزمون تازه. */
export function OfferingQuizzesView() {
  const { offering, token } = useOffering();
  const router = useRouter();
  const [quizzes, setQuizzes] = useState<TeachQuiz[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const can = offering.permissions;

  const load = useCallback(() => {
    fetchOfferingQuizzesForStaff(offering.id, token)
      .then(setQuizzes)
      .catch((cause) => setError(errorText(cause)));
  }, [offering.id, token]);

  useEffect(load, [load]);

  if (!quizzes && !error) return <SkeletonRow label="در حال بارگذاری آزمون‌ها" />;
  if (!quizzes) return <ErrorLine>{error}</ErrorLine>;

  return (
    <div className="flex flex-col gap-6">
      <SectionHeader
        title="آزمون‌ها"
        description="آزمون پیش‌نویس را دانشجو نمی‌بیند. سؤال‌ها تا پیش از اولین تلاش قابل ویرایش‌اند."
        action={
          can.create_quizzes && !creating ? (
            <Button onClick={() => setCreating(true)}>آزمون تازه</Button>
          ) : undefined
        }
      />
      {creating && (
        <Card className="flex flex-col gap-4">
          <div className="flex items-center justify-between">
            <h3 className="text-[16px]">آزمون تازه</h3>
            <Button variant="ghost" size="sm" onClick={() => setCreating(false)}>
              انصراف
            </Button>
          </div>
          <QuizSettingsForm
            weeks={offering.weeks}
            submitLabel="ساخت و رفتن به سؤال‌ها"
            onSubmit={async (input) => {
              const quiz = await createQuiz(offering.id, input, token);
              router.push(`/teach/quizzes/${quiz.id}/edit`);
            }}
          />
        </Card>
      )}
      {quizzes.length === 0 && !creating ? (
        <EmptyState
          title="هنوز آزمونی ساخته نشده"
          description="هر هفته می‌تواند یک آزمون کوتاه داشته باشد؛ نمره‌اش خودکار در دفتر نمره و نمرهٔ یادگیری می‌نشیند."
        />
      ) : (
        <QuizList quizzes={quizzes} />
      )}
    </div>
  );
}
