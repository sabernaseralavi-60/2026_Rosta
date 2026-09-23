import type { Metadata } from 'next';

import { MetricsView } from '@/components/domain/MetricsView';

export const metadata: Metadata = {
  title: 'فعالیت و فروش',
  description: 'ثبت تماس، جلسه، سرنخ و فروش؛ و وضعیت تأیید هر ردیف.',
};

/** `/ventures/[id]/metrics` — §3.4، FR-VEN-02. */
export default async function VentureMetricsPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <MetricsView owner={{ kind: 'venture', id }} backHref={`/ventures/${id}`} />;
}
