import type { Metadata } from 'next';

import { TopicDetailView } from './TopicDetailView';

export const metadata: Metadata = {
  title: 'موضوع پژوهشی',
  description: 'شرح، پیش‌نیاز و وضعیت رزرو یک موضوع پژوهشی.',
};

/** `/research/topics/[id]` — FR-RES-03. */
export default async function TopicPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <TopicDetailView id={id} />;
}
