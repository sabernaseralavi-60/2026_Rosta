'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';

import { readSession } from '@/lib/auth/session';

/**
 * هدر شفاف ناحیهٔ عمومی — §10.10.
 *
 * `[ورود]  پروژه‌ها  دروس  …  [SILP]`. کاربری که وارد است به‌جای «ورود»
 * «داشبورد» می‌بیند؛ نشست در `sessionStorage` است و سرور آن را نمی‌بیند،
 * پس این تنها بخش کلاینتیِ صفحهٔ عمومی است.
 */
export function PublicHeader() {
  const [signedIn, setSignedIn] = useState(false);

  useEffect(() => {
    setSignedIn(readSession() !== null);
  }, []);

  return (
    <header className="bg-transparent">
      <div className="page flex h-16 items-center justify-between gap-4">
        <div className="flex items-center gap-6">
          <Link href="/" className="text-[18px] font-bold text-[var(--brand-700)]">
            سیلپ
          </Link>
          <nav aria-label="ناوبری عمومی" className="hidden items-center gap-5 text-[14px] sm:flex">
            <Link
              href="/projects"
              className="text-[var(--fg-secondary)] hover:text-[var(--brand-700)]"
            >
              پروژه‌ها
            </Link>
            <Link
              href="/ideas"
              className="text-[var(--fg-secondary)] hover:text-[var(--brand-700)]"
            >
              ایده‌ها
            </Link>
            <Link
              href="/research"
              className="text-[var(--fg-secondary)] hover:text-[var(--brand-700)]"
            >
              مسیر پژوهش
            </Link>
            <Link href="/city" className="text-[var(--fg-secondary)] hover:text-[var(--brand-700)]">
              شهر هوشمند
            </Link>
          </nav>
        </div>
        <Link
          href={signedIn ? '/dashboard' : '/login'}
          className="rounded-[var(--radius-md)] border border-[var(--border-default)] px-4 py-2 text-[14px] font-medium hover:bg-[var(--bg-sunken)]"
        >
          {signedIn ? 'داشبورد' : 'ورود'}
        </Link>
      </div>
    </header>
  );
}
