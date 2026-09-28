import type { Metadata } from 'next';

import { OwnerDashboardView } from './OwnerDashboardView';

export const metadata: Metadata = {
  title: 'داشبورد مالک',
  description: 'یک نگاه به درخواست‌های ورودی، دانشجویان، درس‌ها، محتوا و مواردِ نیازمند پیگیری.',
};

/** `/admin/owner` — ADR-0032، فایل مشخصات فاز ۰ بند ۲۶. فقط مدیر سامانه. */
export default function OwnerPage() {
  return <OwnerDashboardView />;
}
