import type { Metadata } from 'next';

import { OutputsView } from './OutputsView';

export const metadata: Metadata = {
  title: 'مقاله‌های من',
  description: 'مقاله، پایان‌نامه و گزارش پژوهشی — امتیاز پس از راستی‌آزمایی.',
};

/** `/research/outputs` — §3.4، FR-RES-02. */
export default function OutputsPage() {
  return <OutputsView />;
}
