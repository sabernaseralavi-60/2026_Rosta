import type { Metadata } from 'next';

import { WeekEditorView } from './WeekEditorView';

export const metadata: Metadata = {
  title: 'ویرایش هفته',
  description: 'مشخصات، منابع و محتوای کتابخانهٔ یک هفته.',
};

/** `/teach/offerings/[id]/weeks/[n]` — §3.5، FR-EDU-02/03. */
export default async function WeekEditorPage({ params }: { params: Promise<{ n: string }> }) {
  const { n } = await params;
  return <WeekEditorView weekNumber={Number(n)} />;
}
