import type { Metadata } from 'next';

import { OfferingView } from './OfferingView';

export const metadata: Metadata = {
  title: 'نمای درس',
  description: 'هفتهٔ جاری، پیشرفت مطالعه، نمره و اعلانات درس.',
};

/** `/courses/[offeringId]` — §3.4. */
export default async function OfferingPage({
  params,
}: {
  params: Promise<{ offeringId: string }>;
}) {
  const { offeringId } = await params;
  return <OfferingView offeringId={offeringId} />;
}
