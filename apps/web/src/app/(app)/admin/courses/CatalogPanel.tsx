'use client';

import Link from 'next/link';
import { type FormEvent, useState } from 'react';

import { errorText, ErrorLine, FactList, Field, SELECT_CLASS } from '@/components/admin/common';
import { SectionHeader } from '@/components/teach/common';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { Textarea } from '@/components/ui/Textarea';
import {
  ACCESS_TIER_LABELS,
  type AccessTier,
  type AdminCourse,
  createCourse,
  type CourseInput,
  DEGREE_LABELS,
  type DegreeLevel,
  slugFromCode,
  updateCourse,
} from '@/lib/api/course-admin';
import { toLatinDigits, toPersianDigits } from '@/lib/format/digits';

import type { CatalogData } from './CoursesAdminView';

/**
 * دروس — درس پوشه‌ای (`Courses/…/course.yml`) اینجا فقط‌خواندنی است، چون
 * همگام‌سازی بعدی هر تغییری را برمی‌گرداند. درسی که هنوز پوشه ندارد اینجا
 * ساخته و ویرایش می‌شود؛ اگر بعداً پوشه‌ای با همان کد بیاید، همان را برمی‌دارد.
 */
export function CatalogPanel({
  token,
  data,
  onChanged,
}: {
  token: string;
  data: CatalogData;
  onChanged: () => void;
}) {
  const [adding, setAdding] = useState(false);

  return (
    <section className="flex flex-col gap-4">
      <SectionHeader
        title="دروس"
        description="درسی که کتاب و جزوه دارد از پوشهٔ Courses می‌آید و آنجا ویرایش می‌شود. درس بی‌پوشه را اینجا تعریف کن."
        action={
          !adding && (
            <Button size="sm" onClick={() => setAdding(true)}>
              درس تازه
            </Button>
          )
        }
      />
      {adding && (
        <CourseForm
          token={token}
          onDone={() => {
            setAdding(false);
            onChanged();
          }}
          onCancel={() => setAdding(false)}
        />
      )}
      <ul className="flex flex-col gap-3">
        {data.courses.map((course) => (
          <li key={course.id}>
            <CourseRow course={course} token={token} onChanged={onChanged} />
          </li>
        ))}
      </ul>
    </section>
  );
}

function CourseRow({
  course,
  token,
  onChanged,
}: {
  course: AdminCourse;
  token: string;
  onChanged: () => void;
}) {
  const [editing, setEditing] = useState(false);

  if (editing) {
    return (
      <CourseForm
        token={token}
        course={course}
        onDone={() => {
          setEditing(false);
          onChanged();
        }}
        onCancel={() => setEditing(false)}
      />
    );
  }

  return (
    <Card className="flex flex-col gap-2">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 flex-col gap-0.5">
          <span className="flex flex-wrap items-center gap-2 font-semibold">
            {course.title_fa}
            {!course.is_active && <Badge tone="neutral">غیرفعال</Badge>}
            {course.source_dir ? (
              <Badge tone="info">از پوشه</Badge>
            ) : (
              <Badge tone="accent">ساخته‌شده در پنل</Badge>
            )}
          </span>
          <FactList
            className="text-[var(--fg-tertiary)]"
            items={[
              <span key="code" dir="ltr">
                {course.code}
              </span>,
              course.degree_level && DEGREE_LABELS[course.degree_level],
              course.credits && `${toPersianDigits(course.credits)} واحد`,
              `ارائه: ${toPersianDigits(course.offering_count)}`,
              `محتوای کتابخانه: ${toPersianDigits(course.material_count)}`,
              !!course.syllabus_weeks &&
                `برنامهٔ درسی: ${toPersianDigits(course.syllabus_weeks)} هفته`,
            ]}
          />
        </div>
        <div className="flex flex-wrap gap-2">
          {course.is_active && (
            <Button asChild size="sm" variant="ghost">
              <Link href={`/courses/${course.slug}`}>ویترین</Link>
            </Button>
          )}
          {!course.source_dir && (
            <Button size="sm" variant="ghost" onClick={() => setEditing(true)}>
              ویرایش
            </Button>
          )}
        </div>
      </div>
      {course.source_dir && (
        <p className="text-[12.5px] text-[var(--fg-secondary)]">
          ویرایش در <span dir="ltr">Courses/{course.source_dir}/course.yml</span> و سپس همگام‌سازی
          دروس.
        </p>
      )}
    </Card>
  );
}

