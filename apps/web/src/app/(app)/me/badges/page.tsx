import type { Metadata } from 'next';

import { BadgesView } from './BadgesView';

export const metadata: Metadata = {
  title: 'نشان‌ها',
  description: 'نشان‌های کسب‌شده و شرط نشان‌های بعدی.',
};

/** `/me/badges` — §3.4. «نشان‌های کسب‌شده و قفل‌شده با شرایط.» */
export default function BadgesPage() {
  return <BadgesView />;
}
