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

const OPERATIONS = ['ADMIN', 'SUPPORT'];
const ADMIN_ONLY = ['ADMIN'];
const COURSES = ['ADMIN', 'COORDINATOR'];

const LINKS: { href: string; label: string; roles: string[] }[] = [
  { href: '/admin', label: 'شاخص‌های کلان', roles: OPERATIONS },
  { href: '/admin/courses', label: 'درس‌ها و ارائه‌ها', roles: COURSES },
  { href: '/admin/users', label: 'کاربران و نقش‌ها', roles: OPERATIONS },
  { href: '/admin/audit', label: 'لاگ حسابرسی', roles: OPERATIONS },
  { href: '/admin/subscriptions', label: 'اشتراک‌ها', roles: OPERATIONS },
  { href: '/admin/notifications', label: 'صف ارسال و الگوها', roles: OPERATIONS },
  { href: '/admin/point-rules', label: 'قواعد امتیاز', roles: ADMIN_ONLY },
  { href: '/admin/certificates', label: 'گواهی‌ها', roles: ADMIN_ONLY },
];

function linkFor(pathname: string) {
  return pathname === '/admin'
    ? LINKS[0]
    : LINKS.filter((link) => link.href !== '/admin' && pathname.startsWith(link.href))[0];
}

export function AdminShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { session, loading } = useSession();
  const roles = session?.user.roles ?? [];

  if (loading) return <SkeletonCard label="در حال بارگذاری پنل مدیریت" />;
  if (!canSeeAdmin(roles)) {
    return (
      <EmptyState
        as="h1"
        title="این بخش برای مدیر، مدیر آموزشی و پشتیبانی است"
        description="اگر باید به پنل مدیریت دسترسی داشته باشی، از مدیر سامانه بخواه نقش «پشتیبانی»، «مدیر آموزشی» یا «مدیر سامانه» را به حسابت بدهد. پس از اعطای نقش، یک بار خارج و دوباره وارد شو."
        action={
          <Link href="/dashboard" className="text-[14px] font-medium text-[var(--fg-brand)]">
            بازگشت به داشبورد
          </Link>
        }
      />
    );
  }
  const visible = LINKS.filter((link) => link.roles.some((role) => roles.includes(role)));
  const here = linkFor(pathname);
  // صفحه‌ای که نقش بیننده به آن نمی‌رسد: توضیح و راه، نه ۴۰۳ خام (§3.8).
  const blocked = here && !visible.includes(here);

  return (
    <div className="flex flex-col gap-6 lg:flex-row lg:items-start">
      <nav
        aria-label="ناوبری مدیریت"
        className="flex shrink-0 gap-1 overflow-x-auto lg:sticky lg:top-6 lg:w-52 lg:flex-col"
      >
        {visible.map((link) => {
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
      <div className="min-w-0 flex-1">
        {blocked ? (
          <EmptyState
            as="h1"
            title="این بخش با نقش تو باز نیست"
            description="از فهرست کنار، بخشی را که به آن دسترسی داری باز کن."
            action={
              visible[0] && (
                <Link
                  href={visible[0].href}
                  className="text-[14px] font-medium text-[var(--fg-brand)]"
                >
                  {visible[0].label}
                </Link>
              )
            }
          />
        ) : (
          children
        )}
      </div>
    </div>
  );
}
