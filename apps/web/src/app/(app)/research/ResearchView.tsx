'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';

import { Badge, type BadgeTone } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { SkeletonCard } from '@/components/ui/Skeleton';
import { ApiError, NetworkError } from '@/lib/api/client';
import { type Level, type LevelState, type Track, fetchTrack } from '@/lib/api/research';
import { useSession } from '@/lib/auth/use-session';
import { toPersianDigits } from '@/lib/format/digits';

/**
 * `/research` — مسیر پژوهش چهارسطحی، FR-RES-01.
 *
 * چهار سطح پشت‌سرهم؛ فقط «سطح جاری» دکمهٔ کار دارد، بقیه یا تأییدشده‌اند
 * یا قفل. موضوع رزروشده با شمارش روزهای باقی‌مانده تا آزادسازی دیده
 * می‌شود — قاعدهٔ ۳۰ روز بی‌تحرکی (FR-RES-03) نباید غافلگیرکننده باشد.
 */

const STATE_TONE: Record<LevelState, BadgeTone> = {
  LOCKED: 'neutral',
  AVAILABLE: 'brand',
  IN_PROGRESS: 'brand',
  SUBMITTED: 'warning',
  APPROVED: 'success',
};

export function ResearchView() {
  // ویترین عمومی (ADR-0017): مهمان می‌بیند و هر اقدامی خودش پشت ورود است.
  const { accessToken, loading: sessionLoading } = useSession({ required: false });
  const [track, setTrack] = useState<Track | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (sessionLoading) return;
    fetchTrack(accessToken)
      .then(setTrack)
      .catch((cause) =>
        setError(
          cause instanceof ApiError || cause instanceof NetworkError
            ? cause.message
            : 'مسیر پژوهش بارگذاری نشد.',
        ),
      );
  }, [accessToken, sessionLoading]);

  return (
    <div className="flex flex-col gap-8">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="flex flex-col gap-1">
          <h1>مسیر پژوهش</h1>
          <p className="text-[15px] text-[var(--fg-secondary)]">
            از مرور ادبیات تا مقالهٔ Q1 — هر سطح با تأیید منتور باز می‌شود.
          </p>
        </div>
        <nav aria-label="بخش‌های پژوهش" className="flex flex-wrap gap-2">
          <Button asChild variant="secondary" size="sm">
            <Link href="/research/topics">بانک موضوع</Link>
          </Button>
          {accessToken && (
            <Button asChild variant="secondary" size="sm">
              <Link href="/research/outputs">مقاله‌های من</Link>
            </Button>
          )}
          {track?.can_review && (
            <Button asChild size="sm">
              <Link href="/research/review">صف بررسی</Link>
            </Button>
          )}
        </nav>
      </header>

      {error && (
        <p role="alert" className="text-[13.5px] text-[var(--fg-danger)]">
          {error}
        </p>
      )}

      {track === null ? (
        !error && <SkeletonCard label="در حال بارگذاری مسیر پژوهش" />
      ) : (
        <>
          {track.completed && (
            <Card variant="raised" className="flex flex-col gap-1">
              <p className="text-[16px] font-semibold">هر چهار سطح را گذرانده‌ای.</p>
              <p className="text-[14px] text-[var(--fg-secondary)]">
                مقاله‌هایت را در «مقاله‌های من» ثبت کن تا پس از راستی‌آزمایی در نیمرخت دیده شوند.
              </p>
            </Card>
          )}

          {track.topic && (
            <Card className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex flex-col gap-1">
                <p className="text-[13px] text-[var(--fg-tertiary)]">موضوع پژوهش تو</p>
                <Link
                  href={`/research/topics/${track.topic.id}`}
                  className="text-[15.5px] font-semibold hover:text-[var(--fg-brand)]"
                >
                  {track.topic.title}
                </Link>
              </div>
              <div className="flex items-center gap-2">
                <Badge tone={track.topic.status === 'TAKEN' ? 'success' : 'warning'}>
                  {track.topic.status_fa}
                </Badge>
                {track.topic.idle_days_left !== null && (
                  <span className="text-[13px] text-[var(--fg-secondary)]">
                    {toPersianDigits(track.topic.idle_days_left)} روز تا آزاد شدن، اگر تحویلی نفرستی
                  </span>
                )}
              </div>
            </Card>
          )}

          {!track.can_participate && (
            <p className="text-[14px] text-[var(--fg-secondary)]">
              راهنمای سطح‌ها برای همه باز است؛ ثبت تحویل مخصوص دانشجویان است.
            </p>
          )}

          <ol className="flex flex-col gap-4">
            {track.levels.map((level) => (
              <li key={level.level}>
                <LevelCard level={level} current={track.current_level === level.level} />
              </li>
            ))}
          </ol>
        </>
      )}
    </div>
  );
}

function LevelCard({ level, current }: { level: Level; current: boolean }) {
  const locked = level.state === 'LOCKED';
  const latest = level.submissions[0];
  return (
    <Card
      variant={current ? 'raised' : 'flat'}
      // قفل با حاشیهٔ خط‌چین و نشان «قفل» دیده می‌شود، نه با کم‌رنگ کردن کل
      // کارت: opacity متن را به ۲٫۶ به ۱ می‌رساند (M7-14).
      className={locked ? 'flex flex-col gap-3 border-dashed shadow-none' : 'flex flex-col gap-3'}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-3">
          <span
            aria-hidden
            className="flex size-9 items-center justify-center rounded-full bg-[var(--bg-sunken)] text-[15px] font-bold"
          >
            {toPersianDigits(level.level)}
          </span>
          <h2 className="text-[17px] font-semibold">
            <span className="sr-only">سطح {toPersianDigits(level.level)}: </span>
            {level.title_fa}
          </h2>
        </div>
        <div className="flex items-center gap-2">
          {level.points && (
            <span className="text-[12.5px] text-[var(--fg-tertiary)]">
              {toPersianDigits(Number(level.points))} امتیاز پژوهش
            </span>
          )}
          <Badge tone={STATE_TONE[level.state]}>{level.state_fa}</Badge>
        </div>
      </div>
      <p className="text-[14px] leading-[1.9] text-[var(--fg-secondary)]">{level.deliverable_fa}</p>
      {latest?.status === 'CHANGES_REQUESTED' && (
        <p className="rounded-[var(--radius-md)] bg-[var(--bg-sunken)] p-3 text-[13.5px] leading-[1.9]">
          <span className="font-semibold">بازخورد منتور: </span>
          {latest.feedback}
        </p>
      )}
      <div className="flex flex-wrap items-center gap-3">
        <Button asChild size="sm" variant={current && !locked ? 'primary' : 'secondary'}>
          <Link href={`/research/level/${level.level}`}>
            {level.state === 'APPROVED'
              ? 'مرور تحویل'
              : level.state === 'LOCKED'
                ? 'دیدن راهنما'
                : level.state === 'SUBMITTED'
                  ? 'دیدن تحویل'
                  : 'راهنما و تحویل'}
          </Link>
        </Button>
        {level.mentor?.name && (
          <span className="text-[12.5px] text-[var(--fg-tertiary)]">
            منتور: {level.mentor.name}
          </span>
        )}
      </div>
    </Card>
  );
}
