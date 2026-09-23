'use client';

import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';

import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card, CardDescription, CardTitle } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { Input } from '@/components/ui/Input';
import { SkeletonCard } from '@/components/ui/Skeleton';
import { Textarea } from '@/components/ui/Textarea';
import { ApiError, NetworkError } from '@/lib/api/client';
import { formatBytes, uploadFile } from '@/lib/api/files';
import {
  type EvidenceField,
  type Level,
  type Submission,
  type Track,
  fetchTrack,
  submissionFileUrl,
  submitLevel,
} from '@/lib/api/research';
import { useSession } from '@/lib/auth/use-session';
import { formatDateLong } from '@/lib/format/date';
import { toLatinDigits, toPersianDigits } from '@/lib/format/digits';

/**
 * `/research/level/[n]` — راهنما، الگو و تحویل یک سطح، FR-RES-01.
 *
 * «هر سطح الگو و راهنمای گام‌به‌گام دارد». الگوی ستونی (ماتریس مرور،
 * ساختار دفترچه، …) به‌صورت CSV با BOM دانلود می‌شود تا Excel فارسی را
 * درست باز کند. شاهدهای ساختاریافته از سرور می‌آیند و فرم از روی آن‌ها
 * ساخته می‌شود؛ کمبودها را سرور یک‌جا برمی‌گرداند (`details.missing`).
 */

const MAX_FILES = 10;
/** Excel بدون BOM، CSV فارسی را با کدگذاری ویندوز می‌خواند و درهم نشان می‌دهد. */
const UTF8_BOM = String.fromCharCode(0xfeff);

