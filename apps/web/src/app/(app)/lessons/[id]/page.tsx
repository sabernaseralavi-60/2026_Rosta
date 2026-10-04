import type { Metadata } from 'next';

import { LessonView } from './LessonView';

export const metadata: Metadata = {
  title: 'درس‌نامه',
  description: 'درس‌نامهٔ کوتاه و چالش وصل‌شده به آن.',
};

/** `/lessons/[id]` — خواندن یک درس‌نامه (ADR-0036). */
export default async function LessonPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <LessonView lessonId={id} />;
}
