/**
 * نگهداری نشست سمت کلاینت.
 *
 * تصمیم آگاهانه: توکن در `sessionStorage` می‌ماند، نه `localStorage`.
 * دانشجو معمولاً از رایانهٔ مشترک سایت دانشگاه استفاده می‌کند؛ بستن
 * مرورگر باید نشست را ببندد.
 *
 * `refresh_token` عمر ۳۰ روزه دارد ولی همچنان در همین حافظه است — تا
 * وقتی کوکی `HttpOnly` اضافه نشده، نگه‌داشتن آن در `localStorage` فقط
 * پنجرهٔ سرقت XSS را بازتر می‌کند بدون اینکه امنیت بیشتری بدهد.
 */

import type { AuthUser, OnboardingState } from '@/lib/api/auth';

const ACCESS_KEY = 'silp.access_token';
const REFRESH_KEY = 'silp.refresh_token';
const USER_KEY = 'silp.user';

function storage(): Storage | null {
  // در رندر سمت سرور، هیچ حافظه‌ای وجود ندارد.
  if (typeof window === 'undefined') return null;
  try {
    return window.sessionStorage;
  } catch {
    // حالت مرور خصوصی در بعضی مرورگرها دسترسی را رد می‌کند.
    return null;
  }
}

export interface StoredSession {
  accessToken: string;
  refreshToken: string;
  user: AuthUser;
}

export function saveSession(session: StoredSession): void {
  const store = storage();
  if (!store) return;
  try {
    store.setItem(ACCESS_KEY, session.accessToken);
    store.setItem(REFRESH_KEY, session.refreshToken);
    store.setItem(USER_KEY, JSON.stringify(session.user));
  } catch {
    // سهمیهٔ حافظه پر است — نشست در همین تب زنده می‌ماند.
  }
}

export function readSession(): StoredSession | null {
  const store = storage();
  if (!store) return null;

  const accessToken = store.getItem(ACCESS_KEY);
  const refreshToken = store.getItem(REFRESH_KEY);
  const rawUser = store.getItem(USER_KEY);
  if (!accessToken || !refreshToken || !rawUser) return null;

  try {
    return { accessToken, refreshToken, user: JSON.parse(rawUser) as AuthUser };
  } catch {
    clearSession();
    return null;
  }
}

export function clearSession(): void {
  const store = storage();
  if (!store) return;
  for (const key of [ACCESS_KEY, REFRESH_KEY, USER_KEY]) {
    store.removeItem(key);
  }
}

/**
 * مقصد پس از ورود — §7.1.
 *
 * تصمیم با سرور است (`onboarding_state`)، نه با کلاینت؛ این تابع فقط
 * آن تصمیم را به مسیر ترجمه می‌کند.
 */
export function routeForOnboarding(state: OnboardingState): string {
  switch (state) {
    case 'BASIC_INFO_REQUIRED':
      return '/onboarding/basic';
    case 'SURVEY_REQUIRED':
      return '/onboarding/survey/1';
    case 'SURVEY_INCOMPLETE':
    case 'COMPLETE':
      return '/dashboard';
  }
}
