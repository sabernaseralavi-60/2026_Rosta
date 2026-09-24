import { readFileSync } from 'node:fs';

import AxeBuilder from '@axe-core/playwright';
import { type Browser, type Page, expect, test } from '@playwright/test';

import { type Role, SESSIONS_FILE, type StoredSession } from './global-setup';

/**
 * ممیزی دسترس‌پذیری صفحه‌های کلیدی — §10.8، M7-14.
 *
 * «axe-core در Playwright روی هر صفحهٔ کلیدی. شکست = شکست CI.» هر صفحه
 * در تم روشن و تیره سنجیده می‌شود: ممیزی کامل M7-14 نشان داد بیشتر خطاهای
 * کنتراست فقط در یکی از دو تم پیداست (`--brand-700` در تیره ۲٫۷ به ۱،
 * `--warning-600` در روشن ۳٫۲ به ۱).
 *
 * `best-practice` هم در برچسب‌هاست: ترتیب عنوان‌ها و نام یکتای نواحی
 * WCAG نیستند ولی صفحه‌خوان را گمراه می‌کنند و در همین ممیزی رفع شدند.
 */

const TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa', 'best-practice'];
const API = process.env.E2E_API_URL ?? 'http://localhost:8000/api/v1';

const GUEST_PAGES = [
  '/',
  '/login',
  '/verify',
  '/projects',
  '/ideas',
  '/research',
  '/research/topics',
  '/city',
  '/verify/ZZZZ-ZZZZ',
  '/help',
  '/help/student',
  '/help/instructor',
];

const STUDENT_PAGES = [
  '/dashboard',
  '/projects',
  '/projects/new',
  '/courses',
  '/library',
  '/leaderboard',
  '/ideas',
  '/ideas/new',
  '/ventures',
  '/research',
  '/research/topics',
  '/teams/find',
  '/teams/openings',
  '/notifications',
  '/pricing',
  '/me/points',
  '/me/badges',
  '/me/certificates',
  '/me/public-profile',
  '/me/settings',
  '/onboarding/survey/1',
];

const ADMIN_PAGES = ['/admin', '/admin/users', '/admin/audit', '/admin/point-rules'];

function sessions(): Record<Role, StoredSession> {
  return JSON.parse(readFileSync(SESSIONS_FILE, 'utf-8')) as Record<Role, StoredSession>;
}

async function openAs(
  browser: Browser,
  role: Role | null,
  colorScheme: 'light' | 'dark',
): Promise<Page> {
  const context = await browser.newContext({ colorScheme, locale: 'fa-IR' });
  if (role) {
    const session = sessions()[role];
    // فقط اگر نشستی نیست: اسکریپت در هر پیمایش اجرا می‌شود و نباید نشستی
    // را که خود برنامه عوض کرده (مثلاً جعل هویت) بازنویسی کند.
    await context.addInitScript((s: StoredSession) => {
      if (sessionStorage.getItem('silp.access_token')) return;
      sessionStorage.setItem('silp.access_token', s.access_token);
      sessionStorage.setItem('silp.refresh_token', s.refresh_token);
      sessionStorage.setItem('silp.user', JSON.stringify(s.user));
    }, session);
  }
  return context.newPage();
}

async function audit(page: Page, path: string): Promise<void> {
  await page.goto(path, { waitUntil: 'load' });
  // صفحه‌های `(app)` جریان SSE باز نگه می‌دارند و هرگز networkidle نمی‌شوند.
  await expect(page.locator('main h1, main [role="alert"]').first()).toBeVisible({
    timeout: 20_000,
  });
  // جشن نشان (M5) روی اولین صفحهٔ هر حساب باز می‌شود.
  await page.keyboard.press('Escape');
  const results = await new AxeBuilder({ page }).withTags(TAGS).analyze();
  const summary = results.violations.map(
    (v) => `${v.id} (${v.nodes.length}): ${v.nodes[0]?.target.join(' ')}`,
  );
  expect(summary, `${path}`).toEqual([]);
}

for (const scheme of ['light', 'dark'] as const) {
  test.describe(`دسترس‌پذیری — ${scheme === 'light' ? 'تم روشن' : 'تم تیره'}`, () => {
    for (const path of GUEST_PAGES) {
      test(`مهمان ${path}`, async ({ browser }) => {
        await audit(await openAs(browser, null, scheme), path);
      });
    }

    for (const path of STUDENT_PAGES) {
      test(`دانشجو ${path}`, async ({ browser }) => {
        await audit(await openAs(browser, 'student', scheme), path);
      });
    }

    test('دانشجو — صفحهٔ یک پروژه و یک ایده', async ({ browser }) => {
      const token = sessions().student.access_token;
      const headers = { Authorization: `Bearer ${token}` };
      const projects = (await (await fetch(`${API}/projects`, { headers })).json()) as {
        items: { id: string }[];
      };
      const ideas = (await (await fetch(`${API}/ideas`, { headers })).json()) as {
        items: { id: string }[];
      };
      const page = await openAs(browser, 'student', scheme);
      if (projects.items[0]) await audit(page, `/projects/${projects.items[0].id}`);
      if (ideas.items[0]) await audit(page, `/ideas/${ideas.items[0].id}`);
    });

    for (const path of ADMIN_PAGES) {
      test(`مدیر ${path}`, async ({ browser }) => {
        await audit(await openAs(browser, 'admin', scheme), path);
      });
    }
  });
}

test('نمودار روند امتیاز با یک توقف Tab و فلش پیمایش می‌شود', async ({ browser }) => {
  const page = await openAs(browser, 'student', 'light');
  await page.goto('/dashboard', { waitUntil: 'load' });
  const chart = page.getByRole('img', { name: /نمودار ستونی امتیاز هفتگی/ });
  // حساب تازه ممکن است هنوز روندی نداشته باشد؛ آن‌وقت نموداری نیست.
  const present = await chart
    .waitFor({ timeout: 15_000 })
    .then(() => true)
    .catch(() => false);
  test.skip(!present, 'این حساب هنوز روند امتیاز ندارد');
  await chart.focus();
  await expect(chart).toBeFocused();
  await page.keyboard.press('ArrowLeft');
  await expect(chart).toBeFocused();
});
