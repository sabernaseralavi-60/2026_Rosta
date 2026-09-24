import type { Metadata } from 'next';

import { TeachDashboardView } from './TeachDashboardView';

export const metadata: Metadata = {
  title: 'تدریس',
  description: 'آنچه اقدام می‌خواهد: صف تصحیح، درخواست ثبت‌نام، اعتراض و دانشجوی در خطر.',
};

/** `/teach` — §3.5، FR-DASH-02. */
export default function TeachDashboardPage() {
  return <TeachDashboardView />;
}
