'use client';

import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';

import { AreaPreview, polygonsOf } from '@/components/domain/AreaPreview';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card, CardDescription, CardTitle } from '@/components/ui/Card';
import { SkeletonCard } from '@/components/ui/Skeleton';
import { ApiError, NetworkError } from '@/lib/api/client';
import {
  type CityBoard,
  type CityStage,
  type CityWorkflow,
  fetchCityBoard,
  fetchCityWorkflow,
} from '@/lib/api/city';
import { type Team, assignMilestoneOwner, fetchTeam } from '@/lib/api/workspace';
import { readSession } from '@/lib/auth/session';
import { useSession } from '@/lib/auth/use-session';
import { cn } from '@/lib/cn';
import { formatDateLong } from '@/lib/format/date';
import { toPersianDigits } from '@/lib/format/digits';

import { StageDeliverables } from './StageDeliverables';
import { StageSubmitForm } from './StageSubmitForm';

/**
 * `/projects/[id]/city` — گردش‌کار هشت‌مرحله‌ای شهر هوشمند، FR-CITY-01، §7.9.
 *
 * یک مرحله در هر لحظه باز است: مرحلهٔ n پس از تأیید n−۱ تحویل می‌پذیرد
 * (ADR-0016). هر مرحله راهنما، چک‌لیست کیفیت، مسئول و مهلت دارد؛ فرم
 * تحویل از الگوی سرور ساخته می‌شود و بازبین همین‌جا تصمیم می‌گیرد.
 */
