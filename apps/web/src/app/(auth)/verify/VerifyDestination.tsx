'use client';

import { useSearchParams } from 'next/navigation';

/**
 * نمایش مقصد پوشانده — NFR-01.
 *
 * شماره در `<bdi dir="ltr">` می‌نشیند: بدون آن، در یک بند فارسی ترتیب
 * نمایش رقم‌ها به‌هم می‌ریزد (§10.5، دام رایج).
 */
export function VerifyDestination() {
  const masked = useSearchParams().get('to');

  if (!masked) {
    return (
      <p className="text-[15px] text-[var(--fg-secondary)]">
        کد ارسال‌شده را وارد کن.
      </p>
    );
  }

  return (
    <p className="text-[15px] text-[var(--fg-secondary)]">
      کد شش‌رقمی به شمارهٔ{' '}
      <bdi dir="ltr" className="font-medium text-[var(--fg-primary)]">
        {masked}
      </bdi>{' '}
      فرستاده شد.
    </p>
  );
}
