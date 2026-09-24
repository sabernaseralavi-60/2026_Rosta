'use client';

import { useState } from 'react';

import { AreaPreview, polygonsOf } from '@/components/domain/AreaPreview';
import { Button } from '@/components/ui/Button';
import { Card, CardDescription, CardTitle } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { Textarea } from '@/components/ui/Textarea';
import { ApiError, NetworkError } from '@/lib/api/client';
import type { CityEvidenceField, CityStageSpec, CityWorkflow } from '@/lib/api/city';
import { formatBytes, uploadFile } from '@/lib/api/files';
import { type Milestone, submitDeliverable } from '@/lib/api/workspace';
import { cn } from '@/lib/cn';
import { toLatinDigits, toPersianDigits } from '@/lib/format/digits';

/**
 * فرم تحویل یک مرحلهٔ گردش‌کار شهری — FR-CITY-01، ADR-0016.
 *
 * میدان‌ها، چک‌لیست و فایل‌های لازم از الگوی سرور می‌آیند. سه مرحله شاهد
 * ساختاریافته دارند: محدودهٔ GeoJSON (۱)، جدول راستی‌آزمایی با تصویر (۳)،
 * و سناریوها (۶). کمبودها را سرور یک‌جا برمی‌گرداند؛ فرم فقط نشانشان
 * می‌دهد و خودش قاعده‌ای را تکرار نمی‌کند.
 */

const MAX_FILES = 10;

interface CheckRow {
  location: string;
  finding: string;
  verdict: string;
  severity: string;
  sources: string[];
  images: File[];
  resolution: string;
}

interface ScenarioRow {
  name: string;
  description: string;
  is_baseline: boolean;
  values: Record<string, string>;
}

const emptyCheck = (): CheckRow => ({
  location: '',
  finding: '',
  verdict: 'MISMATCH',
  severity: 'NORMAL',
  sources: [],
  images: [],
  resolution: '',
});

const emptyScenario = (baseline = false): ScenarioRow => ({
  name: baseline ? 'وضع موجود' : '',
  description: '',
  is_baseline: baseline,
  values: {},
});

