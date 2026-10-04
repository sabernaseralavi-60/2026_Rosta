'use client';

import { useCallback, useEffect, useState, type FormEvent } from 'react';

import { ErrorLine, errorText, Field, SELECT_CLASS } from '@/components/admin/common';
import { SectionHeader } from '@/components/teach/common';
import { useOffering } from '@/components/teach/OfferingFrame';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { EmptyState } from '@/components/ui/EmptyState';
import { Input } from '@/components/ui/Input';
import { SkeletonRow } from '@/components/ui/Skeleton';
import {
  type Competency,
  createCheckpoint,
  createCompetency,
  createConcept,
  createLesson,
  deleteLesson,
  fetchCompetencies,
  fetchStaffLessons,
  setLessonPublished,
  type StaffLesson,
  updateLesson,
} from '@/lib/api/learning';
import { toPersianDigits } from '@/lib/format/digits';

/** مقدار پیش‌فرض `datetime-local` (ساعت محلی مرورگر). */
function localInput(date: Date): string {
  const shifted = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  return shifted.toISOString().slice(0, 16);
}

function toIso(value: string): string | null {
  return value ? new Date(value).toISOString() : null;
}

/**
 * درس‌نامه، چالش روزانه و شایستگی‌های یک ارائه — ADR-0036.
 *
 * ترتیب کار استاد: (۱) شایستگی و مفهوم بساز، (۲) سؤال بانک را به مفهوم وصل کن،
 * (۳) درس‌نامه بنویس، (۴) چالش را از مفهوم‌ها بساز. انتشار درس‌نامه جدا از ساختن آن است.
 */
export function OfferingLessonsView() {
  const { offering, token } = useOffering();
  const [lessons, setLessons] = useState<StaffLesson[] | null>(null);
  const [competencies, setCompetencies] = useState<Competency[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    fetchStaffLessons(offering.id, token)
      .then(setLessons)
      .catch((cause) => setError(errorText(cause)));
    fetchCompetencies(token)
      .then(setCompetencies)
      .catch(() => setCompetencies([]));
  }, [offering.id, token]);

  useEffect(load, [load]);

  return (
    <div className="flex flex-col gap-10">
      {error && <ErrorLine>{error}</ErrorLine>}
      <LessonsSection offeringId={offering.id} token={token} lessons={lessons} onChanged={load} />
      <CheckpointSection
        offeringId={offering.id}
        token={token}
        lessons={lessons ?? []}
        competencies={competencies}
      />
      <TaxonomySection token={token} competencies={competencies} onChanged={load} />
    </div>
  );
}

// ── درس‌نامه‌ها ─────────────────────────────────────────────────────────
function LessonsSection({
  offeringId,
  token,
  lessons,
  onChanged,
}: {
  offeringId: string;
  token: string;
  lessons: StaffLesson[] | null;
  onChanged: () => void;
}) {
  const [editing, setEditing] = useState<StaffLesson | 'new' | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function act(action: () => Promise<unknown>) {
    setError(null);
    try {
      await action();
      onChanged();
    } catch (cause) {
      setError(errorText(cause));
    }
  }

  return (
    <section aria-labelledby="lessons-title" className="flex flex-col gap-4">
      <SectionHeader
        title="درس‌نامه‌ها"
        description="هر روز یک درس‌نامهٔ کوتاه (۳ تا ۱۰ دقیقه) یا بخشی از یک مقاله. متن Markdown است."
        action={
          editing === null ? (
            <Button onClick={() => setEditing('new')}>درس‌نامهٔ تازه</Button>
          ) : null
        }
      />
      {error && <ErrorLine>{error}</ErrorLine>}
      {editing !== null && (
        <LessonForm
          key={editing === 'new' ? 'new' : editing.id}
          lesson={editing === 'new' ? null : editing}
          onCancel={() => setEditing(null)}
          onSave={async (input, publish) => {
            if (editing === 'new') await createLesson(offeringId, { ...input, publish }, token);
            else await updateLesson(offeringId, editing.id, input, token);
            setEditing(null);
            onChanged();
          }}
        />
      )}
      {!lessons && <SkeletonRow label="در حال بارگذاری درس‌نامه‌ها" />}
      {lessons && lessons.length === 0 && editing === null && (
        <EmptyState
          title="هنوز درس‌نامه‌ای ننوشته‌ای"
          description="با یک درس‌نامهٔ کوتاه شروع کن؛ بعد می‌توانی چالشی بسازی که از آن سؤال بپرسد."
        />
      )}
      <ul className="flex flex-col divide-y divide-[var(--border-subtle)] rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-surface)]">
        {lessons?.map((lesson) => (
          <li key={lesson.id} className="flex flex-wrap items-center gap-3 px-4 py-3">
            <span className="flex-1 text-[14.5px] font-medium">{lesson.title_fa}</span>
            <Badge tone={lesson.status === 'PUBLISHED' ? 'success' : 'neutral'}>
              {lesson.status === 'PUBLISHED' ? 'منتشرشده' : 'پیش‌نویس'}
            </Badge>
            <span className="text-[12.5px] text-[var(--fg-tertiary)]">
              {toPersianDigits(lesson.est_minutes)} دقیقه
            </span>
            <Button size="sm" variant="ghost" onClick={() => setEditing(lesson)}>
              ویرایش
            </Button>
            <Button
              size="sm"
              variant="secondary"
              onClick={() =>
                void act(() =>
                  setLessonPublished(offeringId, lesson.id, lesson.status !== 'PUBLISHED', token),
                )
              }
            >
              {lesson.status === 'PUBLISHED' ? 'برگرداندن به پیش‌نویس' : 'انتشار'}
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => {
                if (window.confirm(`«${lesson.title_fa}» حذف شود؟`)) {
                  void act(() => deleteLesson(offeringId, lesson.id, token));
                }
              }}
            >
              حذف
            </Button>
          </li>
        ))}
      </ul>
    </section>
  );
}

