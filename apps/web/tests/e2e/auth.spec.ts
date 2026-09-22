import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

/**
 * جریان ورود — §3.3، FR-AUTH-01.
 *
 * این تست‌ها روی پشتهٔ کامل (`compose.test.yml`) اجرا می‌شوند و کد
 * ثابت توسعه (`111111`) را استفاده می‌کنند — §14.8.
 */

const DEV_MOBILE = '09120000010';
const DEV_OTP = '111111';

test.describe('ورود با کد یک‌بارمصرف', () => {
  test('صفحهٔ ورود راست‌چین و فارسی است', async ({ page }) => {
    await page.goto('/login');

    // §10.5، §10.8 — جهت و زبان روی <html>
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    await expect(page.locator('html')).toHaveAttribute('lang', 'fa');
    await expect(page.getByRole('heading', { level: 1 })).toContainText('ورود');
  });

  test('شمارهٔ موبایل با جهت چپ‌به‌راست وارد می‌شود', async ({ page }) => {
    await page.goto('/login');
    const field = page.getByLabel('شمارهٔ موبایل');
    await expect(field).toHaveAttribute('dir', 'ltr');
    await expect(field).toHaveAttribute('type', 'tel');
  });

  test('شمارهٔ نامعتبر پیام فارسی می‌گیرد', async ({ page }) => {
    await page.goto('/login');
    await page.getByLabel('شمارهٔ موبایل').fill('0812345678');
    await page.getByRole('button', { name: 'ارسال کد ورود' }).click();

    const alert = page.getByRole('alert');
    await expect(alert).toBeVisible();
    await expect(alert).toContainText(/معتبر|درست/);
  });

  test('جریان کامل: شماره ← کد ← داشبورد', async ({ page }) => {
    await page.goto('/login');
    await page.getByLabel('شمارهٔ موبایل').fill(DEV_MOBILE);
    await page.getByRole('button', { name: 'ارسال کد ورود' }).click();

    await expect(page).toHaveURL(/\/verify/);
    // مقصد پوشانده نمایش داده می‌شود، نه شمارهٔ کامل — NFR-01
    await expect(page.getByText('0912***0010')).toBeVisible();
    await expect(page.locator('body')).not.toContainText(DEV_MOBILE);

    // چسباندن کل کد باید همهٔ خانه‌ها را پر کند — §3.3
    await page.getByLabel('رقم ۱ از ۶').fill(DEV_OTP);

    await expect(page).toHaveURL(/\/onboarding\/basic|\/dashboard/, { timeout: 10_000 });
  });

  test('شمارهٔ کامل در نشانی صفحه ظاهر نمی‌شود', async ({ page }) => {
    await page.goto('/login');
    await page.getByLabel('شمارهٔ موبایل').fill(DEV_MOBILE);
    await page.getByRole('button', { name: 'ارسال کد ورود' }).click();
    await expect(page).toHaveURL(/\/verify/);

    // NFR-01 — نشانی در تاریخچه و لاگ پروکسی می‌ماند.
    expect(page.url()).not.toContain(DEV_MOBILE);
  });
});

test.describe('دسترس‌پذیری — §10.8', () => {
  for (const path of ['/login', '/verify']) {
    test(`${path} خطای axe ندارد`, async ({ page }) => {
      await page.goto(path);
      const results = await new AxeBuilder({ page })
        .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'])
        .analyze();
      expect(results.violations).toEqual([]);
    });
  }

  test('لینک پرش به محتوا اولین عنصر focusable است', async ({ page }) => {
    await page.goto('/login');
    await page.keyboard.press('Tab');
    await expect(page.getByRole('link', { name: 'پرش به محتوای اصلی' })).toBeFocused();
  });
});
