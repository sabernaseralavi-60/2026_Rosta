import { beforeEach, describe, expect, it } from 'vitest';

import type { AuthUser } from '@/lib/api/auth';
import { clearSession, readSession, routeForOnboarding, saveSession } from '@/lib/auth/session';

const user: AuthUser = {
  id: '018f0000-0000-7000-8000-000000000001',
  display_name: 'مریم کریمی',
  username: 'marim-karimi',
  roles: ['STUDENT'],
  onboarding_state: 'SURVEY_INCOMPLETE',
};

describe('نشست', () => {
  beforeEach(() => {
    window.sessionStorage.clear();
  });

  it('نشست ذخیره‌شده را برمی‌گرداند', () => {
    saveSession({ accessToken: 'a', refreshToken: 'r', user });
    expect(readSession()).toEqual({ accessToken: 'a', refreshToken: 'r', user });
  });

  it('بدون نشست، null می‌دهد', () => {
    expect(readSession()).toBeNull();
  });

  it('پاک کردن، همهٔ کلیدها را حذف می‌کند', () => {
    saveSession({ accessToken: 'a', refreshToken: 'r', user });
    clearSession();
    expect(readSession()).toBeNull();
  });

  it('دادهٔ خراب را پاک می‌کند به‌جای اینکه بشکند', () => {
    window.sessionStorage.setItem('silp.access_token', 'a');
    window.sessionStorage.setItem('silp.refresh_token', 'r');
    window.sessionStorage.setItem('silp.user', '{ نه JSON درست');
    expect(readSession()).toBeNull();
  });
});

describe('مقصد پس از ورود — §7.1', () => {
  it('هر حالت به مسیر درست نگاشت می‌شود', () => {
    expect(routeForOnboarding('BASIC_INFO_REQUIRED')).toBe('/onboarding/basic');
    expect(routeForOnboarding('SURVEY_REQUIRED')).toBe('/onboarding/survey/1');
    expect(routeForOnboarding('SURVEY_INCOMPLETE')).toBe('/dashboard');
    expect(routeForOnboarding('COMPLETE')).toBe('/dashboard');
  });
});
