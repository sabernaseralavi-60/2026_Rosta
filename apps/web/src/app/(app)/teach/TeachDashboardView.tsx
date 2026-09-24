'use client';

import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';

import { errorText, StatTile } from '@/components/admin/common';
import { fa } from '@/components/teach/common';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { SkeletonCard } from '@/components/ui/Skeleton';
import { fetchTeachDashboard, type Queue, type TeachDashboard } from '@/lib/api/teach';
import { useSession } from '@/lib/auth/use-session';
import { toPersianDigits } from '@/lib/format/digits';

/**
 * `/teach` — داشبورد استثنامحور (FR-DASH-02، M5-11).
 *
 * فقط آنچه اقدام می‌خواهد: صف‌ها با قدیمی‌ترین مورد، دانشجو و پروژهٔ در
 * خطر. ارائه‌ای که همه‌چیزش روبه‌راه است، فقط یک ردیف آمار می‌گیرد.
 */
export function TeachDashboardView() {
  const { accessToken } = useSession();
  const [data, setData] = useState<TeachDashboard | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    if (!accessToken) return;
    setError(null);
    fetchTeachDashboard(accessToken)
      .then(setData)
      .catch((cause) => setError(errorText(cause)));
  }, [accessToken]);

  useEffect(load, [load]);

  if (error && !data) {
    return (
      <EmptyState
        title="داشبورد بارگذاری نشد"
        description={error}
        action={<Button onClick={load}>تلاش دوباره</Button>}
      />
    );
  }
  if (!data) return <SkeletonCard label="در حال بارگذاری داشبورد استاد" />;

  const attention = data.needs_attention;
  const nothing =
    attention.essays_pending.count +
      attention.enrollment_requests.count +
      attention.grade_appeals.count +
      attention.deliverables_pending.count ===
      0 &&
    attention.students_at_risk.length === 0 &&
    attention.projects_at_risk.length === 0;

  return (
    <div className="flex flex-col gap-8">
      <header className="flex flex-col gap-1">
        <h1>آنچه اقدام می‌خواهد</h1>
        <p className="text-[14px] text-[var(--fg-secondary)]">
          فقط کارهای منتظر تو. هرچه اینجا نیست، روبه‌راه است.
        </p>
      </header>

      <section aria-labelledby="queues" className="flex flex-col gap-3">
        <h2 id="queues" className="sr-only">
          صف‌ها
        </h2>
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <QueueTile
            label="پاسخ تشریحی بی‌نمره"
            queue={attention.essays_pending}
            href="/teach/quizzes"
          />
          <QueueTile
            label="درخواست ثبت‌نام"
            queue={attention.enrollment_requests}
            href="/teach/offerings"
          />
          <QueueTile label="اعتراض به نمره" queue={attention.grade_appeals} href="/teach/quizzes" />
          <QueueTile label="تحویل‌دادنی پروژه" queue={attention.deliverables_pending} />
        </div>
      </section>

      {nothing && (
        <EmptyState
          title="هیچ کاری منتظر تو نیست"
          description="صف‌ها خالی‌اند و دانشجو یا پروژه‌ای در خطر نیست. برای ساخت آزمون یا انتشار هفتهٔ بعد به ارائه‌هایت برو."
          action={
            <Button asChild>
              <Link href="/teach/offerings">ارائه‌های من</Link>
            </Button>
          }
        />
      )}

      {attention.students_at_risk.length > 0 && (
        <section aria-labelledby="students-risk" className="flex flex-col gap-2">
          <h2 id="students-risk" className="text-[18px]">
            دانشجوی در خطر
          </h2>
          <ul className="flex flex-col divide-y divide-[var(--border-subtle)] rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-surface)]">
            {attention.students_at_risk.map((student) => (
              <li
                key={`${student.offering_id}-${student.user_id}`}
                className="flex flex-wrap items-center justify-between gap-2 px-4 py-3"
              >
                <div className="flex flex-col">
                  <span className="font-medium">{student.display_name ?? 'بی‌نام'}</span>
                  <span className="text-[12.5px] text-[var(--fg-tertiary)]">
                    {student.course_title_fa}
                  </span>
                </div>
                <div className="flex items-center gap-3">
                  <Badge tone="warning">{student.reason}</Badge>
                  <Link
                    href={`/teach/offerings/${student.offering_id}/grades`}
                    className="text-[13.5px] text-[var(--fg-brand)]"
                  >
                    دفتر نمره
                  </Link>
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}

      {attention.projects_at_risk.length > 0 && (
        <section aria-labelledby="projects-risk" className="flex flex-col gap-2">
          <h2 id="projects-risk" className="text-[18px]">
            پروژهٔ در خطر
          </h2>
          <ul className="flex flex-col divide-y divide-[var(--border-subtle)] rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-surface)]">
            {attention.projects_at_risk.map((project) => (
              <li
                key={project.id}
                className="flex flex-wrap items-center justify-between gap-2 px-4 py-3"
              >
                <Link
                  href={`/projects/${project.id}`}
                  className="font-medium hover:text-[var(--fg-brand)]"
                >
                  {project.title_fa}
                </Link>
                <span className="flex items-center gap-2 text-[13px] text-[var(--fg-secondary)]">
                  <Badge tone={project.health === 'STALLED' ? 'danger' : 'warning'}>
                    {project.health_fa}
                  </Badge>
                  {toPersianDigits(project.days_inactive)} روز بی‌فعالیت
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section aria-labelledby="offering-stats" className="flex flex-col gap-2">
        <h2 id="offering-stats" className="text-[18px]">
          ارائه‌ها در یک نگاه
        </h2>
        {data.offerings.length === 0 ? (
          <p className="text-[14px] text-[var(--fg-secondary)]">
            هنوز ارائه‌ای به نام تو ثبت نشده است. ارائه را مدیر آموزشی می‌سازد.
          </p>
        ) : (
          <div className="grid gap-3 md:grid-cols-2">
            {data.offerings.map((offering) => (
              <Card key={offering.id} variant="interactive" className="p-0">
                <Link href={`/teach/offerings/${offering.id}`} className="flex flex-col gap-3 p-4">
                  <span className="font-semibold">{offering.title_fa}</span>
                  <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-[13px] sm:grid-cols-4">
                    <Metric label="دانشجو" value={toPersianDigits(offering.students)} />
                    <Metric
                      label="میانگین مطالعه"
                      value={
                        offering.avg_progress === null
                          ? '—'
                          : `${fa(Number(offering.avg_progress) * 100, 0)}٪`
                      }
                    />
                    <Metric label="میانگین آزمون (از ۲۰)" value={fa(offering.avg_quiz_score, 1)} />
                    <Metric label="نمرهٔ یادگیری" value={fa(offering.avg_learning_score, 0)} />
                  </dl>
                </Link>
              </Card>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function QueueTile({ label, queue, href }: { label: string; queue: Queue; href?: string }) {
  const hint =
    queue.count > 0 && queue.oldest_days !== null
      ? `قدیمی‌ترین: ${toPersianDigits(queue.oldest_days)} روز`
      : 'خالی';
  const tile = <StatTile label={label} value={queue.count} hint={hint} tone="warning" />;
  if (!href || queue.count === 0) return tile;
  return (
    <Link href={href} className="rounded-[var(--radius-lg)] focus-visible:outline-2">
      {tile}
    </Link>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col">
      <dt className="text-[var(--fg-tertiary)]">{label}</dt>
      <dd className="font-semibold tabular-nums">{value}</dd>
    </div>
  );
}