export function StageSubmitForm({
  spec,
  workflow,
  milestone,
  accessToken,
  isRevision,
  onSubmitted,
}: {
  spec: CityStageSpec;
  workflow: CityWorkflow;
  milestone: Milestone;
  accessToken: string;
  isRevision: boolean;
  onSubmitted: () => void;
}) {
  const [summary, setSummary] = useState('');
  const [fields, setFields] = useState<Record<string, string>>({});
  const [links, setLinks] = useState('');
  const [files, setFiles] = useState<File[]>([]);
  const [confirmed, setConfirmed] = useState<Set<number>>(new Set());
  const [areaText, setAreaText] = useState('');
  const [checks, setChecks] = useState<CheckRow[]>([emptyCheck()]);
  const [scenarios, setScenarios] = useState<ScenarioRow[]>([
    emptyScenario(true),
    emptyScenario(),
    emptyScenario(),
  ]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [missing, setMissing] = useState<string[]>([]);

  const area = parseJson(areaText);
  const imageCount = checks.reduce((sum, row) => sum + row.images.length, 0);
  const totalFiles = files.length + imageCount;

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setMissing([]);
    if (spec.structured === 'AREA' && areaText.trim() && area === undefined) {
      setMissing(['متن GeoJSON قابل خواندن نیست']);
      return;
    }
    if (totalFiles > MAX_FILES) {
      setMissing([`حداکثر ${toPersianDigits(MAX_FILES)} فایل در هر تحویل`]);
      return;
    }
    setBusy(true);
    try {
      const uploaded: string[] = [];
      for (const file of files) {
        uploaded.push((await uploadFile(file, 'DELIVERABLE', accessToken)).id);
      }
      const evidence: Record<string, unknown> = {};
      for (const field of spec.evidence) {
        const raw = (fields[field.key] ?? '').trim();
        if (raw) evidence[field.key] = convert(field, raw);
      }
      if (spec.structured === 'AREA' && area !== undefined) evidence.area = area;
      if (spec.structured === 'CHECKS') {
        const rows = [];
        for (const row of checks) {
          const ids: string[] = [];
          for (const image of row.images) {
            const stored = await uploadFile(image, 'DELIVERABLE', accessToken);
            ids.push(stored.id);
            uploaded.push(stored.id);
          }
          rows.push({
            location: row.location,
            finding: row.finding,
            verdict: row.verdict,
            severity: row.severity,
            sources: row.sources,
            image_file_ids: ids,
            resolution: row.resolution,
          });
        }
        evidence.checks = rows;
      }
      if (spec.structured === 'SCENARIOS') {
        evidence.scenarios = scenarios.map((row) => ({
          name: row.name,
          description: row.description,
          is_baseline: row.is_baseline,
          ...Object.fromEntries(
            workflow.scenario_kpis.map((kpi) => {
              const raw = (row.values[kpi.key] ?? '').trim();
              return [kpi.key, raw ? Number(toLatinDigits(raw)) : null];
            }),
          ),
        }));
      }
      await submitDeliverable(
        milestone.id,
        {
          body: summary.trim() || null,
          links: links
            .split('\n')
            .map((line) => line.trim())
            .filter(Boolean),
          file_ids: uploaded,
          evidence,
          checklist_confirmed: [...confirmed],
        },
        accessToken,
      );
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

  const manual = spec.checklist
    .map((item, index) => ({ ...item, index }))
    .filter((item) => !item.auto);

  return (
    <Card variant="raised" className="flex flex-col gap-4">
      <div className="flex flex-col gap-1">
        <CardTitle>{isRevision ? 'نسخهٔ اصلاح‌شده' : `تحویل «${spec.title_fa}»`}</CardTitle>
        <CardDescription>{spec.deliverable_fa}</CardDescription>
      </div>

      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        <Textarea
          label="خلاصهٔ تحویل"
          hint="چه کردی، چه یافتی، و بازبین کجا را باید با دقت ببیند؟"
          value={summary}
          onChange={(event) => setSummary(event.target.value)}
          maxLength={5000}
          rows={4}
          required
        />

        {spec.structured === 'AREA' && (
          <AreaInput
            text={areaText}
            onText={setAreaText}
            parsed={area}
            min={workflow.area_min_km2}
            max={workflow.area_max_km2}
          />
        )}

        {spec.evidence.map((field) => (
          <EvidenceInput
            key={field.key}
            field={field}
            value={fields[field.key] ?? ''}
            onChange={(value) => setFields((prev) => ({ ...prev, [field.key]: value }))}
          />
        ))}

        {spec.structured === 'CHECKS' && (
          <ChecksEditor rows={checks} onChange={setChecks} workflow={workflow} />
        )}
        {spec.structured === 'SCENARIOS' && (
          <ScenariosEditor rows={scenarios} onChange={setScenarios} workflow={workflow} />
        )}

        {(spec.files.length > 0 || spec.min_attachments > 0 || spec.structured !== 'CHECKS') && (
          <div className="flex flex-col gap-1.5">
            <label
              htmlFor={`city-files-${spec.number}`}
              className="text-[13.5px] font-medium text-[var(--fg-primary)]"
            >
              فایل‌ها
            </label>
            {spec.files.length > 0 && (
              <p className="text-[12.5px] text-[var(--fg-tertiary)]">
                لازم: {spec.files.map((rule) => rule.label_fa).join('، ')}
              </p>
            )}
            <input
              id={`city-files-${spec.number}`}
              type="file"
              multiple
              onChange={(event) =>
                setFiles(Array.from(event.target.files ?? []).slice(0, MAX_FILES))
              }
              className="text-[13px] text-[var(--fg-secondary)] file:me-3 file:rounded-[var(--radius-sm)] file:border file:border-[var(--border-default)] file:bg-[var(--bg-surface)] file:px-3 file:py-1.5 file:text-[13px]"
            />
            {files.length > 0 && (
              <ul className="flex flex-col gap-0.5 text-[12.5px] text-[var(--fg-tertiary)]">
                {files.map((file) => (
                  <li key={file.name}>
                    <span dir="ltr">{file.name}</span> — {formatBytes(file.size)}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        <Textarea
          label="پیوندها"
          hint={spec.attachments_hint_fa ?? 'هر پیوند در یک خط — مخزن کد، سند آنلاین.'}
          value={links}
          onChange={(event) => setLinks(event.target.value)}
          rows={2}
          dir="ltr"
        />

        {manual.length > 0 && (
          <fieldset className="flex flex-col gap-2">
            <legend className="mb-1 text-[13.5px] font-medium text-[var(--fg-primary)]">
              تأیید چک‌لیست کیفیت
            </legend>
            {manual.map((item) => (
              <label key={item.index} className="flex items-start gap-2 text-[14px]">
                <input
                  type="checkbox"
                  className="mt-1.5"
                  checked={confirmed.has(item.index)}
                  onChange={(event) =>
                    setConfirmed((prev) => {
                      const next = new Set(prev);
                      if (event.target.checked) next.add(item.index);
                      else next.delete(item.index);
                      return next;
                    })
                  }
                />
                {item.text}
              </label>
            ))}
            <p className="text-[12.5px] text-[var(--fg-tertiary)]">
              بقیهٔ موارد چک‌لیست را سامانه خودش می‌سنجد.
            </p>
          </fieldset>
        )}

        {missing.length > 0 && (
          <div role="alert" className="flex flex-col gap-1 text-[13.5px] text-[var(--fg-danger)]">
            <p className="font-semibold">تحویل هنوز کامل نیست:</p>
            <ul className="list-disc ps-5">
              {missing.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </div>
        )}
        {error && (
          <p role="alert" className="text-[13.5px] text-[var(--fg-danger)]">
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

// ── محدوده ─────────────────────────────────────────────────────────────
function AreaInput({
  text,
  onText,
  parsed,
  min,
  max,
}: {
  text: string;
  onText: (value: string) => void;
  parsed: unknown;
  min: number;
  max: number;
}) {
  const polygons = polygonsOf(parsed);

  async function readFile(file: File | undefined) {
    if (file) onText(await file.text());
  }

  return (
    <div className="flex flex-col gap-2">
      <label
        htmlFor="city-area-file"
        className="text-[13.5px] font-medium text-[var(--fg-primary)]"
      >
        محدودهٔ مطالعه (GeoJSON)
      </label>
      <p className="text-[12.5px] text-[var(--fg-tertiary)]">
        چندضلعی بسته، با مساحت بین {toPersianDigits(min)} و {toPersianDigits(max)} کیلومتر مربع.
        فایل را از geojson.io یا QGIS بارگذاری کن یا متنش را بچسبان.
      </p>
      <input
        id="city-area-file"
        type="file"
        accept=".geojson,.json,application/geo+json,application/json"
        onChange={(event) => void readFile(event.target.files?.[0])}
        className="text-[13px] text-[var(--fg-secondary)] file:me-3 file:rounded-[var(--radius-sm)] file:border file:border-[var(--border-default)] file:bg-[var(--bg-surface)] file:px-3 file:py-1.5 file:text-[13px]"
      />
      <Textarea
        label="متن GeoJSON"
        value={text}
        onChange={(event) => onText(event.target.value)}
        rows={4}
        dir="ltr"
        className="font-mono text-[12px]"
      />
      {polygons.length > 0 && (
        <div className="max-w-[220px]">
          <AreaPreview polygons={polygons} />
        </div>
      )}
      {text.trim() && parsed === undefined && (
        <p className="text-[12.5px] text-[var(--fg-danger)]">این متن JSON معتبر نیست.</p>
      )}
    </div>
  );
}

// ── جدول راستی‌آزمایی ──────────────────────────────────────────────────
function ChecksEditor({
  rows,
  onChange,
  workflow,
}: {
  rows: CheckRow[];
  onChange: (rows: CheckRow[]) => void;
  workflow: CityWorkflow;
}) {
  function update(index: number, patch: Partial<CheckRow>) {
    onChange(rows.map((row, i) => (i === index ? { ...row, ...patch } : row)));
  }

  return (
    <fieldset className="flex flex-col gap-3">
      <legend className="mb-1 text-[13.5px] font-medium text-[var(--fg-primary)]">
        جدول راستی‌آزمایی
      </legend>
      <p className="text-[12.5px] leading-[1.9] text-[var(--fg-tertiary)]">
        هر ردیف یک نقطهٔ بررسی‌شده است. مغایرت با دست‌کم دو منبع مستقل، مورد بحرانی با بازدید
        میدانی، و هر ردیف با دست‌کم یک تصویر — بدون شواهد تصویری تأیید نمی‌شود.
      </p>
      {rows.map((row, index) => (
        <div
          key={index}
          className="flex flex-col gap-3 rounded-[var(--radius-md)] border border-[var(--border-subtle)] p-3"
        >
          <div className="flex items-center justify-between">
            <span className="text-[13.5px] font-semibold">ردیف {toPersianDigits(index + 1)}</span>
            {rows.length > 1 && (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => onChange(rows.filter((_, i) => i !== index))}
              >
                حذف ردیف
              </Button>
            )}
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <Input
              label="موقعیت"
              value={row.location}
              onChange={(event) => update(index, { location: event.target.value })}
            />
            <div className="flex gap-3">
              <Choice
                label="نتیجه"
                value={row.verdict}
                options={workflow.verdicts}
                onChange={(verdict) => update(index, { verdict })}
              />
              <Choice
                label="شدت"
                value={row.severity}
                options={workflow.severities}
                onChange={(severity) => update(index, { severity })}
              />
            </div>
          </div>
          <Textarea
            label="یافته"
            value={row.finding}
            onChange={(event) => update(index, { finding: event.target.value })}
            rows={2}
          />
          <div className="flex flex-wrap gap-2" role="group" aria-label="منابع بررسی">
            {workflow.sources.map((source) => {
              const active = row.sources.includes(source.code);
              return (
                <button
                  key={source.code}
                  type="button"
                  aria-pressed={active}
                  onClick={() =>
                    update(index, {
                      sources: active
                        ? row.sources.filter((s) => s !== source.code)
                        : [...row.sources, source.code],
                    })
                  }
                  className={cn(
                    'rounded-[var(--radius-sm)] border px-3 py-1 text-[13px]',
                    active
                      ? 'border-[var(--brand-500)] bg-[var(--brand-50)] text-[var(--fg-brand)]'
                      : 'border-[var(--border-default)] text-[var(--fg-secondary)]',
                  )}
                >
                  {active ? '✓ ' : ''}
                  {source.title_fa}
                </button>
              );
            })}
          </div>
          <label className="flex flex-col gap-1 text-[13px]">
            <span className="font-medium">تصویرها</span>
            <input
              type="file"
              accept="image/png,image/jpeg,image/webp"
              multiple
              onChange={(event) => update(index, { images: Array.from(event.target.files ?? []) })}
              className="text-[13px] text-[var(--fg-secondary)] file:me-3 file:rounded-[var(--radius-sm)] file:border file:border-[var(--border-default)] file:bg-[var(--bg-surface)] file:px-3 file:py-1 file:text-[13px]"
            />
            {row.images.length > 0 && (
              <span className="text-[12px] text-[var(--fg-tertiary)]">
                {toPersianDigits(row.images.length)} تصویر انتخاب شد
              </span>
            )}
          </label>
          {row.verdict === 'MISMATCH' && (
            <Input
              label="اصلاح انجام‌شده در داده"
              value={row.resolution}
              onChange={(event) => update(index, { resolution: event.target.value })}
            />
          )}
        </div>
      ))}
      <Button
        type="button"
        variant="secondary"
        size="sm"
        className="self-start"
        onClick={() => onChange([...rows, emptyCheck()])}
      >
        افزودن ردیف
      </Button>
    </fieldset>
  );
}

// ── سناریوها ───────────────────────────────────────────────────────────
function ScenariosEditor({
  rows,
  onChange,
  workflow,
}: {
  rows: ScenarioRow[];
  onChange: (rows: ScenarioRow[]) => void;
  workflow: CityWorkflow;
}) {
  function update(index: number, patch: Partial<ScenarioRow>) {
    onChange(rows.map((row, i) => (i === index ? { ...row, ...patch } : row)));
  }

  return (
    <fieldset className="flex flex-col gap-3">
      <legend className="mb-1 text-[13.5px] font-medium text-[var(--fg-primary)]">سناریوها</legend>
      <p className="text-[12.5px] text-[var(--fg-tertiary)]">
        دست‌کم سه سناریو، دقیقاً یکی «پایه» (وضع موجود)؛ هر سه شاخص برای همه.
      </p>
      {rows.map((row, index) => (
        <div
          key={index}
          className="flex flex-col gap-3 rounded-[var(--radius-md)] border border-[var(--border-subtle)] p-3"
        >
          <div className="flex flex-wrap items-center justify-between gap-2">
            <label className="flex items-center gap-2 text-[13.5px]">
              <input
                type="radio"
                name="baseline"
                checked={row.is_baseline}
                onChange={() => onChange(rows.map((r, i) => ({ ...r, is_baseline: i === index })))}
              />
              سناریوی پایه
            </label>
            {rows.length > 3 && (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => onChange(rows.filter((_, i) => i !== index))}
              >
                حذف
              </Button>
            )}
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <Input
              label="نام"
              value={row.name}
              onChange={(event) => update(index, { name: event.target.value })}
            />
            <Input
              label="شرح"
              value={row.description}
              onChange={(event) => update(index, { description: event.target.value })}
            />
          </div>
          <div className="grid gap-3 sm:grid-cols-3">
            {workflow.scenario_kpis.map((kpi) => (
              <Input
                key={kpi.key}
                label={kpi.title_fa}
                inputMode="decimal"
                value={row.values[kpi.key] ?? ''}
                onChange={(event) =>
                  update(index, { values: { ...row.values, [kpi.key]: event.target.value } })
                }
              />
            ))}
          </div>
        </div>
      ))}
      <Button
        type="button"
        variant="secondary"
        size="sm"
        className="self-start"
        onClick={() => onChange([...rows, emptyScenario()])}
      >
        افزودن سناریو
      </Button>
    </fieldset>
  );
}

// ── کمکی‌ها ────────────────────────────────────────────────────────────
function Choice({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: { code: string; title_fa: string }[];
  onChange: (value: string) => void;
}) {
  return (
    <label className="flex flex-1 flex-col gap-1.5 text-[13.5px] font-medium">
      {label}
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="h-10 rounded-[var(--radius-md)] border border-[var(--border-default)] bg-[var(--bg-surface)] px-2 text-[14px] font-normal"
      >
        {options.map((option) => (
          <option key={option.code} value={option.code}>
            {option.title_fa}
          </option>
        ))}
      </select>
    </label>
  );
}

function EvidenceInput({
  field,
  value,
  onChange,
}: {
  field: CityEvidenceField;
  value: string;
  onChange: (value: string) => void;
}) {
  const hint = field.hint_fa ?? undefined;
  if (field.kind === 'text' && (field.min_length ?? 0) >= 20) {
    return (
      <Textarea
        label={field.label_fa}
        hint={hint}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        rows={field.min_length && field.min_length >= 100 ? 6 : 3}
        maxLength={field.max_length}
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
      inputMode={field.kind === 'int' ? 'numeric' : field.kind === 'number' ? 'decimal' : undefined}
      forceLtr={field.kind === 'url' || field.kind === 'date'}
    />
  );
}

function convert(field: CityEvidenceField, raw: string): string | number {
  if (field.kind === 'int' || field.kind === 'number') {
    const number = Number(toLatinDigits(raw).replace(/[,٬]/g, ''));
    return Number.isFinite(number) ? number : raw;
  }
  return raw;
}

function parseJson(text: string): unknown {
  if (!text.trim()) return undefined;
  try {
    return JSON.parse(text);
  } catch {
    return undefined;
  }
}

function messageFor(cause: unknown): string {
  if (cause instanceof ApiError || cause instanceof NetworkError) return cause.message;
  return 'تحویل ارسال نشد. کمی بعد دوباره تلاش کن.';
}
