'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';

import { BadgeIcon } from '@/components/domain/BadgeTile';
import { CategoryTiles } from '@/components/domain/CategoryTiles';
import { HealthIndicator } from '@/components/domain/HealthIndicator';
import { NextStepCard } from '@/components/domain/NextStepCard';
import { PointsTrend } from '@/components/domain/PointsTrend';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { Progress } from '@/components/ui/Progress';
import { SkeletonCard } from '@/components/ui/Skeleton';
import { ApiError } from '@/lib/api/client';
import { fetchDashboard, points, type StudentDashboard } from '@/lib/api/points';
import { useSession } from '@/lib/auth/use-session';
import { formatDateLong, formatDateTime } from '@/lib/format/date';
import { formatNumber, toPersianDigits } from '@/lib/format/digits';

/**
 * داشبورد دانشجو — FR-DASH-01، M5-10.
 *
 * ترتیب از بالا، همان ترتیب اهمیت: **یک** قدم بعدی (بزرگ‌ترین عنصر)،
 * امتیاز و روندش، دروس، پروژه‌ها، رویدادهای دو هفتهٔ آینده، نشان‌های اخیر.
 * همه از یک درخواست (`GET /me/dashboard`) — روی اینترنت همراه، شش
 * رفت‌وبرگشت یعنی شش بار اسکلت خالی.
 */

const UPCOMING_LABEL = {
  QUIZ_OPENS: 'آزمون',
  QUIZ_CLOSES: 'آزمون',
  MILESTONE_DUE: 'پروژه',
} as const;

