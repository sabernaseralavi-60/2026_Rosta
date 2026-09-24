import type { Metadata } from 'next';

import { WeeksView } from './WeeksView';

export const metadata: Metadata = {
  title: 'هفته‌های ارائه',
  description: 'هفته‌ها، انتشار و زمان‌بندی.',
};

/** `/teach/offerings/[id]` — §3.5، FR-EDU-02. */
export default function WeeksPage() {
  return <WeeksView />;
}
