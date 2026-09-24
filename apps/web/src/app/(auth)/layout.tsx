import type { ReactNode } from 'react';

/**
 * پوستهٔ ناحیهٔ ورود — §3.3.
 *
 * بدون ناوبری و بدون حواس‌پرتی: در این ناحیه کاربر یک کار دارد و باید
 * همان را تمام کند.
 */
export default function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-dvh flex-col bg-[var(--bg-canvas)]">
      <header className="px-4 py-6 md:px-8">
        <span className="text-[17px] font-bold text-[var(--fg-brand)]">سیلپ</span>
      </header>

      {/* عرض را خود صفحه تعیین می‌کند: فرم ورود باریک است ولی صفحهٔ
          پیشنهادها (§3.3) به فضای بیشتری برای کارت پروژه نیاز دارد. */}
      <main
        id="main"
        className="flex flex-1 justify-center px-4 pb-16 max-md:items-start md:items-center"
      >
        {children}
      </main>

      <footer className="px-4 pb-6 text-center text-[12.5px] text-[var(--fg-tertiary)] md:px-8">
        سامانهٔ نوآوری و یادگیری صابر
      </footer>
    </div>
  );
}
