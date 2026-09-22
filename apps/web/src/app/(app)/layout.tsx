import type { ReactNode } from 'react';

import { AppHeader } from '@/components/domain/AppHeader';

/**
 * پوستهٔ اپلیکیشن — §3.1.
 *
 * ناوبری کامل (سایدبار، جستجوی ⌘K، مرکز اعلان) در مراحل بعد اضافه
 * می‌شود. در M0 فقط هدر و ناحیهٔ محتوا لازم است.
 */
export default function AppLayout({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-dvh flex-col bg-[var(--bg-canvas)]">
      <AppHeader />
      <main id="main" className="page flex-1 py-8">
        {children}
      </main>
    </div>
  );
}
