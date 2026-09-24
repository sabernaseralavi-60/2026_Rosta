'use client';

import { useCallback, useEffect, useState } from 'react';

import { AreaPreview, polygonsOf } from '@/components/domain/AreaPreview';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Textarea } from '@/components/ui/Textarea';
import { ApiError, NetworkError } from '@/lib/api/client';
import { type CityStageSpec, type CityWorkflow, projectFileUrl } from '@/lib/api/city';
import { formatBytes } from '@/lib/api/files';
import {
  type Deliverable,
  type ReviewDecision,
  fetchDeliverables,
  reviewDeliverable,
} from '@/lib/api/workspace';
import { formatRelative } from '@/lib/format/date';
import { toPersianDigits } from '@/lib/format/digits';

/**
 * همهٔ نسخه‌های تحویل یک مرحلهٔ شهری — برای تیم و بازبین.
 *
 * شاهد ساختاریافته خوانا نمایش داده می‌شود (محدوده با شکلش، جدول
 * راستی‌آزمایی با منبع و تصویر، سناریوها با شاخص‌ها) و فایل‌ها از
 * کتابخانهٔ پروژه دانلود می‌شوند، نه از مسیر شخصی آپلودکننده.
 */
export function StageDeliverables({
  projectId,
  milestoneId,
  spec,
  workflow,
  canReview,
  currentUserId,
  accessToken,
  refreshKey,
  onReviewed,
}: {
  projectId: string;
  milestoneId: string;
  spec: CityStageSpec;
  workflow: CityWorkflow;
  canReview: boolean;
  currentUserId: string | null;
  accessToken: string;
  refreshKey: number;
  onReviewed: (completed: boolean) => void;
}) {
  const [items, setItems] = useState<Deliverable[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    fetchDeliverables(milestoneId, accessToken)
      .then((rows) => setItems([...rows].reverse()))
      .catch((cause) => setError(messageFor(cause)));
  }, [accessToken, milestoneId]);

  useEffect(load, [load, refreshKey]);

  async function open(fileId: string) {
    try {
      const { download_url } = await projectFileUrl(projectId, fileId, accessToken);
      window.open(download_url, '_blank', 'noopener');
    } catch (cause) {
      setError(messageFor(cause));
    }
  }

  if (error) {
    return (
      <p role="alert" className="text-[13px] text-[var(--fg-danger)]">
        {error}
      </p>
    );
  }
  if (items === null || items.length === 0) return null;

  const labels = Object.fromEntries(spec.evidence.map((f) => [f.key, f.label_fa]));
  const sources = Object.fromEntries(workflow.sources.map((s) => [s.code, s.title_fa]));
  const verdicts = Object.fromEntries(workflow.verdicts.map((s) => [s.code, s.title_fa]));

  return (
    <section className="flex flex-col gap-3" aria-label="تحویل‌های این مرحله">
      <h3 className="text-[16px] font-semibold">تحویل‌ها</h3>
      {items.map((item) => {
        const evidence = (item.evidence ?? {}) as Record<string, unknown>;
        const reviewable =
          canReview &&
          item.submitter_id !== currentUserId &&
          (item.status === 'SUBMITTED' || item.status === 'UNDER_REVIEW');
        return (
          <Card key={item.id} className="flex flex-col gap-3">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-[14px] font-semibold">
                {item.submitter_name ?? 'عضو تیم'} — نسخهٔ {toPersianDigits(item.version)}
              </span>
              <Badge tone={toneFor(item.status)}>{item.status_fa}</Badge>
              {item.is_late && <Badge tone="warning">با تأخیر</Badge>}
              <span className="text-[12px] text-[var(--fg-tertiary)]">
                {formatRelative(item.submitted_at)}
              </span>
            </div>
            {item.body && (
              <p className="whitespace-pre-line text-[14px] leading-[1.9]">{item.body}</p>
            )}

            {'area' in evidence && <AreaEvidence evidence={evidence} />}

            <dl className="grid gap-1.5 text-[13px] sm:grid-cols-2">
              {Object.entries(labels).map(([key, label]) =>
                evidence[key] !== undefined ? (
                  <div key={key} className="flex flex-col">
                    <dt className="text-[var(--fg-tertiary)]">{label}</dt>
                    <dd className="whitespace-pre-line break-words">
                      {toPersianDigits(String(evidence[key]))}
                    </dd>
                  </div>
                ) : null,
              )}
            </dl>

            {Array.isArray(evidence.checks) && (
              <ChecksTable
                rows={evidence.checks as CheckEvidence[]}
                sources={sources}
                verdicts={verdicts}
                files={item.files}
                onOpen={open}
              />
            )}
            {Array.isArray(evidence.scenarios) && (
              <ScenariosTable
                rows={evidence.scenarios as Record<string, unknown>[]}
                kpis={workflow.scenario_kpis}
              />
            )}

            {(item.links.length > 0 || item.files.length > 0) && (
              <ul className="flex flex-wrap gap-2 text-[13px]">
                {item.links.map((link) => (
                  <li key={link}>
                    <a
                      href={link}
                      target="_blank"
                      rel="noopener noreferrer"
                      dir="ltr"
                      className="text-[var(--fg-brand)] underline"
                    >
                      {link}
                    </a>
                  </li>
                ))}
                {item.files.map((file) => (
                  <li key={file.id}>
                    <button
                      type="button"
                      onClick={() => void open(file.id)}
                      className="text-[var(--fg-brand)] underline"
                    >
                      <span dir="ltr">{file.original_name}</span> ({formatBytes(file.size_bytes)})
                    </button>
                  </li>
                ))}
              </ul>
            )}

            {item.feedback && (
              <p className="rounded-[var(--radius-md)] bg-[var(--bg-sunken)] p-3 text-[13.5px] leading-[1.9]">
                <span className="font-semibold">بازخورد: </span>
                {item.feedback}
              </p>
            )}

            {reviewable && (
              <ReviewForm
                deliverable={item}
                accessToken={accessToken}
                onReviewed={(completed) => {
                  load();
                  onReviewed(completed);
                }}
              />
            )}
          </Card>
        );
      })}
    </section>
  );
}

