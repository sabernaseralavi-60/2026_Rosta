import type { Metadata } from 'next';

import { StudentsView } from './StudentsView';

export const metadata: Metadata = {
  title: 'دانشجویان ارائه',
  description: 'درخواست‌های ثبت‌نام و فهرست کلاس.',
};

/** `/teach/offerings/[id]/students` — §3.5. */
export default function StudentsPage() {
  return <StudentsView />;
}
