import type { Metadata } from 'next';

import { ResultsView } from './ResultsView';

export const metadata: Metadata = {
  title: 'پیشنهادهای تو',
  description: 'پروژه‌هایی که بر اساس نیمرخ تو انتخاب شده‌اند.',
};

/** `/onboarding/results` — §3.3، «لحظهٔ طلایی» §01. */
export default function ResultsPage() {
  return <ResultsView />;
}
