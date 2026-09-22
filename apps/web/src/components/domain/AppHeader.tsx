'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';

import { Button } from '@/components/ui/Button';
import { logout } from '@/lib/api/auth';
import { clearSession, readSession } from '@/lib/auth/session';

/**
 * هدر اپلیکیشن — نسخهٔ M0.
 *
 * `PointsBadge`، مرکز اعلان و جستجوی سراسری در M5 تا M7 اضافه می‌شوند.
 */
export function AppHeader() {
  const router = useRouter();
  const [displayName, setDisplayName] = useState<string | null>(null);

  useEffect(() => {
    const session = readSession();
    if (!session) {
      router.replace('/login');
      return;
    }
    setDisplayName(session.user.display_name ?? session.user.username);
  }, [router]);

  async function handleLogout() {
    const session = readSession();
    if (session) {
      // خروج سمت سرور ممکن است شکست بخورد؛ نشست محلی در هر حال پاک می‌شود.
      await logout(session.refreshToken).catch(() => undefined);
    }
    clearSession();
    router.replace('/login');
  }

  return (
    <header className="border-b border-[var(--border-subtle)] bg-[var(--bg-surface)]">
      <div className="page flex h-16 items-center justify-between">
        <Link href="/dashboard" className="text-[17px] font-bold text-[var(--brand-700)]">
          سیلپ
        </Link>

        <div className="flex items-center gap-3">
          {displayName && (
            <span className="text-[13.5px] text-[var(--fg-secondary)]">{displayName}</span>
          )}
          <Button variant="ghost" size="sm" onClick={handleLogout}>
            خروج
          </Button>
        </div>
      </div>
    </header>
  );
}
