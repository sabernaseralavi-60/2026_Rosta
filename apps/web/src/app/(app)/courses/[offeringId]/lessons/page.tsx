import type { Metadata } from 'next';

import { LessonsListView } from './LessonsListView';

export const metadata: Metadata = {
  title: 'درس‌نامه‌ها',
  description: 'همهٔ درس‌نامه‌های منتشرشدهٔ این درس.',
};

/** `/courses/[offeringId]/lessons` — فهرست درس‌نامه‌ها (ADR-0036). */
export default async function LessonsPage({ params }: { params: Promise<{ offeringId: string }> }) {
  const { offeringId } = await params;
  return <LessonsListView offeringId={offeringId} />;
}
