import type { Metadata } from 'next';
import Link from 'next/link';

import { LoginForm } from './LoginForm';

export const metadata: Metadata = {
  title: 'ورود',
  description: 'با شمارهٔ موبایل خود وارد سامانهٔ نوآوری و یادگیری صابر شوید.',
};

/**
 * `/login` — §3.3.
 *
 * «ورودی موبایل ← ارسال OTP.» ورود با رمز مسیر دوم است (D-05) و در
 * M0 فقط پیوندش گذاشته می‌شود؛ خودش با FR-AUTH-02 کامل است ولی صفحهٔ
 * جدا ندارد تا گام اول ساده بماند.
 */
export default function LoginPage() {
  return (
    <section className="flex w-full max-w-[26rem] flex-col gap-6">
      <div className="flex flex-col gap-2">
        <h1>ورود به رُستا</h1>
        <p className="text-[15px] text-[var(--fg-secondary)]">
          شمارهٔ موبایلت را وارد کن. یک کد شش‌رقمی برایت می‌فرستیم.
        </p>
      </div>

      <LoginForm />

      <p className="text-center text-[13.5px] text-[var(--fg-secondary)]">
        دانشجوی یکی از درس‌هایی؟{' '}
        <Link href="/student" className="underline">
          با شمارهٔ دانشجویی فعال کن یا با رمز وارد شو
        </Link>
      </p>
    </section>
  );
}
