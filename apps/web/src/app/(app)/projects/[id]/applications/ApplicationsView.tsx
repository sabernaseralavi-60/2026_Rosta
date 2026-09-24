'use client';

import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';

import { MatchRing } from '@/components/domain/MatchRing';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card, CardDescription, CardTitle } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { SkeletonCard, SkeletonText } from '@/components/ui/Skeleton';
import { Textarea } from '@/components/ui/Textarea';
import { ApiError, NetworkError } from '@/lib/api/client';
import {
  type Alternative,
  type Application,
  type ApplicationDecision,
  decideApplication,
  fetchApplications,
} from '@/lib/api/workspace';
import { useSession } from '@/lib/auth/use-session';
import { formatRelative } from '@/lib/format/date';
import { toPersianDigits } from '@/lib/format/digits';

/**
 * `/projects/[id]/applications` — §3.4، FR-PRJ-04، §7.5.
 *
 * مدیر پروژه انگیزه‌نامه، امتیاز تطابق و تفکیک شش‌گانه را **کنار هم**
 * می‌بیند؛ همان چیزی که سند می‌خواهد. مرتب‌سازی با سرور است و بر اساس
 * امتیاز تطابق، نه تاریخ: مدیری که بیست درخواست دارد باید از بالا
 * بخواند.
 *
 * پس از «رد»، سه پروژهٔ جایگزین که سرور برگردانده نمایش داده می‌شود —
 * §7.5 «رد محترمانه». این‌ها همان‌هایی هستند که در اعلان رد برای دانشجو
 * می‌روند، پس مدیر می‌بیند دانشجو چه پیشنهادی گرفت.
 */

const BREAKDOWN_LABELS: Record<string, string> = {
  skill: 'مهارت',
  asset: 'امکانات',
  interest: 'علاقه',
  time: 'زمان',
  style: 'سبک کار',
  goal: 'هدف',
};

