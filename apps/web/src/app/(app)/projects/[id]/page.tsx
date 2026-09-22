import type { Metadata } from 'next';

import { ProjectDetailView } from './ProjectDetailView';

export const metadata: Metadata = {
  title: 'جزئیات پروژه',
  description: 'شرح پروژه، مهارت‌های لازم و میزان تطابق آن با نیمرخ شما.',
};

/** `/projects/[id]` — §3.4. */
export default async function ProjectPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <ProjectDetailView id={id} />;
}
