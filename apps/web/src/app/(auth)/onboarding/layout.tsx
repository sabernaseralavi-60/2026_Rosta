import type { ReactNode } from 'react';

/**
 * پوستهٔ ورود اولیه — §3.3.
 *
 * گام‌های فرم باریک می‌مانند (خواندن سطر بلند سخت است)، ولی صفحهٔ
 * `/onboarding/results` خودش عرضش را تعیین می‌کند چون کارت پروژه با
 * دلایل، به فضا نیاز دارد.
 */
export default function OnboardingLayout({ children }: { children: ReactNode }) {
  return <div className="flex w-full justify-center py-4">{children}</div>;
}
