import type { Metadata } from 'next';

import { StudentAccess } from './StudentAccess';

export const metadata: Metadata = {
  title: 'ورود دانشجوی درس',
  description: 'دانشجوی درس‌های سامانه با موبایل و شمارهٔ دانشجویی حساب خود را فعال می‌کند.',
};

/**
 * `/student` — ADR-0035.
 *
 * دو کار در یک صفحه: فعال‌سازی اولیه (موبایل + شمارهٔ دانشجویی + کد ایمیل) و ورودِ
 * بعدی با موبایل + رمز. ورود با رمز اینجا هست چون ورود با کد پیامکی به سرویس پیامک
 * وابسته است و دانشجوی فهرست‌شده نباید به آن وابسته باشد.
 */
export default function StudentPage() {
  return (
    <section className="flex w-full max-w-[26rem] flex-col gap-6">
      <StudentAccess />
    </section>
  );
}
