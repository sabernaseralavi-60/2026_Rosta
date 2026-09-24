import type { Metadata } from 'next';

import { AnnouncementsView } from './AnnouncementsView';

export const metadata: Metadata = {
  title: 'اعلان‌های درس',
  description: 'انتشار اعلان برای کلاس.',
};

/** `/teach/offerings/[id]/announcements` — FR-EDU-06. */
export default function AnnouncementsPage() {
  return <AnnouncementsView />;
}
