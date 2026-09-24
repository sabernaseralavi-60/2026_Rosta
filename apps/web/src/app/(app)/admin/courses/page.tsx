import type { Metadata } from 'next';

import { CoursesAdminView } from './CoursesAdminView';

export const metadata: Metadata = {
  title: 'درس‌ها و ارائه‌ها',
  description: 'تعریف نیم‌سال و درس، و ساخت ارائه با استادش.',
};

/** `/admin/courses` — §3.6، ADR-0020. */
export default function CoursesAdminPage() {
  return <CoursesAdminView />;
}
