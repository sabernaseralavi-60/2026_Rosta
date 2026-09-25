'use client';

import { useEffect, useState } from 'react';

import { Badge } from '@/components/ui/Badge';
import { Card, CardDescription, CardTitle } from '@/components/ui/Card';
import { Progress } from '@/components/ui/Progress';
import { SkeletonText } from '@/components/ui/Skeleton';
import { ApiError, NetworkError } from '@/lib/api/client';
import {
  type Contribution,
  type ContributionMember,
  type PeerAverage,
  fetchContribution,
  fetchPeerEvaluationSummary,
} from '@/lib/api/workspace';
import { formatNumber, toPersianDigits } from '@/lib/format/digits';

/**
 * تحلیل مشارکت تیمی — FR-PRJ-08، ADR-0026.
 *
 * سهم هر عضو از **کارِ ثبت‌شده** در سامانه، نه داوری دربارهٔ او. کار حضوری و
 * گفت‌وگوی بیرون از سامانه دیده نمی‌شود؛ پس شمارهای خام همیشه کنار درصد می‌آید
 * و هیچ‌جا برچسب «مقصر» نداریم. مدیر و ناظر همهٔ اعضا را می‌بینند و عضو عادی
 * فقط ردیف خودش را — سرور تعیین می‌کند (`scope`)، اینجا فقط نمایش است.
 *
 * برای مدیرِ پروژهٔ بسته‌شده، میانگین ارزیابی همتا کنار هر عضو می‌آید: دو
 * نشانهٔ جدا که در یک عدد ادغام نمی‌شوند.
 */

const STATUS_LABELS: Record<string, string> = {
  LEFT: 'تیم را ترک کرد',
  REMOVED: 'از تیم حذف شد',
};

export function ContributionTab({
  projectId,
  accessToken,
  isLead,
  projectStatus,
}: {
  projectId: string;
  accessToken: string;
  isLead: boolean;
  projectStatus: string;
}) {
  const [data, setData] = useState<Contribution | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [peers, setPeers] = useState<Map<string, PeerAverage>>(new Map());

  useEffect(() => {
    let cancelled = false;
    fetchContribution(projectId, accessToken)
      .then((result) => {
        if (!cancelled) setData(result);
      })
      .catch((cause) => {
        if (!cancelled) setError(messageFor(cause));
      });
    return () => {
      cancelled = true;
    };
  }, [projectId, accessToken]);

  // میانگین همتا فقط برای مدیرِ پروژهٔ بسته‌شده؛ نبودنش خطا نیست.
  useEffect(() => {
    if (!isLead || projectStatus !== 'COMPLETED') return;
    let cancelled = false;
    fetchPeerEvaluationSummary(projectId, accessToken)
      .then((summary) => {
        if (!cancelled) setPeers(new Map(summary.members.map((item) => [item.user_id, item])));
      })
      .catch(() => {
        if (!cancelled) setPeers(new Map());
      });
    return () => {
      cancelled = true;
    };
  }, [isLead, projectStatus, projectId, accessToken]);

  if (error) {
    return (
      <Card>
        <p role="alert" className="text-[13.5px] text-[var(--fg-secondary)]">
          {error}
        </p>
      </Card>
    );
  }
  if (!data) {
    return (
      <Card>
        <SkeletonText label="در حال بارگذاری تحلیل مشارکت" />
      </Card>
    );
  }

  const live = data.dimensions.filter((dimension) => dimension.weight > 0);
  const everyoneEmpty = data.members.every((member) => member.share_percent === null);

  return (
    <Card className="flex flex-col gap-5" aria-labelledby="contribution-title">
      <div className="flex flex-col gap-1">
        <CardTitle as="h2" id="contribution-title">
          {data.scope === 'TEAM' ? 'سهم هر عضو از کار ثبت‌شده' : 'سهم من از کار ثبت‌شده'}
        </CardTitle>
        <CardDescription>
          این عدد فقط از چیزهایی می‌آید که در سامانه ثبت شده است: تحویل‌دادنی تأییدشده، فعالیت
          تأییدشده، وظیفهٔ انجام‌شده و پیام‌های گفتگو. کار حضوری و بحث بیرون از سامانه دیده نمی‌شود؛
          پس آن را داوری نگیر، شروع گفت‌وگو بگیر. به امتیاز و گواهی هم ربطی ندارد.
        </CardDescription>
      </div>

      {everyoneEmpty ? (
        <p className="text-[13.5px] text-[var(--fg-secondary)]">
          هنوز چیزی ثبت نشده است. با اولین تحویل تأییدشده، وظیفهٔ انجام‌شده یا پیام، سهم‌ها پدیدار
          می‌شود.
        </p>
      ) : null}

      <ul className="flex flex-col gap-5">
        {data.members.map((member) => (
          <MemberRow
            key={member.user_id}
            member={member}
            data={data}
            peer={peers.get(member.user_id)}
          />
        ))}
      </ul>

      {data.scope === 'TEAM' && live.length > 0 && (
        <section
          aria-labelledby="contribution-weights"
          className="flex flex-col gap-1 border-t border-[var(--border-subtle)] pt-4"
        >
          <h3
            id="contribution-weights"
            className="text-[13px] font-medium text-[var(--fg-secondary)]"
          >
            وزنِ هر بخش در سهم نهایی
          </h3>
          <ul className="flex flex-wrap gap-x-4 gap-y-1 text-[12.5px] text-[var(--fg-tertiary)]">
            {live.map((dimension) => (
              <li key={dimension.dimension}>
                {dimension.title}: {formatNumber(Math.round(dimension.weight * 100))}٪
                {dimension.team_total !== null &&
                  ` (کل تیم: ${toPersianDigits(dimension.team_total)})`}
              </li>
            ))}
          </ul>
          {live.length < data.dimensions.length && (
            <p className="text-[12.5px] text-[var(--fg-tertiary)]">
              بخشی که کل تیم در آن چیزی ثبت نکرده کنار گذاشته می‌شود تا کسی برایش جریمه نشود.
            </p>
          )}
        </section>
      )}
    </Card>
  );
}

