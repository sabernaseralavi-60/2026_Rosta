'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';

import { MatchRing } from '@/components/domain/MatchRing';
import { ApplyPanel } from './ApplyPanel';
import { ReasonList } from '@/components/domain/ReasonList';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card, CardTitle } from '@/components/ui/Card';
import { SkeletonCard, SkeletonText } from '@/components/ui/Skeleton';
import { ApiError, NetworkError } from '@/lib/api/client';
import { type Breakdown, type ProjectDetail, fetchProject } from '@/lib/api/projects';
import { useSession } from '@/lib/auth/use-session';
import { toPersianDigits } from '@/lib/format/digits';

/**
 * `/projects/[id]` — §3.4.
 *
 * «جزئیات، تطابق من، تیم، مراحل، درخواست پیوستن.» تیم و مراحل داخل
 * فضای کاری (`/projects/[id]/workspace`) هستند، چون فقط برای عضو تیم
 * معنا دارند؛ این صفحه عمومی است.
 *
 * تفکیک شش‌گانهٔ امتیاز عمداً نمایش داده می‌شود — اصل ۳ §00: «دانشجو
 * باید بتواند روی هر عدد کلیک کند و ببیند از کجا آمده. جعبهٔ سیاه
 * اعتماد را می‌کشد.»
 */

const BREAKDOWN_LABELS: { key: keyof Breakdown; label: string }[] = [
  { key: 'skill', label: 'مهارت' },
  { key: 'asset', label: 'امکانات' },
  { key: 'interest', label: 'علاقه' },
  { key: 'time', label: 'زمان' },
  { key: 'style', label: 'سبک کار' },
  { key: 'goal', label: 'هدف' },
];