function LessonForm({
  lesson,
  onCancel,
  onSave,
}: {
  lesson: StaffLesson | null;
  onCancel: () => void;
  onSave: (
    input: { title_fa: string; body_md: string; est_minutes: number; publish_at: string | null },
    publish: boolean,
  ) => Promise<void>;
}) {
  const [title, setTitle] = useState(lesson?.title_fa ?? '');
  const [body, setBody] = useState(lesson?.body_md ?? '');
  const [minutes, setMinutes] = useState(String(lesson?.est_minutes ?? 5));
  const [publishAt, setPublishAt] = useState(
    lesson?.publish_at ? localInput(new Date(lesson.publish_at)) : '',
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>, publish: boolean) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await onSave(
        {
          title_fa: title,
          body_md: body,
          est_minutes: Number(minutes) || 5,
          publish_at: toIso(publishAt),
        },
        publish,
      );
    } catch (cause) {
      setError(errorText(cause));
      setBusy(false);
    }
  }

  return (
    <form
      onSubmit={(event) => void submit(event, false)}
      className="flex flex-col gap-4 rounded-[var(--radius-lg)] border border-[var(--border-default)] bg-[var(--bg-surface)] p-5"
    >
      <Input
        label="عنوان"
        value={title}
        maxLength={200}
        onChange={(event) => setTitle(event.target.value)}
      />
      <div className="flex flex-col gap-1.5">
        <label htmlFor="lesson-body" className="text-[14px] font-medium">
          متن (Markdown)
        </label>
        <textarea
          id="lesson-body"
          value={body}
          onChange={(event) => setBody(event.target.value)}
          rows={12}
          dir="rtl"
          className="w-full rounded-[var(--radius-md)] border border-[var(--border-default)] bg-[var(--bg-canvas)] p-3 font-mono text-[14px] leading-[1.9]"
        />
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <Input
          label="زمان مطالعه (دقیقه)"
          type="number"
          min={1}
          max={120}
          value={minutes}
          onChange={(event) => setMinutes(event.target.value)}
        />
        <Input
          label="نمایش به دانشجو از (اختیاری)"
          type="datetime-local"
          value={publishAt}
          onChange={(event) => setPublishAt(event.target.value)}
        />
      </div>
      {error && <ErrorLine>{error}</ErrorLine>}
      <div className="flex flex-wrap gap-2">
        <Button type="submit" loading={busy} loadingLabel="در حال ذخیره…">
          {lesson ? 'ذخیرهٔ ویرایش' : 'ذخیره به‌عنوان پیش‌نویس'}
        </Button>
        {!lesson && (
          <Button
            type="button"
            variant="secondary"
            disabled={busy}
            onClick={(event) => void submit(event as unknown as FormEvent<HTMLFormElement>, true)}
          >
            ذخیره و انتشار
          </Button>
        )}
        <Button type="button" variant="ghost" onClick={onCancel}>
          انصراف
        </Button>
      </div>
    </form>
  );
}

