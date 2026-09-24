import type { Metadata } from 'next';

import { AnalyticsView } from './AnalyticsView';

export const metadata: Metadata = {
  title: 'تحلیل سؤال',
  description: 'ضریب دشواری و تمیز هر سؤال.',
};

/** `/teach/quizzes/[id]/analytics` — M4-13. */
export default function AnalyticsPage() {
  return <AnalyticsView />;
}