export function ApplicationsView({ id }: { id: string }) {
  const { accessToken, loading: sessionLoading } = useSession();
  const [applications, setApplications] = useState<Application[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [denied, setDenied] = useState(false);

  const load = useCallback(async () => {
    if (!accessToken) return;
    try {
      setApplications(await fetchApplications(id, accessToken));
      setError(null);
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 403) setDenied(true);
      else setError(messageFor(cause));
    }
  }, [accessToken, id]);

  useEffect(() => {
    if (sessionLoading) return;
    void load();
  }, [load, sessionLoading]);

  if (denied) {
    return (
      <Card className="flex flex-col gap-3">
        <CardTitle>تصمیم دربارهٔ درخواست‌ها با مدیر پروژه است</CardTitle>
        <CardDescription>شما برای این پروژه چنین اختیاری ندارید.</CardDescription>
        <Button asChild variant="secondary" className="self-start">
          <Link href={`/projects/${id}`}>بازگشت به پروژه</Link>
        </Button>
      </Card>
    );
  }

  if (applications === null) {
    return (
      <div className="flex flex-col gap-4">
        <SkeletonText label="در حال بارگذاری درخواست‌ها" />
        <SkeletonCard />
      </div>
    );
  }

  const pending = applications.filter((row) => row.status === 'PENDING');
  const decided = applications.filter((row) => row.status !== 'PENDING');

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-1">
        <h1>درخواست‌های پیوستن</h1>
        <p className="text-[15px] text-[var(--fg-secondary)]">
          به ترتیب امتیاز تطابق مرتب شده‌اند — بالاترین تطابق، اول.
        </p>
      </header>

      {error && (
        <p role="alert" className="text-[13.5px] text-[var(--fg-danger)]">
          {error}
        </p>
      )}

      {pending.length === 0 ? (
        <EmptyState
          title="درخواست بازی نیست"
          description="وقتی دانشجویی درخواست بدهد، همین‌جا با امتیاز تطابقش می‌آید."
          action={
            <Button asChild variant="secondary">
              <Link href={`/projects/${id}/workspace`}>فضای کاری پروژه</Link>
            </Button>
          }
        />
      ) : (
        <ul className="flex flex-col gap-4">
          {pending.map((application) => (
            <li key={application.id}>
              <ApplicationCard
                application={application}
                accessToken={accessToken!}
                onDecided={load}
              />
            </li>
          ))}
        </ul>
      )}

      {decided.length > 0 && (
        <details>
          <summary className="cursor-pointer text-[14px] font-medium text-[var(--fg-secondary)]">
            درخواست‌های تعیین‌تکلیف‌شده ({toPersianDigits(decided.length)})
          </summary>
          <ul className="mt-3 flex flex-col gap-2">
            {decided.map((application) => (
              <li
                key={application.id}
                className="flex flex-wrap items-center gap-2 text-[13.5px] text-[var(--fg-secondary)]"
              >
                <span>{application.applicant_name ?? 'متقاضی'}</span>
                <Badge tone={application.status === 'ACCEPTED' ? 'success' : 'neutral'}>
                  {application.status_fa}
                </Badge>
                {application.decided_at && (
                  <span className="text-[12px] text-[var(--fg-tertiary)]">
                    {formatRelative(application.decided_at)}
                  </span>
                )}
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

function ApplicationCard({
  application,
  accessToken,
  onDecided,
}: {
  application: Application;
  accessToken: string;
  onDecided: () => void;
}) {
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState<ApplicationDecision | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [alternatives, setAlternatives] = useState<Alternative[] | null>(null);

  async function decide(decision: ApplicationDecision) {
    setBusy(decision);
    setError(null);
    try {
      const result = await decideApplication(
        application.id,
        { decision, note: note.trim() || null },
        accessToken,
      );
      if (decision === 'REJECTED' && result.alternatives.length > 0) {
        // پیش از تازه‌سازی نشان داده می‌شود: مدیر باید ببیند دانشجو
        // به‌جای این پروژه چه پیشنهادی گرفت.
        setAlternatives(result.alternatives);
      } else {
        onDecided();
      }
    } catch (cause) {
      setError(messageFor(cause));
    } finally {
      setBusy(null);
    }
  }

  if (alternatives) {
    return (
      <Card variant="raised" className="flex flex-col gap-3">
        <CardTitle>درخواست رد شد</CardTitle>
        <CardDescription>
          این سه پروژه به‌عنوان جایگزین به {application.applicant_name ?? 'متقاضی'} پیشنهاد شد:
        </CardDescription>
        <ul className="flex flex-col gap-2">
          {alternatives.map((alternative) => (
            <li key={alternative.project.id} className="flex flex-col gap-1">
              <div className="flex flex-wrap items-center gap-2">
                <Link
                  href={`/projects/${alternative.project.id}`}
                  className="text-[14px] font-medium text-[var(--fg-brand)]"
                >
                  {alternative.project.title_fa}
                </Link>
                <Badge tone="brand">
                  {toPersianDigits(Math.round(alternative.match_score))}٪ تطابق
                </Badge>
              </div>
              {alternative.reasons[0] && (
                <p className="text-[12.5px] text-[var(--fg-tertiary)]">
                  {alternative.reasons[0].text}
                </p>
              )}
            </li>
          ))}
        </ul>
        <Button size="sm" variant="secondary" className="self-start" onClick={onDecided}>
          باشد
        </Button>
      </Card>
    );
  }

  return (
    <Card variant="raised" className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        {application.match_score !== null && <MatchRing score={application.match_score} />}
        <div className="flex flex-col gap-0.5">
          <span className="text-[15.5px] font-semibold text-[var(--fg-primary)]">
            {application.applicant_name ?? 'متقاضی'}
          </span>
          <span className="text-[12.5px] text-[var(--fg-tertiary)]">
            {formatRelative(application.created_at)}
            {application.role_title_fa && ` — برای نقش «${application.role_title_fa}»`}
          </span>
        </div>
      </div>

      <blockquote className="border-s-2 border-[var(--border-default)] ps-3 text-[14px] leading-[1.95] text-[var(--fg-secondary)]">
        {application.motivation}
      </blockquote>

      {application.match_breakdown && (
        <details>
          <summary className="cursor-pointer text-[13px] font-medium text-[var(--fg-brand)]">
            تفکیک امتیاز تطابق
          </summary>
          <dl className="mt-2 grid gap-1.5 sm:grid-cols-2">
            {Object.entries(application.match_breakdown).map(([key, value]) => (
              <div key={key} className="flex items-center gap-2 text-[12.5px]">
                <dt className="w-16 shrink-0 text-[var(--fg-tertiary)]">
                  {BREAKDOWN_LABELS[key] ?? key}
                </dt>
                <dd className="flex flex-1 items-center gap-2">
                  <span className="h-1.5 flex-1 overflow-hidden rounded-[var(--radius-full)] bg-[var(--bg-sunken)]">
                    <span
                      className="block h-full rounded-[var(--radius-full)] bg-[var(--brand-500)]"
                      style={{ width: `${Math.max(0, Math.min(100, value))}%` }}
                    />
                  </span>
                  <span className="w-9 text-end tabular-nums text-[var(--fg-tertiary)]">
                    {toPersianDigits(Math.round(value))}
                  </span>
                </dd>
              </div>
            ))}
          </dl>
          <p className="mt-2 text-[12px] text-[var(--fg-tertiary)]">
            این عدد، عکسِ لحظهٔ ارسال درخواست است — همان چیزی که دانشجو آن روز دید.
          </p>
        </details>
      )}

      <Textarea
        label="پیام به متقاضی"
        hint="اختیاری برای پذیرش؛ برای رد، یک جملهٔ کوتاه فرق بزرگی می‌کند."
        value={note}
        onChange={(event) => setNote(event.target.value)}
        maxLength={1000}
        rows={2}
      />

      {error && (
        <p role="alert" className="text-[13px] text-[var(--fg-danger)]">
          {error}
        </p>
      )}

      <div className="flex flex-wrap gap-2">
        <Button size="sm" loading={busy === 'ACCEPTED'} onClick={() => decide('ACCEPTED')}>
          پذیرش
        </Button>
        <Button
          size="sm"
          variant="secondary"
          loading={busy === 'WAITLISTED'}
          onClick={() => decide('WAITLISTED')}
        >
          فهرست انتظار
        </Button>
        <Button
          size="sm"
          variant="ghost"
          loading={busy === 'REJECTED'}
          onClick={() => decide('REJECTED')}
        >
          رد
        </Button>
      </div>
    </Card>
  );
}

function messageFor(cause: unknown): string {
  if (cause instanceof ApiError || cause instanceof NetworkError) return cause.message;
  return 'انجام نشد. کمی بعد دوباره تلاش کن.';
}
