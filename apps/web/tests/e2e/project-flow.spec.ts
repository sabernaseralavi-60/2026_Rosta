import { type Page, expect, test } from '@playwright/test';

/**
 * چرخهٔ پروژه در مرورگر واقعی — M2، تعریف انجام‌شدهٔ §13.
 *
 * تست یکپارچهٔ بک‌اند ثابت می‌کند API درست است؛ این تست ثابت می‌کند
 * **کاربر** می‌تواند همان کار را انجام دهد: فرم پر کند، دکمه بزند و
 * نتیجه را ببیند.
 *
 * همهٔ صفحه‌های `(app)` نیازمند ورودند (پوستهٔ M0)؛ مرور عمومی بانک
 * پروژه در M7-10 می‌آید. پس هر تست اول وارد می‌شود.
 *
 * **اجرای پشت‌سرهم روی یک ماشین:** هر تست یک ورود تازه می‌سازد و
 * `OTP_PER_IP_PER_HOUR` پیش‌فرض ۱۰ است. در CI که پشته تازه بالا می‌آید
 * مشکلی نیست؛ محلی اگر ۴۲۹ گرفتید، Redis را خالی کنید.
 */

const DEV_OTP = '111111';

/** شمارهٔ یکتا برای هر اجرا — تست‌ها نباید به هم داده نشت بدهند. */
function uniqueMobile(): string {
  const tail = String(Math.floor(Math.random() * 10_000_000)).padStart(7, '0');
  return `0913${tail}`;
}

async function login(page: Page, mobile: string): Promise<void> {
  await page.goto('/login');
  await page.getByLabel('شمارهٔ موبایل').fill(mobile);
  await page.getByRole('button', { name: /ارسال کد|ورود/ }).first().click();

  await page.waitForURL(/\/verify/, { timeout: 30_000 });
  const boxes = page.getByRole('textbox');
  for (let index = 0; index < DEV_OTP.length; index += 1) {
    await boxes.nth(index).fill(DEV_OTP.charAt(index));
  }
  await page.waitForURL(/\/onboarding|\/dashboard/, { timeout: 30_000 });
}

/**
 * چهار گام ارزیابی با مقادیر پیش‌فرض — شرط §7.5 برای درخواست پیوستن.
 *
 * برچسب دکمه‌ها از خود رابط گرفته شده‌اند (§3.3): «ذخیره و ادامه» در
 * گام‌های ۱ تا ۳ و «ببین چه پیشنهادهایی داری» در گام ۴.
 */
async function completeOnboarding(page: Page, firstName: string): Promise<void> {
  if (page.url().includes('/onboarding/basic')) {
    await page.getByLabel('نام', { exact: true }).fill(firstName);
    await page.getByLabel('نام خانوادگی').fill('آزمون');
    await page.getByRole('button', { name: 'ادامه' }).click();
    await page.waitForURL(/\/onboarding\/survey/, { timeout: 30_000 });
  }

  for (let guard = 0; guard < 6; guard += 1) {
    if (!page.url().includes('/onboarding/survey')) break;
    // گام ارزیابی طبقه‌بندی‌ها را async می‌گیرد؛ دکمه پیش از آن در صفحه
    // نیست. کلیک بدون انتظار، تست را به‌جای اشکال محصول، به اشکال
    // زمان‌بندی تبدیل می‌کند.
    const next = page.getByRole('button', {
      name: /ذخیره و ادامه|ببین چه پیشنهادهایی داری/,
    });
    await next.waitFor({ state: 'visible', timeout: 30_000 });
    await next.click();
    await page.waitForTimeout(900);
  }

  await page.goto('/dashboard');
}

async function firstProjectHref(page: Page): Promise<string> {
  await page.goto('/projects');
  const link = page.locator('a[href^="/projects/"]').first();
  await expect(link).toBeVisible({ timeout: 30_000 });
  const href = await link.getAttribute('href');
  expect(href).toBeTruthy();
  return href as string;
}

// ورود + چهار گام ارزیابی + رفت‌وبرگشت با API، از مهلت پیش‌فرض ۳۰ ثانیه
// بیشتر طول می‌کشد. مهلت کوتاه، تست را قرمز می‌کند بی‌آنکه چیزی خراب باشد.
test.describe.configure({ timeout: 150_000 });

