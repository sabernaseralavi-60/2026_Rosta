'use client';

import Link from 'next/link';
import { type FormEvent, useMemo, useState } from 'react';

import { errorText, ErrorLine, FactList, Field, SELECT_CLASS } from '@/components/admin/common';
import { InstructorPicker } from '@/components/admin/InstructorPicker';
import { OfferingStatusBadge, SectionHeader, todayInput } from '@/components/teach/common';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { Input } from '@/components/ui/Input';
import {
  type AdminCourse,
  type AdminOffering,
  createOffering,
  deleteOffering,
  type InstructorCandidate,
  reassignOffering,
  termIsOver,
  type WeekSource,
} from '@/lib/api/course-admin';
import { toLatinDigits, toPersianDigits } from '@/lib/format/digits';

import type { CatalogData } from './CoursesAdminView';

/**
 * ارائه‌ها — ساخت و سپردن به استاد، تغییر استاد یا نیم‌سال، و حذف ارائه‌ای
 * که به اشتباه ساخته شده (ADR-0020). وضعیت و ثبت‌نام در «تنظیمات» خود ارائه
 * در ناحیهٔ تدریس است؛ پیوندش روی هر ردیف هست.
 */
export function OfferingsPanel({
  token,
  data,
  onChanged,
}: {
  token: string;
  data: CatalogData;
  onChanged: () => void;
}) {
  const today = todayInput();
  const current = data.terms.find((t) => t.is_current);
  const [termId, setTermId] = useState(current?.id ?? '');
  const [adding, setAdding] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const rows = termId ? data.offerings.filter((o) => o.term_id === termId) : data.offerings;
  const openTerms = data.terms.filter((t) => !termIsOver(t, today));
  const activeCourses = data.courses.filter((c) => c.is_active);

  let blocker: string | null = null;
  if (openTerms.length === 0) blocker = 'اول یک نیم‌سال جاری یا آینده تعریف کن.';
  else if (activeCourses.length === 0) blocker = 'اول درسی تعریف یا همگام کن.';

  return (
    <section className="flex flex-col gap-4">
      <SectionHeader
        title="ارائه‌ها"
        description="هر ارائه یک درس در یک نیم‌سال با یک استاد است. دسترسی استاد همان لحظه باز می‌شود؛ اگر همین حالا وارد سامانه است، پیوند «تدریس» پس از یک بار خروج و ورود پیدا می‌شود."
        action={
          !adding &&
          !blocker && (
            <Button
              size="sm"
              onClick={() => {
                setNotice(null);
                setAdding(true);
              }}
            >
              ارائهٔ تازه
            </Button>
          )
        }
      />
      {blocker && <p className="text-[13.5px] text-[var(--fg-warning)]">{blocker}</p>}
      {adding && (
        <OfferingForm
          token={token}
          data={data}
          defaultTermId={
            termId && openTerms.some((t) => t.id === termId) ? termId : openTerms[0]?.id
          }
          onCancel={() => setAdding(false)}
          onCreated={(message) => {
            setAdding(false);
            setNotice(message);
            onChanged();
          }}
        />
      )}
      {notice && (
        <p role="status" className="text-[13.5px] text-[var(--fg-success)]">
          {notice}
        </p>
      )}

      <Field label="نیم‌سال">
        <select
          className={`${SELECT_CLASS} max-w-sm`}
          value={termId}
          onChange={(event) => setTermId(event.target.value)}
        >
          <option value="">همهٔ نیم‌سال‌ها</option>
          {data.terms.map((term) => (
            <option key={term.id} value={term.id}>
              {term.title_fa}
              {term.is_current ? ' (جاری)' : ''}
            </option>
          ))}
        </select>
      </Field>

      {rows.length === 0 ? (
        <EmptyState
          title="در این نیم‌سال ارائه‌ای نیست"
          description="با «ارائهٔ تازه» درس را به استادش بسپار."
        />
      ) : (
        <ul className="flex flex-col gap-3">
          {rows.map((offering) => (
            <li key={offering.id}>
              <OfferingRow offering={offering} data={data} token={token} onChanged={onChanged} />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function OfferingRow({
  offering,
  data,
  token,
  onChanged,
}: {
  offering: AdminOffering;
  data: CatalogData;
  token: string;
  onChanged: () => void;
}) {
  const [mode, setMode] = useState<'instructor' | 'term' | 'delete' | null>(null);
  const [instructor, setInstructor] = useState<InstructorCandidate | null>(null);
  const [termId, setTermId] = useState(offering.term_id);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const today = todayInput();
  const hasStudents = offering.active_students + offering.pending_students > 0;
  const otherTerms = data.terms.filter((t) => t.id !== offering.term_id && !termIsOver(t, today));

  function close() {
    setMode(null);
    setInstructor(null);
    setTermId(offering.term_id);
    setError(null);
  }

  async function act(action: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await action();
      close();
      onChanged();
    } catch (cause) {
      setError(errorText(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="flex flex-col gap-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 flex-col gap-0.5">
          <span className="flex flex-wrap items-center gap-2 font-semibold">
            {offering.course_title_fa}
            <OfferingStatusBadge status={offering.status} />
          </span>
          <FactList
            className="text-[var(--fg-tertiary)]"
            items={[offering.term_title_fa, `استاد: ${offering.instructor_name ?? 'بی‌نام'}`]}
          />
          <FactList
            className="text-[var(--fg-secondary)]"
            items={[
              offering.capacity
                ? `دانشجو: ${toPersianDigits(offering.active_students)} از ${toPersianDigits(offering.capacity)}`
                : `دانشجو: ${toPersianDigits(offering.active_students)}`,
              offering.pending_students > 0 &&
                `در انتظار تأیید: ${toPersianDigits(offering.pending_students)}`,
              `هفتهٔ منتشرشده: ${toPersianDigits(offering.published_weeks)} از ${toPersianDigits(offering.week_count)}`,
              !offering.has_enrollment_code && 'بی کد ثبت‌نام',
            ]}
          />
        </div>
        <div className="flex flex-wrap gap-2">
          <Button asChild size="sm" variant="secondary">
            <Link href={`/teach/offerings/${offering.id}/settings`}>تنظیمات در تدریس</Link>
          </Button>
          {!mode && (
            <>
              <Button size="sm" variant="ghost" onClick={() => setMode('instructor')}>
                تغییر استاد
              </Button>
              {!hasStudents && otherTerms.length > 0 && (
                <Button size="sm" variant="ghost" onClick={() => setMode('term')}>
                  تغییر نیم‌سال
                </Button>
              )}
              {!hasStudents && (
                <Button size="sm" variant="ghost" onClick={() => setMode('delete')}>
                  حذف
                </Button>
              )}
            </>
          )}
        </div>
      </div>

      {mode === 'instructor' && (
        <div className="flex flex-col gap-2 rounded-[var(--radius-md)] bg-[var(--bg-sunken)] p-3">
          <InstructorPicker
            token={token}
            label="استاد تازه"
            selected={instructor}
            onSelect={setInstructor}
          />
          <p className="text-[12.5px] text-[var(--fg-secondary)]">
            استاد قبلی همین حالا دسترسی‌اش به این ارائه را از دست می‌دهد؛ آزمون‌ها و نمره‌ها سر
            جایشان می‌مانند.
          </p>
          <div className="flex gap-2">
            <Button
              size="sm"
              loading={busy}
              disabled={!instructor || instructor.id === offering.instructor_id}
              onClick={() =>
                instructor &&
                act(() => reassignOffering(token, offering.id, { instructor_id: instructor.id }))
              }
            >
              سپردن به استاد تازه
            </Button>
            <Button size="sm" variant="ghost" onClick={close}>
              انصراف
            </Button>
          </div>
        </div>
      )}

      {mode === 'term' && (
        <div className="flex flex-wrap items-end gap-2 rounded-[var(--radius-md)] bg-[var(--bg-sunken)] p-3">
          <Field label="نیم‌سال تازه">
            <select
              className={SELECT_CLASS}
              value={termId}
              onChange={(event) => setTermId(event.target.value)}
            >
              <option value={offering.term_id}>انتخاب کن…</option>
              {otherTerms.map((term) => (
                <option key={term.id} value={term.id}>
                  {term.title_fa}
                </option>
              ))}
            </select>
          </Field>
          <Button
            size="sm"
            loading={busy}
            disabled={termId === offering.term_id}
            onClick={() => act(() => reassignOffering(token, offering.id, { term_id: termId }))}
          >
            انتقال
          </Button>
          <Button size="sm" variant="ghost" onClick={close}>
            انصراف
          </Button>
        </div>
      )}

      {mode === 'delete' && (
        <div className="flex flex-wrap items-center gap-2 rounded-[var(--radius-md)] bg-[var(--bg-sunken)] p-3">
          <p className="flex-1 text-[13.5px]">
            ارائه و هفته‌هایش پاک می‌شوند. ارائه‌ای که آزمون، جلسه یا اعلان دارد حذف نمی‌شود — آن را
            در تنظیمات بایگانی کن.
          </p>
          <Button
            size="sm"
            variant="danger"
            loading={busy}
            onClick={() => act(() => deleteOffering(token, offering.id))}
          >
            حذف قطعی
          </Button>
          <Button size="sm" variant="ghost" onClick={close}>
            انصراف
          </Button>
        </div>
      )}
      {error && <ErrorLine>{error}</ErrorLine>}
    </Card>
  );
}

const WEEK_SOURCE_LABELS: Record<WeekSource, string> = {
  SYLLABUS: 'از برنامهٔ درسی پوشهٔ درس',
  OFFERING: 'کپی از ارائهٔ قبلی همین درس',
  NONE: 'خالی — استاد هفته‌ها را خودش می‌سازد',
};

function defaultWeekSource(course: AdminCourse | undefined, previous: AdminOffering[]): WeekSource {
  if (course?.syllabus_weeks) return 'SYLLABUS';
  if (previous.length > 0) return 'OFFERING';
  return 'NONE';
}

function OfferingForm({
  token,
  data,
  defaultTermId,
  onCancel,
  onCreated,
}: {
  token: string;
  data: CatalogData;
  defaultTermId: string | undefined;
  onCancel: () => void;
  onCreated: (message: string) => void;
}) {
  const today = todayInput();
  const [courseId, setCourseId] = useState('');
  const [termId, setTermId] = useState(defaultTermId ?? '');
  const [instructor, setInstructor] = useState<InstructorCandidate | null>(null);
  const [status, setStatus] = useState<'DRAFT' | 'OPEN'>('DRAFT');
  const [capacity, setCapacity] = useState('');
  const [code, setCode] = useState('');
  const [requiresApproval, setRequiresApproval] = useState(false);
  const [weeksFrom, setWeeksFrom] = useState<WeekSource>('NONE');
  const [copyFrom, setCopyFrom] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const course = data.courses.find((c) => c.id === courseId);
  const previous = useMemo(
    () => data.offerings.filter((o) => o.course_id === courseId),
    [data.offerings, courseId],
  );
  const capacityNumber = capacity.trim() ? Number(toLatinDigits(capacity.trim())) : null;
  const capacityValid =
    capacityNumber === null ||
    (Number.isInteger(capacityNumber) && capacityNumber >= 1 && capacityNumber <= 2000);
  const codeValid = !code.trim() || code.trim().length >= 4;

  function pickCourse(id: string) {
    setCourseId(id);
    const chosen = data.courses.find((c) => c.id === id);
    const earlier = data.offerings.filter((o) => o.course_id === id);
    setWeeksFrom(defaultWeekSource(chosen, earlier));
    setCopyFrom(earlier[0]?.id ?? '');
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!instructor) return;
    setBusy(true);
    setError(null);
    try {
      const created = await createOffering(token, {
        course_id: courseId,
        term_id: termId,
        instructor_id: instructor.id,
        status,
        capacity: capacityNumber,
        enrollment_code: code.trim() || null,
        requires_approval: requiresApproval,
        weeks_from: weeksFrom,
        ...(weeksFrom === 'OFFERING' ? { copy_from_offering_id: copyFrom } : {}),
      });
      const weeks =
        created.weeks_created > 0
          ? `${toPersianDigits(created.weeks_created)} هفتهٔ پیش‌نویس ساخته شد`
          : 'هفته‌ها را استاد می‌سازد';
      onCreated(
        `«${created.course_title_fa}» به ${created.instructor_name ?? 'استاد'} سپرده شد؛ ${weeks}.`,
      );
    } catch (cause) {
      setError(errorText(cause));
      setBusy(false);
    }
  }

  const sources: WeekSource[] = ['SYLLABUS', 'OFFERING', 'NONE'];
  const sourceDisabled: Record<WeekSource, boolean> = {
    SYLLABUS: !course?.syllabus_weeks,
    OFFERING: previous.length === 0,
    NONE: false,
  };

  return (
    <Card>
      <form onSubmit={submit} className="grid gap-4 md:grid-cols-2">
        <h3 className="text-[16px] md:col-span-2">ارائهٔ تازه</h3>
        <Field label="درس">
          <select
            className={SELECT_CLASS}
            required
            value={courseId}
            onChange={(event) => pickCourse(event.target.value)}
          >
            <option value="">انتخاب کن…</option>
            {data.courses
              .filter((c) => c.is_active)
              .map((c) => (
                <option key={c.id} value={c.id}>
                  {c.title_fa}
                </option>
              ))}
          </select>
        </Field>
        <Field label="نیم‌سال">
          <select
            className={SELECT_CLASS}
            required
            value={termId}
            onChange={(event) => setTermId(event.target.value)}
          >
            {data.terms
              .filter((t) => !termIsOver(t, today))
              .map((t) => (
                <option key={t.id} value={t.id}>
                  {t.title_fa}
                  {t.is_current ? ' (جاری)' : ''}
                </option>
              ))}
          </select>
        </Field>
        <div className="md:col-span-2">
          <InstructorPicker token={token} selected={instructor} onSelect={setInstructor} />
        </div>

        <fieldset className="flex flex-col gap-2 md:col-span-2">
          <legend className="mb-1 text-[13.5px] font-medium">هفته‌ها</legend>
          {sources.map((source) => (
            <label
              key={source}
              className={`flex items-center gap-2 text-[14px] ${
                sourceDisabled[source] ? 'text-[var(--fg-tertiary)]' : ''
              }`}
            >
              <input
                type="radio"
                name="weeks_from"
                value={source}
                checked={weeksFrom === source}
                disabled={sourceDisabled[source]}
                onChange={() => setWeeksFrom(source)}
              />
              {WEEK_SOURCE_LABELS[source]}
              {source === 'SYLLABUS' && course?.syllabus_weeks
                ? ` (${toPersianDigits(course.syllabus_weeks)} هفته)`
                : ''}
            </label>
          ))}
          {weeksFrom === 'OFFERING' && previous.length > 0 && (
            <select
              className={`${SELECT_CLASS} max-w-md`}
              aria-label="ارائهٔ مبدأ"
              value={copyFrom}
              onChange={(event) => setCopyFrom(event.target.value)}
            >
              {previous.map((o) => (
                <option key={o.id} value={o.id}>
                  {o.term_title_fa} — {o.instructor_name ?? 'بی‌نام'} (
                  {toPersianDigits(o.week_count)} هفته)
                </option>
              ))}
            </select>
          )}
          <p className="text-[12.5px] text-[var(--fg-tertiary)]">
            هفته‌ها پیش‌نویس ساخته می‌شوند؛ انتشارشان با استاد است.
          </p>
        </fieldset>

        <fieldset className="flex flex-col gap-2">
          <legend className="mb-1 text-[13.5px] font-medium">وضعیت آغاز</legend>
          <label className="flex items-center gap-2 text-[14px]">
            <input
              type="radio"
              name="status"
              checked={status === 'DRAFT'}
              onChange={() => setStatus('DRAFT')}
            />
            پیش‌نویس — استاد خودش باز می‌کند
          </label>
          <label className="flex items-center gap-2 text-[14px]">
            <input
              type="radio"
              name="status"
              checked={status === 'OPEN'}
              onChange={() => setStatus('OPEN')}
            />
            باز برای ثبت‌نام
          </label>
        </fieldset>
        <div className="flex flex-col gap-3">
          <Input
            label="ظرفیت"
            hint="خالی یعنی بی‌سقف"
            inputMode="numeric"
            maxLength={4}
            value={capacity}
            error={capacityValid ? undefined : 'بین ۱ تا ۲۰۰۰'}
            onChange={(event) => setCapacity(event.target.value)}
          />
          <Input
            label="کد ثبت‌نام"
            hint="دست‌کم ۴ نویسه؛ خالی یعنی بی کد"
            forceLtr
            maxLength={32}
            value={code}
            error={codeValid ? undefined : 'دست‌کم ۴ نویسه'}
            onChange={(event) => setCode(event.target.value)}
          />
          <label className="flex items-center gap-2 text-[14px]">
            <input
              type="checkbox"
              checked={requiresApproval}
              onChange={(event) => setRequiresApproval(event.target.checked)}
            />
            ثبت‌نام با تأیید استاد
          </label>
        </div>
        <p className="text-[12.5px] text-[var(--fg-tertiary)] md:col-span-2">
          وزن نمره پیش‌فرض است (آزمون ۳۰، پروژه ۵۰، حضور ۱۰، مشارکت ۱۰)؛ استاد در تنظیمات ارائه عوضش
          می‌کند.
        </p>

        <div className="flex gap-2 md:col-span-2">
          <Button
            type="submit"
            loading={busy}
            disabled={
              !courseId ||
              !termId ||
              !instructor ||
              !capacityValid ||
              !codeValid ||
              (weeksFrom === 'OFFERING' && !copyFrom)
            }
          >
            ساخت و سپردن به استاد
          </Button>
          <Button type="button" variant="ghost" onClick={onCancel}>
            انصراف
          </Button>
        </div>
        {error && (
          <div className="md:col-span-2">
            <ErrorLine>{error}</ErrorLine>
          </div>
        )}
      </form>
    </Card>
  );
}
