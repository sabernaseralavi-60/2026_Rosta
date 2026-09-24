import type { Metadata } from 'next';

import { AllQuizzesView } from './AllQuizzesView';

export const metadata: Metadata = {
  title: 'آزمون‌ها',
  description: 'آزمون‌های همهٔ ارائه‌های من.',
};

/** `/teach/quizzes` — §3.5. */
export default function AllQuizzesPage() {
  return <AllQuizzesView />;
}