export function DashboardView() {
  const { accessToken, loading } = useSession({ required: false });
  const [data, setData] = useState<StudentDashboard | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (loading || !accessToken) return;
    let cancelled = false;
    fetchDashboard(accessToken)
      .then((value) => !cancelled && setData(value))
      .catch((cause: unknown) => {
        if (cancelled) return;
        setError(cause instanceof ApiError ? cause.message : 'داشبورد بارگذاری نشد.');
      });
    return () => {
      cancelled = true;
    };
  }, [accessToken, loading]);

  if (error) {
    return <EmptyState title="داشبورد بارگذاری نشد" description={error} />;
  }
  if (!data) {
    // هم‌شکل بخش‌های واقعی و دست‌کم یک صفحه بلند: پیش از M7-15 یک کارت کوچک
    // بود و آمدن داشبورد «کارهای من» و پیشنهادها را از دید بیرون می‌راند
    // (CLS ۰٫۴۶). حالا آن‌ها از اول زیر خط دیدند.
    return (
      <div className="flex flex-col gap-8">
        <SkeletonCard label="در حال بارگذاری داشبورد" className="min-h-[360px]" />
        <SkeletonCard className="min-h-[220px]" />
        <SkeletonCard className="min-h-[220px]" />
      </div>
    );
  }

  const { level } = data.points;
  const toNext = Math.ceil(points(level.to_next));

  return (
    <div className="flex flex-col gap-8">
      <NextStepCard step={data.next_step} />

      <section aria-labelledby="points-title" className="flex flex-col gap-4">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 id="points-title" className="text-[19px] font-semibold">
            امتیاز و سطح
          </h2>
          <Link
            href="/me/points"
            className="text-[13.5px] font-medium text-[var(--fg-brand)] hover:underline"
          >
            دفتر امتیاز
          </Link>
        </div>
        <Card className="flex flex-col gap-5">
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div className="flex flex-col gap-1">
              <span className="text-[13px] text-[var(--fg-secondary)]">
                سطح {toPersianDigits(level.level)} — {level.title_fa}
              </span>
              <span className="text-[34px] font-bold leading-none">
                {formatNumber(points(data.points.total))}
                <span className="ms-1.5 text-[15px] font-medium text-[var(--fg-secondary)]">
                  امتیاز
                </span>
              </span>
            </div>
            <div className="min-w-56 flex-1 sm:max-w-80">
              <Progress
                value={points(level.ratio) * 100}
                max={100}
                label="تا سطح بعد"
                valueText={
                  level.next_at === null ? 'بالاترین سطح' : `${formatNumber(toNext)} امتیاز مانده`
                }
              />
            </div>
          </div>
          <CategoryTiles
            totals={data.points.term_by_category}
            caption={`امتیاز این نیم‌سال: ${formatNumber(points(data.points.term_total))}`}
          />
          <PointsTrend trend={data.trend} />
        </Card>
      </section>

      <div className="grid gap-8 lg:grid-cols-2">
        <section aria-labelledby="courses-title" className="flex flex-col gap-3">
          <h2 id="courses-title" className="text-[19px] font-semibold">
            دروس من
          </h2>
          {data.courses.length === 0 ? (
            <EmptyState
              title="هنوز درسی نداری"
              description="با ثبت‌نام در یک درس، جزوه‌ها، آزمون‌ها و نمرهٔ یادگیری اینجا می‌آیند."
              action={
                <Button asChild>
                  <Link href="/courses">دیدن دروس</Link>
                </Button>
              }
            />
          ) : (
            <ul className="flex flex-col gap-3">
              {data.courses.map((course) => (
                <li key={course.offering_id}>
                  <Card variant="interactive" className="flex flex-col gap-3">
                    <div className="flex flex-wrap items-baseline justify-between gap-2">
                      <Link
                        href={`/courses/${course.offering_id}`}
                        className="text-[15.5px] font-semibold text-[var(--fg-primary)]"
                      >
                        {course.course_title_fa}
                      </Link>
                      <span className="text-[12.5px] text-[var(--fg-tertiary)]">
                        {course.term_title_fa}
                        {course.current_week_number !== null &&
                          ` · هفتهٔ ${toPersianDigits(course.current_week_number)}`}
                      </span>
                    </div>
                    {course.study_ratio !== null && (
                      <Progress
                        value={Math.round(points(course.study_ratio) * 100)}
                        max={100}
                        label="مطالعهٔ منابع الزامی"
                        valueText={`${toPersianDigits(Math.round(points(course.study_ratio) * 100))}٪`}
                      />
                    )}
                    <p className="text-[13px] text-[var(--fg-secondary)]">
                      نمرهٔ یادگیری:{' '}
                      <span className="font-semibold text-[var(--fg-primary)]">
                        {course.learning_score === null
                          ? 'هنوز محاسبه نشده'
                          : `${toPersianDigits(Math.round(points(course.learning_score)))} از ۱۰۰`}
                      </span>
                    </p>
                  </Card>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section aria-labelledby="projects-title" className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 id="projects-title" className="text-[19px] font-semibold">
              پروژه‌های من
            </h2>
            <Button asChild variant="secondary" size="sm">
              <Link href="/projects/new">پروژهٔ تازه</Link>
            </Button>
          </div>
          {data.projects.length === 0 ? (
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
            <ul className="flex flex-col gap-3">
              {data.projects.map((project) => (
                <li key={project.project_id}>
                  <Card variant="interactive" className="flex flex-col gap-2">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <Link
                        href={`/projects/${project.project_id}/workspace`}
                        className="text-[15.5px] font-semibold text-[var(--fg-primary)]"
                      >
                        {project.title_fa}
                      </Link>
                      {project.status === 'IN_PROGRESS' && (
                        <HealthIndicator health={project.health} label={project.health_fa} />
                      )}
                    </div>
                    {project.required_milestones > 0 && (
                      <Progress
                        value={project.approved_milestones}
                        max={project.required_milestones}
                        label="مراحل تأییدشده"
                      />
                    )}
                    {project.next_milestone_title && (
                      <p className="text-[13px] text-[var(--fg-secondary)]">
                        مرحلهٔ بعد: {project.next_milestone_title}
                        {project.next_milestone_due_on &&
                          ` — مهلت ${formatDateLong(project.next_milestone_due_on)}`}
                      </p>
                    )}
                  </Card>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      <div className="grid gap-8 lg:grid-cols-2">
        <section aria-labelledby="upcoming-title" className="flex flex-col gap-3">
          <h2 id="upcoming-title" className="text-[19px] font-semibold">
            دو هفتهٔ آینده
          </h2>
          {data.upcoming.length === 0 ? (
            <p className="text-[14px] text-[var(--fg-secondary)]">
              آزمون یا مهلتی در دو هفتهٔ آینده نداری.
            </p>
          ) : (
            <ul className="flex flex-col divide-y divide-[var(--border-subtle)] rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-surface)]">
              {data.upcoming.map((event) => (
                <li key={`${event.kind}-${event.href}-${event.at}`}>
                  <Link
                    href={event.href}
                    className="flex flex-wrap items-baseline justify-between gap-2 px-4 py-3 hover:bg-[var(--bg-sunken)]"
                  >
                    <span className="text-[14px] text-[var(--fg-primary)]">
                      <span className="me-2 text-[12px] text-[var(--fg-tertiary)]">
                        {UPCOMING_LABEL[event.kind]}
                      </span>
                      {event.title}
                    </span>
                    <span className="text-[12.5px] text-[var(--fg-secondary)]">
                      {formatDateTime(event.at)}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section aria-labelledby="badges-title" className="flex flex-col gap-3">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 id="badges-title" className="text-[19px] font-semibold">
              نشان‌های اخیر
            </h2>
            <Link
              href="/me/badges"
              className="text-[13.5px] font-medium text-[var(--fg-brand)] hover:underline"
            >
              همهٔ نشان‌ها
            </Link>
          </div>
          {data.recent_badges.length === 0 ? (
            <p className="text-[14px] text-[var(--fg-secondary)]">
              هنوز نشانی نگرفته‌ای. شرط هر نشان را در صفحهٔ نشان‌ها ببین.
            </p>
          ) : (
            <ul className="flex flex-wrap gap-4">
              {data.recent_badges.map((badge) => (
                <li key={badge.code} className="flex items-center gap-2.5">
                  <BadgeIcon icon={badge.icon} earned tier={badge.tier} />
                  <span className="flex flex-col">
                    <span className="text-[14px] font-medium">{badge.title_fa}</span>
                    <span className="text-[12px] text-[var(--fg-tertiary)]">{badge.tier_fa}</span>
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </div>
  );
}
