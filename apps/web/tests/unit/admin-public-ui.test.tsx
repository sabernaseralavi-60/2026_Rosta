import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { isGuestBrowsable } from '@/components/domain/AppHeader';
import { PublicProfileBody } from '@/components/public/PublicProfileBody';
import { canSeeAdmin } from '@/lib/api/admin';
import type { AuthUser } from '@/lib/api/auth';
import type { PublicProfile, PublicStats } from '@/lib/api/public';
import { matchCommands, normalizeFa } from '@/lib/api/search';
import {
  IMPERSONATION_REFRESH,
  readImpersonation,
  readSession,
  saveSession,
  startImpersonation,
  stopImpersonation,
} from '@/lib/auth/session';
import { formatCompact } from '@/lib/format/digits';
import { statTiles } from '@/lib/public/home';

const admin: AuthUser = {
  id: 'admin-1',
  display_name: 'مدیر',
  username: 'modir',
  roles: ['STUDENT', 'ADMIN'],
  onboarding_state: 'COMPLETE',
};

const zeroStats: PublicStats = {
  students: 0,
  active_projects: 0,
  completed_projects: 0,
  completed_milestones: 0,
  research_outputs: 0,
  verified_revenue_rial: 0,
  active_courses: 0,
  certificates: 0,
};

describe('صفحهٔ اصلی — آمار زنده (§10.10)', () => {
  it('صفر نشان داده نمی‌شود و «درس فعال» جای مقالهٔ صفر را می‌گیرد', () => {
    const tiles = statTiles({ ...zeroStats, students: 214, active_courses: 4 });
    expect(tiles).toEqual([
      { value: '۲۱۴', label: 'دانشجو' },
      { value: '۴', label: 'درس فعال' },
    ]);
  });

  it('حداکثر چهار کاشی، به ترتیب اهمیت', () => {
    const tiles = statTiles({
      students: 214,
      active_projects: 38,
      completed_projects: 9,
      completed_milestones: 461,
      research_outputs: 12,
      verified_revenue_rial: 460_000_000,
      active_courses: 4,
      certificates: 30,
    });
    expect(tiles.map((t) => t.label)).toEqual([
      'دانشجو',
      'پروژهٔ فعال',
      'مقالهٔ راستی‌آزمایی‌شده',
      'ریال فروش تأییدشده',
    ]);
    expect(tiles[3]?.value).toBe('۴۶۰ میلیون');
  });

  it('عدد بزرگ کوتاه می‌شود', () => {
    expect(formatCompact(1_250_000_000)).toBe('۱٫۳ میلیارد');
    expect(formatCompact(850)).toBe('۸۵۰');
  });
});

describe('جستجوی سراسری ⌘K', () => {
  it('«ي» و «ك» عربی همان فارسی‌اند', () => {
    expect(normalizeFa('ثبت ايده')).toBe(normalizeFa('ثبت ایده'));
    expect(normalizeFa('كتابخانه')).toBe('کتابخانه');
  });

  it('دستور با واژهٔ کلیدی هم پیدا می‌شود', () => {
    expect(matchCommands('رزومه', ['STUDENT']).map((c) => c.id)).toEqual(['certificates']);
    expect(matchCommands('ايده', ['STUDENT']).map((c) => c.id)).toContain('idea-new');
  });

  it('دستورهای مدیریت فقط برای مدیر و پشتیبانی', () => {
    expect(matchCommands('حسابرسی', ['STUDENT'])).toEqual([]);
    expect(matchCommands('حسابرسی', ['SUPPORT']).map((c) => c.id)).toEqual(['admin-audit']);
    expect(canSeeAdmin(['STUDENT', 'MENTOR'])).toBe(false);
  });
});

describe('مهمان در ویترین', () => {
  it('فهرست‌ها باز، فرم ساخت و فضای کاری بسته', () => {
    expect(isGuestBrowsable('/projects')).toBe(true);
    expect(isGuestBrowsable('/projects/018f')).toBe(true);
    expect(isGuestBrowsable('/projects/new')).toBe(false);
    expect(isGuestBrowsable('/projects/018f/workspace')).toBe(false);
    expect(isGuestBrowsable('/dashboard')).toBe(false);
    expect(isGuestBrowsable('/admin')).toBe(false);
  });
});

describe('جعل هویت — §6.5', () => {
  beforeEach(() => window.sessionStorage.clear());

  it('نشست پشتیبان کنار می‌رود و با «خروج» برمی‌گردد', () => {
    saveSession({ accessToken: 'admin-token', refreshToken: 'admin-refresh', user: admin });
    startImpersonation(
      {
        accessToken: 'imp-token',
        user: { ...admin, id: 'student-1', roles: ['STUDENT'], display_name: 'سارا' },
      },
      {
        userId: 'student-1',
        userName: 'سارا',
        expiresAt: '2026-09-23T10:30:00Z',
        returnTo: '/admin/users/student-1',
      },
    );
    expect(readSession()?.accessToken).toBe('imp-token');
    expect(readSession()?.refreshToken).toBe(IMPERSONATION_REFRESH);
    expect(readImpersonation()?.userName).toBe('سارا');

    const original = stopImpersonation();
    expect(original?.accessToken).toBe('admin-token');
    expect(readSession()?.refreshToken).toBe('admin-refresh');
    expect(readImpersonation()).toBeNull();
  });
});

describe('نیمرخ عمومی', () => {
  const profile: PublicProfile = {
    username: 'zahra-rostami',
    name: 'زهرا رستمی',
    bio: null,
    is_owner: false,
    is_public: true,
    sections: {
      university: true,
      skills: true,
      projects: false,
      certificates: true,
      research: true,
      badges: true,
      points: false,
    },
    university: 'دانشگاه شهید باهنر کرمان',
    field_of_study: 'مهندسی عمران',
    degree_level_fa: 'کارشناسی',
    skills: [{ title_fa: 'Python', level: 5, verified: true }],
    projects: [],
    certificates: [
      {
        public_code: '7KQ2-MX9P',
        kind: 'PROJECT',
        title_fa: 'تکمیل پروژهٔ «خرما»',
        issued_at: '2026-09-20T08:00:00Z',
      },
    ],
    research_level: null,
    research_level_fa: null,
    research_outputs: [],
    badges: [],
    points: null,
    member_since: '2026-01-01T00:00:00Z',
  };

  it('بخش‌ها و پیوند راستی‌آزمایی را نشان می‌دهد، بخش خاموش را نه', () => {
    render(<PublicProfileBody profile={profile} />);
    expect(screen.getByRole('heading', { name: 'زهرا رستمی' })).toBeInTheDocument();
    expect(screen.getByText(/Python/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /7KQ2-MX9P/ })).toHaveAttribute(
      'href',
      '/verify/7KQ2-MX9P',
    );
    expect(screen.queryByRole('heading', { name: 'پروژه‌های تکمیل‌شده' })).toBeNull();
    expect(screen.queryByText(/امتیاز/)).toBeNull();
  });
});
