import Link from 'next/link';
import type { ReactNode } from 'react';

import { Logo } from '@/components/domain/Logo';
import { PublicHeader } from '@/components/public/PublicHeader';

/**
 * ناحیهٔ عمومی — §3.2: صفحهٔ اصلی، مطالب، نیمرخ عمومی و راستی‌آزمایی گواهی.
 * بی‌ورود، رندر سمت سرور، بدون Providerهای امتیاز و اعلان.
 */
export default function PublicLayout({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-dvh flex-col bg-[var(--bg-canvas)]">
      <PublicHeader />
      <main id="main" className="flex-1">
        {children}
      </main>
      <footer className="mt-8 border-t border-[var(--border-subtle)] bg-[var(--bg-surface)]">
        <div className="page grid gap-8 py-10 text-[14px] md:grid-cols-[1.4fr_1fr_1fr]">
          <div className="flex flex-col gap-2">
            <Logo className="text-[18px] font-bold" />
            <p className="max-w-[44ch] leading-[1.9] text-[var(--fg-secondary)]">
              یاد بگیر و رشد کن.
            </p>
          </div>
          <nav aria-label="مسیرها" className="flex flex-col gap-2">
            <span className="font-semibold">مسیرها</span>
            <Link
              href="/content"
              className="text-[var(--fg-secondary)] hover:text-[var(--fg-brand)]"
            >
              مطالب
            </Link>
            <Link
              href="/intake"
              className="text-[var(--fg-secondary)] hover:text-[var(--fg-brand)]"
            >
              ثبت درخواست
            </Link>
            <Link
              href="/collaborate"
              className="text-[var(--fg-secondary)] hover:text-[var(--fg-brand)]"
            >
              همکاری با ما
            </Link>
          </nav>
          <nav aria-label="سامانه" className="flex flex-col gap-2">
            <span className="font-semibold">سامانه</span>
            <Link href="/help" className="text-[var(--fg-secondary)] hover:text-[var(--fg-brand)]">
              راهنما
            </Link>
            <Link
              href="/credits"
              className="text-[var(--fg-secondary)] hover:text-[var(--fg-brand)]"
            >
              منبع عکس‌ها
            </Link>
            <Link href="/login" className="text-[var(--fg-secondary)] hover:text-[var(--fg-brand)]">
              ورود و ثبت‌نام
            </Link>
          </nav>
        </div>
      </footer>
    </div>
  );
}
