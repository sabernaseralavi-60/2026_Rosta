import type { Metadata } from 'next';

import { MetricsView } from './MetricsView';

export const metadata: Metadata = {
  title: 'پنل مدیریت',
  description: 'شاخص‌های کلان سامانه: کاربران، پروژه‌ها، صف‌های بررسی و صف ارسال.',
};

/** `/admin` — §3.6 «شاخص‌های کلان سامانه». */
export default function AdminPage() {
  return <MetricsView />;
}
