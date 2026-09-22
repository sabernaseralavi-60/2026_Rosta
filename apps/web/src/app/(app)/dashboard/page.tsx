import type { Metadata } from 'next';

import { MyWork } from './MyWork';
import { OnboardingNotice } from './OnboardingNotice';

export const metadata: Metadata = {
  title: 'داشبورد',
  description: 'نمای کلی دروس، پروژه‌ها و امتیازهای شما.',
};

/**
 * `/dashboard` — §3.4.
 *
 * از M2 دو چیز واقعی اینجاست: پروژه‌هایی که کاربر در آن‌هاست و
 * درخواست‌هایی که داده. بدون این‌ها، دانشجو پس از ارسال درخواست هیچ
 * جایی ندارد که ببیند چه شد.
 *
 * دروس (M3)، امتیاز و `NextStepCard` (M5-10) بعداً اضافه می‌شوند —
 * نه با عدد ساختگی، که با دادهٔ واقعی همان مرحله.
 */
export default function DashboardPage() {
  return (
    <div className="flex flex-col gap-8">
      <div className="flex flex-col gap-1">
        <h1>داشبورد</h1>
        <p className="text-[15px] text-[var(--fg-secondary)]">
          اینجا مسیر رشدت را دنبال می‌کنی.
        </p>
      </div>

      <OnboardingNotice />
      <MyWork />
    </div>
  );
}
