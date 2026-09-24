import type { Metadata } from 'next';

import { SubscriptionsAdminView } from './SubscriptionsAdminView';

export const metadata: Metadata = {
  title: 'اشتراک‌ها',
  description: 'تأیید پرداخت، فعال‌سازی و رد درخواست اشتراک.',
};

/** `/admin/subscriptions` — ADR-0009، ADR-0019. */
export default function SubscriptionsAdminPage() {
  return <SubscriptionsAdminView />;
}
