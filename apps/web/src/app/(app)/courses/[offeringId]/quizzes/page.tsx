import type { Metadata } from 'next';

import { QuizListView } from './QuizListView';

export const metadata: Metadata = {
  title: 'آزمون‌های درس',
  description: 'آزمون‌های این درس، وضعیت هر کدام و تلاش‌های شما.',
};

/** `/courses/[offeringId]/quizzes` — §3.4. */
export default async function OfferingQuizzesPage({
  params,
}: {
  params: Promise<{ offeringId: string }>;
}) {
  const { offeringId } = await params;
  return <QuizListView offeringId={offeringId} />;
}
