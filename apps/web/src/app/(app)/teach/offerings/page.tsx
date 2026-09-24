import type { Metadata } from 'next';

import { OfferingsView } from './OfferingsView';

export const metadata: Metadata = {
  title: 'ارائه‌های من',
  description: 'درس‌هایی که در آن‌ها استاد یا دستیار آموزشی هستی.',
};

/** `/teach/offerings` — §3.5. */
export default function OfferingsPage() {
  return <OfferingsView />;
}
