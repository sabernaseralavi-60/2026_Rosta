import type { Metadata } from 'next';

import { GradebookView } from './GradebookView';

export const metadata: Metadata = {
  title: 'دفتر نمره',
  description: 'آزمون‌ها، حضور، نمرهٔ یادگیری و نمرهٔ نهایی — با خروجی Excel.',
};

/** `/teach/offerings/[id]/grades` — §3.5، §9.6. */
export default function GradebookPage() {
  return <GradebookView />;
}
