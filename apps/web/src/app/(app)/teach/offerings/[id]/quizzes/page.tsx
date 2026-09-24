import type { Metadata } from 'next';

import { OfferingQuizzesView } from './OfferingQuizzesView';

export const metadata: Metadata = {
  title: 'آزمون‌های ارائه',
  description: 'آزمون‌های این ارائه و ساخت آزمون تازه.',
};

/** `/teach/offerings/[id]/quizzes` — FR-QUIZ-01. */
export default function OfferingQuizzesPage() {
  return <OfferingQuizzesView />;
}
