'use client';

import { type FormEvent, useState } from 'react';

import { errorText, ErrorLine, FactList } from '@/components/admin/common';
import { INPUT_CLASS, SectionHeader } from '@/components/teach/common';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { Input } from '@/components/ui/Input';
import {
  type AdminTerm,
  createTerm,
  deleteTerm,
  type TermInput,
  updateTerm,
} from '@/lib/api/course-admin';
import { formatDateShort } from '@/lib/format/date';
import { toPersianDigits } from '@/lib/format/digits';

import type { CatalogData } from './CoursesAdminView';

/** نیم‌سال‌ها — فقط یکی «جاری» است؛ ارائهٔ تازه پیش‌فرض در همان ساخته می‌شود. */
export function TermsPanel({
  token,
  data,
  onChanged,
}: {
  token: string;
  data: CatalogData;
  onChanged: () => void;
}) {
  const [adding, setAdding] = useState(data.terms.length === 0);

  return (
    <section className="flex flex-col gap-4">
      <SectionHeader
        title="نیم‌سال‌ها"
        description="ارائهٔ تازه پیش‌فرض در نیم‌سال جاری ساخته می‌شود. نیم‌سالی که ارائه یا امتیاز دارد حذف نمی‌شود."
        action={
          !adding && (
            <Button size="sm" onClick={() => setAdding(true)}>
              نیم‌سال تازه
            </Button>
          )
        }
      />
      {adding && (
        <TermForm
          token={token}
          onDone={() => {
            setAdding(false);
            onChanged();
          }}
          onCancel={data.terms.length ? () => setAdding(false) : undefined}
        />
      )}
      {data.terms.length === 0 && !adding && <EmptyState title="هنوز نیم‌سالی تعریف نشده" />}
      <ul className="flex flex-col gap-3">
        {data.terms.map((term) => (
          <li key={term.id}>
            <TermRow term={term} token={token} onChanged={onChanged} />
          </li>
        ))}
      </ul>
    </section>
  );
}

function TermRow({
  term,
  token,
  onChanged,
}: {
  term: AdminTerm;
  token: string;
  onChanged: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function act(action: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await action();
      onChanged();
    } catch (cause) {
      setError(errorText(cause));
    } finally {
      setBusy(false);
    }
  }

  if (editing) {
    return (
      <TermForm
        token={token}
        term={term}
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
        <div className="flex flex-col gap-0.5">
          <span className="flex flex-wrap items-center gap-2 font-semibold">
            {term.title_fa}
            {term.is_current && <Badge tone="success">جاری</Badge>}
          </span>
          <FactList
            className="text-[var(--fg-tertiary)]"
            items={[
              <span key="code" dir="ltr">
                {term.code}
              </span>,
              `${formatDateShort(term.starts_on)} تا ${formatDateShort(term.ends_on)}`,
              `ارائه: ${toPersianDigits(term.offering_count)}`,
            ]}
          />
        </div>
        <div className="flex flex-wrap gap-2">
          {!term.is_current && (
            <Button
              size="sm"
              variant="secondary"
              loading={busy}
              onClick={() => act(() => updateTerm(token, term.id, { is_current: true }))}
            >
              جاری کن
            </Button>
          )}
          <Button size="sm" variant="ghost" onClick={() => setEditing(true)}>
            ویرایش
          </Button>
          {term.offering_count === 0 &&
            (confirmDelete ? (
              <>
                <Button
                  size="sm"
                  variant="danger"
                  loading={busy}
                  onClick={() => act(() => deleteTerm(token, term.id))}
                >
                  حذف قطعی
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setConfirmDelete(false)}>
                  انصراف
                </Button>
              </>
            ) : (
              <Button size="sm" variant="ghost" onClick={() => setConfirmDelete(true)}>
                حذف
              </Button>
            ))}
        </div>
      </div>
      {error && <ErrorLine>{error}</ErrorLine>}
    </Card>
  );
}

function TermForm({
  token,
  term,
  onDone,
  onCancel,
}: {
  token: string;
  term?: AdminTerm;
  onDone: () => void;
  onCancel?: () => void;
}) {
  const [values, setValues] = useState<TermInput>({
    code: term?.code ?? '',
    title_fa: term?.title_fa ?? '',
    starts_on: term?.starts_on ?? '',
    ends_on: term?.ends_on ?? '',
    is_current: term?.is_current ?? false,
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const set = (patch: Partial<TermInput>) => setValues((v) => ({ ...v, ...patch }));
  const datesValid = values.starts_on && values.ends_on && values.ends_on > values.starts_on;

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const body = { ...values, code: values.code.trim(), title_fa: values.title_fa.trim() };
      if (term) await updateTerm(token, term.id, body);
      else await createTerm(token, body);
      onDone();
    } catch (cause) {
      setError(errorText(cause));
      setBusy(false);
    }
  }

  return (
    <Card>
      <form onSubmit={submit} className="grid gap-3 md:grid-cols-2">
        <h3 className="text-[16px] md:col-span-2">{term ? 'ویرایش نیم‌سال' : 'نیم‌سال تازه'}</h3>
        <Input
          label="کد"
          hint="حروف لاتین، رقم و خط تیره — مثل 1405-1"
          forceLtr
          required
          maxLength={20}
          value={values.code}
          onChange={(event) => set({ code: event.target.value })}
        />
        <Input
          label="عنوان"
          required
          maxLength={200}
          placeholder="نیم‌سال اول ۱۴۰۵-۱۴۰۶"
          value={values.title_fa}
          onChange={(event) => set({ title_fa: event.target.value })}
        />
        <DateField
          label="شروع"
          value={values.starts_on}
          onChange={(starts_on) => set({ starts_on })}
        />
        <DateField label="پایان" value={values.ends_on} onChange={(ends_on) => set({ ends_on })} />
        {!term?.is_current && (
          <label className="flex items-center gap-2 text-[14px] md:col-span-2">
            <input
              type="checkbox"
              checked={values.is_current ?? false}
              onChange={(event) => set({ is_current: event.target.checked })}
            />
            نیم‌سال جاری شود (جاری قبلی خاموش می‌شود)
          </label>
        )}
        {values.starts_on && values.ends_on && !datesValid && (
          <p className="text-[13px] text-[var(--fg-warning)] md:col-span-2">
            پایان باید بعد از شروع باشد.
          </p>
        )}
        <div className="flex gap-2 md:col-span-2">
          <Button
            type="submit"
            loading={busy}
            disabled={
              values.code.trim().length < 2 || values.title_fa.trim().length < 2 || !datesValid
            }
          >
            {term ? 'ذخیره' : 'تعریف نیم‌سال'}
          </Button>
          {onCancel && (
            <Button type="button" variant="ghost" onClick={onCancel}>
              انصراف
            </Button>
          )}
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

/** ورودی تاریخ بومی میلادی است؛ تاریخ شمسی زیرش می‌آید. */
function DateField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className="flex flex-col gap-1.5 text-[13.5px] font-medium">
      {label}
      <input
        type="date"
        className={INPUT_CLASS}
        required
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
      <span className="text-[12px] font-normal text-[var(--fg-tertiary)]">
        {value ? formatDateShort(value) : 'تاریخ را انتخاب کن'}
      </span>
    </label>
  );
}
