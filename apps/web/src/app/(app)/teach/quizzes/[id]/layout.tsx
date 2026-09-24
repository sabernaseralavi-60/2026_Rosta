import type { ReactNode } from 'react';

import { QuizFrame } from '@/components/teach/QuizFrame';

/** یک آزمون: سرصفحه و زبانه‌های ویرایش، تصحیح و تحلیل. */
export default async function QuizLayout({
  children,
  params,
}: {
  children: ReactNode;
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <QuizFrame quizId={id}>{children}</QuizFrame>;
}
