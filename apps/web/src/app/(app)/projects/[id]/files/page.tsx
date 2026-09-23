import type { Metadata } from 'next';

import { LibraryView } from './LibraryView';

export const metadata: Metadata = {
  title: 'کتابخانهٔ فایل پروژه',
  description: 'پیوست تحویل‌ها و پیام‌های تیم، و نسخه‌های فایل‌های مدل شهری.',
};

/** `/projects/[id]/files` — §3.4، FR-PRJ-06، FR-CITY-01. */
export default async function LibraryPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <LibraryView id={id} />;
}
