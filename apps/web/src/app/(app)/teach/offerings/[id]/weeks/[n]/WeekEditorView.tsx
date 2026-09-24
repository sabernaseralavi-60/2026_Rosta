'use client';

import Link from 'next/link';
import { type FormEvent, useCallback, useEffect, useState } from 'react';

import { errorText, ErrorLine, Field, SELECT_CLASS } from '@/components/admin/common';
import {
  DateTimeField,
  fromLocalInput,
  SectionHeader,
  toLocalInput,
} from '@/components/teach/common';
import { useOffering } from '@/components/teach/OfferingFrame';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { Input } from '@/components/ui/Input';
import { SkeletonCard } from '@/components/ui/Skeleton';
import { Textarea } from '@/components/ui/Textarea';
import {
  fetchCourse,
  fetchWeek,
  type Material,
  type ResourceKind,
  type WeekDetail,
} from '@/lib/api/courses';
import { formatBytes, uploadFile } from '@/lib/api/files';
import {
  addResource,
  linkMaterial,
  publishWeek,
  removeResource,
  RESOURCE_KIND_LABELS,
  saveWeek,
  unlinkMaterial,
} from '@/lib/api/teach';
import { formatDateTime } from '@/lib/format/date';
import { toPersianDigits } from '@/lib/format/digits';

/**
 * `/teach/offerings/[id]/weeks/[n]` — ویرایش محتوای هفته (§3.5، FR-EDU-02/03).
 *
 * سه بخش: مشخصات هفته و انتشار، منابع خود هفته (جزوه، ویدئو، پیوند)، و
 * محتوای کتابخانهٔ درس که به هفته بسته می‌شود (ADR-0008).
 */
export function WeekEditorView({ weekNumber }: { weekNumber: number }) {
  const { offering, token, reload } = useOffering();
  const [week, setWeek] = useState<WeekDetail | null>(null);
  const [library, setLibrary] = useState<Material[]>([]);
  const [error, setError] = useState<string | null>(null);

  const summary = offering.weeks.find((w) => w.week_number === weekNumber);
  const can = offering.permissions;

  const load = useCallback(async () => {
    try {
      setWeek(await fetchWeek(offering.id, weekNumber, token));
      setError(null);
    } catch (cause) {
      setError(errorText(cause));
    }
  }, [offering.id, weekNumber, token]);

  useEffect(() => {
    void load();
    fetchCourse(offering.course_slug, token)
      .then((course) => setLibrary(course.materials))
      .catch(() => setLibrary([]));
  }, [load, offering.course_slug, token]);

  if (!summary) {
    return (
      <EmptyState
        title={`هفتهٔ ${toPersianDigits(weekNumber)} ساخته نشده`}
        description="هفته را از فهرست هفته‌ها بساز."
        action={
          <Link
            href={`/teach/offerings/${offering.id}`}
            className="text-[14px] text-[var(--fg-brand)]"
          >
            بازگشت به هفته‌ها
          </Link>
        }
      />
    );
  }
  if (error && !week) return <ErrorLine>{error}</ErrorLine>;
  if (!week) return <SkeletonCard label="در حال بارگذاری هفته" />;

  const refresh = async () => {
    await Promise.all([load(), reload()]);
  };

  return (
    <div className="flex flex-col gap-8">
      <nav aria-label="مسیر هفته" className="text-[13px] text-[var(--fg-tertiary)]">
        <Link href={`/teach/offerings/${offering.id}`} className="hover:text-[var(--fg-brand)]">
          هفته‌ها
        </Link>{' '}
        ‹ هفتهٔ {toPersianDigits(weekNumber)}
      </nav>
      <WeekDetailsForm
        offeringId={offering.id}
        token={token}
        key={summary.id}
        week={week}
        weekId={summary.id}
        publishAt={summary.publish_at}
        editable={can.edit_weeks}
        publishable={can.publish_weeks}
        onSaved={refresh}
      />
      <ResourcesSection
        offeringId={offering.id}
        token={token}
        week={week}
        weekId={summary.id}
        editable={can.upload_resources}
        onChanged={refresh}
      />
      <MaterialsSection
        offeringId={offering.id}
        token={token}
        week={week}
        weekId={summary.id}
        library={library}
        editable={can.edit_weeks}
        onChanged={refresh}
      />
    </div>
  );
}

