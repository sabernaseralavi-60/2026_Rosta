'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import type { ReactNode } from 'react';

import { EmptyState } from '@/components/ui/EmptyState';
import { SkeletonCard } from '@/components/ui/Skeleton';
import { canSeeAdmin } from '@/lib/api/admin';
import { useSession } from '@/lib/auth/use-session';
import { cn } from '@/lib/cn';

/**
 * پوستهٔ ناحیهٔ مدیریت — §3.6، M7-12.
 *
 * پیوندها بر اساس نقش ذخیره‌شده در نشست نمایش داده می‌شوند؛ سرور هر مسیر
 * را جداگانه می‌سنجد، پس پنهان کردن پیوند فقط برای آرامش چشم است، نه
 * امنیت. کاربری که نقش ندارد «بدون دسترسی» می‌بیند با توضیح، نه ۴۰۳ خام
 * (§3.8).
 */

const LINKS: { href: string; label: string; adminOnly?: boolean }[] = [
  { href: '/admin', label: 'شاخص‌های کلان' },
  { href: '/admin/users', label: 'کاربران و نقش‌ها' },
  { href: '/admin/audit', label: 'لاگ حسابرسی' },
  { href: '/admin/subscriptions', label: 'اشتراک‌ها' },
  { href: '/admin/notifications', label: 'صف ارسال و الگوها' },
  { href: '/admin/point-rules', label: 'قواعد امتیاز', adminOnly: true },
  { href: '/admin/certificates', label: 'گواهی‌ها', adminOnly: true },
];

export function AdminShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { session, loading } = useSession();
  const roles = session?.user.roles ?? [];

  if (loading) return <SkeletonCard label="در حال بارگذاری پنل مدیریت" />;
  if (!canSeeAdmin(roles)) {
    return (
      <EmptyState
        as="h1"
        title="این بخش برای مدیر و پشتیبانی است"
        description="اگر باید به پنل مدیریت دسترسی داشته باشی، از مدیر سامانه بخواه نقش «پشتیبانی» یا «مدیر سامانه» را به حسابت بدهد. پس از اعطای نقش، یک بار خارج و دوباره وارد شو."
        action={
          <Link href="/dashboard" className="text-[14px] font-medium text-[var(--fg-brand)]">
            بازگشت به داشبورد
          </Link>
        }
      />
    );
  }
  const isAdmin = roles.includes('ADMIN');

  return (
    <div className="flex flex-col gap-6 lg:flex-row lg:items-start">
      <nav
        aria-label="ناوبری مدیریت"
        className="flex shrink-0 gap-1 overflow-x-auto lg:sticky lg:top-6 lg:w-52 lg:flex-col"
      >
        {LINKS.filter((link) => isAdmin || !link.adminOnly).map((link) => {
          const current =
            link.href === '/admin' ? pathname === '/admin' : pathname.startsWith(link.href);
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
