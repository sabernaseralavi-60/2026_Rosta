import type { Metadata } from 'next';

import { CourseLibraryView } from './CourseLibraryView';

export const metadata: Metadata = {
  title: 'درس',
  description: 'سرفصل، کتابخانه و ارائه‌های باز این درس.',
};

/** `/library/[slug]` — صفحهٔ درس با کتابخانه و دروازهٔ اشتراک. */
export default async function CoursePage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  return <CourseLibraryView slug={slug} />;
}
