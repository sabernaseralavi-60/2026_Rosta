'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';

import { ProjectCard } from '@/components/domain/ProjectCard';
import { Button } from '@/components/ui/Button';
import { EmptyState } from '@/components/ui/EmptyState';
import { Progress } from '@/components/ui/Progress';
import { SkeletonCard, SkeletonText } from '@/components/ui/Skeleton';
import { ApiError, NetworkError } from '@/lib/api/client';
import {
  type Recommendation,
  fetchRecommendations,
  sendRecommendationFeedback,
} from '@/lib/api/projects';
import { useSession } from '@/lib/auth/use-session';
import { toPersianDigits } from '@/lib/format/digits';

/**
 * `/onboarding/results` — §3.3، «لحظهٔ طلایی» §01.
 *
 * تنها هدف این صفحه: دانشجو باید ببیند وقتی که برای فرم گذاشت، همین حالا
 * چیزی برگرداند. هیچ فرم دیگری اینجا نیست.
 *
 * دکمهٔ «این به من نمی‌خورد» عمداً از همین اولین برخورد در دسترس است
 * (§8.9): بازخورد زودهنگام، هم پیشنهادها را بهتر می‌کند و هم به کاربر
 * می‌فهماند که کنترل دستِ اوست.
 */

const RESULT_LIMIT = 6;

export function ResultsView() {
  const { accessToken, loading: sessionLoading } = useSession();

  const [items, setItems] = useState<Recommendation[] | null>(null);
  const [completeness, setCompleteness] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [dismissing, setDismissing] = useState<string | null>(null);

  useEffect(() => {
    if (!accessToken) return;
    let cancelled = false;

    fetchRecommendations(accessToken, RESULT_LIMIT)
      .then((result) => {
        if (cancelled) return;
        setItems(result.items);
        setCompleteness(result.profile_completeness);
      })
      .catch((cause) => {
        if (!cancelled) {
          setError(messageFor(cause));
          setItems([]);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [accessToken]);

  async function dismiss(projectId: string) {
    if (!accessToken) return;
    setDismissing(projectId);
    try {
      await sendRecommendationFeedback(projectId, 'NOT_RELEVANT', accessToken);
      setItems((prev) => prev?.filter((item) => item.project.id !== projectId) ?? null);
    } catch {
      // بازخورد، عملیات حیاتی نیست: اگر نرسید، کارت سر جایش می‌ماند.
    } finally {
      setDismissing(null);
    }
  }

  if (sessionLoading || items === null) {
    return (
      <div className="flex w-full max-w-[44rem] flex-col gap-4">
        <SkeletonText label="در حال آماده‌سازی پیشنهادها" />
        <SkeletonCard />
        <SkeletonCard />
      </div>
    );
  }

  const incomplete = completeness < 1;

  return (
    <div className="flex w-full max-w-[44rem] flex-col gap-6">
      <header className="flex flex-col gap-2">
        <h1 className="text-[26px] font-bold text-[var(--fg-primary)]">
          {items.length > 0
            ? `${toPersianDigits(items.length)} پروژه برای تو پیدا شد`
            : 'هنوز پیشنهاد مناسبی پیدا نشد'}
        </h1>
        <p className="text-[14.5px] leading-[1.9] text-[var(--fg-secondary)]">
          این‌ها بر اساس همان چیزی است که دربارهٔ خودت گفتی. کنار هر پروژه نوشته‌ایم
          <strong className="font-semibold"> چرا </strong>
          به تو پیشنهاد شده — اگر دلیلی درست نیست، نیمرخت را اصلاح کن و نتیجه عوض می‌شود.
        </p>
      </header>

      {incomplete && (
        <div className="flex flex-col gap-2 rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-4">
          <Progress
            value={Math.round(completeness * 100)}
            max={100}
            label="کامل بودن نیمرخ"
            valueText={`${toPersianDigits(Math.round(completeness * 100))}٪`}
          />
          <p className="text-[13px] text-[var(--fg-secondary)]">
            هرچه نیمرخت کامل‌تر باشد، پیشنهادها دقیق‌تر می‌شوند.
          </p>
          <Link
            href="/onboarding/survey/1"
            className="self-start text-[13.5px] font-medium text-[var(--brand-700)] hover:underline"
          >
            تکمیل نیمرخ
          </Link>
        </div>
      )}

      {error && (
        <p role="alert" className="text-[13.5px] text-[var(--danger-600)]">
          {error}
        </p>
      )}

      {items.length === 0 ? (
        <EmptyState
          title="فعلاً پروژه‌ای که به تو بخورد باز نیست"
          description="بانک پروژه‌ها مدام به‌روز می‌شود. می‌توانی همهٔ پروژه‌های باز را ببینی و خودت انتخاب کنی."
          action={
            <Button asChild>
              <Link href="/projects">دیدن بانک پروژه</Link>
            </Button>
          }
        />
      ) : (
        <ul className="flex flex-col gap-4">
          {items.map((item) => (
            <li key={item.project.id}>
              <ProjectCard
                project={item.project}
                matchScore={item.match_score}
                reasons={item.reasons}
                isStretch={item.is_stretch}
                footer={
                  <button
                    type="button"
                    onClick={() => dismiss(item.project.id)}
                    disabled={dismissing === item.project.id}
                    className="text-[12.5px] text-[var(--fg-tertiary)] hover:text-[var(--fg-secondary)] hover:underline disabled:opacity-50"
                  >
                    این به من نمی‌خورد
                  </button>
                }
              />
            </li>
          ))}
        </ul>
      )}

      <div className="flex flex-col gap-3 sm:flex-row-reverse">
        <Button asChild size="lg" className="sm:flex-1">
          <Link href="/dashboard">برو به داشبورد</Link>
        </Button>
        <Button asChild variant="secondary" size="lg" className="sm:flex-1">
          <Link href="/projects">همهٔ پروژه‌ها</Link>
        </Button>
      </div>
    </div>
  );
}

function messageFor(cause: unknown): string {
  if (cause instanceof ApiError || cause instanceof NetworkError) return cause.message;
  return 'پیشنهادها بارگذاری نشد. کمی بعد دوباره تلاش کن.';
}
