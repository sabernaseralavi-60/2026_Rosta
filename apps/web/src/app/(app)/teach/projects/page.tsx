import type { Metadata } from 'next';

import { SupervisedProjectsView } from './SupervisedProjectsView';

export const metadata: Metadata = {
  title: 'پروژه‌های تحت نظارت',
  description: 'پروژه‌های ارائه‌هایت با شاخص سلامت و تحویل‌های منتظر.',
};

/** `/teach/projects` — §3.5، ADR-0022. */
export default function SupervisedProjectsPage() {
  return <SupervisedProjectsView />;
}
