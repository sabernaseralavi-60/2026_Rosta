import type { ReactNode } from 'react';

import { AppHeader } from '@/components/domain/AppHeader';
import { NotificationsProvider } from '@/components/domain/NotificationsProvider';
import { PointsProvider } from '@/components/domain/PointsProvider';

/**
 * پوستهٔ اپلیکیشن — §3.1.
 *
 * ناوبری کامل (سایدبار، جستجوی ⌘K) در M7 اضافه می‌شود. از M5،
 * `PointsProvider` کل پوسته را می‌پوشاند: امتیاز هدر، Toast «+۵۰» و جشن
 * سطح و نشان در همهٔ صفحات یکی‌اند (§9.10). از M6، `NotificationsProvider`
 * یک جریان SSE برای کل پوسته باز نگه می‌دارد — نه یکی برای هر صفحه.
 */
export default function AppLayout({ children }: { children: ReactNode }) {
  return (
    <PointsProvider>
      <NotificationsProvider>
        <div className="flex min-h-dvh flex-col bg-[var(--bg-canvas)]">
          <AppHeader />
          <main id="main" className="page flex-1 py-8">
            {children}
          </main>
        </div>
      </NotificationsProvider>
    </PointsProvider>
  );
}
