'use client';

import Link from 'next/link';
import { useState } from 'react';

import { MilestoneTracker } from '@/components/domain/MilestoneTracker';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card, CardDescription, CardTitle } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { Textarea } from '@/components/ui/Textarea';
import { ApiError, NetworkError } from '@/lib/api/client';
import { formatBytes, uploadFile } from '@/lib/api/files';
import {
  type Deliverable,
  type Milestone,
  type ReviewDecision,
  fetchDeliverables,
  reviewDeliverable,
  submitDeliverable,
} from '@/lib/api/workspace';
import { formatDateLong, formatRelative } from '@/lib/format/date';
import { toPersianDigits } from '@/lib/format/digits';

/**
 * مراحل و تحویل‌دادنی — FR-PRJ-05، §7.6.
 *
 * دو نقش در یک صفحه‌اند و عمداً از هم جدا نشده‌اند: عضو تحویل می‌فرستد و
 * مدیر همان‌جا بررسی می‌کند. جدا کردنشان یعنی مدیر پروژه‌ای که خودش هم
 * عضو است، باید بین دو صفحه برود و بیاید.
 *
 * «اصلاح کن» و «رد» بدون بازخورد ارسال نمی‌شوند — سرور هم همین را
 * می‌گوید (§7.6)، ولی گرفتن جلوی کلیک بهتر از خطای پس از کلیک است.
 */

const MAX_FILES = 10;

export function MilestonesTab({
  projectId,
  milestones,
  canReview,
  isMember,
  accessToken,
  onChanged,
}: {
  projectId: string;
  milestones: Milestone[];
  canReview: boolean;
  isMember: boolean;
  accessToken: string;
  onChanged: () => void;
}) {
  if (milestones.length === 0) {
    return (
      <EmptyState
        title="هنوز مرحله‌ای تعریف نشده"
        description="پروژه بدون مرحله، تحویل‌دادنی ندارد. مدیر پروژه باید دست‌کم یک مرحله تعریف کند."
      />
    );
  }

  return (
    <MilestoneTracker
      milestones={milestones}
      renderExtra={(milestone) => (
        <MilestonePanel
          key={milestone.id}
          projectId={projectId}
          milestone={milestone}
          canReview={canReview}
          isMember={isMember}
          accessToken={accessToken}
          onChanged={onChanged}
        />
      )}
    />
  );
}

