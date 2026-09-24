'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';

import { ProjectCard } from '@/components/domain/ProjectCard';
import { Button } from '@/components/ui/Button';
import { EmptyState } from '@/components/ui/EmptyState';
import { Progress } from '@/components/ui/Progress';
import { SkeletonCard } from '@/components/ui/Skeleton';
import { fetchMe, type Me } from '@/lib/api/profile';
import { type Recommendation, fetchRecommendations } from '@/lib/api/projects';
import { useSession } from '@/lib/auth/use-session';
import { toPersianDigits } from '@/lib/format/digits';

/**
 * بخش «قدم بعدی» داشبورد — §7.1، FR-DASH-01.
 *
 * «داشبورد خالی ممنوع است. هر حالت خالی باید یک دعوت به اقدام مشخص
 * باشد» (اصل ۲ §00). سه حالت:
 *
 * ۱. نیمرخ شروع نشده ⇒ دعوت به ارزیابی.
 * ۲. نیمرخ ناقص ⇒ نوار پیشرفت + پیشنهادهای فعلی. مسدودکننده نیست.
 * ۳. نیمرخ کامل ⇒ پیشنهادهای برتر.
 *
 * `NextStepCard` کامل و کارت‌های امتیاز در M5-10 می‌آیند؛ اینجا همان
 * اسکلت با دادهٔ واقعی M1 پر شده است.
 */

const TOP_COUNT = 3;

export function OnboardingNotice() {
  const { accessToken, loading } = useSession({ required: false });

  const [me, setMe] = useState<Me | null>(null);
  const [recommended, setRecommended] = useState<Recommendation[] | null>(null);

  useEffect(() => {
    if (loading || !accessToken) return;
    let cancelled = false;

    fetchMe(accessToken)
      .then((value) => !cancelled && setMe(value))
      .catch(() => !cancelled && setMe(null));

    fetchRecommendations(accessToken, TOP_COUNT)
      .then((result) => !cancelled && setRecommended(result.items))
      .catch(() => !cancelled && setRecommended([]));

    return () => {
      cancelled = true;
    };
  }, [accessToken, loading]);

  if (loading || (accessToken && me === null && recommended === null)) {
    return <SkeletonCard label="در حال بارگذاری داشبورد" />;
  }

  const onboarding = me?.onboarding;
  const notStarted =
    onboarding?.state === 'BASIC_INFO_REQUIRED' || onboarding?.state === 'SURVEY_REQUIRED';

  if (notStarted) {
    return (
      <EmptyState
        title="نیمرخت را کامل کن"
        description="با پر کردن ارزیابی کوتاه، پروژه‌های متناسب با مهارت‌ها و علاقه‌هایت را پیشنهاد می‌دهیم. حدود ۲ دقیقه وقت می‌گیرد."
        action={
          <Button asChild>
            <Link href={onboarding?.next_route ?? '/onboarding/basic'}>شروع ارزیابی</Link>
          </Button>
        }
      />
    );
  }

  return (
    <div className="flex flex-col gap-6">
      {onboarding && onboarding.completed_steps < onboarding.total_steps && (
        <div className="flex flex-col gap-2.5 rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-5">
          <Progress
            value={onboarding.completed_steps}
            max={onboarding.total_steps}
            label="کامل بودن نیمرخ"
            valueText={`${toPersianDigits(onboarding.completed_steps)} از ${toPersianDigits(onboarding.total_steps)} گام`}
          />
          <p className="text-[13.5px] text-[var(--fg-secondary)]">
            هر گامی که پر کنی، پیشنهادها دقیق‌تر می‌شوند.
          </p>
          <Button asChild variant="secondary" size="sm" className="self-start">
            <Link href={`/onboarding/survey/${onboarding.completed_steps + 1}`}>
              ادامهٔ ارزیابی
            </Link>
          </Button>
        </div>
      )}

      {recommended && recommended.length > 0 ? (
        <section className="flex flex-col gap-4">
          <div className="flex items-baseline justify-between gap-3">
            <h2 className="text-[19px] font-semibold">پیشنهادهای تو</h2>
            <Link
              href="/projects"
              className="text-[13.5px] font-medium text-[var(--fg-brand)] hover:underline"
            >
              همهٔ پروژه‌ها
            </Link>
          </div>
          <ul className="flex flex-col gap-4">
            {recommended.map((item) => (
              <li key={item.project.id}>
                <ProjectCard
                  project={item.project}
                  matchScore={item.match_score}
                  reasons={item.reasons}
                  isStretch={item.is_stretch}
                />
              </li>
            ))}
          </ul>
        </section>
      ) : (
        <EmptyState
          title="هنوز پروژه‌ای برای تو پیدا نشد"
          description="بانک پروژه مدام به‌روز می‌شود. می‌توانی همهٔ پروژه‌های باز را ببینی و خودت انتخاب کنی."
          action={
            <Button asChild>
              <Link href="/projects">دیدن بانک پروژه</Link>
            </Button>
          }
        />
      )}
    </div>
  );
}