export function LevelView({ level: number }: { level: number }) {
  const { accessToken, loading: sessionLoading } = useSession();
  const [track, setTrack] = useState<Track | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    if (sessionLoading) return;
    fetchTrack(accessToken)
      .then(setTrack)
      .catch((cause) => setError(messageFor(cause)));
  }, [accessToken, sessionLoading]);

  useEffect(load, [load]);

  const level = track?.levels.find((item) => item.level === number);

  if (error) {
    return (
      <p role="alert" className="text-[13.5px] text-[var(--danger-600)]">
        {error}
      </p>
    );
  }
  if (track === null) return <SkeletonCard label="در حال بارگذاری سطح" />;
  if (!level) {
    return (
      <EmptyState
        title="این سطح وجود ندارد"
        description="مسیر پژوهش چهار سطح دارد."
        action={
          <Button asChild>
            <Link href="/research">بازگشت به مسیر</Link>
          </Button>
        }
      />
    );
  }

  const canSubmit =
    track.can_participate && (level.state === 'AVAILABLE' || level.state === 'IN_PROGRESS');

  return (
    <div className="flex flex-col gap-8">
      <header className="flex flex-col gap-2">
        <Link href="/research" className="text-[13px] text-[var(--fg-tertiary)] hover:underline">
          ← مسیر پژوهش
        </Link>
        <div className="flex flex-wrap items-center gap-3">
          <h1>
            سطح {toPersianDigits(level.level)}: {level.title_fa}
          </h1>
          <Badge tone={level.state === 'APPROVED' ? 'success' : 'brand'}>{level.state_fa}</Badge>
        </div>
        <p className="text-[15px] text-[var(--fg-secondary)]">{level.deliverable_fa}</p>
        {track.topic && (
          <p className="text-[13.5px] text-[var(--fg-secondary)]">
            موضوع: <span className="font-medium">{track.topic.title}</span>
          </p>
        )}
      </header>

      <div className="grid gap-6 lg:grid-cols-[1.2fr_1fr]">
        <section className="flex flex-col gap-4" aria-labelledby="guide-title">
          <h2 id="guide-title" className="text-[18px] font-semibold">
            راهنمای گام‌به‌گام
          </h2>
          <ol className="flex flex-col gap-2 ps-6 text-[14.5px] leading-[1.95] [list-style-type:persian]">
            {level.steps.map((step) => (
              <li key={step}>{step}</li>
            ))}
          </ol>
          <h3 className="mt-2 text-[16px] font-semibold">پیش از تحویل، این‌ها را بسنج</h3>
          <ul className="flex flex-col gap-1.5 text-[14px] leading-[1.9] text-[var(--fg-secondary)]">
            {level.checklist.map((item) => (
              <li key={item} className="flex gap-2">
                <span aria-hidden>☐</span>
                {item}
              </li>
            ))}
          </ul>
        </section>

        <aside className="flex flex-col gap-4">
          <TemplateCard level={level} />
          {level.mentor?.name && (
            <p className="text-[13.5px] text-[var(--fg-secondary)]">
              منتور این سطح: <span className="font-medium">{level.mentor.name}</span>
            </p>
          )}
        </aside>
      </div>

      {canSubmit && accessToken && (
        <SubmitForm level={level} accessToken={accessToken} onSubmitted={load} />
      )}
      {level.state === 'LOCKED' && (
        <p className="text-[14px] text-[var(--fg-secondary)]">
          این سطح پس از تأیید سطح {toPersianDigits(level.level - 1)} باز می‌شود. راهنما را از همین
          حالا بخوان.
        </p>
      )}
      {level.state === 'SUBMITTED' && (
        <p className="text-[14px] text-[var(--fg-secondary)]">
          تحویلت در صف بررسی است. نتیجه را با اعلان خبر می‌دهیم.
        </p>
      )}

      {level.submissions.length > 0 && accessToken && (
        <section className="flex flex-col gap-3" aria-labelledby="history-title">
          <h2 id="history-title" className="text-[18px] font-semibold">
            تحویل‌ها
          </h2>
          <ul className="flex flex-col gap-3">
            {level.submissions.map((submission) => (
              <li key={submission.id}>
                <SubmissionCard
                  submission={submission}
                  fields={level.evidence_fields}
                  accessToken={accessToken}
                />
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

function TemplateCard({ level }: { level: Level }) {
  function download() {
    // BOM تا Excel متن فارسی را UTF-8 بخواند.
    const header = level.template_columns.map((c) => `"${c.replace(/"/g, '""')}"`).join(',');
    const blob = new Blob([`${UTF8_BOM}${header}\n`], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `research-level-${level.level}-template.csv`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  return (
    <Card className="flex flex-col gap-3">
      <CardTitle>الگو: {level.template_title_fa}</CardTitle>
      <ul className="flex flex-wrap gap-1.5">
        {level.template_columns.map((column) => (
          <li key={column}>
            <Badge tone="neutral">{column}</Badge>
          </li>
        ))}
      </ul>
      <Button variant="secondary" size="sm" className="self-start" onClick={download}>
        دانلود الگو (CSV)
      </Button>
    </Card>
  );
}

function SubmitForm({
  level,
  accessToken,
  onSubmitted,
}: {
  level: Level;
  accessToken: string;
  onSubmitted: () => void;
}) {
  const isRevision = level.submissions[0]?.status === 'CHANGES_REQUESTED';
  const [summary, setSummary] = useState('');
  const [links, setLinks] = useState('');
  const [files, setFiles] = useState<File[]>([]);
  const [evidence, setEvidence] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [missing, setMissing] = useState<string[]>([]);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setMissing([]);
    try {
      const uploaded = [];
      for (const file of files) {
        uploaded.push(await uploadFile(file, 'DELIVERABLE', accessToken));
      }
      const values: Record<string, string | number> = {};
      for (const field of level.evidence_fields) {
        const raw = (evidence[field.key] ?? '').trim();
        if (!raw) continue;
        values[field.key] = field.kind === 'int' ? Number(toLatinDigits(raw)) : raw;
      }
      await submitLevel(accessToken, level.level, {
        summary: summary.trim(),
        links: links
          .split('\n')
          .map((line) => line.trim())
          .filter(Boolean),
        file_ids: uploaded.map((file) => file.id),
        evidence: values,
      });
      setSummary('');
      setLinks('');
      setFiles([]);
      setEvidence({});
      onSubmitted();
    } catch (cause) {
      const list =
        cause instanceof ApiError && Array.isArray(cause.details.missing)
          ? (cause.details.missing as string[])
          : [];
      if (list.length > 0) setMissing(list);
      else setError(messageFor(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card variant="raised" className="flex flex-col gap-4">
      <CardTitle>{isRevision ? 'نسخهٔ اصلاح‌شده' : 'تحویل این سطح'}</CardTitle>
      {level.attachments_hint_fa && <CardDescription>{level.attachments_hint_fa}</CardDescription>}
      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        <Textarea
          label="خلاصهٔ تحویل"
          hint="چه کردی، چه یافتی، و بازبین کجا را باید با دقت ببیند؟"
          value={summary}
          onChange={(event) => setSummary(event.target.value)}
          maxLength={4000}
          rows={5}
          required
        />
        {level.evidence_fields.map((field) => (
          <EvidenceInput
            key={field.key}
            field={field}
            value={evidence[field.key] ?? ''}
            onChange={(value) => setEvidence((prev) => ({ ...prev, [field.key]: value }))}
          />
        ))}
        <Textarea
          label="پیوندها"
          hint="هر پیوند در یک خط — ماتریس آنلاین، مخزن کد، صفحهٔ کنفرانس."
          value={links}
          onChange={(event) => setLinks(event.target.value)}
          rows={2}
          dir="ltr"
        />
        <div className="flex flex-col gap-1.5">
          <label
            htmlFor={`research-files-${level.level}`}
            className="text-[13.5px] font-medium text-[var(--fg-primary)]"
          >
            فایل‌ها
          </label>
          <input
            id={`research-files-${level.level}`}
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

        {missing.length > 0 && (
          <div role="alert" className="flex flex-col gap-1 text-[13.5px] text-[var(--danger-600)]">
            <p className="font-semibold">تحویل هنوز کامل نیست:</p>
            <ul className="list-disc ps-5">
              {missing.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </div>
        )}
        {error && (
          <p role="alert" className="text-[13.5px] text-[var(--danger-600)]">
            {error}
          </p>
        )}
        <Button type="submit" loading={busy} className="self-start">
          ارسال برای بررسی
        </Button>
      </form>
    </Card>
  );
}

function EvidenceInput({
  field,
  value,
  onChange,
}: {
  field: EvidenceField;
  value: string;
  onChange: (value: string) => void;
}) {
  const hint = field.hint_fa ?? undefined;
  if (field.kind === 'text' && (field.min_length ?? 0) >= 50) {
    return (
      <Textarea
        label={field.label_fa}
        hint={hint}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        rows={3}
        maxLength={1500}
      />
    );
  }
  return (
    <Input
      label={field.label_fa}
      hint={hint}
      value={value}
      onChange={(event) => onChange(event.target.value)}
      type={field.kind === 'date' ? 'date' : field.kind === 'url' ? 'url' : 'text'}
      inputMode={field.kind === 'int' ? 'numeric' : undefined}
      forceLtr={field.kind === 'url' || field.kind === 'date'}
    />
  );
}

function SubmissionCard({
  submission,
  fields,
  accessToken,
}: {
  submission: Submission;
  fields: EvidenceField[];
  accessToken: string;
}) {
  const [error, setError] = useState<string | null>(null);
  const labels = Object.fromEntries(fields.map((f) => [f.key, f.label_fa]));

  async function open(fileId: string) {
    try {
      const { download_url } = await submissionFileUrl(accessToken, submission.id, fileId);
      window.open(download_url, '_blank', 'noopener');
    } catch (cause) {
      setError(messageFor(cause));
    }
  }

  return (
    <Card className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-[14.5px] font-semibold">نسخهٔ {toPersianDigits(submission.version)}</p>
        <div className="flex items-center gap-2">
          <Badge
            tone={
              submission.status === 'APPROVED'
                ? 'success'
                : submission.status === 'CHANGES_REQUESTED'
                  ? 'warning'
                  : 'neutral'
            }
          >
            {submission.status_fa}
          </Badge>
          <span className="text-[12.5px] text-[var(--fg-tertiary)]">
            {formatDateLong(submission.submitted_at)}
          </span>
        </div>
      </div>
      <p className="whitespace-pre-line text-[14px] leading-[1.9]">{submission.summary}</p>
      <dl className="grid gap-1 text-[13px] sm:grid-cols-2">
        {Object.entries(submission.evidence).map(([key, value]) => (
          <div key={key} className="flex gap-1.5">
            <dt className="text-[var(--fg-tertiary)]">{labels[key] ?? key}:</dt>
            <dd className="break-words">{toPersianDigits(String(value))}</dd>
          </div>
        ))}
      </dl>
      {(submission.links.length > 0 || submission.files.length > 0) && (
        <ul className="flex flex-wrap gap-2 text-[13px]">
          {submission.links.map((link) => (
            <li key={link}>
              <a
                href={link}
                target="_blank"
                rel="noopener noreferrer"
                dir="ltr"
                className="text-[var(--brand-700)] underline"
              >
                {link}
              </a>
            </li>
          ))}
          {submission.files.map((file) => (
            <li key={file.id}>
              <button
                type="button"
                onClick={() => open(file.id)}
                className="text-[var(--brand-700)] underline"
              >
                {file.original_name}
              </button>
            </li>
          ))}
        </ul>
      )}
      {submission.feedback && (
        <p className="rounded-[var(--radius-md)] bg-[var(--bg-sunken)] p-3 text-[13.5px] leading-[1.9]">
          <span className="font-semibold">
            بازخورد{submission.reviewer?.name ? ` ${submission.reviewer.name}` : ''}:{' '}
          </span>
          {submission.feedback}
        </p>
      )}
      {error && (
        <p role="alert" className="text-[13px] text-[var(--danger-600)]">
          {error}
        </p>
      )}
    </Card>
  );
}

function messageFor(cause: unknown): string {
  if (cause instanceof ApiError || cause instanceof NetworkError) return cause.message;
  return 'کار انجام نشد. کمی بعد دوباره تلاش کن.';
}
