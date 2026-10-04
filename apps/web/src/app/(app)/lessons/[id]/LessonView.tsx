'use client';

import Link from 'next/link';
import { type ReactNode, useEffect, useState } from 'react';

import { ErrorLine, errorText } from '@/components/admin/common';
import { SkeletonCard } from '@/components/ui/Skeleton';
import { fetchLesson, type LessonDetail } from '@/lib/api/learning';
import { useSession } from '@/lib/auth/use-session';
import { formatDateTime } from '@/lib/format/date';
import { toPersianDigits } from '@/lib/format/digits';

/**
 * یک درس‌نامه. متن Markdown در مرورگر و با بارگذاری تنبل رندر می‌شود (صفحه پشت ورود است و
 * سرور بی‌نشست نمی‌تواند آن را بسازد). بخش «چالش‌ها» به آزمون‌های روزانهٔ وصل‌شده می‌رود.
 * متن درس‌نامه برخلاف زمان آزمون **قابل کپی** است — فقط آزمون قفل دارد.
 */
export function LessonView({ lessonId }: { lessonId: string }) {
  const { accessToken } = useSession();
  const [lesson, setLesson] = useState<LessonDetail | null>(null);
  const [body, setBody] = useState<ReactNode>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!accessToken) return;
    let cancelled = false;
    (async () => {
      try {
        const detail = await fetchLesson(lessonId, accessToken);
        if (cancelled) return;
        setLesson(detail);
        const { render } = await import('@/lib/markdown/render');
        if (!cancelled) setBody(render(detail.body_md, (href: string) => href));
      } catch (cause) {
        if (!cancelled) setError(errorText(cause));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [accessToken, lessonId]);

  if (error) return <ErrorLine>{error}</ErrorLine>;
  if (!lesson) return <SkeletonCard label="در حال بارگذاری درس‌نامه" />;

  return (
    <article className="mx-auto flex max-w-[72ch] flex-col gap-6">
      <nav aria-label="مسیر" className="text-[13.5px]">
        <Link href={`/courses/${lesson.offering_id}/lessons`} className="text-[var(--fg-brand)]">
          ← درس‌نامه‌های این درس
        </Link>
      </nav>
      <header className="flex flex-col gap-1">
        <h1>{lesson.title_fa}</h1>
        <p className="text-[13.5px] text-[var(--fg-secondary)]">
          حدود {toPersianDigits(lesson.est_minutes)} دقیقه مطالعه
        </p>
      </header>
      <div className="flex flex-col gap-4 text-[16px] [&_h2]:mt-8 [&_p]:leading-[2.1]">
        {body ?? <SkeletonCard label="در حال آماده‌سازی متن" />}
      </div>

      {lesson.checkpoints.length > 0 && (
        <section
          aria-labelledby="lesson-checkpoints"
          className="flex flex-col gap-3 rounded-[var(--radius-xl)] bg-[var(--brand-50)] p-5"
        >
          <h2 id="lesson-checkpoints" className="text-[17px]">
            حالا خودت را بسنج
          </h2>
          <ul className="flex flex-col gap-2 text-[14px]">
            {lesson.checkpoints.map((checkpoint) => (
              <li key={checkpoint.quiz_id}>
                {checkpoint.title_fa} · {toPersianDigits(checkpoint.duration_min)} دقیقه · تا{' '}
                {toPersianDigits(formatDateTime(checkpoint.closes_at))}
              </li>
            ))}
          </ul>
          <Link href="/dashboard" className="text-[14px] font-semibold text-[var(--fg-brand)]">
            شروع از «امروز» در داشبورد ←
          </Link>
        </section>
      )}
    </article>
  );
}