function WeekDetailsForm({
  offeringId,
  token,
  week: current,
  weekId,
  publishAt,
  editable,
  publishable,
  onSaved,
}: {
  offeringId: string;
  token: string;
  week: WeekDetail;
  weekId: string;
  publishAt: string | null;
  editable: boolean;
  publishable: boolean;
  onSaved: () => Promise<void>;
}) {
  const [title, setTitle] = useState(current.title_fa);
  const [description, setDescription] = useState(current.description ?? '');
  const [objectives, setObjectives] = useState(current.objectives.join('\n'));
  const [schedule, setSchedule] = useState(toLocalInput(publishAt));
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);

  async function save(event: FormEvent) {
    event.preventDefault();
    setBusy('save');
    setFailure(null);
    setMessage(null);
    try {
      await saveWeek(
        offeringId,
        {
          week_number: current.week_number,
          title_fa: title.trim(),
          description: description.trim() || null,
          objectives: objectives
            .split('\n')
            .map((line) => line.trim())
            .filter(Boolean),
        },
        token,
      );
      setMessage('ذخیره شد.');
      await onSaved();
    } catch (cause) {
      setFailure(errorText(cause));
    } finally {
      setBusy(null);
    }
  }

  async function publish(at: string | null) {
    setBusy(at ? 'schedule' : 'publish');
    setFailure(null);
    setMessage(null);
    try {
      await publishWeek(weekId, at, token);
      setMessage(
        at ? `برای ${formatDateTime(at)} زمان‌بندی شد.` : 'منتشر شد و به دانشجویان اعلان رفت.',
      );
      await onSaved();
    } catch (cause) {
      setFailure(errorText(cause));
    } finally {
      setBusy(null);
    }
  }

  return (
    <Card className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-[18px]">مشخصات هفتهٔ {toPersianDigits(current.week_number)}</h2>
        {current.status === 'PUBLISHED' ? (
          <Badge tone="success">
            منتشرشده{current.published_at ? ` · ${formatDateTime(current.published_at)}` : ''}
          </Badge>
        ) : (
          <Badge tone="neutral">پیش‌نویس</Badge>
        )}
      </div>
      <form onSubmit={save} className="flex flex-col gap-4">
        <Input
          label="عنوان هفته"
          value={title}
          required
          maxLength={200}
          disabled={!editable}
          onChange={(event) => setTitle(event.target.value)}
        />
        <Textarea
          label="شرح"
          rows={3}
          value={description}
          maxLength={4000}
          disabled={!editable}
          onChange={(event) => setDescription(event.target.value)}
        />
        <Textarea
          label="اهداف یادگیری"
          hint="هر هدف در یک سطر — حداکثر ۲۰ سطر."
          rows={4}
          value={objectives}
          disabled={!editable}
          onChange={(event) => setObjectives(event.target.value)}
        />
        {editable && (
          <div>
            <Button type="submit" loading={busy === 'save'} disabled={!title.trim()}>
              ذخیرهٔ مشخصات
            </Button>
          </div>
        )}
      </form>
      {publishable && current.status !== 'PUBLISHED' && (
        <div className="flex flex-col gap-3 border-t border-[var(--border-subtle)] pt-4">
          <h3 className="text-[15px]">انتشار</h3>
          <div className="flex flex-wrap items-end gap-3">
            <Button variant="secondary" loading={busy === 'publish'} onClick={() => publish(null)}>
              انتشار همین حالا
            </Button>
            <div className="w-64">
              <DateTimeField
                label="یا زمان‌بندی"
                value={schedule}
                onChange={setSchedule}
                hint="خودکار در همان لحظه منتشر می‌شود"
              />
            </div>
            <Button
              variant="ghost"
              disabled={!schedule}
              loading={busy === 'schedule'}
              onClick={() => publish(fromLocalInput(schedule))}
            >
              زمان‌بندی
            </Button>
          </div>
        </div>
      )}
      {message && (
        <p role="status" className="text-[13.5px] text-[var(--fg-success)]">
          {message}
        </p>
      )}
      {failure && <ErrorLine>{failure}</ErrorLine>}
    </Card>
  );
}

