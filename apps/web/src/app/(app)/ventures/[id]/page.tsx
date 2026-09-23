import type { Metadata } from 'next';

import { VentureDetailView } from './VentureDetailView';

export const metadata: Metadata = {
  title: 'کسب‌وکار',
  description: 'مرحلهٔ بلوغ، معیار گام بعد، تیم و تاریخچهٔ کسب‌وکار.',
};

/** `/ventures/[id]` — §3.4، §7.7. */
export default async function VenturePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <VentureDetailView id={id} />;
}
