'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';

import { CommandPaletteTrigger } from '@/components/domain/CommandPaletteTrigger';
import { ImpersonationBanner } from '@/components/domain/ImpersonationBanner';
import { Logo } from '@/components/domain/Logo';
import { NotificationBell } from '@/components/domain/NotificationBell';
import { PointsBadge } from '@/components/domain/PointsBadge';
import { Button } from '@/components/ui/Button';
import { adminHome, canSeeAdmin } from '@/lib/api/admin';
import { canSeeTeach } from '@/lib/api/teach';
import { logout } from '@/lib/api/auth';
import { releasePush } from '@/lib/push/client';
import {
  clearSession,
  IMPERSONATION_REFRESH,
  readSession,
  stopImpersonation,
} from '@/lib/auth/session';

/**
 * هدر اپلیکیشن — §3.7.
 *
 * `[لوگو] [جستجوی سراسری ⌘K] … [امتیاز و سطح] [زنگوله] [آواتار]`. ناوبری
 * عمدی کوتاه است: مقصدهایی که دانشجو هر روز می‌خواهد. پیوند «تدریس» فقط
 * برای کادر آموزشی و «مدیریت» فقط برای مدیر و پشتیبانی دیده می‌شود؛ سرور
 * هر مسیر را جداگانه می‌سنجد.
 *
 * مهمان در صفحه‌های ویترین (پروژه‌ها، ایده‌ها، شهر هوشمند، پژوهش) به
 * ورود فرستاده نمی‌شود — دکمهٔ «پروژه‌ها را ببین» صفحهٔ اصلی باید به خود
 * پروژه‌ها برسد، نه به فرم ورود (§3.10).
 */

const NAV: { href: string; label: string }[] = [
  { href: '/dashboard', label: 'داشبورد' },
  { href: '/courses', label: 'دروس من' },
  { href: '/library', label: 'کتابخانه' },
  { href: '/projects', label: 'پروژه‌ها' },
  { href: '/research', label: 'پژوهش' },
  { href: '/city', label: 'شهر هوشمند' },
  { href: '/teams/openings', label: 'تیم' },
  { href: '/ideas', label: 'ایده‌ها' },
  { href: '/ventures', label: 'کسب‌وکار' },
  { href: '/leaderboard', label: 'رتبه‌بندی' },
];

/** مسیرهایی که مهمان هم می‌بیند — API فهرستشان احراز هویت نمی‌خواهد. */
const GUEST_BROWSABLE = ['/projects', '/ideas', '/city', '/research'];

export function isGuestBrowsable(pathname: string): boolean {
  return GUEST_BROWSABLE.some(
    (prefix) =>
      (pathname === prefix || pathname.startsWith(`${prefix}/`)) &&
      !pathname.endsWith('/new') &&
      !pathname.includes('/workspace'),
  );
}

