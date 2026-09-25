'use client';

import { type FormEvent, useCallback, useEffect, useState } from 'react';

import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card, CardDescription, CardTitle } from '@/components/ui/Card';
import { SkeletonText } from '@/components/ui/Skeleton';
import { ApiError, NetworkError } from '@/lib/api/client';
import {
  type PeerEvaluationState,
  type PeerEvaluationSummary,
  type PeerRatingInput,
  fetchPeerEvaluationSummary,
  fetchPeerEvaluations,
  submitPeerEvaluations,
} from '@/lib/api/workspace';
import { cn } from '@/lib/cn';
import { formatNumber, toPersianDigits } from '@/lib/format/digits';

/**
 * ارزیابی همتا — FR-PRJ-08، ADR-0024 برش ب.
 *
 * فقط برای پروژهٔ بسته‌شده و عضو فعال تیم. **یک فرم برای همهٔ هم‌تیمی‌ها**:
 * ناقص ثبت نمی‌شود، یک‌بار ثبت می‌شود و ویرایش ندارد. امتیاز برای *انجام*
 * است نه برای *مقدار* — پس هیچ‌جا نمرهٔ «بهتر» تشویق نمی‌شود. متن آزاد
 * (`note`) عمداً نداریم: ناشناسی را می‌شکند.
 *
 * مدیر پروژه علاوه بر فرم، میانگین‌ها را می‌بیند؛ سرور میانگینی را که کمتر از
 * حداقل ارزیابیِ «دیگران» دارد `null` می‌دهد و همین‌جا «کافی نیست» نوشته می‌شود.
 */

const CONTRIBUTION_LABELS = ['خیلی کم', 'کم', 'متوسط', 'خوب', 'عالی'];

export function PeerEvaluationCard({
  projectId,
  accessToken,
  isLead,
}: {
  projectId: string;
  accessToken: string;
  isLead: boolean;
}) {
  const [state, setState] = useState<PeerEvaluationState | null>(null);
  const [summary, setSummary] = useState<PeerEvaluationSummary | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setState(await fetchPeerEvaluations(projectId, accessToken));
      setLoadError(null);
    } catch (cause) {
      setLoadError(messageFor(cause));
    }
  }, [projectId, accessToken]);

  useEffect(() => {
    void load();
  }, [load]);

  // میانگین‌ها تا وقتی مدیر خودش ارزیابی نکرده هم می‌آیند؛ ولی با هر ثبتِ او
  // تازه می‌شوند تا کارت هم‌زمان دو حالت متناقض نشان ندهد.
  useEffect(() => {
    if (!isLead) return;
    let cancelled = false;
    fetchPeerEvaluationSummary(projectId, accessToken)
      .then((result) => {
        if (!cancelled) setSummary(result);
      })
      .catch(() => {
        if (!cancelled) setSummary(null);
      });
    return () => {
      cancelled = true;
    };
  }, [isLead, projectId, accessToken, state?.mine.length]);

  if (loadError) {
    return (
      <Card>
        <p role="alert" className="text-[13.5px] text-[var(--fg-danger)]">
          {loadError}
        </p>
      </Card>
    );
  }
  if (!state) {
    return (
      <Card>
        <SkeletonText label="در حال بارگذاری ارزیابی همتا" />
      </Card>
    );
  }

  const summaryBlock = isLead && state.peers.length > 0 && summary && (
    <SummaryBlock summary={summary} />
  );

  if (state.mine.length > 0) {
    return (
      <Card className="flex flex-col gap-4" aria-labelledby="peer-title">
        <div className="flex flex-col gap-1">
          <CardTitle as="h2" id="peer-title">
            ارزیابی هم‌تیمی‌هایت ثبت شد
          </CardTitle>
          <CardDescription>
            فقط خودت این ارزیابی را می‌بینی و ویرایش‌پذیر نیست. هم‌تیمی‌هایت نمرهٔ تو را نمی‌بینند.
          </CardDescription>
        </div>
        <ul className="flex flex-col gap-2">
          {state.mine.map((rating) => {
            const peer = state.peers.find((item) => item.user_id === rating.evaluatee_id);
            return (
              <li
                key={rating.evaluatee_id}
                className="flex flex-wrap items-center justify-between gap-2 text-[14px]"
              >
                <span className="text-[var(--fg-primary)]">{peer?.full_name ?? 'عضو تیم'}</span>
                <span className="text-[var(--fg-secondary)]">
                  سهم همکاری: {toPersianDigits(rating.contribution)} از {toPersianDigits(5)}
                  {rating.reliability !== null &&
                    `، قابل‌اعتماد بودن: ${toPersianDigits(rating.reliability)} از ${toPersianDigits(5)}`}
                </span>
              </li>
            );
          })}
        </ul>
        {summaryBlock}
      </Card>
    );
  }

  if (!state.can_submit) return summaryBlock ? <Card>{summaryBlock}</Card> : null;

  return (
    <div className="flex flex-col gap-4">
      <PeerEvaluationForm
        projectId={projectId}
        accessToken={accessToken}
        state={state}
        onSaved={load}
      />
      {summaryBlock && <Card>{summaryBlock}</Card>}
    </div>
  );
}

