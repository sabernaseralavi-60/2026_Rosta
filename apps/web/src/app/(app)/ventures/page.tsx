import type { Metadata } from 'next';

import { VenturesView } from './VenturesView';

export const metadata: Metadata = {
  title: 'کسب‌وکارها',
  description: 'کسب‌وکارهای دانشجویی، مرحلهٔ بلوغشان، و تیم‌هایی که هم‌بنیان‌گذار می‌خواهند.',
};

/** `/ventures` — §3.4، FR-VEN-01. */
export default function VenturesPage() {
  return <VenturesView />;
}