// ── چالش روزانه ─────────────────────────────────────────────────────────
function CheckpointSection({
  offeringId,
  token,
  lessons,
  competencies,
}: {
  offeringId: string;
  token: string;
  lessons: StaffLesson[];
  competencies: Competency[];
}) {
  const now = new Date();
  const [title, setTitle] = useState('چالش امروز');
  const [lessonId, setLessonId] = useState('');
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [draw, setDraw] = useState('8');
  const [minutes, setMinutes] = useState('8');
  const [opens, setOpens] = useState(localInput(now));
  const [closes, setCloses] = useState(localInput(new Date(now.getTime() + 8 * 60 * 60 * 1000)));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  function toggle(id: string) {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const created = await createCheckpoint(
        offeringId,
        {
          title_fa: title,
          lesson_id: lessonId || null,
          concept_ids: [...selected],
          draw_count: Number(draw) || 8,
          opens_at: toIso(opens) ?? new Date().toISOString(),
          closes_at: toIso(closes) ?? new Date().toISOString(),
          duration_min: Number(minutes) || 8,
          publish: true,
        },
        token,
      );
      setNotice(
        `چالش منتشر شد: هر دانشجو ${toPersianDigits(created.draw_count ?? 0)} سؤال از استخر ${toPersianDigits(created.pool_size)} سؤالی می‌گیرد.`,
      );
    } catch (cause) {
      setError(errorText(cause));
    } finally {
      setBusy(false);
    }
  }

  const hasConcepts = competencies.some((c) => c.concepts.length > 0);

  return (
    <section aria-labelledby="checkpoint-title" className="flex flex-col gap-4">
      <SectionHeader
        title="ساخت چالش روزانه"
        description="چالش از سؤال‌های بانک ساخته می‌شود که به مفهوم وصل‌اند. هر دانشجو تعدادی سؤال متفاوت از استخر می‌گیرد؛ نمرهٔ رسمی ندارد و فقط امتیاز و مهارت می‌سازد."
      />
      {!hasConcepts ? (
        <EmptyState
          title="اول مفهوم بساز"
          description="در بخش «شایستگی‌ها و مفاهیم» پایین همین صفحه، و بعد سؤال‌های بانک را به مفهوم وصل کن."
        />
      ) : (
        <form
          onSubmit={(event) => void submit(event)}
          className="flex flex-col gap-4 rounded-[var(--radius-lg)] border border-[var(--border-default)] bg-[var(--bg-surface)] p-5"
        >
          <div className="grid gap-3 sm:grid-cols-2">
            <Input
              label="عنوان"
              value={title}
              maxLength={200}
              onChange={(event) => setTitle(event.target.value)}
            />
            <Field label="درس‌نامهٔ مرتبط (اختیاری)">
              <select
                className={SELECT_CLASS}
                value={lessonId}
                onChange={(event) => setLessonId(event.target.value)}
              >
                <option value="">بدون درس‌نامه</option>
                {lessons.map((lesson) => (
                  <option key={lesson.id} value={lesson.id}>
                    {lesson.title_fa}
                  </option>
                ))}
              </select>
            </Field>
          </div>
          <fieldset className="flex flex-col gap-2">
            <legend className="text-[14px] font-medium">مفاهیم استخر</legend>
            {competencies
              .filter((comp) => comp.concepts.length > 0)
              .map((comp) => (
                <div key={comp.id} className="flex flex-wrap items-center gap-x-4 gap-y-1">
                  <span className="text-[13px] text-[var(--fg-secondary)]">{comp.title_fa}:</span>
                  {comp.concepts.map((concept) => (
                    <label key={concept.id} className="flex items-center gap-1.5 text-[14px]">
                      <input
                        type="checkbox"
                        checked={selected.has(concept.id)}
                        onChange={() => toggle(concept.id)}
                      />
                      {concept.title_fa}
                    </label>
                  ))}
                </div>
              ))}
          </fieldset>
          <div className="grid gap-3 sm:grid-cols-4">
            <Input
              label="سؤال هر تلاش"
              type="number"
              min={1}
              max={30}
              value={draw}
              onChange={(event) => setDraw(event.target.value)}
            />
            <Input
              label="مدت (دقیقه)"
              type="number"
              min={1}
              max={30}
              value={minutes}
              onChange={(event) => setMinutes(event.target.value)}
            />
            <Input
              label="باز می‌شود"
              type="datetime-local"
              value={opens}
              onChange={(event) => setOpens(event.target.value)}
            />
            <Input
              label="بسته می‌شود"
              type="datetime-local"
              value={closes}
              onChange={(event) => setCloses(event.target.value)}
            />
          </div>
          {error && <ErrorLine>{error}</ErrorLine>}
          {notice && (
            <p role="status" className="text-[14px] text-[var(--fg-success)]">
              {notice}
            </p>
          )}
          <div>
            <Button
              type="submit"
              loading={busy}
              loadingLabel="در حال ساخت…"
              disabled={selected.size === 0}
            >
              ساخت و انتشار چالش
            </Button>
          </div>
        </form>
      )}
    </section>
  );
}

