'use client';

import { useEffect } from 'react';

import { Button } from '@/components/ui/Button';
import { EmptyState } from '@/components/ui/EmptyState';

/**
 * مرز خطای سراسری — NFR-12.
 *
 * «هیچ Stack Trace به کاربر نمایش داده نمی‌شود.» اما `digest` نشان داده
 * می‌شود: همان چیزی است که کاربر می‌تواند به پشتیبانی بدهد.
 */
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // در تولید به Sentry می‌رود (M7-17).
    console.error(error);
  }, [error]);

  return (
    <main id="main" className="page flex min-h-dvh items-center justify-center py-16">
      <EmptyState
        title="مشکلی پیش آمد"
        description={
          error.digest
            ? `اگر مشکل ادامه داشت، این شناسه را به پشتیبانی بده: ${error.digest}`
            : 'کمی بعد دوباره تلاش کن.'
        }
        action={<Button onClick={reset}>تلاش دوباره</Button>}
      />
    </main>
  );
}
