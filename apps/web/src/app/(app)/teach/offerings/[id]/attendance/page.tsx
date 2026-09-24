import type { Metadata } from 'next';

import { AttendanceView } from './AttendanceView';

export const metadata: Metadata = {
  title: 'حضور و غیاب',
  description: 'ثبت سریع حضور کلاس و اصلاح جلسه‌های گذشته.',
};

/** `/teach/offerings/[id]/attendance` — §3.5، FR-EDU-05. */
export default function AttendancePage() {
  return <AttendanceView />;
}
