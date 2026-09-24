'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';

import { errorText } from '@/components/admin/common';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { EmptyState } from '@/components/ui/EmptyState';
import { SkeletonCard } from '@/components/ui/Skeleton';
import { ApiError } from '@/lib/api/client';
import {
  fetchTeachOffering,
  type OfferingPermissions,
  STAFF_ROLE_LABELS,
  type TeachOfferingDetail,
} from '@/lib/api/teach';
import { useSession } from '@/lib/auth/use-session';
import { cn } from '@/lib/cn';
import { toPersianDigits } from '@/lib/format/digits';

import { OfferingStatusBadge } from './common';

/**
 * قاب یک ارائه — سرصفحه و زبانه‌ها، و ارائه یک بار برای همهٔ زبانه‌ها.
 *
 * زبانه‌ای که بیننده مجوزش را ندارد اصلاً نشان داده نمی‌شود (دستیار دفتر
 * نمره و تنظیمات را نمی‌بیند). سرور همان را جدا می‌سنجد.
 */

interface OfferingContextValue {
  offering: TeachOfferingDetail;
  token: string;
  reload: () => Promise<void>;
  replace: (offering: TeachOfferingDetail) => void;
}

const OfferingContext = createContext<OfferingContextValue | null>(null);

export function useOffering(): OfferingContextValue {
  const value = useContext(OfferingContext);
  if (!value) throw new Error('useOffering بیرون از OfferingFrame');
  return value;
}

const TABS: { path: string; label: string; needs?: keyof OfferingPermissions }[] = [
  { path: '', label: 'هفته‌ها' },
  { path: '/students', label: 'دانشجویان' },
  { path: '/attendance', label: 'حضور و غیاب', needs: 'record_attendance' },
  { path: '/grades', label: 'دفتر نمره', needs: 'manage' },
  { path: '/quizzes', label: 'آزمون‌ها' },
  { path: '/announcements', label: 'اعلان‌ها' },
  { path: '/settings', label: 'تنظیمات', needs: 'manage' },
];

export function OfferingFrame({
  offeringId,
  children,
}: {
  offeringId: string;
  children: ReactNode;
}) {
  const pathname = usePathname();
  const { accessToken } = useSession();
  const [offering, setOffering] = useState<TeachOfferingDetail | null>(null);
  const [error, setError] = useState<{ text: string; status: number | null } | null>(null);

  const reload = useCallback(async () => {
    if (!accessToken) return;
    try {
      setOffering(await fetchTeachOffering(offeringId, accessToken));
      setError(null);
    } catch (cause) {
      setError({
        text: errorText(cause),
        status: cause instanceof ApiError ? cause.status : null,
      });
    }
  }, [accessToken, offeringId]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const value = useMemo(
    () =>
      offering && accessToken
        ? { offering, token: accessToken, reload, replace: setOffering }
        : null,
    [offering, accessToken, reload],
  );

  if (error && !offering) {
    if (error.status === 403 || error.status === 404) {
      return (
        <EmptyState
          as="h1"
          title={error.status === 404 ? 'این ارائه پیدا نشد' : 'این ارائه در دسترس تو نیست'}
          description="فقط استاد و دستیار همین ارائه آن را می‌بینند. اگر فکر می‌کنی باید دسترسی داشته باشی، از مدیر سامانه بخواه تو را به این ارائه اضافه کند."
          action={
            <Link
              href="/teach/offerings"
              className="text-[14px] font-medium text-[var(--fg-brand)]"
            >
              بازگشت به ارائه‌های من
            </Link>
          }
        />
      );
    }
    return (
      <EmptyState
        as="h1"
        title="ارائه بارگذاری نشد"
        description={error.text}
        action={<Button onClick={() => void reload()}>تلاش دوباره</Button>}
      />
    );
  }
  if (!value) return <SkeletonCard label="در حال بارگذاری ارائه" />;

  const base = `/teach/offerings/${offeringId}`;
  const tabs = TABS.filter((tab) => !tab.needs || value.offering.permissions[tab.needs]);

  return (
    <OfferingContext.Provider value={value}>
      <div className="flex flex-col gap-6">
        <header className="flex flex-col gap-2">
          <nav aria-label="مسیر" className="text-[13px] text-[var(--fg-tertiary)]">
            <Link href="/teach/offerings" className="hover:text-[var(--fg-brand)]">
              ارائه‌های من
            </Link>{' '}
            ‹ {value.offering.course_title_fa}
          </nav>
          <div className="flex flex-wrap items-center gap-3">
            <h1>{value.offering.course_title_fa}</h1>
            <OfferingStatusBadge status={value.offering.status} />
          </div>
          <p className="text-[13.5px] text-[var(--fg-secondary)]">
            {value.offering.term_title_fa} · {toPersianDigits(value.offering.active_students)}{' '}
            دانشجوی فعال
            {value.offering.staff_role && (
              <> · نقش تو: {STAFF_ROLE_LABELS[value.offering.staff_role]}</>
            )}
          </p>
        </header>
        <nav
          aria-label="بخش‌های ارائه"
          className="flex gap-1 overflow-x-auto border-b border-[var(--border-subtle)]"
        >
          {tabs.map((tab) => {
            const href = `${base}${tab.path}`;
            const current =
              tab.path === ''
                ? pathname === base || pathname.startsWith(`${base}/weeks`)
                : pathname.startsWith(href);
            return (
              <Link
                key={tab.path}
                href={href}
                aria-current={current ? 'page' : undefined}
                className={cn(
                  '-mb-px whitespace-nowrap border-b-2 px-3 py-2 text-[14px]',
                  current
                    ? 'border-[var(--brand-600)] font-semibold text-[var(--fg-brand)]'
                    : 'border-transparent text-[var(--fg-secondary)] hover:text-[var(--fg-primary)]',
                )}
              >
                {tab.label}
                {tab.path === '/students' && value.offering.pending_enrollments > 0 && (
                  <Badge tone="warning" className="ms-1.5">
                    {toPersianDigits(value.offering.pending_enrollments)}
                    <span className="sr-only"> درخواست در انتظار</span>
                  </Badge>
                )}
              </Link>
            );
          })}
        </nav>
        {children}
      </div>
    </OfferingContext.Provider>
  );
}
