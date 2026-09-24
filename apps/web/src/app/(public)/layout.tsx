import Link from 'next/link';
import type { ReactNode } from 'react';

import { PublicHeader } from '@/components/public/PublicHeader';

/**
 * ناحیهٔ عمومی — §3.2: صفحهٔ اصلی، نیمرخ عمومی و راستی‌آزمایی گواهی.
 * بی‌ورود، رندر سمت سرور، بدون Providerهای امتیاز و اعلان.
 */
export default function PublicLayout({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-dvh flex-col bg-[var(--bg-canvas)]">
      <PublicHeader />
      <main id="main" className="flex-1">
        {children}
      </main>
      <footer className="border-t border-[var(--border-subtle)] py-8">
        <div className="page flex flex-wrap items-center justify-between gap-4 text-[13px] text-[var(--fg-tertiary)]">
          <span>سامانهٔ نوآوری و یادگیری صابر — از مصرف‌کنندهٔ دانش، به تولیدکنندهٔ ارزش</span>
          <nav aria-label="پیوندهای پانویس" className="flex gap-4">
            <Link href="/projects" className="hover:text-[var(--fg-brand)]">
              پروژه‌ها
            </Link>
            <Link href="/help" className="hover:text-[var(--fg-brand)]">
              راهنما
            </Link>
            <Link href="/login" className="hover:text-[var(--fg-brand)]">
              ورود و ثبت‌نام
            </Link>
          </nav>
        </div>
      </footer>
    </div>
  );
}
