import type { Metadata } from 'next';
import { Suspense } from 'react';

import { SkeletonCard } from '@/components/ui/Skeleton';

import { PointsLedgerView } from './PointsLedgerView';

export const metadata: Metadata = {
  title: 'دفتر امتیاز',
  description: 'هر امتیاز با منبع و تاریخش — و هر اصلاحی که رویش انجام شده.',
};

/**
 * `/me/points` — §3.4، M5-09. «دفتر کل شخصی: هر امتیاز با منبع و تاریخ.»
 *
 * فیلترها در نشانی صفحه‌اند (`?category=…`، `?source_type=…&source_id=…`)
 * تا هر عدد در جای دیگر رابط بتواند مستقیم به منشأش پیوند بخورد (§9.10).
 */
export default function PointsPage() {
  return (
    <Suspense fallback={<SkeletonCard label="در حال بارگذاری دفتر امتیاز" />}>
      <PointsLedgerView />
    </Suspense>
  );
}