interface CheckEvidence {
  location: string;
  finding: string;
  verdict: string;
  severity: string;
  sources: string[];
  image_file_ids: string[];
  resolution: string | null;
}

function AreaEvidence({ evidence }: { evidence: Record<string, unknown> }) {
  const overlaps = (evidence.overlaps as { project_id: string; title_fa: string }[]) ?? [];
  return (
    <div className="flex flex-wrap items-start gap-4">
      <div className="w-[140px]">
        <AreaPreview polygons={polygonsOf(evidence.area)} />
      </div>
      <div className="flex flex-col gap-1 text-[13.5px]">
        <p>
          مساحت:{' '}
          <span className="font-semibold">
            {toPersianDigits(Number(evidence.area_km2 ?? 0).toFixed(2))}
          </span>{' '}
          کیلومتر مربع
        </p>
        {overlaps.length === 0 ? (
          <p className="text-[var(--fg-success)]">با محدودهٔ پروژهٔ فعال دیگری هم‌پوشانی ندارد.</p>
        ) : (
          <p className="text-[var(--fg-warning)]">
            هشدار هم‌پوشانی با: {overlaps.map((o) => o.title_fa).join('، ')}
          </p>
        )}
      </div>
    </div>
  );
}

function ChecksTable({
  rows,
  sources,
  verdicts,
  files,
  onOpen,
}: {
  rows: CheckEvidence[];
  sources: Record<string, string>;
  verdicts: Record<string, string>;
  files: Deliverable['files'];
  onOpen: (fileId: string) => void;
}) {
  const names = Object.fromEntries(files.map((f) => [f.id, f.original_name]));
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[560px] text-[13px]">
        <caption className="mb-1 text-start font-medium">جدول راستی‌آزمایی</caption>
        <thead className="text-[var(--fg-tertiary)]">
          <tr className="text-start">
            <th className="p-1.5 text-start font-medium">موقعیت</th>
            <th className="p-1.5 text-start font-medium">یافته</th>
            <th className="p-1.5 text-start font-medium">منابع</th>
            <th className="p-1.5 text-start font-medium">تصویر</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={index} className="border-t border-[var(--border-subtle)] align-top">
              <td className="p-1.5">
                {row.location}
                <div className="mt-1 flex gap-1">
                  <Badge tone={row.verdict === 'MISMATCH' ? 'warning' : 'success'}>
                    {verdicts[row.verdict] ?? row.verdict}
                  </Badge>
                  {row.severity === 'CRITICAL' && <Badge tone="danger">بحرانی</Badge>}
                </div>
              </td>
              <td className="p-1.5">
                {row.finding}
                {row.resolution && (
                  <p className="mt-1 text-[var(--fg-tertiary)]">اصلاح: {row.resolution}</p>
                )}
              </td>
              <td className="p-1.5">{row.sources.map((s) => sources[s] ?? s).join('، ')}</td>
              <td className="p-1.5">
                <ul className="flex flex-col gap-0.5">
                  {row.image_file_ids.map((id) => (
                    <li key={id}>
                      <button
                        type="button"
                        onClick={() => onOpen(id)}
                        className="text-[var(--fg-brand)] underline"
                        dir="ltr"
                      >
                        {names[id] ?? 'تصویر'}
                      </button>
                    </li>
                  ))}
                </ul>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ScenariosTable({
  rows,
  kpis,
}: {
  rows: Record<string, unknown>[];
  kpis: { key: string; title_fa: string }[];
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[480px] text-[13px]">
        <caption className="mb-1 text-start font-medium">سناریوها</caption>
        <thead className="text-[var(--fg-tertiary)]">
          <tr>
            <th className="p-1.5 text-start font-medium">سناریو</th>
            {kpis.map((kpi) => (
              <th key={kpi.key} className="p-1.5 text-start font-medium">
                {kpi.title_fa}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={index} className="border-t border-[var(--border-subtle)]">
              <td className="p-1.5">
                {String(row.name)}
                {row.is_baseline === true && (
                  <Badge tone="neutral" className="ms-1">
                    پایه
                  </Badge>
                )}
              </td>
              {kpis.map((kpi) => (
                <td key={kpi.key} className="p-1.5 tabular-nums">
                  {toPersianDigits(String(row[kpi.key] ?? '—'))}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const DECISIONS: { value: ReviewDecision; label: string }[] = [
  { value: 'APPROVED', label: 'تأیید' },
  { value: 'CHANGES_REQUESTED', label: 'اصلاح کن' },
  { value: 'REJECTED', label: 'رد' },
];

function ReviewForm({
  deliverable,
  accessToken,
  onReviewed,
}: {
  deliverable: Deliverable;
  accessToken: string;
  onReviewed: (completed: boolean) => void;
}) {
  const [decision, setDecision] = useState<ReviewDecision>('APPROVED');
  const [feedback, setFeedback] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const blocked = decision !== 'APPROVED' && !feedback.trim();

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const result = await reviewDeliverable(
        deliverable.id,
        { decision, feedback: feedback.trim() || null },
        accessToken,
      );
      onReviewed(result.workflow_completed === true);
    } catch (cause) {
      setError(messageFor(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form
      onSubmit={submit}
      className="flex flex-col gap-3 rounded-[var(--radius-md)] border border-[var(--border-subtle)] p-3"
    >
      <fieldset className="flex flex-wrap gap-2">
        <legend className="mb-1 text-[13.5px] font-medium">بررسی</legend>
        {DECISIONS.map((option) => (
          <label
            key={option.value}
            className={`cursor-pointer rounded-[var(--radius-sm)] border px-3 py-1.5 text-[13.5px] ${
              decision === option.value
                ? 'border-[var(--brand-500)] bg-[var(--brand-50)] text-[var(--fg-brand)]'
                : 'border-[var(--border-default)] text-[var(--fg-secondary)]'
            }`}
          >
            <input
              type="radio"
              name={`decision-${deliverable.id}`}
              value={option.value}
              checked={decision === option.value}
              onChange={() => setDecision(option.value)}
              className="sr-only"
            />
            {option.label}
          </label>
        ))}
      </fieldset>
      <Textarea
        label="بازخورد"
        hint={decision === 'APPROVED' ? 'اختیاری' : 'اجباری — تیم باید بداند چه چیزی را درست کند.'}
        value={feedback}
        onChange={(event) => setFeedback(event.target.value)}
        rows={3}
        maxLength={5000}
      />
      {error && (
        <p role="alert" className="text-[13px] text-[var(--fg-danger)]">
          {error}
        </p>
      )}
      <Button type="submit" size="sm" className="self-start" loading={busy} disabled={blocked}>
        ثبت بررسی
      </Button>
    </form>
  );
}

function toneFor(status: Deliverable['status']) {
  if (status === 'APPROVED') return 'success' as const;
  if (status === 'CHANGES_REQUESTED') return 'warning' as const;
  if (status === 'REJECTED') return 'danger' as const;
  return 'info' as const;
}

function messageFor(cause: unknown): string {
  if (cause instanceof ApiError || cause instanceof NetworkError) return cause.message;
  return 'انجام نشد. کمی بعد دوباره تلاش کن.';
}
