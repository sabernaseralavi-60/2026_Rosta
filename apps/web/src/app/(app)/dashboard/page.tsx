import type { Metadata } from 'next';

import { TodaySection } from '@/components/learning/TodaySection';

import { DashboardView } from './DashboardView';
import { MyWork } from './MyWork';
import { OnboardingNotice } from './OnboardingNotice';

export const metadata: Metadata = {
  title: 'داشبورد',
  description: 'نمای کلی دروس، پروژه‌ها و امتیازهای شما.',
};

/**
 * `/dashboard` — §3.4.
 *
 * از M5 داشبورد کامل است (FR-DASH-01): «قدم بعدی تو»، امتیاز و روندش،
 * دروس با نمرهٔ یادگیری، پروژه‌ها با سلامت، رویدادهای پیش‌رو و نشان‌ها
 * (`DashboardView`). زیرش درخواست‌های در جریان (M2) و پیشنهادهای
 * پروژه (M1) می‌مانند.
 */
export default function DashboardPage() {
  return (
    <div className="flex flex-col gap-8">
      <div className="flex flex-col gap-1">
        <h1>داشبورد</h1>
        <p className="text-[15px] text-[var(--fg-secondary)]">اینجا مسیر رشدت را دنبال می‌کنی.</p>
      </div>

      <TodaySection />
      <DashboardView />
      <MyWork />
      <OnboardingNotice />
    </div>
  );
}