function MilestonePanel({
  milestone,
  canReview,
  isMember,
  accessToken,
  onChanged,
}: {
  projectId: string;
  milestone: Milestone;
  canReview: boolean;
  isMember: boolean;
  accessToken: string;
  onChanged: () => void;
}) {
  const [history, setHistory] = useState<Deliverable[] | null>(null);
  const [historyError, setHistoryError] = useState<string | null>(null);

  const mine = milestone.my_deliverable;
  // مرحلهٔ گردش‌کار شهری شاهد ساختاریافته دارد؛ فرمش در صفحهٔ گردش‌کار است.
  const isCityStage = milestone.workflow_stage !== null;
  const canSubmit =
    !isCityStage &&
    isMember &&
    milestone.status !== 'APPROVED' &&
    (mine === null || mine.status === 'CHANGES_REQUESTED');

  async function loadHistory() {
    try {
      setHistory(await fetchDeliverables(milestone.id, accessToken));
    } catch (cause) {
      setHistoryError(messageFor(cause));
    }
  }

  return (
    <div className="mt-2 flex flex-col gap-3">
      {milestone.owner_name && (
        <p className="text-[12.5px] text-[var(--fg-tertiary)]">مسئول: {milestone.owner_name}</p>
      )}
      {isCityStage && (
        <Button asChild variant="secondary" size="sm" className="self-start">
          <Link href={`/projects/${milestone.project_id}/city`}>
            تحویل و بررسی در صفحهٔ گردش‌کار شهری
          </Link>
        </Button>
      )}
      {mine && <DeliverableCard deliverable={mine} label="آخرین تحویل تو" />}

      {!isCityStage && mine && canReview && mine.status !== 'APPROVED' && (
        <ReviewForm deliverable={mine} accessToken={accessToken} onReviewed={onChanged} />
      )}

      {canSubmit && (
        <SubmitForm
          milestone={milestone}
          accessToken={accessToken}
          onSubmitted={onChanged}
          isRevision={mine !== null}
        />
      )}

      {milestone.deliverable_count > 0 && (
        <div>
          {history === null ? (
            <Button variant="ghost" size="sm" onClick={loadHistory}>
              دیدن همهٔ نسخه‌ها ({toPersianDigits(milestone.deliverable_count)})
            </Button>
          ) : (
            <div className="flex flex-col gap-2">
              {history.map((item) => (
                <DeliverableCard
                  key={item.id}
                  deliverable={item}
                  label={`${item.submitter_name ?? 'عضو تیم'} — نسخهٔ ${toPersianDigits(item.version)}`}
                  compact
                />
              ))}
            </div>
          )}
          {historyError && (
            <p role="alert" className="text-[12.5px] text-[var(--fg-danger)]">
              {historyError}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

function DeliverableCard({
  deliverable,
  label,
  compact = false,
}: {
  deliverable: Deliverable;
  label: string;
  compact?: boolean;
}) {
  return (
    <Card className={compact ? 'flex flex-col gap-2 p-4' : 'flex flex-col gap-2.5'}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[13.5px] font-medium text-[var(--fg-primary)]">{label}</span>
        <Badge tone={toneFor(deliverable.status)}>{deliverable.status_fa}</Badge>
        {deliverable.is_late && <Badge tone="warning">با تأخیر</Badge>}
        <span className="text-[12px] text-[var(--fg-tertiary)]">
          {formatRelative(deliverable.submitted_at)}
        </span>
      </div>

      {deliverable.body && (
        <p className="whitespace-pre-line text-[13.5px] leading-[1.95] text-[var(--fg-secondary)]">
          {deliverable.body}
        </p>
      )}

      {deliverable.links.length > 0 && (
        <ul className="flex flex-col gap-1">
          {deliverable.links.map((link) => (
            <li key={link}>
              <a
                href={link}
                target="_blank"
                rel="noreferrer noopener"
                dir="ltr"
                className="inline-block text-[12.5px] text-[var(--fg-brand)] underline"
              >
                {link}
              </a>
            </li>
          ))}
        </ul>
      )}

      {deliverable.files.length > 0 && (
        <ul className="flex flex-wrap gap-2">
          {deliverable.files.map((file) => (
            <li
              key={file.id}
              className="rounded-[var(--radius-sm)] bg-[var(--bg-sunken)] px-2.5 py-1 text-[12.5px] text-[var(--fg-secondary)]"
            >
              {file.original_name} — {formatBytes(file.size_bytes)}
            </li>
          ))}
        </ul>
      )}

      {deliverable.feedback && (
        <div className="rounded-[var(--radius-sm)] bg-[var(--bg-sunken)] p-3">
          <p className="text-[12.5px] font-medium text-[var(--fg-primary)]">بازخورد بازبین</p>
          <p className="mt-1 whitespace-pre-line text-[13px] leading-[1.9] text-[var(--fg-secondary)]">
            {deliverable.feedback}
          </p>
          {deliverable.score !== null && (
            <p className="mt-1.5 text-[12.5px] text-[var(--fg-tertiary)]">
              نمره: {toPersianDigits(deliverable.score)}
            </p>
          )}
        </div>
      )}
    </Card>
  );
}

function SubmitForm({
  milestone,
  accessToken,
  onSubmitted,
  isRevision,
}: {
  milestone: Milestone;
  accessToken: string;
  onSubmitted: () => void;
  isRevision: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [body, setBody] = useState('');
  const [links, setLinks] = useState('');
  const [files, setFiles] = useState<File[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!open) {
    return (
      <Button
        variant={isRevision ? 'primary' : 'secondary'}
        size="sm"
        className="self-start"
        onClick={() => setOpen(true)}
      >
        {isRevision ? 'ارسال نسخهٔ اصلاح‌شده' : 'ارسال تحویل‌دادنی'}
      </Button>
    );
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      // فایل‌ها اول آپلود می‌شوند: تحویل‌دادنی با پیوست نیمه‌کاره بدتر از
      // تحویل‌دادنی ساخته‌نشده است.
      const uploaded = [];
      for (const file of files) {
        uploaded.push(await uploadFile(file, 'DELIVERABLE', accessToken));
      }

      await submitDeliverable(
        milestone.id,
        {
          body: body.trim() || null,
          links: links
            .split('\n')
            .map((line) => line.trim())
            .filter(Boolean),
          file_ids: uploaded.map((file) => file.id),
        },
        accessToken,
      );
      setOpen(false);
      setBody('');
      setLinks('');
      setFiles([]);
      onSubmitted();
    } catch (cause) {
      setError(messageFor(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card variant="raised" className="flex flex-col gap-3">
      <CardTitle>{isRevision ? 'نسخهٔ اصلاح‌شده' : 'تحویل این مرحله'}</CardTitle>
      {milestone.due_on && (
        <CardDescription>مهلت: {formatDateLong(milestone.due_on)}</CardDescription>
      )}

      <form onSubmit={handleSubmit} className="flex flex-col gap-3">
        <Textarea
          label="توضیح"
          hint="چه کاری انجام شد و نتیجه چه بود؟"
          value={body}
          onChange={(event) => setBody(event.target.value)}
          maxLength={5000}
          rows={4}
        />

        <Textarea
          label="لینک‌ها"
          hint="هر لینک در یک خط — مثلاً مخزن کد یا سند آنلاین."
          value={links}
          onChange={(event) => setLinks(event.target.value)}
          rows={2}
          dir="ltr"
        />

        <div className="flex flex-col gap-1.5">
          <label
            htmlFor={`files-${milestone.id}`}
            className="text-[13.5px] font-medium text-[var(--fg-primary)]"
          >
            فایل‌ها
          </label>
          <input
            id={`files-${milestone.id}`}
            type="file"
            multiple
            onChange={(event) => setFiles(Array.from(event.target.files ?? []).slice(0, MAX_FILES))}
            className="text-[13px] text-[var(--fg-secondary)] file:me-3 file:rounded-[var(--radius-sm)] file:border file:border-[var(--border-default)] file:bg-[var(--bg-surface)] file:px-3 file:py-1.5 file:text-[13px]"
          />
          {files.length > 0 && (
            <ul className="flex flex-col gap-0.5 text-[12.5px] text-[var(--fg-tertiary)]">
              {files.map((file) => (
                <li key={file.name}>
                  {file.name} — {formatBytes(file.size)}
                </li>
              ))}
            </ul>
          )}
        </div>

        {error && (
          <p role="alert" className="text-[13px] text-[var(--fg-danger)]">
            {error}
          </p>
        )}

        <div className="flex items-center gap-2">
          <Button type="submit" size="sm" loading={busy}>
            ارسال
          </Button>
          <Button type="button" size="sm" variant="ghost" onClick={() => setOpen(false)}>
            انصراف
          </Button>
        </div>
      </form>
    </Card>
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
  onReviewed: () => void;
}) {
  const [decision, setDecision] = useState<ReviewDecision>('APPROVED');
  const [feedback, setFeedback] = useState('');
  const [score, setScore] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [readyToClose, setReadyToClose] = useState(false);

  const feedbackRequired = decision !== 'APPROVED';
  const blocked = feedbackRequired && feedback.trim().length === 0;

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const result = await reviewDeliverable(
        deliverable.id,
        {
          decision,
          feedback: feedback.trim() || null,
          score: score.trim() ? Number(score) : null,
        },
        accessToken,
      );
      setReadyToClose(result.project_ready_to_close);
      onReviewed();
    } catch (cause) {
      setError(messageFor(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card variant="raised" className="flex flex-col gap-3">
      <CardTitle>بررسی تحویل</CardTitle>

      <form onSubmit={handleSubmit} className="flex flex-col gap-3">
        <fieldset className="flex flex-col gap-2">
          <legend className="text-[13.5px] font-medium text-[var(--fg-primary)]">تصمیم</legend>
          <div className="flex flex-wrap gap-2">
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
          </div>
        </fieldset>

        <Textarea
          label="بازخورد"
          hint={
            feedbackRequired
              ? 'برای «اصلاح کن» و «رد» اجباری است: دانشجو باید بداند چه چیزی را درست کند.'
              : 'اختیاری، ولی یک جملهٔ کوتاه هم بهتر از سکوت است.'
          }
          value={feedback}
          onChange={(event) => setFeedback(event.target.value)}
          maxLength={5000}
          rows={3}
          required={feedbackRequired}
        />

        <label className="flex flex-col gap-1.5">
          <span className="text-[13.5px] font-medium text-[var(--fg-primary)]">نمره (اختیاری)</span>
          <input
            type="number"
            min={0}
            step="0.5"
            value={score}
            onChange={(event) => setScore(event.target.value)}
            className="h-10 w-28 rounded-[var(--radius-md)] border border-[var(--border-default)] bg-[var(--bg-surface)] px-3 text-[14px] tabular-nums"
          />
        </label>

        {error && (
          <p role="alert" className="text-[13px] text-[var(--fg-danger)]">
            {error}
          </p>
        )}

        {readyToClose && (
          <p className="text-[13px] text-[var(--fg-success)]">
            همهٔ مراحل الزامی تأیید شدند — پروژه آمادهٔ بسته شدن است.
          </p>
        )}

        <Button type="submit" size="sm" className="self-start" loading={busy} disabled={blocked}>
          ثبت بررسی
        </Button>
      </form>
    </Card>
  );
}

function toneFor(status: Deliverable['status']) {
  switch (status) {
    case 'APPROVED':
      return 'success' as const;
    case 'CHANGES_REQUESTED':
      return 'warning' as const;
    case 'REJECTED':
      return 'danger' as const;
    default:
      return 'info' as const;
  }
}

function messageFor(cause: unknown): string {
  if (cause instanceof ApiError || cause instanceof NetworkError) return cause.message;
  return 'انجام نشد. کمی بعد دوباره تلاش کن.';
}
