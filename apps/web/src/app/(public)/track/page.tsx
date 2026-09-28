import type { Metadata } from 'next';

import { TrackForm } from '@/components/public/TrackForm';

export const metadata: Metadata = {
  title: 'پیگیری درخواست',
  description:
    'با کد پیگیری و شمارهٔ موبایل یا ایمیلی که هنگام ثبت دادید، وضعیت درخواستتان را ببینید.',
};

/** `/track` — پیگیری بی‌ورود (ADR-0032). */
export default function TrackPage() {
  return (
    <div className="page mx-auto flex max-w-[640px] flex-col gap-6 py-12">
      <header className="flex flex-col gap-2">
        <h1>پیگیری درخواست</h1>
        <p className="text-[15px] leading-[2] text-[var(--fg-secondary)]">
          کد پیگیری‌ای که پس از ثبت گرفتید و همان شماره یا ایمیلی را بنویسید که هنگام ثبت دادید.
        </p>
      </header>
      <TrackForm />
    </div>
  );
}
