'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import type { ReactNode } from 'react';

import { EmptyState } from '@/components/ui/EmptyState';
import { SkeletonCard } from '@/components/ui/Skeleton';
import { canSeeAdmin } from '@/lib/api/admin';
import { canSeeTeach } from '@/lib/api/teach';
import { useSession } from '@/lib/auth/use-session';
import { cn } from '@/lib/cn';

/**
 * پوستهٔ ناحیهٔ استاد — §3.5، ADR-0019.
 *
 * مثل پنل مدیریت: ناوبری فرعی کنار محتوا، و پیوندها بر اساس نقش نشست. سرور
 * هر مسیر را با قلمرو ارائه جداگانه می‌سنجد؛ کسی که نقش کادر آموزشی ندارد
 * توضیح می‌بیند، نه ۴۰۳ خام (§3.8).
 */

const LINKS: { href: string; label: string; exact?: boolean }[] = [
  { href: '/teach', label: 'آنچه اقدام می‌خواهد', exact: true },
  { href: '/teach/offerings', label: 'ارائه‌های من' },
  { href: '/teach/quizzes', label: 'آزمون‌ها' },
  { href: '/teach/question-bank', label: 'بانک سؤال' },
];

export function TeachShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { session, loading } = useSession();
  const roles = session?.user.roles ?? [];

  if (loading) return <SkeletonCard label="در حال بارگذاری ناحیهٔ استاد" />;
  if (!canSeeTeach(roles) && !canSeeAdmin(roles)) {
    return (
      <EmptyState
        as="h1"
        title="این بخش برای استاد و دستیار آموزشی است"
        description="اگر درسی را تدریس یا در آن دستیاری می‌کنی، از مدیر سامانه بخواه تو را استاد یا دستیار همان ارائه کند. پس از آن یک بار خارج و دوباره وارد شو."
        action={
          <Link href="/courses" className="text-[14px] font-medium text-[var(--fg-brand)]">
            رفتن به دروس من
          </Link>
        }
      />
    );
  }

  return (
    <div className="flex flex-col gap-6 lg:flex-row lg:items-start">
      <nav
        aria-label="ناوبری تدریس"
        className="flex shrink-0 gap-1 overflow-x-auto lg:sticky lg:top-6 lg:w-52 lg:flex-col"
      >
        {LINKS.map((link) => {
          const current = link.exact ? pathname === link.href : pathname.startsWith(link.href);
          return (
            <Link
              key={link.href}
              href={link.href}
              aria-current={current ? 'page' : undefined}
              className={cn(
                'whitespace-nowrap rounded-[var(--radius-sm)] px-3 py-2 text-[14px]',
                current
                  ? 'bg-[var(--brand-50)] font-semibold text-[var(--fg-brand)]'
                  : 'text-[var(--fg-secondary)] hover:bg-[var(--bg-sunken)]',
              )}
            >
              {link.label}
            </Link>
          );
        })}
      </nav>
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  );
}
