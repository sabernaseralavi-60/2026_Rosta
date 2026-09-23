'use client';

import { useEffect, useState } from 'react';

import { endImpersonation } from '@/lib/api/admin';
import { type ImpersonationState, readImpersonation, stopImpersonation } from '@/lib/auth/session';
import { formatDateTime } from '@/lib/format/date';

/**
 * بنر قرمز دائمی جعل هویت — §6.5، FR-ADM-01.
 *
 * «شما در حال مشاهده به‌عنوان {نام} هستید — خروج». تا نشست پشتیبان کنار
 * گذاشته شده، در بالای همهٔ صفحه‌های پوسته می‌ماند و بسته نمی‌شود؛ تنها
 * راه رفتنش «خروج» است. خروج با **توکن خود پشتیبان** ثبت می‌شود — توکن
 * جعل هویت فقط خواندنی است و `POST` نمی‌پذیرد.
 */
export function ImpersonationBanner() {
  const [state, setState] = useState<ImpersonationState | null>(null);
  const [leaving, setLeaving] = useState(false);

  useEffect(() => {
    setState(readImpersonation());
  }, []);

  if (!state) return null;

  async function exit() {
    if (!state) return;
    setLeaving(true);
    const original = stopImpersonation();
    if (original) {
      // ثبت «پایان» نباید خروج را نگه دارد؛ اگر نرسید، شروع و تک‌تک
      // درخواست‌ها در لاگ هست.
      await endImpersonation(original.accessToken, state.userId).catch(() => undefined);
    }
    // بارگذاری کامل، نه `router.push`: همهٔ Providerها (امتیاز، اعلان SSE)
    // باید با نشست پشتیبان از نو ساخته شوند.
    window.location.assign(original ? state.returnTo : '/login');
  }

  return (
    <div role="status" className="sticky top-0 z-30 bg-[var(--danger-600)] text-[var(--neutral-0)]">
      <div className="page flex min-h-11 flex-wrap items-center justify-between gap-x-4 gap-y-1 py-2 text-[13.5px]">
        <p>
          شما در حال مشاهده به‌عنوان <strong>{state.userName ?? 'کاربر'}</strong> هستید — فقط
          خواندنی؛ هر صفحه‌ای که باز کنید در لاگ حسابرسی ثبت می‌شود. پایان خودکار:{' '}
          {formatDateTime(state.expiresAt)}
        </p>
        <button
          type="button"
          onClick={exit}
          disabled={leaving}
          className="rounded-[var(--radius-sm)] border border-white/70 px-3 py-1 font-semibold hover:bg-white/15 disabled:opacity-60"
        >
          {leaving ? 'در حال خروج…' : 'خروج'}
        </button>
      </div>
    </div>
  );
}
