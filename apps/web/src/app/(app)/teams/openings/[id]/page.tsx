import type { Metadata } from 'next';

import { OpeningDetailView } from './OpeningDetailView';

export const metadata: Metadata = {
  title: 'آگهی هم‌تیمی',
  description: 'نقش، مهارت لازم، تعهد زمانی و درخواست پیوستن.',
};

/** `/teams/openings/[id]` — FR-TEAM-02/03. */
export default async function OpeningPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <OpeningDetailView id={id} />;
}