function CourseForm({
  token,
  course,
  onDone,
  onCancel,
}: {
  token: string;
  course?: AdminCourse;
  onDone: () => void;
  onCancel: () => void;
}) {
  const [values, setValues] = useState({
    code: course?.code ?? '',
    slug: course?.slug ?? '',
    title_fa: course?.title_fa ?? '',
    title_en: course?.title_en ?? '',
    description: course?.description ?? '',
    degree_level: (course?.degree_level ?? '') as DegreeLevel | '',
    credits: course?.credits ? String(course.credits) : '',
    default_access_tier: course?.default_access_tier ?? ('SUBSCRIBER' as AccessTier),
    topics: (course?.topics ?? []).join('، '),
    is_public: course?.is_public ?? false,
    is_active: course?.is_active ?? true,
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const set = (patch: Partial<typeof values>) => setValues((v) => ({ ...v, ...patch }));
  const credits = values.credits.trim() ? Number(toLatinDigits(values.credits.trim())) : null;
  const creditsValid =
    credits === null || (Number.isInteger(credits) && credits >= 1 && credits <= 12);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    const body: CourseInput = {
      code: values.code.trim(),
      title_fa: values.title_fa.trim(),
      title_en: values.title_en.trim() || null,
      description: values.description.trim() || null,
      degree_level: values.degree_level || null,
      credits,
      default_access_tier: values.default_access_tier,
      topics: values.topics
        .split(/[،,]/)
        .map((t) => t.trim())
        .filter(Boolean),
      is_public: values.is_public,
      is_active: values.is_active,
      ...(values.slug.trim() ? { slug: values.slug.trim() } : {}),
    };
    try {
      if (course) await updateCourse(token, course.id, body);
      else await createCourse(token, body);
      onDone();
    } catch (cause) {
      setError(errorText(cause));
      setBusy(false);
    }
  }

  return (
    <Card>
      <form onSubmit={submit} className="grid gap-3 md:grid-cols-2">
        <h3 className="text-[16px] md:col-span-2">{course ? 'ویرایش درس' : 'درس تازه'}</h3>
        <Input
          label="عنوان فارسی"
          required
          maxLength={200}
          value={values.title_fa}
          onChange={(event) => set({ title_fa: event.target.value })}
        />
        <Input
          label="عنوان انگلیسی"
          forceLtr
          maxLength={200}
          value={values.title_en}
          onChange={(event) => set({ title_en: event.target.value })}
        />
        <Input
          label="کد درس"
          hint="حروف لاتین، رقم و خط تیره — اگر بعداً پوشه‌ای با همین کد همگام شود، همین درس را برمی‌دارد."
          forceLtr
          required
          maxLength={32}
          value={values.code}
          onChange={(event) => set({ code: event.target.value })}
        />
        <Input
          label="نشانی ویترین"
          hint={
            values.slug.trim()
              ? `/courses/${values.slug.trim()}`
              : `خالی: /courses/${slugFromCode(values.code) || '…'}`
          }
          forceLtr
          maxLength={64}
          value={values.slug}
          onChange={(event) => set({ slug: event.target.value.toLowerCase() })}
        />
        <Field label="مقطع">
          <select
            className={SELECT_CLASS}
            value={values.degree_level}
            onChange={(event) => set({ degree_level: event.target.value as DegreeLevel | '' })}
          >
            <option value="">نامشخص</option>
            {(Object.keys(DEGREE_LABELS) as DegreeLevel[]).map((level) => (
              <option key={level} value={level}>
                {DEGREE_LABELS[level]}
              </option>
            ))}
          </select>
        </Field>
        <Input
          label="واحد"
          inputMode="numeric"
          maxLength={2}
          value={values.credits}
          error={creditsValid ? undefined : 'بین ۱ تا ۱۲'}
          onChange={(event) => set({ credits: event.target.value })}
        />
        <Field label="دسترسی پیش‌فرض کتابخانه">
          <select
            className={SELECT_CLASS}
            value={values.default_access_tier}
            onChange={(event) => set({ default_access_tier: event.target.value as AccessTier })}
          >
            {(Object.keys(ACCESS_TIER_LABELS) as AccessTier[]).map((tier) => (
              <option key={tier} value={tier}>
                {ACCESS_TIER_LABELS[tier]}
              </option>
            ))}
          </select>
        </Field>
        <Input
          label="موضوع‌ها"
          hint="با ویرگول جدا کن"
          maxLength={400}
          value={values.topics}
          onChange={(event) => set({ topics: event.target.value })}
        />
        <div className="md:col-span-2">
          <Textarea
            label="توضیح"
            maxLength={4000}
            rows={3}
            value={values.description}
            onChange={(event) => set({ description: event.target.value })}
          />
        </div>
        <div className="flex flex-col gap-2 md:col-span-2">
          <label className="flex items-center gap-2 text-[14px]">
            <input
              type="checkbox"
              checked={values.is_public}
              onChange={(event) => set({ is_public: event.target.checked })}
            />
            درس عمومی (برای فراگیر بیرون از دانشگاه هم)
          </label>
          <label className="flex items-center gap-2 text-[14px]">
            <input
              type="checkbox"
              checked={values.is_active}
              onChange={(event) => set({ is_active: event.target.checked })}
            />
            فعال — در ویترین دیده می‌شود و ارائه می‌گیرد
          </label>
        </div>
        <div className="flex gap-2 md:col-span-2">
          <Button
            type="submit"
            loading={busy}
            disabled={
              values.code.trim().length < 2 || values.title_fa.trim().length < 2 || !creditsValid
            }
          >
            {course ? 'ذخیره' : 'تعریف درس'}
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
