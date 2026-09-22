import type { Metadata } from 'next';

import { QuizRunner } from './QuizRunner';

export const metadata: Metadata = {
  title: 'آزمون',
  description: 'محیط برگزاری آزمون با زمان‌سنج سروری و ذخیرهٔ خودکار پاسخ‌ها.',
};

/** `/quiz/[attemptId]` — محیط آزمون، §3.4. */
export default async function QuizAttemptPage({
  params,
}: {
  params: Promise<{ attemptId: string }>;
}) {
  const { attemptId } = await params;
  return <QuizRunner attemptId={attemptId} />;
}
