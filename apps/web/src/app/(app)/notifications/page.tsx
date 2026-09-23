import type { Metadata } from 'next';
import { Suspense } from 'react';

import { SkeletonCard } from '@/components/ui/Skeleton';

import { NotificationsView } from './NotificationsView';

export const metadata: Metadata = {
  title: 'اعلان‌ها',
  description: 'خبرهای درس، پروژه و حساب — همه در یک جا.',
};

/** `/notifications` — FR-MSG-01، M6-08. */
export default function NotificationsPage() {
  return (
    <Suspense fallback={<SkeletonCard label="در حال بارگذاری اعلان‌ها" />}>
      <NotificationsView />
    </Suspense>
  );
}
