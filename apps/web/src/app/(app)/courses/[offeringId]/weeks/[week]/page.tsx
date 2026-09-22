import type { Metadata } from 'next';

import { WeekView } from './WeekView';

export const metadata: Metadata = {
  title: 'محتوای هفته',
  description: 'جزوه، ویدئو، منابع کتابخانه و پیشرفت مطالعهٔ این هفته.',
};

/** `/courses/[offeringId]/weeks/[n]` — §3.4. */
export default async function WeekPage({
  params,
}: {
  params: Promise<{ offeringId: string; week: string }>;
}) {
  const { offeringId, week } = await params;
  return <WeekView offeringId={offeringId} weekNumber={Number(week)} />;
}
