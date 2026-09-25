import type { Metadata } from 'next';
import { Suspense } from 'react';

import { SkeletonCard } from '@/components/ui/Skeleton';

import { RevenueView } from './RevenueView';

export const metadata: Metadata = {
  title: 'درآمد و سهم من',
  description: 'فروش‌های تأییدشدهٔ پروژه‌های کارآفرینی و سهم تو از هر کدام، به تفکیک ماه.',
};

/**
 * `/me/revenue` — FR-VEN-03، ADR-0025. فقط ثبت و گزارش؛ پرداخت بیرون از سامانه است.
 */
export default function RevenuePage() {
  return (
    <Suspense fallback={<SkeletonCard label="در حال بارگذاری گزارش درآمد" />}>
      <RevenueView />
    </Suspense>
  );
}