function ResourcesSection({
  offeringId,
  token,
  week: current,
  weekId,
  editable,
  onChanged,
}: {
  offeringId: string;
  token: string;
  week: WeekDetail;
  weekId: string;
  editable: boolean;
  onChanged: () => Promise<void>;
}) {
  const [kind, setKind] = useState<ResourceKind>('PDF');
  const [title, setTitle] = useState('');
  const [url, setUrl] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [minutes, setMinutes] = useState('');
  const [required, setRequired] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);

  async function add(event: FormEvent) {
    event.preventDefault();
    setBusy('add');
    setFailure(null);
    try {
      const stored = file ? await uploadFile(file, 'RESOURCE', token) : null;
      await addResource(
        offeringId,
        weekId,
        {
          kind,
          title_fa: title.trim(),
          file_id: stored?.id ?? null,
          external_url: stored ? null : url.trim() || null,
          duration_sec: minutes ? Math.round(Number(minutes) * 60) : null,
          is_required: required,
        },
        token,
      );
      setTitle('');
      setUrl('');
      setFile(null);
      setMinutes('');
      await onChanged();
    } catch (cause) {
      setFailure(errorText(cause));
    } finally {
      setBusy(null);
    }
  }

  async function remove(resourceId: string) {
    setBusy(resourceId);
    setFailure(null);
    try {
      await removeResource(resourceId, token);
      await onChanged();
    } catch (cause) {
      setFailure(errorText(cause));
    } finally {
      setBusy(null);
    }
  }

  return (
    <section className="flex flex-col gap-3">
      <SectionHeader
        title="منابع هفته"
        description="جزوه، ویدئو یا پیوندی که فقط مال همین هفته است. منبع «الزامی» در پیشرفت مطالعه و نمرهٔ یادگیری شمرده می‌شود."
      />
      {current.resources.length === 0 ? (
        <p className="text-[14px] text-[var(--fg-secondary)]">هنوز منبعی اضافه نشده.</p>
      ) : (
        <ul className="flex flex-col divide-y divide-[var(--border-subtle)] rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-surface)]">
          {current.resources.map((resource) => (
            <li
              key={resource.id}
              className="flex flex-wrap items-center justify-between gap-2 px-4 py-3"
            >
              <span className="flex flex-wrap items-center gap-2">
                <Badge tone="brand">{RESOURCE_KIND_LABELS[resource.kind]}</Badge>
                <span className="font-medium">{resource.title_fa}</span>
                {resource.is_required && <Badge tone="neutral">الزامی</Badge>}
                {resource.has_file ? (
                  <span className="text-[12.5px] text-[var(--fg-tertiary)]">فایل</span>
                ) : resource.external_url ? (
                  <span
                    className="max-w-[28ch] truncate text-[12.5px] text-[var(--fg-tertiary)]"
                    dir="ltr"
                  >
                    {resource.external_url}
                  </span>
                ) : null}
              </span>
              {editable && (
                <Button
                  size="sm"
                  variant="ghost"
                  loading={busy === resource.id}
                  onClick={() => remove(resource.id)}
                >
                  حذف
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}
      {editable && (
        <Card className="flex flex-col gap-3">
          <h3 className="text-[15px]">افزودن منبع</h3>
          <form onSubmit={add} className="grid gap-3 md:grid-cols-2">
            <Field label="نوع">
              <select
                className={SELECT_CLASS}
                value={kind}
                onChange={(event) => setKind(event.target.value as ResourceKind)}
              >
                {(Object.keys(RESOURCE_KIND_LABELS) as ResourceKind[]).map((key) => (
                  <option key={key} value={key}>
                    {RESOURCE_KIND_LABELS[key]}
                  </option>
                ))}
              </select>
            </Field>
            <Input
              label="عنوان"
              value={title}
              required
              maxLength={200}
              onChange={(event) => setTitle(event.target.value)}
            />
            <Input
              label="پیوند (اگر فایل نمی‌گذاری)"
              forceLtr
              type="url"
              placeholder="https://"
              value={url}
              disabled={Boolean(file)}
              onChange={(event) => setUrl(event.target.value)}
            />
            <Field label="یا فایل">
              <input
                type="file"
                className="text-[13px]"
                onChange={(event) => setFile(event.target.files?.[0] ?? null)}
              />
              {file && (
                <span className="text-[12px] font-normal text-[var(--fg-tertiary)]">
                  {file.name} · {formatBytes(file.size)}
                </span>
              )}
            </Field>
            {kind === 'VIDEO' && (
              <Input
                label="مدت ویدئو (دقیقه)"
                inputMode="numeric"
                value={minutes}
                onChange={(event) => setMinutes(event.target.value.replace(/[^\d.]/g, ''))}
              />
            )}
            <label className="flex items-center gap-2 text-[13.5px]">
              <input
                type="checkbox"
                checked={required}
                onChange={(event) => setRequired(event.target.checked)}
              />
              مطالعه‌اش الزامی است
            </label>
            <div className="md:col-span-2">
              <Button
                type="submit"
                loading={busy === 'add'}
                disabled={!title.trim() || (!file && !url.trim())}
              >
                افزودن منبع
              </Button>
            </div>
          </form>
          {failure && <ErrorLine>{failure}</ErrorLine>}
        </Card>
      )}
      {!editable && failure && <ErrorLine>{failure}</ErrorLine>}
    </section>
  );
}

function MaterialsSection({
  offeringId,
  token,
  week: current,
  weekId,
  library: materials,
  editable,
  onChanged,
}: {
  offeringId: string;
  token: string;
  week: WeekDetail;
  weekId: string;
  library: Material[];
  editable: boolean;
  onChanged: () => Promise<void>;
}) {
  const linked = new Set(current.materials.map((m) => m.id));
  const available = materials.filter((m) => !linked.has(m.id));
  const [choice, setChoice] = useState('');
  const [busy, setBusy] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);

  async function run(id: string, action: () => Promise<void>) {
    setBusy(id);
    setFailure(null);
    try {
      await action();
      setChoice('');
      await onChanged();
    } catch (cause) {
      setFailure(errorText(cause));
    } finally {
      setBusy(null);
    }
  }

  return (
    <section className="flex flex-col gap-3">
      <SectionHeader
        title="از کتابخانهٔ درس"
        description="کتاب، جزوه و ویدئوی کتابخانهٔ درس را به این هفته ببند. دسترسی هر ماده همان قاعدهٔ کتابخانه است."
      />
      {current.materials.length === 0 ? (
        <p className="text-[14px] text-[var(--fg-secondary)]">
          هیچ محتوایی از کتابخانه به این هفته بسته نشده.
        </p>
      ) : (
        <ul className="flex flex-col divide-y divide-[var(--border-subtle)] rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-surface)]">
          {current.materials.map((material) => (
            <li
              key={material.id}
              className="flex flex-wrap items-center justify-between gap-2 px-4 py-3"
            >
              <span className="flex flex-wrap items-center gap-2">
                <Badge tone="accent">{material.kind_fa}</Badge>
                <span className="font-medium">{material.title_fa}</span>
                {material.size_bytes ? (
                  <span className="text-[12.5px] text-[var(--fg-tertiary)]">
                    {formatBytes(material.size_bytes)}
                  </span>
                ) : null}
              </span>
              {editable && (
                <Button
                  size="sm"
                  variant="ghost"
                  loading={busy === material.id}
                  onClick={() =>
                    run(material.id, () => unlinkMaterial(offeringId, weekId, material.id, token))
                  }
                >
                  برداشتن
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}
      {editable && available.length > 0 && (
        <div className="flex flex-wrap items-end gap-3">
          <div className="min-w-[16rem] flex-1">
            <Field label="افزودن از کتابخانه">
              <select
                className={SELECT_CLASS}
                value={choice}
                onChange={(event) => setChoice(event.target.value)}
              >
                <option value="">انتخاب کن…</option>
                {available.map((material) => (
                  <option key={material.id} value={material.id}>
                    {material.kind_fa} — {material.title_fa}
                  </option>
                ))}
              </select>
            </Field>
          </div>
          <Button
            variant="secondary"
            disabled={!choice}
            loading={busy === 'link'}
            onClick={() => run('link', () => linkMaterial(offeringId, weekId, choice, token))}
          >
            افزودن به هفته
          </Button>
        </div>
      )}
      {failure && <ErrorLine>{failure}</ErrorLine>}
    </section>
  );
}
