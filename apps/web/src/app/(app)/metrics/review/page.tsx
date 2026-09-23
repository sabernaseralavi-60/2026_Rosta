import type { Metadata } from 'next';

import { MetricReviewView } from './MetricReviewView';

export const metadata: Metadata = {
  title: 'تأیید فعالیت و فروش',
  description: 'صف ثبت‌های فعالیت و فروش که منتظر تأیید شما هستند.',
};

/** `/metrics/review` — FR-VEN-02. */
export default function MetricReviewPage() {
  return <MetricReviewView />;
}