function PeerEvaluationForm({
  projectId,
  accessToken,
  state,
  onSaved,
}: {
  projectId: string;
  accessToken: string;
  state: PeerEvaluationState;
  onSaved: () => void;
}) {
  const [contribution, setContribution] = useState<Record<string, number>>({});
  const [reliability, setReliability] = useState<Record<string, number>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const remaining = state.peers.filter((peer) => contribution[peer.user_id] === undefined).length;

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (remaining > 0) return;
    const evaluations: PeerRatingInput[] = state.peers.map((peer) => ({
      evaluatee_id: peer.user_id,
      contribution: contribution[peer.user_id] ?? 0,
      reliability: reliability[peer.user_id] ?? null,
    }));
    setBusy(true);
    setError(null);
    try {
      await submitPeerEvaluations(projectId, evaluations, accessToken);
      onSaved();
    } catch (cause) {
      setError(messageFor(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="flex flex-col gap-4" aria-labelledby="peer-title">
      <div className="flex flex-col gap-1">
        <CardTitle as="h2" id="peer-title">
          هم‌تیمی‌هایت را ارزیابی کن
        </CardTitle>
        <CardDescription>
          برای همهٔ هم‌تیمی‌ها یک نمره بده؛ ناقص ثبت نمی‌شود و بعد از ثبت ویرایش نمی‌شود. نمره‌ها
          فقط به‌صورت میانگین و فقط به مدیر پروژه نشان داده می‌شود.
          {state.points !== null &&
            ` ثبتش ${toPersianDigits(state.points)} امتیاز جامعه دارد، صرف‌نظر از نمره‌ای که می‌دهی.`}
        </CardDescription>
      </div>

      <form onSubmit={handleSubmit} className="flex flex-col gap-5">
        {state.peers.map((peer) => (
          <div
            key={peer.user_id}
            className="flex flex-col gap-3 border-t border-[var(--border-subtle)] pt-4 first:border-t-0 first:pt-0"
          >
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-[14.5px] font-medium text-[var(--fg-primary)]">
                {peer.full_name ?? 'عضو تیم'}
              </span>
              {peer.is_lead && <Badge tone="neutral">مدیر پروژه</Badge>}
            </div>
            <ScaleField
              legend="سهم همکاری در پروژه"
              value={contribution[peer.user_id]}
              onChange={(value) => setContribution((prev) => ({ ...prev, [peer.user_id]: value }))}
              labels={CONTRIBUTION_LABELS}
            />
            <ScaleField
              legend="قابل‌اعتماد بودن (اختیاری)"
              value={reliability[peer.user_id]}
              onChange={(value) => setReliability((prev) => ({ ...prev, [peer.user_id]: value }))}
              onClear={() =>
                setReliability((prev) => {
                  const next = { ...prev };
                  delete next[peer.user_id];
                  return next;
                })
              }
              labels={CONTRIBUTION_LABELS}
            />
          </div>
        ))}

        {error && (
          <p role="alert" className="text-[13px] text-[var(--fg-danger)]">
            {error}
          </p>
        )}
        <div className="flex items-center gap-3">
          <Button type="submit" loading={busy} disabled={remaining > 0}>
            ثبت ارزیابی
          </Button>
          {remaining > 0 && (
            <span className="text-[12.5px] text-[var(--fg-tertiary)]">
              سهم همکاری {toPersianDigits(remaining)} نفر هنوز مانده است
            </span>
          )}
        </div>
      </form>
    </Card>
  );
}

function ScaleField({
  legend,
  value,
  onChange,
  onClear,
  labels,
}: {
  legend: string;
  value: number | undefined;
  onChange: (value: number) => void;
  /** اگر باشد، دوباره زدنِ گزینهٔ انتخاب‌شده آن را پس می‌گیرد (میدان اختیاری). */
  onClear?: () => void;
  labels: string[];
}) {
  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="text-[13px] text-[var(--fg-secondary)]">{legend}</legend>
      <div className="flex flex-wrap gap-2">
        {labels.map((label, index) => {
          const point = index + 1;
          const selected = value === point;
          return (
            <button
              key={point}
              type="button"
              aria-pressed={selected}
              aria-label={`${legend}: ${toPersianDigits(point)} از ${toPersianDigits(5)}، ${label}`}
              onClick={() => (selected && onClear ? onClear() : onChange(point))}
              className={cn(
                'h-9 min-w-9 rounded-[var(--radius-full)] border px-3 text-[13.5px] font-medium',
                'transition-colors duration-[var(--dur-instant)]',
                selected
                  ? 'border-[var(--brand-600)] bg-[var(--brand-600)] text-[var(--fg-on-brand)]'
                  : 'border-[var(--border-default)] bg-[var(--bg-surface)] text-[var(--fg-secondary)] hover:border-[var(--border-strong)]',
              )}
            >
              {toPersianDigits(point)}
            </button>
          );
        })}
      </div>
    </fieldset>
  );
}

function SummaryBlock({ summary }: { summary: PeerEvaluationSummary }) {
  const shown = summary.members.filter((member) => member.contribution_avg !== null);
  return (
    <section aria-labelledby="peer-summary-title" className="flex flex-col gap-3">
      <div className="flex flex-col gap-1">
        <h3 id="peer-summary-title" className="text-[14.5px] font-medium text-[var(--fg-primary)]">
          نتیجهٔ ارزیابی همتا (فقط مدیر پروژه)
        </h3>
        <p className="text-[12.5px] text-[var(--fg-tertiary)]">
          میانگین نمره‌های دیگران، بدون نظر خودت. میانگین وقتی نشان داده می‌شود که دست‌کم{' '}
          {toPersianDigits(summary.min_evaluations)} نفر ارزیابی کرده باشند تا نمرهٔ هیچ‌کس مشخص
          نشود.
        </p>
      </div>
      {shown.length === 0 ? (
        <p className="text-[13.5px] text-[var(--fg-secondary)]">هنوز ارزیابیِ کافی نیست.</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {summary.members.map((member) => (
            <li
              key={member.user_id}
              className="flex flex-wrap items-center justify-between gap-2 text-[14px]"
            >
              <span className="text-[var(--fg-primary)]">{member.full_name ?? 'عضو تیم'}</span>
              {member.contribution_avg === null ? (
                <span className="text-[var(--fg-tertiary)]">ارزیابی کافی نیست</span>
              ) : (
                <span className="text-[var(--fg-secondary)]">
                  سهم همکاری: {formatNumber(member.contribution_avg)} از {toPersianDigits(5)}
                  {member.reliability_avg !== null &&
                    `، قابل‌اعتماد بودن: ${formatNumber(member.reliability_avg)} از ${toPersianDigits(5)}`}
                  ، از {toPersianDigits(member.evaluations)} ارزیابی
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function messageFor(cause: unknown): string {
  if (cause instanceof ApiError || cause instanceof NetworkError) return cause.message;
  return 'ارزیابی همتا بارگذاری نشد. کمی بعد دوباره تلاش کن.';
}
