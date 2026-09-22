/**
 * مقصد OTP در جریان ورود.
 *
 * شماره در `sessionStorage` می‌ماند، نه در query string: آدرس صفحه در
 * تاریخچهٔ مرورگر، در لاگ پروکسی و در هدر `Referer` ظاهر می‌شود، و
 * شمارهٔ موبایل طبق NFR-01 دادهٔ **محرمانه** است.
 *
 * با بستن تب پاک می‌شود — که همان رفتار درست است: جریان ورود نیمه‌کاره
 * نباید تا فردا زنده بماند.
 */

const KEY = 'silp.pending_otp_destination';

function storage(): Storage | null {
  if (typeof window === 'undefined') return null;
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

export function rememberOtpDestination(destination: string): void {
  try {
    storage()?.setItem(KEY, destination);
  } catch {
    // اگر ذخیره نشد، ارسال مجدد کاربر را به /login برمی‌گرداند.
  }
}

export function readOtpDestination(): string | null {
  return storage()?.getItem(KEY) ?? null;
}

export function forgetOtpDestination(): void {
  storage()?.removeItem(KEY);
}
