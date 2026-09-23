import type { Metadata } from 'next';

import { IdeaForm } from './IdeaForm';

export const metadata: Metadata = {
  title: 'ثبت ایده',
  description: 'ایده‌ات را با مسئله‌ای که حل می‌کند ثبت کن.',
};

/** `/ideas/new` — §3.4، FR-IDEA-01. */
export default function NewIdeaPage() {
  return <IdeaForm />;
}
