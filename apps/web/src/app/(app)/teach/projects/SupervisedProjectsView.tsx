'use client';

import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';

import { errorText, ErrorLine, FactList } from '@/components/admin/common';
import { Badge, type BadgeTone } from '@/components/ui/Badge';
import { Card } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { SkeletonRow } from '@/components/ui/Skeleton';
import {
  SUPERVISED_STATUS_LABELS,
  type ProjectHealth,
  type TeachProject,
  fetchTeachProjects,
} from '@/lib/api/teach';
import { useSession } from '@/lib/auth/use-session';
import { cn } from '@/lib/cn';
import { toPersianDigits } from '@/lib/format/digits';

/**
 * `/teach/projects` — پروژه‌های تحت نظارت با شاخص سلامت (§3.5، ADR-0022).
 *
 * «متوقف» و «در خطر» بالا می‌آیند (ترتیب از سرور): استاد اول به چیزی سر
 * می‌زند که دارد از دست می‌رود. فیلتر «نیازمند توجه» همین‌ها را تنها نگه
 * می‌دارد — هر چه سالم است و تحویل منتظر ندارد، اقدامی نمی‌خواهد.
 */

const HEALTH_TONES: Record<ProjectHealth, BadgeTone> = {
  HEALTHY: 'success',
  AT_RISK: 'warning',
  STALLED: 'danger',
};

type Filter = 'all' | 'attention';

function needsAttention(project: TeachProject): boolean {
  return (
    project.health !== 'HEALTHY' || project.open_deliverables > 0 || project.milestones_overdue > 0
  );
}

export function SupervisedProjectsView() {
  const { accessToken } = useSession();
  const [projects, setProjects] = useState<TeachProject[] | null>(null);
  const [filter, setFilter] = useState<Filter>('all');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!accessToken) return;
    fetchTeachProjects(accessToken)
      .then(setProjects)
      .catch((cause) => setError(errorText(cause)));
  }, [accessToken]);

  const attention = useMemo(() => (projects ?? []).filter(needsAttention), [projects]);
  const shown = filter === 'attention' ? attention : (projects ?? []);

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div className="flex flex-col gap-1">
          <h1>پروژه‌های تحت نظارت</h1>
          <p className="text-[14px] text-[var(--fg-secondary)]">
            پروژه‌های ارائه‌هایت و پروژه‌هایی که خودت مدیرشان هستی.
          </p>
        </div>
        <Link href="/teach/review-queue" className="text-[14px] font-medium text-[var(--fg-brand)]">
          صف بررسی تحویل‌ها
        </Link>
      </header>

      {error && <ErrorLine>{error}</ErrorLine>}
      {!projects && !error && (
        <div className="flex flex-col gap-3">
          <SkeletonRow />
          <SkeletonRow />
          <SkeletonRow />
        </div>
      )}

      {projects && projects.length === 0 && (
        <EmptyState
          title="هنوز پروژه‌ای زیر نظر تو نیست"
          description="هنگام ساخت پروژه (نوع کارآفرینی، پژوهشی یا حل مسئله) یکی از ارائه‌هایت را انتخاب کن؛ آن پروژه اینجا و در صف بررسی می‌آید."
          action={
            <Link href="/projects/new" className="text-[14px] font-medium text-[var(--fg-brand)]">
              ساخت پروژه
            </Link>
          }
        />
      )}

      {projects && projects.length > 0 && (
        <>
          <div role="group" aria-label="فیلتر پروژه‌ها" className="flex flex-wrap gap-2">
            <FilterButton active={filter === 'all'} onClick={() => setFilter('all')}>
              همه ({toPersianDigits(projects.length)})
            </FilterButton>
            <FilterButton active={filter === 'attention'} onClick={() => setFilter('attention')}>
              نیازمند توجه ({toPersianDigits(attention.length)})
            </FilterButton>
          </div>

          {shown.length === 0 ? (
            <EmptyState
              title="همه‌چیز روبه‌راه است"
              description="پروژه‌ای متوقف، در خطر، یا با تحویل منتظر نیست."
            />
          ) : (
            <ul className="flex flex-col gap-3">
              {shown.map((project) => (
                <li key={project.id}>
                  <ProjectCard project={project} />
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  );
}

function FilterButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={cn(
        'rounded-full border px-3 py-1.5 text-[13.5px]',
        active
          ? 'border-[var(--brand-500)] bg-[var(--brand-50)] font-medium text-[var(--fg-brand)]'
          : 'border-[var(--border-default)] text-[var(--fg-secondary)] hover:bg-[var(--bg-sunken)]',
      )}
    >
      {children}
    </button>
  );
}

function ProjectCard({ project }: { project: TeachProject }) {
  return (
    <Card className="flex flex-col gap-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="flex min-w-0 flex-col gap-0.5">
          <h2 className="text-[16px]">
            <Link href={`/projects/${project.id}/workspace`} className="hover:underline">
              {project.title_fa}
            </Link>
          </h2>
          <p className="text-[13.5px] text-[var(--fg-secondary)]">
            {project.kind_fa}
            {project.course_title_fa ? ` — ${project.course_title_fa}` : ''}
          </p>
        </div>
        <div className="flex flex-wrap gap-1.5">
          <Badge tone={HEALTH_TONES[project.health]}>{project.health_fa}</Badge>
          <Badge tone="neutral">{SUPERVISED_STATUS_LABELS[project.status]}</Badge>
        </div>
      </div>

      <FactList
        className="text-[var(--fg-secondary)]"
        items={[
          <span key="lead">مدیر: {project.lead_name ?? 'بدون نام'}</span>,
          <span key="team">
            اعضا: {toPersianDigits(project.active_members)} از{' '}
            {toPersianDigits(project.team_size_max)}
          </span>,
          project.milestones_total > 0 && (
            <span key="ms">
              مرحلهٔ تأییدشده: {toPersianDigits(project.milestones_approved)} از{' '}
              {toPersianDigits(project.milestones_total)}
            </span>
          ),
          project.milestones_overdue > 0 && (
            <span key="late" className="text-[var(--fg-warning)]">
              مرحلهٔ از مهلت گذشته: {toPersianDigits(project.milestones_overdue)}
            </span>
          ),
          project.status === 'IN_PROGRESS' && project.days_inactive > 0 && (
            <span key="idle">بی‌فعالیت: {toPersianDigits(project.days_inactive)} روز</span>
          ),
        ]}
      />

      {project.open_deliverables > 0 && (
        <p className="text-[13.5px]">
          <Link href="/teach/review-queue" className="font-medium text-[var(--fg-brand)]">
            {toPersianDigits(project.open_deliverables)} تحویل منتظر بررسی
          </Link>
          {project.oldest_open_days !== null && project.oldest_open_days > 0 && (
            <span className="text-[var(--fg-tertiary)]">
              {' '}
              — قدیمی‌ترین {toPersianDigits(project.oldest_open_days)} روز پیش
            </span>
          )}
        </p>
      )}
    </Card>
  );
}
