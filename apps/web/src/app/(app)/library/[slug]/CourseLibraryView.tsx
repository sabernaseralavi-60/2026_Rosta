'use client';

import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';

import { MaterialRow } from '@/components/domain/MaterialRow';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card, CardDescription, CardTitle } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { SkeletonCard } from '@/components/ui/Skeleton';
import { ApiError, NetworkError } from '@/lib/api/client';
import { type CourseDetail, type OfferingRef, enroll, fetchCourse } from '@/lib/api/courses';
import { useSession } from '@/lib/auth/use-session';
import { toPersianDigits } from '@/lib/format/digits';

/**
 * `/library/[slug]` — صفحهٔ درس.
 *
 * سه کار در یک صفحه، به همین ترتیب:
 *
 * ۱. **ثبت‌نام** — راه رایگان رسیدن به محتوا؛ اول نشان داده می‌شود.
 * ۲. **کتابخانه** — چه چیزی هست و هر کدام چه وضعی دارد.
 * ۳. **اشتراک** — فقط وقتی چیزی قفل باشد، و با قیمتی که سرور گفته.
 */

export function CourseLibraryView({ slug }: { slug: string }) {
  const { accessToken, loading: sessionLoading } = useSession({ required: false });
  const [course, setCourse] = useState<CourseDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setCourse(await fetchCourse(slug, accessToken));
      setError(null);
    } catch (cause) {
      setError(messageFor(cause));
    }
  }, [accessToken, slug]);

  useEffect(() => {
    if (sessionLoading) return;
    void load();
  }, [load, sessionLoading]);

  if (error) {
    return (
      <Card className="flex flex-col gap-4">
        <CardTitle as="h1">این درس پیدا نشد</CardTitle>
        <CardDescription>{error}</CardDescription>
        <div>
          <Button variant="secondary" asChild>
            <Link href="/library">بازگشت به کتابخانه</Link>
          </Button>
        </div>
      </Card>
    );
  }

  if (!course) return <SkeletonCard />;

  const locked = course.materials.filter((m) => !m.access.allowed);
  const monthly = course.plans.find((p) => p.scope === 'ALL_COURSES');

  return (
    <div className="flex flex-col gap-8">
      <header className="flex flex-col gap-3">
        <Link
          href="/library"
          className="text-[13px] text-[var(--fg-secondary)] hover:text-[var(--fg-brand)]"
        >
          ← کتابخانهٔ دروس
        </Link>
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-[26px] font-bold text-[var(--fg-primary)]">{course.title_fa}</h1>
          {course.degree_level_fa && <Badge tone="neutral">{course.degree_level_fa}</Badge>}
          {course.credits && <Badge tone="neutral">{toPersianDigits(course.credits)} واحد</Badge>}
        </div>
        {course.title_en && (
          <p className="text-[13px] text-[var(--fg-tertiary)]">{course.title_en}</p>
        )}
        {course.description && (
          <p className="max-w-[70ch] text-[14.5px] leading-7 text-[var(--fg-secondary)]">
            {course.description}
          </p>
        )}
        {course.topics.length > 0 && (
          <ul className="flex flex-wrap gap-1.5">
            {course.topics.map((topic) => (
              <li key={topic}>
                <Badge tone="brand">{topic}</Badge>
              </li>
            ))}
          </ul>
        )}
      </header>

      {course.my_enrollment_offering_id ? (
        <Card className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex flex-col gap-1">
            <CardTitle as="h2">شما دانشجوی این درس هستید</CardTitle>
            <CardDescription>محتوای این درس برای شما رایگان است.</CardDescription>
          </div>
          <Button asChild>
            <Link href={`/courses/${course.my_enrollment_offering_id}`}>ورود به کلاس</Link>
          </Button>
        </Card>
      ) : (
        course.offerings.length > 0 && (
          <section className="flex flex-col gap-3">
            <h2 className="text-[19px] font-semibold text-[var(--fg-primary)]">ارائه‌های باز</h2>
            <ul className="flex flex-col gap-3">
              {course.offerings.map((offering) => (
                <EnrollRow
                  key={offering.id}
                  offering={offering}
                  accessToken={accessToken}
                  onEnrolled={load}
                />
              ))}
            </ul>
          </section>
        )
      )}

      <section className="flex flex-col gap-3">
        <div className="flex items-baseline justify-between gap-3">
          <h2 className="text-[19px] font-semibold text-[var(--fg-primary)]">کتابخانهٔ درس</h2>
          <span className="text-[13px] text-[var(--fg-tertiary)]">
            {toPersianDigits(course.materials.length)} محتوا
          </span>
        </div>

        {course.materials.length === 0 ? (
          <p className="rounded-[var(--radius-lg)] border border-dashed border-[var(--border-default)] px-4 py-6 text-center text-[13.5px] text-[var(--fg-secondary)]">
            هنوز محتوایی برای این درس بارگذاری نشده است.
          </p>
        ) : (
          <ul className="flex flex-col gap-3">
            {course.materials.map((material) => (
              <MaterialRow key={material.id} material={material} accessToken={accessToken} />
            ))}
          </ul>
        )}
      </section>

      {locked.length > 0 && monthly && (
        <Card variant="raised" className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex flex-col gap-1">
            <CardTitle as="h2">{toPersianDigits(locked.length)} محتوا پشت اشتراک است</CardTitle>
            <CardDescription>
              اگر دانشجوی این درس نیستید، با اشتراک ماهانه به کتابخانهٔ همهٔ دروس دسترسی پیدا
              می‌کنید.
            </CardDescription>
          </div>
          <Button asChild>
            <Link href="/pricing">دیدن طرح‌ها</Link>
          </Button>
        </Card>
      )}
    </div>
  );
}