export function ProjectDetailView({ id }: { id: string }) {
  const { accessToken, loading: sessionLoading } = useSession({ required: false });

  const [project, setProject] = useState<ProjectDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (sessionLoading) return;
    let cancelled = false;

    fetchProject(id, accessToken)
      .then((detail) => !cancelled && setProject(detail))
      .catch((cause) => !cancelled && setError(messageFor(cause)));

    return () => {
      cancelled = true;
    };
  }, [accessToken, id, sessionLoading]);

  if (error) {
    return (
      <div className="flex flex-col gap-4">
        <p role="alert" className="text-[15px] text-[var(--danger-600)]">
          {error}
        </p>
        <Button asChild variant="secondary" className="self-start">
          <Link href="/projects">بازگشت به فهرست پروژه‌ها</Link>
        </Button>
      </div>
    );
  }

  if (!project) {
    return (
      <div className="flex flex-col gap-4">
        <SkeletonText label="در حال بارگذاری پروژه" />
        <SkeletonCard />
      </div>
    );
  }

  return (
    <article className="flex flex-col gap-8">
      <header className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-1.5">
          <Badge tone="brand">{project.kind_fa}</Badge>
          {project.workflow === 'CITY' && (
            <Link href="/city">
              <Badge tone="accent">آزمایشگاه شهر هوشمند — گردش‌کار ۸ مرحله‌ای</Badge>
            </Link>
          )}
          <Badge tone="neutral">دشواری: {project.difficulty_fa}</Badge>
          {project.tags.map((tag) => (
            <Badge key={tag} tone="neutral">
              {tag}
            </Badge>
          ))}
        </div>
        <h1>{project.title_fa}</h1>
        <p className="text-[15.5px] leading-[1.95] text-[var(--fg-secondary)]">
          {project.summary}
        </p>
      </header>

      {project.match && (
        <Card variant="raised" className="flex flex-col gap-4">
          <div className="flex items-center gap-4">
            {/* پروژهٔ حذف‌شده حلقه نمی‌گیرد: «۰٪» کنار دلایل مثبت، پیام
                اشتباهی می‌دهد. به‌جایش علت را می‌نویسیم. */}
            {!project.match.is_excluded && <MatchRing score={project.match.match_score} />}
            <div className="flex flex-col gap-0.5">
              <CardTitle>تطابق تو با این پروژه</CardTitle>
              <p className="text-[13px] text-[var(--fg-secondary)]">
                {project.match.exclusion_note ?? 'بر اساس نیمرخی که پر کرده‌ای محاسبه شده است.'}
              </p>
            </div>
          </div>

          <ReasonList reasons={project.match.reasons} />

          <details className="group">
            <summary className="cursor-pointer text-[13.5px] font-medium text-[var(--brand-700)]">
              این عدد از کجا آمد؟
            </summary>
            <dl className="mt-3 grid gap-2 sm:grid-cols-2">
              {BREAKDOWN_LABELS.map(({ key, label }) => {
                const value = project.match?.breakdown[key] ?? 0;
                return (
                  <div key={key} className="flex items-center gap-3">
                    <dt className="w-20 shrink-0 text-[13px] text-[var(--fg-secondary)]">
                      {label}
                    </dt>
                    <dd className="flex flex-1 items-center gap-2">
                      <div className="h-1.5 flex-1 overflow-hidden rounded-[var(--radius-full)] bg-[var(--bg-sunken)]">
                        <div
                          className="h-full rounded-[var(--radius-full)] bg-[var(--brand-500)]"
                          style={{ width: `${Math.max(0, Math.min(100, value))}%` }}
                        />
                      </div>
                      <span className="w-10 text-end text-[12.5px] tabular-nums text-[var(--fg-tertiary)]">
                        {toPersianDigits(Math.round(value))}
                      </span>
                    </dd>
                  </div>
                );
              })}
            </dl>
            <p className="mt-3 text-[12.5px] leading-[1.9] text-[var(--fg-tertiary)]">
              وزن هر بخش به کامل بودن نیمرخ تو بستگی دارد: بخشی که هنوز پاسخ نداده‌ای،
              در محاسبه شرکت نمی‌کند.
            </p>
          </details>
        </Card>
      )}

      <section className="flex flex-col gap-3">
        <h2 className="text-[19px] font-semibold">شرح پروژه</h2>
        <div className="flex flex-col gap-3 text-[15px] leading-[2] text-[var(--fg-primary)]">
          {project.description.split('\n\n').map((paragraph, index) => (
            <p key={index}>{paragraph}</p>
          ))}
        </div>
      </section>

      <section className="grid gap-4 sm:grid-cols-2">
        <Card className="flex flex-col gap-3">
          <CardTitle>مهارت‌های لازم</CardTitle>
          {project.required_skills.length === 0 ? (
            <p className="text-[13.5px] text-[var(--fg-tertiary)]">
              مهارت پیش‌نیاز خاصی ندارد.
            </p>
          ) : (
            <ul className="flex flex-col gap-2">
              {project.required_skills.map((skill) => (
                <li
                  key={skill.skill_id}
                  className="flex items-center justify-between gap-2 text-[13.5px]"
                >
                  <span className="text-[var(--fg-primary)]">{skill.title_fa}</span>
                  <span className="flex items-center gap-1.5">
                    <span className="text-[var(--fg-tertiary)] tabular-nums">
                      سطح {toPersianDigits(skill.min_level)}
                    </span>
                    {skill.is_teachable && <Badge tone="success">قابل یادگیری</Badge>}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card className="flex flex-col gap-3">
          <CardTitle>امکانات لازم</CardTitle>
          {project.required_assets.length === 0 ? (
            <p className="text-[13.5px] text-[var(--fg-tertiary)]">
              وسیلهٔ خاصی لازم ندارد.
            </p>
          ) : (
            <ul className="flex flex-col gap-2">
              {project.required_assets.map((asset) => (
                <li
                  key={asset.asset_id}
                  className="flex items-center justify-between gap-2 text-[13.5px]"
                >
                  <span className="text-[var(--fg-primary)]">{asset.title_fa}</span>
                  <Badge tone={asset.is_mandatory ? 'warning' : 'neutral'}>
                    {asset.is_mandatory ? 'الزامی' : 'ترجیحی'}
                  </Badge>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </section>

      <Card className="flex flex-col gap-2">
        <CardTitle>در پایان چه تحویل می‌شود؟</CardTitle>
        <p className="text-[14.5px] leading-[1.95] text-[var(--fg-secondary)]">
          {project.expected_output}
        </p>
      </Card>

      <ApplyPanel project={project} accessToken={accessToken} />
    </article>
  );
}

function messageFor(cause: unknown): string {
  if (cause instanceof ApiError || cause instanceof NetworkError) return cause.message;
  return 'این پروژه بارگذاری نشد. کمی بعد دوباره تلاش کن.';
}
