import type { Metadata } from 'next';

import { ResearchView } from './ResearchView';

export const metadata: Metadata = {
  title: 'مسیر پژوهش',
  description: 'چهار سطح از مرور ادبیات تا مقالهٔ Q1 — هر سطح با راهنما، الگو و تأیید منتور.',
};

/** `/research` — §3.4، FR-RES-01. */
export default function ResearchPage() {
  return <ResearchView />;
}
