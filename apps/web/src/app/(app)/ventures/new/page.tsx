import type { Metadata } from 'next';

import { VentureForm } from './VentureForm';

export const metadata: Metadata = {
  title: 'ثبت کسب‌وکار',
  description: 'کسب‌وکارت را ثبت کن و مسیر بلوغش را قدم‌به‌قدم طی کن.',
};

/** `/ventures/new` — §3.4، FR-VEN-01. */
export default function NewVenturePage() {
  return <VentureForm />;
}
