import type { Metadata } from 'next';

import { CoursesView } from './CoursesView';

export const metadata: Metadata = {
  title: 'دروس من',
  description: 'درس‌هایی که در آن‌ها ثبت‌نام کرده‌اید، با نوار پیشرفت مطالعه.',
};

/** `/courses` — §3.4. */
export default function CoursesPage() {
  return <CoursesView />;
}
