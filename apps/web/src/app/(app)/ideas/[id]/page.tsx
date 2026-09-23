import type { Metadata } from 'next';

import { IdeaDetailView } from './IdeaDetailView';

export const metadata: Metadata = {
  title: 'ایده',
  description: 'شرح ایده، رأی‌ها و نظرها.',
};

/** `/ideas/[id]` — §3.4، FR-IDEA-02/03. */
export default async function IdeaPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <IdeaDetailView id={id} />;
}
