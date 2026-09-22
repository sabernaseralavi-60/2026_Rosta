import type { Metadata } from 'next';

import { ResultView } from './ResultView';

export const metadata: Metadata = {
  title: 'نتیجهٔ آزمون',
  description: 'نمرهٔ کل، نمرهٔ هر سؤال، پاسخ درست و مقایسه با میانگین کلاس.',
};

/** `/quiz/[attemptId]/result` — §3.4، FR-QUIZ-04. */
export default async function QuizResultPage({
  params,
}: {
  params: Promise<{ attemptId: string }>;
}) {
  const { attemptId } = await params;
  return <ResultView attemptId={attemptId} />;
}
