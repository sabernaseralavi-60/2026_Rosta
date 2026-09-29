'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';

import { PageBanner } from '@/components/domain/PageBanner';
import { Badge } from '@/components/ui/Badge';
import { Card, CardDescription, CardTitle } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { Progress } from '@/components/ui/Progress';
import { SkeletonCard } from '@/components/ui/Skeleton';
import { ApiError, NetworkError } from '@/lib/api/client';
import {
  type CityProject,
  type CityWorkflow,
  fetchCityProjects,
  fetchCityWorkflow,
} from '@/lib/api/city';
import { toPersianDigits } from '@/lib/format/digits';

/**
 * `/city` — آزمایشگاه شهر هوشمند، §14 سند v1 «Shared City Platform».
 *
 * الگوی هشت‌مرحله‌ای برای همه یکی است و همین‌جا دیده می‌شود؛ پروژه‌های
 * شهری منتشرشده با پیشرفت گردش‌کارشان فهرست می‌شوند.
 */
export function CityLabView() {
  const [workflow, setWorkflow] = useState<CityWorkflow | null>(null);
  const [projects, setProjects] = useState<CityProject[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([fetchCityWorkflow(), fetchCityProjects()])
      .then(([spec, list]) => {
        setWorkflow(spec);
        setProjects(list);
      })
      .catch((cause) => setError(messageFor(cause)));
  }, []);

  if (error) {
    return (
      <p role="alert" className="text-[13.5px] text-[var(--fg-danger)]">
        {error}
      </p>
    );
  }
  if (!workflow || !projects) return <SkeletonCard label="در حال بارگذاری آزمایشگاه" />;

  return (
    <div className="flex flex-col gap-8">
      <PageBanner
        photo="research"
        title="آزمایشگاه شهر هوشمند"
        description={`تولید خدمات هوشمند ترافیکی برای شهرداری‌ها، در هشت مرحلهٔ ثابت. هر مرحله تحویل‌دادنی، چک‌لیست کیفیت و مسئول دارد و فقط پس از تأیید مرحلهٔ قبل باز می‌شود. کل مسیر ${toPersianDigits(workflow.total_days / 7)} هفته و ${toPersianDigits(workflow.total_points)} امتیاز است؛ کامل کردنش نشان «شهرساز» دارد.`}
      />

      <section aria-labelledby="stages-title" className="flex flex-col gap-3">
        <h2 id="stages-title" className="text-[18px] font-semibold">
          هشت مرحله
        </h2>
        <ol className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {workflow.stages.map((stage) => (
            <li key={stage.number}>
              <Card className="flex h-full flex-col gap-1.5">
                <div className="flex items-center justify-between gap-2">
                  <span className="flex h-7 w-7 items-center justify-center rounded-full bg-[var(--brand-600)] text-[13px] font-semibold text-white">
                    {toPersianDigits(stage.number)}
                  </span>
                  <span className="text-[12px] text-[var(--fg-tertiary)]">
                    {toPersianDigits(stage.duration_days / 7)} هفته ·{' '}
                    {toPersianDigits(stage.points)} امتیاز
                  </span>
                </div>
                <CardTitle className="text-[16px]">{stage.title_fa}</CardTitle>
                <CardDescription>{stage.deliverable_fa}</CardDescription>
              </Card>
            </li>
          ))}
        </ol>
        <p className="text-[13.5px] text-[var(--fg-secondary)]">
          قاعدهٔ حیاتی مرحلهٔ ۳: راستی‌آزمایی OSM بدون شواهد تصویری تأیید نمی‌شود — دادهٔ OSM ایران
          ناقص است و مدلی که روی دادهٔ خام ساخته شود، بی‌ارزش است.
        </p>
      </section>

      <section aria-labelledby="projects-title" className="flex flex-col gap-3">
        <h2 id="projects-title" className="text-[18px] font-semibold">
          پروژه‌های شهری
        </h2>
        {projects.length === 0 ? (
          <EmptyState
            title="هنوز پروژهٔ شهری منتشر نشده"
            description="استاد یا منتور می‌تواند پروژهٔ «حل مسئلهٔ واقعی» را با الگوی شهر هوشمند بسازد."
          />
        ) : (
          <ul className="grid gap-4 md:grid-cols-2">
            {projects.map((item) => (
              <li key={item.project.id}>
                <Link href={`/projects/${item.project.id}`} className="block">
                  <Card variant="interactive" className="flex flex-col gap-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <CardTitle className="text-[16px]">{item.project.title_fa}</CardTitle>
                      {item.workflow_completed_at && <Badge tone="success">کامل</Badge>}
                    </div>
                    <CardDescription>{item.project.summary}</CardDescription>
                    <Progress
                      value={item.approved_count}
                      max={8}
                      label="پیشرفت گردش‌کار"
                      valueText={`${toPersianDigits(item.approved_count)} از ۸ مرحله`}
                    />
                    <p className="text-[12.5px] text-[var(--fg-tertiary)]">
                      {item.current_stage
                        ? `مرحلهٔ جاری: ${workflow.stages[item.current_stage - 1]?.title_fa}`
                        : 'هر هشت مرحله تأیید شده'}
                      {item.area_km2 !== null &&
                        ` · محدوده ${toPersianDigits(item.area_km2.toFixed(1))} کیلومتر مربع`}
                    </p>
                  </Card>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function messageFor(cause: unknown): string {
  if (cause instanceof ApiError || cause instanceof NetworkError) return cause.message;
  return 'آزمایشگاه بارگذاری نشد. کمی بعد دوباره تلاش کن.';
}
