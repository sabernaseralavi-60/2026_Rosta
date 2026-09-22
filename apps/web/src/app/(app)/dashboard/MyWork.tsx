'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';

import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card, CardTitle } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { SkeletonText } from '@/components/ui/Skeleton';
import type { ProjectSummary } from '@/lib/api/projects';
import { type Application, fetchMyApplications, fetchMyProjects } from '@/lib/api/workspace';
import { useSession } from '@/lib/auth/use-session';
import { formatRelative } from '@/lib/format/date';
import { toPersianDigits } from '@/lib/format/digits';

/**
 * «پروژه‌های من» و «درخواست‌های من» — §3.4، FR-DASH-01 (بخش M2).
 *
 * داشبورد کامل با `NextStepCard` و امتیاز در M5-10 می‌آید. آنچه اینجا
 * هست، دو چیزی است که بدون آن‌ها کاربر پس از درخواست دادن گم می‌شود:
 * کارش کجاست، و درخواستش چه شد.
 */

const STATUS_LABELS: Record<string, string> = {
  DRAFT: 'پیش‌نویس',
  OPEN: 'باز برای عضوگیری',
  IN_PROGRESS: 'در جریان',
  PAUSED: 'متوقف',
  COMPLETED: 'بسته شده',
  CANCELLED: 'لغو شده',
};

export function MyWork() {
  const { accessToken, loading: sessionLoading } = useSession({ required: false });
  const [projects, setProjects] = useState<ProjectSummary[] | null>(null);
  const [applications, setApplications] = useState<Application[]>([]);

  useEffect(() => {
    if (sessionLoading || !accessToken) return;
    let cancelled = false;

    Promise.all([fetchMyProjects(accessToken), fetchMyApplications(accessToken)])
      .then(([projectRows, applicationRows]) => {
        if (cancelled) return;
        setProjects(projectRows);
        setApplications(applicationRows);
      })
      .catch(() => !cancelled && setProjects([]));

    return () => {
      cancelled = true;
    };
  }, [accessToken, sessionLoading]);

  if (!accessToken) return null;
  if (projects === null) return <SkeletonText label="در حال بارگذاری پروژه‌های شما" />;

  const openApplications = applications.filter(
    (application) => application.status === 'PENDING' || application.status === 'WAITLISTED',
  );

  return (
    <div className="flex flex-col gap-8">
      <section className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-[19px] font-semibold">پروژه‌های من</h2>
          <Button asChild variant="secondary" size="sm">
            <Link href="/projects/new">پروژهٔ تازه</Link>
          </Button>
        </div>

        {projects.length === 0 ? (
          <EmptyState
            title="هنوز در هیچ پروژه‌ای نیستی"
            description="بانک پروژه را ببین و به پروژه‌ای که به تو می‌خورد درخواست بده — یا خودت یکی بساز."
            action={
              <Button asChild>
                <Link href="/projects">بانک پروژه</Link>
              </Button>
            }
          />
        ) : (
          <ul className="grid gap-3 sm:grid-cols-2">
            {projects.map((project) => (
              <li key={project.id}>
                <Card variant="interactive" className="flex h-full flex-col gap-2">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <Badge tone={project.status === 'IN_PROGRESS' ? 'success' : 'neutral'}>
                      {STATUS_LABELS[project.status] ?? project.status}
                    </Badge>
                    <Badge tone="brand">{project.kind_fa}</Badge>
                  </div>
                  <Link
                    href={`/projects/${project.id}/workspace`}
                    className="text-[15.5px] font-semibold text-[var(--fg-primary)]"
                  >
                    {project.title_fa}
                  </Link>
                  <p className="text-[13px] text-[var(--fg-secondary)]">{project.summary}</p>
                  <p className="mt-auto text-[12.5px] text-[var(--fg-tertiary)]">
                    {toPersianDigits(project.active_members)} عضو فعال
                    {project.open_seats > 0 &&
                      ` — ${toPersianDigits(project.open_seats)} جای خالی`}
                  </p>
                </Card>
              </li>
            ))}
          </ul>
        )}
      </section>

      {openApplications.length > 0 && (
        <section className="flex flex-col gap-3">
          <h2 className="text-[19px] font-semibold">درخواست‌های در جریان</h2>
          <ul className="flex flex-col gap-2">
            {openApplications.map((application) => (
              <li key={application.id}>
                <Card className="flex flex-wrap items-center justify-between gap-3 p-4">
                  <div className="flex flex-col gap-0.5">
                    <Link
                      href={`/projects/${application.project_id}`}
                      className="text-[14.5px] font-medium text-[var(--fg-primary)]"
                    >
                      {application.project_title_fa ?? 'پروژه'}
                    </Link>
                    <span className="text-[12.5px] text-[var(--fg-tertiary)]">
                      {formatRelative(application.created_at)}
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    {application.match_score !== null && (
                      <Badge tone="brand">
                        {toPersianDigits(Math.round(application.match_score))}٪ تطابق
                      </Badge>
                    )}
                    <Badge tone="info">{application.status_fa}</Badge>
                  </div>
                </Card>
              </li>
            ))}
          </ul>
        </section>
      )}

      {projects.length > 0 && (
        <Card className="flex flex-col gap-2">
          <CardTitle>قدم بعدی</CardTitle>
          <p className="text-[13.5px] text-[var(--fg-secondary)]">
            کارت را در فضای کاری هر پروژه دنبال کن: مراحل، وظایف و گفتگوی تیم همان‌جاست.
          </p>
        </Card>
      )}
    </div>
  );
}
