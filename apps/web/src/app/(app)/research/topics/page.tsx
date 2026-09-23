import type { Metadata } from 'next';

import { TopicsView } from './TopicsView';

export const metadata: Metadata = {
  title: 'بانک موضوع پژوهشی',
  description: 'موضوع‌های پژوهشی باز با شرح و پیش‌نیاز — رزرو کن تا کسی موازی کار نکند.',
};

/** `/research/topics` — §3.4، FR-RES-03. */
export default function TopicsPage() {
  return <TopicsView />;
}
