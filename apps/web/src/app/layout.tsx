import type { Metadata, Viewport } from 'next';
import type { ReactNode } from 'react';

import { SESSION_HINT_SCRIPT } from '@/lib/auth/session';

import '@/styles/globals.css';

/**
 * پوستهٔ ریشه — PRD §10.5، §10.8، D-04.
 *
 * `lang="fa" dir="rtl"` روی `<html>` می‌نشیند، نه روی یک `<div>` داخلی:
 * جهت باید پیش از اولین رنگ‌آمیزی مشخص باشد، وگرنه صفحه یک‌بار از چپ
 * به راست می‌پرد (§10.5 ریسک اصلی M0).
 */

export const metadata: Metadata = {
  title: {
    default: 'سامانهٔ نوآوری و یادگیری صابر',
    // §10.8 — عنوان صفحه در هر مسیر منحصربه‌فرد و توصیفی است.
    template: '%s — سیلپ',
  },
  description: 'اکوسیستمی که دانشجو را از مصرف‌کنندهٔ دانش به تولیدکنندهٔ ارزش تبدیل می‌کند.',
  applicationName: 'SILP',
  robots: { index: true, follow: true },
};

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  // §10.8 — کاربر باید بتواند بزرگ‌نمایی کند؛ قفل کردن zoom ممنوع است.
  maximumScale: 5,
  themeColor: [
    { media: '(prefers-color-scheme: light)', color: '#fafaf9' },
    { media: '(prefers-color-scheme: dark)', color: '#1c1b19' },
  ],
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="fa" dir="rtl" suppressHydrationWarning>
      <head>
        {/* M7-15 — `data-session` پیش از اولین رنگ‌آمیزی. next/script این
            تضمین را نمی‌دهد؛ محتوا ثابت زمان ساخت است، نه ورودی کاربر. */}
        {/* eslint-disable-next-line react/no-danger -- رشتهٔ ثابت، بی‌ورودی کاربر */}
        <script dangerouslySetInnerHTML={{ __html: SESSION_HINT_SCRIPT }} />
      </head>
      <body>
        {/* §10.8 — اولین عنصر focusable صفحه */}
        <a href="#main" className="skip-link">
          پرش به محتوای اصلی
        </a>
        {children}
      </body>
    </html>
  );
}
