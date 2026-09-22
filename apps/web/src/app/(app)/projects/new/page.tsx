import type { Metadata } from 'next';

import { ProjectForm } from './ProjectForm';

export const metadata: Metadata = {
  title: 'پروژهٔ تازه',
  description: 'تعریف پروژه با مشخصات تطابق و مراحل تحویل.',
};

/** `/projects/new` — §3.4، FR-PRJ-01. */
export default function NewProjectPage() {
  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-1">
        <h1>پروژهٔ تازه</h1>
        <p className="text-[15px] text-[var(--fg-secondary)]">
          هرچه دقیق‌تر بنویسی، توصیه‌گر بهتر آدم مناسبش را پیدا می‌کند.
        </p>
      </header>

      <ProjectForm />
    </div>
  );
}
