import type { Metadata } from 'next';

import { OnboardingNotice } from './OnboardingNotice';

export const metadata: Metadata = {
  title: 'داشبورد',
  description: 'نمای کلی دروس، پروژه‌ها و امتیازهای شما.',
};

/**
 * `/dashboard` — §3.4.
 *
 * تعریف انجام‌شدهٔ M0: «وارد می‌شود و صفحهٔ خالی داشبورد را می‌بیند.»
 *
 * محتوای واقعی (`NextStepCard`، دروس، پروژه‌ها، امتیاز) در M5-10
 * می‌آید. اینجا عمداً خالی است و **می‌گوید** که خالی است — نه یک
 * داشبورد جعلی با اعداد ساختگی.
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
    </div>
  );
}