export function CityBoardView({ id }: { id: string }) {
  const { accessToken, loading: sessionLoading } = useSession();
  const [board, setBoard] = useState<CityBoard | null>(null);
  const [workflow, setWorkflow] = useState<CityWorkflow | null>(null);
  const [team, setTeam] = useState<Team | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [denied, setDenied] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const [celebrate, setCelebrate] = useState(false);

  const currentUserId = readSession()?.user.id ?? null;

  const load = useCallback(async () => {
    if (!accessToken) return;
    try {
      const [boardData, spec, teamData] = await Promise.all([
        fetchCityBoard(id, accessToken),
        fetchCityWorkflow(),
        fetchTeam(id, accessToken).catch(() => null),
      ]);
      setBoard(boardData);
      setWorkflow(spec);
      setTeam(teamData);
      setSelected((prev) => prev ?? boardData.current_stage ?? 8);
      setRefreshKey((key) => key + 1);
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 403) setDenied(true);
      else setError(messageFor(cause));
    }
  }, [accessToken, id]);

  useEffect(() => {
    if (!sessionLoading) void load();
  }, [load, sessionLoading]);

  if (denied) {
    return (
      <Card className="flex flex-col gap-3">
        <CardTitle as="h1">این گردش‌کار برای تیم پروژه است</CardTitle>
        <CardDescription>برای دیدن مراحل و تحویل‌ها باید عضو تیم باشی.</CardDescription>
        <Button asChild variant="secondary" className="self-start">
          <Link href={`/projects/${id}`}>صفحهٔ پروژه</Link>
        </Button>
      </Card>
    );
  }
  if (error) {
    return (
      <div className="flex flex-col gap-3">
        <h1>گردش‌کار شهر هوشمند</h1>
        <p role="alert" className="text-[13.5px] text-[var(--fg-danger)]">
          {error}
        </p>
      </div>
    );
  }
  if (!board || !workflow || !accessToken) return <SkeletonCard label="در حال بارگذاری گردش‌کار" />;

  const stage = board.stages.find((s) => s.number === selected) ?? board.stages[0];
  const spec = stage && workflow.stages.find((s) => s.number === stage.number);
  if (!stage || !spec) return null;
  const isMember =
    team?.members.some((m) => m.user_id === currentUserId && m.status === 'ACTIVE') === true;
  const mine = stage.milestone.my_deliverable;
  const canSubmit =
    isMember &&
    !stage.locked &&
    stage.milestone.status !== 'APPROVED' &&
    ['OPEN', 'IN_PROGRESS'].includes(board.status) &&
    (mine === null || mine.status === 'CHANGES_REQUESTED');

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-2">
        <Link
          href={`/projects/${id}/workspace`}
          className="text-[13px] text-[var(--fg-tertiary)] hover:underline"
        >
          ← فضای کاری پروژه
        </Link>
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone="brand">آزمایشگاه شهر هوشمند</Badge>
          {board.workflow_completed_at && <Badge tone="success">گردش‌کار کامل شد</Badge>}
        </div>
        <h1>{board.title_fa}</h1>
        <p className="text-[14px] text-[var(--fg-secondary)]">
          {toPersianDigits(board.approved_count)} از ۸ مرحله تأیید شده
          {board.current_stage && ` · مرحلهٔ جاری: ${toPersianDigits(board.current_stage)}`}
        </p>
        <div className="flex flex-wrap gap-2">
          <Button asChild variant="ghost" size="sm">
            <Link href={`/projects/${id}/files`}>کتابخانهٔ فایل</Link>
          </Button>
          <Button asChild variant="ghost" size="sm">
            <Link href="/city">دربارهٔ آزمایشگاه</Link>
          </Button>
        </div>
      </header>

      {celebrate && (
        <Card className="border-[var(--success-500)]">
          <CardTitle>هر هشت مرحله تأیید شد</CardTitle>
          <CardDescription>
            گردش‌کار شهر هوشمند این پروژه کامل است. سهیمان نشان «شهرساز» را می‌گیرند و حالا می‌توانی
            پروژه را از فضای کاری ببندی.
          </CardDescription>
        </Card>
      )}

      <StepRail
        stages={board.stages}
        selected={stage.number}
        onSelect={setSelected}
        workflow={workflow}
      />

      <div className="grid gap-6 lg:grid-cols-[1fr_300px]">
        <div className="flex flex-col gap-5">
          <StageHeader
            stage={stage}
            specTitle={spec.title_fa}
            deliverable={spec.deliverable_fa}
            team={team}
            canManage={board.can_manage}
            accessToken={accessToken}
            onChanged={load}
          />

          <section className="grid gap-5 md:grid-cols-2">
            <div className="flex flex-col gap-2">
              <h2 className="text-[16px] font-semibold">راهنما</h2>
              <ol className="flex flex-col gap-1.5 ps-6 text-[14px] leading-[1.9] [list-style-type:persian]">
                {spec.guide.map((step) => (
                  <li key={step}>{step}</li>
                ))}
              </ol>
            </div>
            <div className="flex flex-col gap-2">
              <h2 className="text-[16px] font-semibold">چک‌لیست کیفیت</h2>
              <ul className="flex flex-col gap-1.5 text-[14px] leading-[1.9]">
                {spec.checklist.map((item) => (
                  <li key={item.text} className="flex items-start gap-2">
                    <span aria-hidden>{item.auto ? '⚙' : '☐'}</span>
                    <span>
                      {item.text}
                      <span className="ms-1 text-[12px] text-[var(--fg-tertiary)]">
                        {item.auto ? '(سامانه می‌سنجد)' : '(تو تأیید می‌کنی، بازبین می‌سنجد)'}
                      </span>
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          </section>

          {stage.locked && (
            <p className="rounded-[var(--radius-md)] bg-[var(--bg-sunken)] p-3 text-[14px]">
              این مرحله پس از تأیید مرحلهٔ {toPersianDigits(stage.number - 1)} باز می‌شود. راهنما را
              از همین حالا بخوان.
            </p>
          )}
          {mine && ['SUBMITTED', 'UNDER_REVIEW'].includes(mine.status) && (
            <p className="text-[14px] text-[var(--fg-secondary)]">
              تحویلت در صف بررسی است؛ نتیجه را با اعلان خبر می‌دهیم.
            </p>
          )}

          {canSubmit && (
            <StageSubmitForm
              key={stage.milestone.id}
              spec={spec}
              workflow={workflow}
              milestone={stage.milestone}
              accessToken={accessToken}
              isRevision={mine?.status === 'CHANGES_REQUESTED'}
              onSubmitted={load}
            />
          )}

          <StageDeliverables
            projectId={id}
            milestoneId={stage.milestone.id}
            spec={spec}
            workflow={workflow}
            canReview={board.can_review}
            currentUserId={currentUserId}
            accessToken={accessToken}
            refreshKey={refreshKey}
            onReviewed={(completed) => {
              if (completed) setCelebrate(true);
              void load();
            }}
          />
        </div>

        <aside className="flex flex-col gap-4">
          <Card className="flex flex-col gap-2">
            <CardTitle className="text-[16px]">محدودهٔ مطالعه</CardTitle>
            {board.area ? (
              <>
                <AreaPreview polygons={polygonsOf(board.area.geometry)} />
                <p className="text-[13px] text-[var(--fg-secondary)]">
                  {toPersianDigits(board.area.area_km2.toFixed(2))} کیلومتر مربع ·{' '}
                  {board.area.approved ? 'تأییدشده' : 'در انتظار تأیید'}
                </p>
              </>
            ) : (
              <p className="text-[13px] text-[var(--fg-tertiary)]">
                محدوده با تحویل مرحلهٔ ۱ مشخص می‌شود.
              </p>
            )}
          </Card>
          <Card className="flex flex-col gap-2">
            <CardTitle className="text-[16px]">فایل‌های مدل</CardTitle>
            <ul className="flex flex-col gap-1.5 text-[13px]">
              {board.artifacts.map((artifact) => (
                <li key={artifact.artifact} className="flex justify-between gap-2">
                  <span>
                    {artifact.title_fa} <span dir="ltr">({artifact.extension})</span>
                  </span>
                  <span className="text-[var(--fg-tertiary)]">
                    {artifact.current_version
                      ? `نسخهٔ جاری ${toPersianDigits(artifact.current_version)}`
                      : artifact.versions > 0
                        ? `${toPersianDigits(artifact.versions)} نسخه، بی‌تأیید`
                        : '—'}
                  </span>
                </li>
              ))}
            </ul>
            <Link
              href={`/projects/${id}/files`}
              className="text-[13px] text-[var(--fg-brand)] underline"
            >
              همهٔ نسخه‌ها
            </Link>
          </Card>
        </aside>
      </div>
    </div>
  );
}

function StepRail({
  stages,
  selected,
  onSelect,
  workflow,
}: {
  stages: CityStage[];
  selected: number;
  onSelect: (n: number) => void;
  workflow: CityWorkflow;
}) {
  return (
    <ol aria-label="هشت مرحلهٔ گردش‌کار" className="grid grid-cols-4 gap-2 sm:grid-cols-8">
      {stages.map((stage) => {
        const status = stage.milestone.status;
        const title = workflow.stages.find((s) => s.number === stage.number)?.title_fa ?? '';
        return (
          <li key={stage.number}>
            <button
              type="button"
              onClick={() => onSelect(stage.number)}
              aria-current={stage.number === selected ? 'step' : undefined}
              className={cn(
                'flex h-full w-full flex-col items-center gap-1 rounded-[var(--radius-md)] border p-2 text-center text-[12px]',
                stage.number === selected
                  ? 'border-[var(--brand-500)] bg-[var(--brand-50)] text-[var(--fg-brand)]'
                  : 'border-[var(--border-subtle)]',
              )}
            >
              <span
                className={cn(
                  'flex h-7 w-7 items-center justify-center rounded-full text-[13px] font-semibold',
                  status === 'APPROVED'
                    ? 'bg-[var(--success-500)] text-white'
                    : stage.locked
                      ? 'bg-[var(--bg-sunken)] text-[var(--fg-tertiary)]'
                      : 'bg-[var(--brand-600)] text-white',
                )}
              >
                {status === 'APPROVED' ? '✓' : toPersianDigits(stage.number)}
              </span>
              <span className="leading-[1.5]">{title}</span>
              {stage.open_deliverables > 0 && (
                <span className="text-[11px] text-[var(--fg-info)]">
                  {toPersianDigits(stage.open_deliverables)} در انتظار
                </span>
              )}
            </button>
          </li>
        );
      })}
    </ol>
  );
}

function StageHeader({
  stage,
  specTitle,
  deliverable,
  team,
  canManage,
  accessToken,
  onChanged,
}: {
  stage: CityStage;
  specTitle: string;
  deliverable: string;
  team: Team | null;
  canManage: boolean;
  accessToken: string;
  onChanged: () => void;
}) {
  const milestone = stage.milestone;
  const [error, setError] = useState<string | null>(null);
  const members = team?.members.filter((m) => m.status === 'ACTIVE') ?? [];

  async function assign(ownerId: string) {
    setError(null);
    try {
      await assignMilestoneOwner(milestone.id, ownerId, accessToken);
      onChanged();
    } catch (cause) {
      setError(messageFor(cause));
    }
  }

  return (
    <Card className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <CardTitle>
          مرحلهٔ {toPersianDigits(stage.number)}: {specTitle}
        </CardTitle>
        <Badge
          tone={milestone.status === 'APPROVED' ? 'success' : stage.locked ? 'neutral' : 'brand'}
        >
          {stage.locked ? 'قفل' : milestone.status_fa}
        </Badge>
      </div>
      <CardDescription>{deliverable}</CardDescription>
      <dl className="grid gap-2 text-[13.5px] sm:grid-cols-3">
        <div>
          <dt className="text-[var(--fg-tertiary)]">مسئول</dt>
          <dd>
            {canManage && milestone.status !== 'APPROVED' && members.length > 0 ? (
              <select
                aria-label="مسئول مرحله"
                value={milestone.owner_id ?? ''}
                onChange={(event) => void assign(event.target.value)}
                className="mt-0.5 h-9 w-full rounded-[var(--radius-md)] border border-[var(--border-default)] bg-[var(--bg-surface)] px-2"
              >
                {members.map((m) => (
                  <option key={m.user_id} value={m.user_id}>
                    {m.full_name ?? m.username ?? 'عضو'}
                    {m.is_lead ? ' (مدیر)' : ''}
                  </option>
                ))}
              </select>
            ) : (
              (milestone.owner_name ?? '—')
            )}
          </dd>
        </div>
        <div>
          <dt className="text-[var(--fg-tertiary)]">مهلت</dt>
          <dd>{milestone.due_on ? formatDateLong(milestone.due_on) : 'تعیین نشده'}</dd>
        </div>
        <div>
          <dt className="text-[var(--fg-tertiary)]">بارم</dt>
          <dd>{toPersianDigits(milestone.points)} امتیاز</dd>
        </div>
      </dl>
      {error && (
        <p role="alert" className="text-[13px] text-[var(--fg-danger)]">
          {error}
        </p>
      )}
    </Card>
  );
}

function messageFor(cause: unknown): string {
  if (cause instanceof ApiError || cause instanceof NetworkError) return cause.message;
  return 'گردش‌کار بارگذاری نشد. کمی بعد دوباره تلاش کن.';
}