test.describe('چرخهٔ پروژه', () => {
  test('بانک پروژه برای کاربر واردشده فهرست دارد', async ({ page }) => {
    await login(page, uniqueMobile());
    await completeOnboarding(page, 'بیننده');

    await page.goto('/projects');
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
    await expect(page.locator('a[href^="/projects/"]').first()).toBeVisible({
      timeout: 30_000,
    });
  });

  test('فضای کاری برای غیرعضو بسته است و راه پیوستن را می‌گوید', async ({ page }) => {
    await login(page, uniqueMobile());
    await completeOnboarding(page, 'غریبه');

    const href = await firstProjectHref(page);
    await page.goto(`${href}/workspace`);

    // §6.4 — تصمیم با سرور است؛ رابط فقط دلیلش را روشن می‌گوید.
    await expect(
      page.getByRole('heading', { name: 'این فضای کاری برای تیم پروژه است' }),
    ).toBeVisible({ timeout: 30_000 });
    await expect(page.getByRole('link', { name: 'صفحهٔ پروژه' })).toBeVisible();
  });

  test('دانشجو می‌تواند به پروژهٔ باز درخواست پیوستن بدهد', async ({ page }) => {
    await login(page, uniqueMobile());
    await completeOnboarding(page, 'متقاضی');

    const href = await firstProjectHref(page);
    await page.goto(href);

    const apply = page.getByRole('button', { name: 'درخواست پیوستن' });
    await expect(apply).toBeVisible({ timeout: 30_000 });
    await apply.click();

    await page.getByLabel('انگیزه‌نامه').fill('به این کار علاقه دارم و وقت آزادش را دارم.');
    await page.getByRole('button', { name: 'ارسال درخواست' }).click();

    // §7.5 — پس از ارسال، وضعیت درخواست دیده می‌شود، نه دکمهٔ دوباره.
    await expect(page.getByText('در انتظار تصمیم')).toBeVisible({ timeout: 30_000 });
    await expect(page.getByRole('heading', { name: 'درخواست تو' })).toBeVisible();

    // داشبورد هم همان درخواست را نشان می‌دهد.
    await page.goto('/dashboard');
    await expect(page.getByText('درخواست‌های در جریان')).toBeVisible({ timeout: 30_000 });
  });

  test('دانشجو پروژه می‌سازد، منتشر می‌کند و فضای کاری را می‌گرداند', async ({ page }) => {
    await login(page, uniqueMobile());
    await completeOnboarding(page, 'سازنده');

    await page.goto('/projects/new');
    await expect(page.getByRole('heading', { level: 1 })).toContainText('پروژهٔ تازه');

    const title = `پروژهٔ آزمون ${Date.now()}`;
    await page.getByLabel('عنوان').fill(title);
    await page.getByLabel('خلاصه').fill('خلاصه‌ای که به‌اندازهٔ کافی بلند است برای اعتبارسنجی.');
    await page
      .getByLabel('شرح کامل')
      .fill('شرح کامل پروژه با جزئیات کافی برای تصمیم دانشجو دربارهٔ پیوستن.');
    await page.getByLabel('در پایان چه تحویل می‌شود؟').fill('گزارش نهایی');

    // دست‌کم یک مهارت لازم — شرط انتشار §7.4.
    await page.locator('button[aria-pressed="false"]').first().click();
    await page.getByLabel('مرحلهٔ ۱').fill('مرحلهٔ اول');

    await page.getByRole('button', { name: 'ساخت پروژه' }).click();

    await page.waitForURL(/\/projects\/[0-9a-f-]{36}\/workspace/, { timeout: 60_000 });
    await expect(page.getByRole('heading', { level: 1 })).toContainText(title);
    await expect(page.getByText('پیش‌نویس')).toBeVisible();

    // §7.12 — انتشار تیم را می‌سازد و مدیر عضو `is_lead` آن است.
    await page.getByRole('button', { name: 'انتشار پروژه' }).click();
    await expect(page.getByText('باز برای عضوگیری')).toBeVisible({ timeout: 30_000 });

    await page.getByRole('tab', { name: 'تیم' }).click();
    await expect(page.getByText('مدیر پروژه')).toBeVisible({ timeout: 30_000 });

    // تختهٔ وظایف — FR-PRJ-06.
    await page.getByRole('tab', { name: 'وظایف' }).click();
    await page.getByLabel('وظیفهٔ تازه').fill('اولین کار تیم');
    await page.getByRole('button', { name: 'افزودن' }).click();
    await expect(page.getByText('اولین کار تیم')).toBeVisible({ timeout: 30_000 });

    // گفتگو — §4.6 نخ یک‌سطحی.
    await page.getByRole('tab', { name: 'گفتگو' }).click();
    await page.getByLabel('پیام تازه').fill('شروع کردیم.');
    await page.getByRole('button', { name: 'ارسال' }).click();
    await expect(page.getByText('شروع کردیم.')).toBeVisible({ timeout: 30_000 });

    // جریان فعالیت انتشار را ثبت کرده است.
    await page.getByRole('tab', { name: 'فعالیت' }).click();
    await expect(page.getByText('پروژه منتشر شد.')).toBeVisible({ timeout: 30_000 });

    // داشبورد پروژه را نشان می‌دهد — بدون آن، کاربر گمش می‌کند.
    await page.goto('/dashboard');
    await expect(page.getByText(title)).toBeVisible({ timeout: 30_000 });
  });
});
