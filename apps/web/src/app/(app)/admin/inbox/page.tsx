import type { Metadata } from 'next';
import { Suspense } from 'react';

import { SkeletonCard } from '@/components/ui/Skeleton';

import { InboxView } from './InboxView';

export const metadata: Metadata = {
  title: 'صندوق درخواست‌ها',
  description:
    'مسئله و نیاز بازدیدکنندگان و درخواست‌های همکاری؛ وضعیت، پیام به مشتری و یادداشت خصوصی.',
};

/** `/admin/inbox` — ADR-0032. فقط مدیر سامانه (`intake.manage`). */
export default function InboxPage() {
  return (
    <Suspense fallback={<SkeletonCard label="در حال بارگذاری صندوق" />}>
      <InboxView />
    </Suspense>
  );
}