function MemberRow({
  member,
  data,
  peer,
}: {
  member: ContributionMember;
  data: Contribution;
  peer: PeerAverage | undefined;
}) {
  const name = member.full_name ?? 'عضو تیم';
  const share = member.share_percent;
  return (
    <li className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[14.5px] font-medium text-[var(--fg-primary)]">{name}</span>
        {member.is_lead && <Badge tone="neutral">مدیر پروژه</Badge>}
        {STATUS_LABELS[member.status] && (
          <Badge tone="warning">{STATUS_LABELS[member.status]}</Badge>
        )}
        {member.is_silent && <Badge tone="info">هنوز چیزی ثبت نشده</Badge>}
      </div>

      {share !== null ? (
        <Progress
          value={share}
          ariaLabel={`سهم ${name}`}
          label="سهم از کار ثبت‌شده"
          valueText={`${formatNumber(share)}٪`}
        />
      ) : (
        <p className="text-[13px] text-[var(--fg-tertiary)]">سهم هنوز قابل محاسبه نیست.</p>
      )}

      <ul className="flex flex-wrap gap-x-4 gap-y-1 text-[12.5px] text-[var(--fg-secondary)]">
        {member.signals.map((signal) => {
          const title = data.dimensions.find((item) => item.dimension === signal.dimension)?.title;
          return (
            <li key={signal.dimension}>
              {title}: {toPersianDigits(signal.count)}
              {signal.share_percent !== null &&
                ` (${formatNumber(signal.share_percent)}٪ از کل تیم)`}
            </li>
          );
        })}
      </ul>

      {peer && peer.contribution_avg !== null && (
        <p className="text-[12.5px] text-[var(--fg-tertiary)]">
          میانگین ارزیابی همتا: {formatNumber(peer.contribution_avg)} از {toPersianDigits(5)}، از{' '}
          {toPersianDigits(peer.evaluations)} ارزیابی. این دو نشانه جدا از هم‌اند؛ ناهم‌خوانی‌شان را
          با گفت‌وگو روشن کن.
        </p>
      )}
    </li>
  );
}

function messageFor(cause: unknown): string {
  if (cause instanceof ApiError || cause instanceof NetworkError) return cause.message;
  return 'تحلیل مشارکت بارگذاری نشد. کمی بعد دوباره تلاش کن.';
}
