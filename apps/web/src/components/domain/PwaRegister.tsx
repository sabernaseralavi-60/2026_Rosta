'use client';

import { useEffect } from 'react';

import { registerServiceWorker } from '@/lib/push/client';

/**
 * ثبت سرویس‌کارگر — ADR-0029. چیزی رندر نمی‌کند.
 *
 * پس از بار کامل صفحه ثبت می‌شود تا نصبش با اولین رنگ‌آمیزی رقابت نکند.
 */
export function PwaRegister() {
  useEffect(() => {
    if (document.readyState === 'complete') {
      void registerServiceWorker();
      return;
    }
    const onLoad = () => void registerServiceWorker();
    window.addEventListener('load', onLoad, { once: true });
    return () => window.removeEventListener('load', onLoad);
  }, []);
  return null;
}
