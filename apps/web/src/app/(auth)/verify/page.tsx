import type { Metadata } from 'next';
import { Suspense } from 'react';

import { SkeletonText } from '@/components/ui/Skeleton';

import { VerifyDestination } from './VerifyDestination';
import { VerifyForm } from './VerifyForm';

export const metadata: Metadata = {
  title: 'تأیید کد',
  description: 'کد شش‌رقمی ارسال‌شده را وارد کنید.',
  robots: { index: false, follow: false },
};

/**
 * `/verify` — §3.3.
 *
 * `useSearchParams` نیازمند مرز Suspense است، وگرنه کل صفحه از حالت
 * ایستا خارج می‌شود.
 */
export default function VerifyPage() {
  return (
    <section className="flex w-full max-w-[26rem] flex-col gap-6">
      <div className="flex flex-col gap-2">
        <h1>کد را وارد کن</h1>
        <Suspense fallback={<SkeletonText label="در حال آماده‌سازی" />}>
          <VerifyDestination />
        </Suspense>
      </div>

      <Suspense fallback={<SkeletonText label="در حال آماده‌سازی فرم" />}>
        <VerifyForm />
      </Suspense>
    </section>
  );
}
