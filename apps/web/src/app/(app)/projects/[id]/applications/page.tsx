import type { Metadata } from 'next';

import { ApplicationsView } from './ApplicationsView';

export const metadata: Metadata = {
  title: 'درخواست‌های پیوستن',
  description: 'بررسی درخواست‌های پیوستن به پروژه با امتیاز تطابق هر متقاضی.',
};

/** `/projects/[id]/applications` — §3.4، FR-PRJ-04. */
export default async function ApplicationsPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <ApplicationsView id={id} />;
}
