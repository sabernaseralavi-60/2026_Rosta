import type { Metadata } from 'next';

import { GradingView } from './GradingView';

export const metadata: Metadata = {
  title: 'تصحیح آزمون',
  description: 'صف تصحیح تشریحی بر اساس سؤال، اعتراض‌ها و تلاش‌ها.',
};

/** `/teach/quizzes/[id]/grade` — §3.5، M4-10/12. */
export default function GradingPage() {
  return <GradingView />;
}
