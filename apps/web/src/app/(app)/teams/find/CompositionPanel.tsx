'use client';

import { useEffect, useState } from 'react';

import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card, CardTitle } from '@/components/ui/Card';
import { ApiError, NetworkError } from '@/lib/api/client';
import {
  type ComposedMember,
  type Composition,
  type CompositionSuggestion,
  composeTeam,
  inviteToProject,
} from '@/lib/api/teams';
import { toPersianDigits } from '@/lib/format/digits';

/**
 * پیشنهاد خودکار ترکیب تیم — FR-TEAM-04، ADR-0027.
 *
 * فقط با کلیک درخواست می‌زند (نه با هر تغییر فیلتر) و فقط‌خواندنی است: هیچ‌کس
 * رزرو یا خبر نمی‌شود تا مدیر خودش «دعوت» را بزند. هر عضو فقط مهارت‌هایی را
 * نشان می‌دهد که **تازه** به تیم می‌آورد؛ پوشش کل ترکیب بالای کارت است.
 */

const SEAT_CHOICES = [1, 2, 3, 4, 5];

export function CompositionPanel({
  projectId,
  accessToken,
}: {
  projectId: string;
  accessToken: string;
}) {
  const [seats, setSeats] = useState('3');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<CompositionSuggestion | null>(null);

  // با عوض شدن پروژه، پیشنهاد پروژهٔ قبل نباید بماند.
  useEffect(() => {
    setResult(null);
    setError(null);
  }, [projectId]);

  async function suggest() {
    setBusy(true);
    setError(null);
    try {
      setResult(await composeTeam(accessToken, projectId, Number(seats)));
    } catch (cause) {
      setError(messageFor(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="flex flex-col gap-4" aria-labelledby="compose-title">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="flex flex-col gap-1">
          <CardTitle as="h2" id="compose-title">
            پیشنهاد ترکیب تیم
          </CardTitle>
          <p className="text-[13.5px] leading-[1.9] text-[var(--fg-secondary)]">
            چند نفر را با هم پیشنهاد می‌دهد که کمبودهای مهارتی تیم را بیشتر می‌پوشانند — نه چند نفر
            که همه یک مهارت را دارند.
          </p>
        </div>
        <div className="flex items-end gap-2">
          <div className="flex flex-col gap-1.5">
            <label htmlFor="compose-seats" className="text-[13px] font-medium">
              حداکثر نفرات
            </label>
            <select
              id="compose-seats"
              value={seats}
              onChange={(event) => setSeats(event.target.value)}
              className="h-10 rounded-[var(--radius-md)] border border-[var(--border-default)] bg-[var(--bg-surface)] px-3 text-[14px]"
            >
              {SEAT_CHOICES.map((n) => (
                <option key={n} value={n}>
                  {toPersianDigits(n)}
                </option>
              ))}
            </select>
          </div>
          <Button size="sm" onClick={suggest} loading={busy}>
            پیشنهاد بده
          </Button>
        </div>
      </div>

      {error && (
        <p role="alert" className="text-[13.5px] text-[var(--fg-danger)]">
          {error}
        </p>
      )}

      {result && result.gaps.length === 0 && (
        <p className="text-[13.5px] text-[var(--fg-secondary)]">
          تیم همهٔ مهارت‌های لازم پروژه را دارد؛ چیزی برای تکمیل نیست.
        </p>
      )}
      {result && result.gaps.length > 0 && result.compositions.length === 0 && (
        <p className="text-[13.5px] leading-[1.9] text-[var(--fg-secondary)]">
          هیچ نیمرخ عمومی‌ای هیچ‌یک از کمبودهای تیم را در سطح لازم ندارد. آگهی هم‌تیمی بده تا
          دانشجویان هم‌خوان خبردار شوند.
        </p>
      )}
      {result && result.compositions.length > 0 && (
        <ol className="flex flex-col gap-4">
          {result.compositions.map((composition, index) => (
            <li key={composition.members.map((m) => m.user.id).join('-')}>
              <CompositionCard
                composition={composition}
                index={index}
                projectId={projectId}
                accessToken={accessToken}
              />
            </li>
          ))}
        </ol>
      )}
    </Card>
  );
}

function CompositionCard({
  composition,
  index,
  projectId,
  accessToken,
}: {
  composition: Composition;
  index: number;
  projectId: string;
  accessToken: string;
}) {
  return (
    <div className="flex flex-col gap-3 rounded-[var(--radius-md)] border border-[var(--border-subtle)] p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-[14px] font-semibold">گزینهٔ {toPersianDigits(index + 1)}</p>
        <div className="flex flex-wrap gap-1.5">
          <Badge tone="neutral">تعداد اعضا: {toPersianDigits(composition.members.length)}</Badge>
          <Badge tone={composition.uncovered.length === 0 ? 'success' : 'warning'}>
            پوشش کمبودها: {toPersianDigits(Math.round(composition.coverage_percent))}٪
          </Badge>
        </div>
      </div>
      <ul className="grid gap-3 md:grid-cols-2">
        {composition.members.map((member) => (
          <li key={member.user.id}>
            <MemberRow member={member} projectId={projectId} accessToken={accessToken} />
          </li>
        ))}
      </ul>
      {composition.uncovered.length > 0 && (
        <p className="text-[13px] text-[var(--fg-tertiary)]">
          هنوز بی‌پوشش:{' '}
          {composition.uncovered
            .map((gap) => `${gap.title_fa} (سطح ${toPersianDigits(gap.min_level)})`)
            .join('، ')}
        </p>
      )}
    </div>
  );
}

function MemberRow({
  member,
  projectId,
  accessToken,
}: {
  member: ComposedMember;
  projectId: string;
  accessToken: string;
}) {
  const [invited, setInvited] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function invite() {
    if (!member.user.username) return;
    try {
      await inviteToProject(accessToken, projectId, member.user.username);
      setInvited(true);
      setError(null);
    } catch (cause) {
      setError(messageFor(cause));
    }
  }

  return (
    <div className="flex h-full flex-col gap-2">
      <div className="flex flex-col gap-0.5">
        <p className="text-[15px] font-semibold">{member.user.display_name}</p>
        <p className="text-[12.5px] text-[var(--fg-tertiary)]">
          {[
            member.user.university,
            member.weekly_hours !== null
              ? `${toPersianDigits(member.weekly_hours)} ساعت در هفته`
              : null,
          ]
            .filter(Boolean)
            .join('، ')}
        </p>
      </div>
      <p className="rounded-[var(--radius-md)] bg-[var(--brand-50)] p-2.5 text-[13.5px] leading-[1.9] text-[var(--fg-brand)]">
        {member.reason}
      </p>
      <ul className="flex flex-wrap gap-1.5" aria-label="مهارت‌هایی که تازه می‌آورد">
        {member.covers.map((skill) => (
          <li key={skill.title_fa}>
            <Badge tone={skill.verified ? 'success' : 'neutral'}>
              {skill.title_fa} {toPersianDigits(skill.level)}
              {skill.verified && ' ✓'}
            </Badge>
          </li>
        ))}
      </ul>
      {member.user.username && (
        <div className="mt-auto">
          <Button size="sm" onClick={invite} disabled={invited}>
            {invited ? 'دعوت فرستاده شد' : 'دعوت به تیم'}
          </Button>
        </div>
      )}
      {error && (
        <p role="alert" className="text-[13px] text-[var(--fg-danger)]">
          {error}
        </p>
      )}
    </div>
  );
}

function messageFor(cause: unknown): string {
  if (cause instanceof ApiError || cause instanceof NetworkError) return cause.message;
  return 'پیشنهاد ساخته نشد. کمی بعد دوباره تلاش کن.';
}