/** یک ارائه با فرم ثبت‌نام — کد فقط وقتی خواسته می‌شود که ارائه کد دارد. */
function EnrollRow({
  offering,
  accessToken,
  onEnrolled,
}: {
  offering: OfferingRef;
  accessToken: string | null;
  onEnrolled: () => Promise<void>;
}) {
  const [code, setCode] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  async function submit() {
    if (!accessToken) return;
    setBusy(true);
    setError(null);
    try {
      const result = await enroll(offering.id, accessToken, code.trim() || undefined);
      setDone(
        result.status === 'PENDING'
          ? 'درخواست شما ثبت شد؛ پس از تأیید استاد به کلاس دسترسی پیدا می‌کنید.'
          : 'ثبت‌نام انجام شد.',
      );
      await onEnrolled();
    } catch (cause) {
      setError(messageFor(cause));
    } finally {
      setBusy(false);
    }
  }

  const full = offering.capacity !== null && offering.active_students >= offering.capacity;

  return (
    <li>
      <Card className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-col gap-1">
            <span className="text-[15px] font-semibold text-[var(--fg-primary)]">
              {offering.term_title_fa}
            </span>
            <span className="text-[12.5px] text-[var(--fg-tertiary)]">
              {offering.instructor_name ?? 'استاد اعلام نشده'} ·{' '}
              {toPersianDigits(offering.active_students)}
              {offering.capacity ? ` از ${toPersianDigits(offering.capacity)}` : ''} دانشجو
            </span>
          </div>
          <div className="flex flex-wrap items-end gap-2">
            {offering.has_enrollment_code && (
              <Input
                label="کد ثبت‌نام"
                value={code}
                onChange={(event) => setCode(event.target.value)}
                hint="کدی که استاد اعلام کرده"
                className="w-36"
              />
            )}
            <Button size="sm" onClick={submit} disabled={busy || full || !accessToken || !!done}>
              {full ? 'ظرفیت تکمیل' : offering.requires_approval ? 'درخواست ثبت‌نام' : 'ثبت‌نام'}
            </Button>
          </div>
        </div>

        {offering.requires_approval && !done && (
          <p className="text-[12.5px] text-[var(--fg-tertiary)]">
            ثبت‌نام در این ارائه نیازمند تأیید استاد است.
          </p>
        )}
        {done && <p className="text-[12.5px] text-[var(--fg-success)]">{done}</p>}
        {error && (
          <p role="alert" className="text-[12.5px] text-[var(--fg-danger)]">
            {error}
          </p>
        )}
      </Card>
    </li>
  );
}

function messageFor(cause: unknown): string {
  if (cause instanceof ApiError || cause instanceof NetworkError) return cause.message;
  return 'خطای غیرمنتظره‌ای رخ داد.';
}
