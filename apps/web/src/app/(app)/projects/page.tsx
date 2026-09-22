import type { Metadata } from 'next';

import { ProjectsView } from './ProjectsView';

export const metadata: Metadata = {
  title: 'پروژه‌ها',
  description: 'پیشنهادهای شخصی و بانک کامل پروژه‌های باز.',
};

/** `/projects` — §3.4. */
export default function ProjectsPage() {
  return <ProjectsView />;
}
