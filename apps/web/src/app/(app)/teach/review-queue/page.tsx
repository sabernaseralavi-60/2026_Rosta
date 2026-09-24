import type { Metadata } from 'next';

import { ReviewQueueView } from './ReviewQueueView';

export const metadata: Metadata = {
  title: 'صف بررسی تحویل‌ها',
  description: 'همهٔ تحویل‌دادنی‌های منتظر بررسی در یک صف.',
};

/** `/teach/review-queue` — §3.5، ADR-0022. */
export default function ReviewQueuePage() {
  return <ReviewQueueView />;
}