// ── شایستگی و مفهوم ─────────────────────────────────────────────────────
function TaxonomySection({
  token,
  competencies,
  onChanged,
}: {
  token: string;
  competencies: Competency[];
  onChanged: () => void;
}) {
  const [compCode, setCompCode] = useState('');
  const [compTitle, setCompTitle] = useState('');
  const [conceptFor, setConceptFor] = useState('');
  const [conceptCode, setConceptCode] = useState('');
  const [conceptTitle, setConceptTitle] = useState('');
  const [error, setError] = useState<string | null>(null);

  async function run(action: () => Promise<unknown>, reset: () => void) {
    setError(null);
    try {
      await action();
      reset();
      onChanged();
    } catch (cause) {
      setError(errorText(cause));
    }
  }

  return (
    <section aria-labelledby="taxonomy-title" className="flex flex-col gap-4">
      <SectionHeader
        title="شایستگی‌ها و مفاهیم"
        description="شایستگی یعنی مهارت درسی («تحلیل ظرفیت»)؛ مفهوم یعنی یک مبحث زیر آن («سطح سرویس»). سؤال به مفهوم وصل می‌شود و نقشهٔ مهارت دانشجو از همین ساخته می‌شود. کدها لاتین و کوچک‌اند."
      />
      {error && <ErrorLine>{error}</ErrorLine>}
      <ul className="flex flex-col gap-2">
        {competencies.map((comp) => (
          <li
            key={comp.id}
            className="rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-surface)] px-4 py-3"
          >
            <p className="text-[14.5px] font-semibold">
              {comp.title_fa}{' '}
              <span className="font-normal text-[var(--fg-tertiary)]">({comp.code})</span>
            </p>
            <p className="text-[13.5px] text-[var(--fg-secondary)]">
              {comp.concepts.length === 0
                ? 'هنوز مفهومی ندارد'
                : comp.concepts.map((c) => c.title_fa).join(' · ')}
            </p>
          </li>
        ))}
      </ul>
      <div className="grid gap-5 md:grid-cols-2">
        <form
          className="flex flex-col gap-3 rounded-[var(--radius-lg)] border border-[var(--border-default)] bg-[var(--bg-surface)] p-4"
          onSubmit={(event) => {
            event.preventDefault();
            void run(
              () => createCompetency({ code: compCode, title_fa: compTitle }, token),
              () => {
                setCompCode('');
                setCompTitle('');
              },
            );
          }}
        >
          <h3 className="text-[15px]">شایستگی تازه</h3>
          <Input label="عنوان" value={compTitle} onChange={(e) => setCompTitle(e.target.value)} />
          <Input
            label="کد (لاتین)"
            forceLtr
            value={compCode}
            onChange={(e) => setCompCode(e.target.value)}
            placeholder="capacity-analysis"
          />
          <div>
            <Button type="submit" size="sm" disabled={!compCode || !compTitle}>
              افزودن شایستگی
            </Button>
          </div>
        </form>
        <form
          className="flex flex-col gap-3 rounded-[var(--radius-lg)] border border-[var(--border-default)] bg-[var(--bg-surface)] p-4"
          onSubmit={(event) => {
            event.preventDefault();
            void run(
              () => createConcept(conceptFor, { code: conceptCode, title_fa: conceptTitle }, token),
              () => {
                setConceptCode('');
                setConceptTitle('');
              },
            );
          }}
        >
          <h3 className="text-[15px]">مفهوم تازه</h3>
          <Field label="زیر شایستگی">
            <select
              className={SELECT_CLASS}
              value={conceptFor}
              onChange={(e) => setConceptFor(e.target.value)}
            >
              <option value="">انتخاب کن</option>
              {competencies.map((comp) => (
                <option key={comp.id} value={comp.id}>
                  {comp.title_fa}
                </option>
              ))}
            </select>
          </Field>
          <Input
            label="عنوان"
            value={conceptTitle}
            onChange={(e) => setConceptTitle(e.target.value)}
          />
          <Input
            label="کد (لاتین)"
            forceLtr
            value={conceptCode}
            onChange={(e) => setConceptCode(e.target.value)}
            placeholder="hcm-level-of-service"
          />
          <div>
            <Button type="submit" size="sm" disabled={!conceptFor || !conceptCode || !conceptTitle}>
              افزودن مفهوم
            </Button>
          </div>
        </form>
      </div>
    </section>
  );
}