export function AppHeader() {
  const router = useRouter();
  const pathname = usePathname();
  const [displayName, setDisplayName] = useState<string | null>(null);
  const [roles, setRoles] = useState<string[]>([]);
  const [guest, setGuest] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    const session = readSession();
    if (!session) {
      if (isGuestBrowsable(pathname)) {
        setGuest(true);
        return;
      }
      router.replace('/login');
      return;
    }
    setGuest(false);
    setDisplayName(session.user.display_name ?? session.user.username);
    setRoles(session.user.roles ?? []);
  }, [router, pathname]);

  // مسیر عوض شود، منوی موبایل بسته بماند — وگرنه پشت صفحهٔ تازه می‌ماند.
  useEffect(() => {
    setMenuOpen(false);
  }, [pathname]);

  async function handleLogout() {
    const session = readSession();
    if (session?.refreshToken === IMPERSONATION_REFRESH) {
      // خروج در حالت جعل هویت یعنی بازگشت به نشست پشتیبان، نه بستن آن.
      stopImpersonation();
      window.location.assign('/admin/users');
      return;
    }
    if (session) {
      // اشتراک Push این مرورگر با کاربر نمی‌ماند (ADR-0029)؛ رایانهٔ مشترک.
      await releasePush(session.accessToken).catch(() => undefined);
      // خروج سمت سرور ممکن است شکست بخورد؛ نشست محلی در هر حال پاک می‌شود.
      await logout(session.refreshToken).catch(() => undefined);
    }
    clearSession();
    router.replace('/login');
  }

  const extraLinks = [
    canSeeTeach(roles) && { href: '/teach', label: 'تدریس', accent: true },
    canSeeAdmin(roles) && { href: adminHome(roles), label: 'مدیریت', accent: true },
  ].filter((link): link is { href: string; label: string; accent: boolean } => Boolean(link));

  return (
    <>
      <ImpersonationBanner />
      <header className="border-b border-[var(--border-subtle)] bg-[var(--bg-surface)]">
        <div className="page flex h-16 items-center justify-between gap-4">
          <div className="flex min-w-0 items-center gap-4">
            <Link href={guest ? '/' : '/dashboard'} className="text-[17px] font-bold">
              <Logo />
            </Link>
            {!guest && <CommandPaletteTrigger />}
            <nav aria-label="ناوبری اصلی" className="hidden items-center gap-3 xl:flex">
              {NAV.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  aria-current={pathname.startsWith(item.href) ? 'page' : undefined}
                  className="whitespace-nowrap text-[13.5px] text-[var(--fg-secondary)] transition-colors hover:text-[var(--fg-brand)] aria-[current=page]:font-semibold aria-[current=page]:text-[var(--fg-brand)]"
                >
                  {item.label}
                </Link>
              ))}
              {extraLinks.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  aria-current={pathname.startsWith(item.href) ? 'page' : undefined}
                  className="whitespace-nowrap text-[13.5px] font-medium text-[var(--fg-accent)] hover:underline"
                >
                  {item.label}
                </Link>
              ))}
            </nav>
          </div>

          <div className="flex shrink-0 items-center gap-3">
            {guest ? (
              <Button asChild size="sm">
                <Link href="/login">ورود یا ثبت‌نام</Link>
              </Button>
            ) : (
              <>
                <PointsBadge />
                <NotificationBell />
                {displayName && (
                  <Link
                    href="/me/public-profile"
                    className="hidden text-[13.5px] text-[var(--fg-secondary)] hover:text-[var(--fg-brand)] 2xl:inline"
                  >
                    {displayName}
                  </Link>
                )}
                <Button variant="ghost" size="sm" onClick={handleLogout}>
                  خروج
                </Button>
              </>
            )}
            <button
              type="button"
              aria-expanded={menuOpen}
              aria-controls="app-menu"
              aria-label={menuOpen ? 'بستن منو' : 'باز کردن منو'}
              onClick={() => setMenuOpen((value) => !value)}
              className="inline-flex size-10 shrink-0 items-center justify-center rounded-[var(--radius-md)] border border-[var(--border-default)] xl:hidden"
            >
              <span aria-hidden="true">{menuOpen ? '✕' : '☰'}</span>
            </button>
          </div>
        </div>
        {menuOpen && (
          <nav
            id="app-menu"
            aria-label="منوی ناوبری"
            className="border-t border-[var(--border-subtle)] bg-[var(--bg-surface)] xl:hidden"
          >
            <ul className="page flex flex-col py-2">
              {[...NAV, ...extraLinks].map((item) => (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    aria-current={pathname.startsWith(item.href) ? 'page' : undefined}
                    className="flex h-12 items-center text-[15px] font-medium text-[var(--fg-primary)] aria-[current=page]:font-semibold aria-[current=page]:text-[var(--fg-brand)]"
                  >
                    {item.label}
                  </Link>
                </li>
              ))}
            </ul>
          </nav>
        )}
      </header>
    </>
  );
}
