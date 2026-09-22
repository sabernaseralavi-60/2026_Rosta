import { redirect } from 'next/navigation';

/**
 * ریشه.
 *
 * صفحهٔ اصلی بازاریابی وظیفهٔ M7-10 است. تا آن زمان کاربر مستقیم به
 * ورود می‌رود — یک صفحهٔ «به‌زودی» چیزی به کسی نمی‌دهد.
 */
export default function HomePage() {
  redirect('/login');
}
