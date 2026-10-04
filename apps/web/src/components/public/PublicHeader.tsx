'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';

import { Logo } from '@/components/domain/Logo';
import { readSession } from '@/lib/auth/session';

/**
 * هدر ناحیهٔ عمومی — §10.10.
 *
 * ناوبری عمومی فقط سه مورد آموزشی دارد؛ مسیر درخواست و همکاری در پایین صفحه است. کاربر واردشده به‌جای «ورود»
 * «داشبورد» می‌بیند؛ نشست در `sessionStorage` است، پس این بخش کلاینتی است.
 */
const NAV = [
  { href: '/content', label: 'مطالب' },
  { href: '/research', label: 'پژوهش' },
  { href: '/projects', label: 'پروژه‌ها' },
] as const;

export function PublicHeader() {
  const [signedIn, setSignedIn] = useState(false);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    setSignedIn(readSession() !== null);
  }, []);

  return (
    <header className="bg-[var(--bg-surface)]/85 sticky top-0 z-40 border-b border-[var(--border-subtle)] backdrop-blur-md">
      <div className="page flex h-16 items-center justify-between gap-4">
        <div className="flex items-center gap-8">
          <Link href="/" className="text-[18px] font-bold">
            <Logo />
          </Link>
          <nav aria-label="ناوبری عمومی" className="hidden items-center gap-1 lg:flex">
            {NAV.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className="rounded-[var(--radius-md)] px-3 py-2 text-[14px] font-medium text-[var(--fg-secondary)] hover:bg-[var(--bg-sunken)] hover:text-[var(--fg-primary)]"
              >
                {item.label}
              </Link>
            ))}
          </nav>
        </div>
        <div className="flex items-center gap-2">
          <Link
            href={signedIn ? '/dashboard' : '/login'}
            className="inline-flex h-10 items-center rounded-[var(--radius-md)] bg-[var(--brand-600)] px-4 text-[14px] font-semibold text-[var(--fg-on-brand)] hover:bg-[var(--brand-700)]"
          >
            {signedIn ? 'داشبورد' : 'ورود'}
          </Link>
          <button
            type="button"
            aria-expanded={open}
            aria-controls="public-menu"
            aria-label="منو"
            onClick={() => setOpen((value) => !value)}
            className="inline-flex size-10 items-center justify-center rounded-[var(--radius-md)] border border-[var(--border-default)] lg:hidden"
          >
            <span aria-hidden="true">{open ? '✕' : '☰'}</span>
          </button>
        </div>
      </div>
      {open && (
        <nav
          id="public-menu"
          aria-label="منوی موبایل"
          className="border-t border-[var(--border-subtle)] bg-[var(--bg-surface)] lg:hidden"
        >
          <ul className="page flex flex-col py-2">
            {NAV.map((item) => (
              <li key={item.href}>
                <Link
                  href={item.href}
                  onClick={() => setOpen(false)}
                  className="flex h-12 items-center text-[15px] font-medium"
                >
                  {item.label}
                </Link>
              </li>
            ))}
          </ul>
        </nav>
      )}
    </header>
  );
}
