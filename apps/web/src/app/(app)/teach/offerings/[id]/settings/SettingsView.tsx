'use client';

import { type FormEvent, useEffect, useState } from 'react';

import { errorText, ErrorLine, Field, SELECT_CLASS } from '@/components/admin/common';
import { OfferingStatusBadge, SectionHeader } from '@/components/teach/common';
import { useOffering } from '@/components/teach/OfferingFrame';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import {
  copyContent,
  fetchTeachOfferings,
  GRADING_LABELS,
  type GradingKey,
  OFFERING_STATUS_LABELS,
  type OfferingStatus,
  setGradingPolicy,
  type TeachOffering,
  updateOffering,
} from '@/lib/api/teach';
import { toLatinDigits, toPersianDigits } from '@/lib/format/digits';

const STATUS_HELP: Record<OfferingStatus, string> = {
  DRAFT: 'فقط کادر آموزشی می‌بیند؛ ثبت‌نام بسته است.',
  OPEN: 'دانشجویان می‌توانند ثبت‌نام کنند.',
  IN_PROGRESS: 'کلاس برگزار می‌شود؛ ثبت‌نام تازه بسته است.',
  CLOSED: 'ترم تمام شده؛ هنوز می‌شود نمره ثبت کرد یا به اعتراض رسید.',
  ARCHIVED: 'بایگانی — بازگشت‌ناپذیر.',
};

/**
 * `/teach/offerings/[id]/settings` — وضعیت، ثبت‌نام، وزن نمره و کپی محتوا.
 *
 * گذارهای مجاز وضعیت از سرور می‌آیند (`allowed_statuses`)؛ رابط فقط همان‌ها
 * را پیشنهاد می‌کند و سرور دوباره می‌سنجد (ADR-0019).
 */
export function SettingsView() {
  return (
    <div className="flex flex-col gap-6">
      <StatusCard />
      <EnrollmentCard />
      <GradingCard />
      <CopyCard />
    </div>
  );
}

function StatusCard() {
  const { offering, token, replace } = useOffering();
  const [busy, setBusy] = useState<OfferingStatus | null>(null);
  const [confirm, setConfirm] = useState<OfferingStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function move(status: OfferingStatus) {
    if (status === 'ARCHIVED' && confirm !== status) {
      setConfirm(status);
      return;
    }
    setBusy(status);
    setError(null);
    try {
      replace(await updateOffering(offering.id, { status }, token));
      setConfirm(null);
    } catch (cause) {
      setError(errorText(cause));
    } finally {
      setBusy(null);
    }
  }

  return (
    <Card className="flex flex-col gap-3">
      <SectionHeader
        title="وضعیت ارائه"
        description={STATUS_HELP[offering.status]}
        action={<OfferingStatusBadge status={offering.status} />}
      />
      {offering.allowed_statuses.length === 0 ? (
        <p className="text-[13.5px] text-[var(--fg-secondary)]">این وضعیت پایانی است.</p>
      ) : (
        <div className="flex flex-wrap gap-2">
          {offering.allowed_statuses.map((status) => (
            <Button
              key={status}
              variant={status === 'ARCHIVED' && confirm === status ? 'danger' : 'secondary'}
              size="sm"
              loading={busy === status}
              onClick={() => move(status)}
            >
              {status === 'ARCHIVED' && confirm === status
                ? 'بله، بایگانی کن'
                : `رفتن به «${OFFERING_STATUS_LABELS[status]}»`}
            </Button>
          ))}
        </div>
      )}
      {error && <ErrorLine>{error}</ErrorLine>}
    </Card>
  );
}

function EnrollmentCard() {
  const { offering, token, replace } = useOffering();
  const [approval, setApproval] = useState(offering.requires_approval);
  const [code, setCode] = useState(offering.enrollment_code ?? '');
  const [capacity, setCapacity] = useState(offering.capacity ? String(offering.capacity) : '');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function save(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setMessage(null);
    const cap = toLatinDigits(capacity).trim();
    try {
      replace(
        await updateOffering(
          offering.id,
          {
            requires_approval: approval,
            ...(code.trim() ? { enrollment_code: code.trim() } : { clear_enrollment_code: true }),
            ...(cap ? { capacity: Number(cap) } : { clear_capacity: true }),
          },
          token,
        ),
      );
      setMessage('ذخیره شد.');
    } catch (cause) {
      setError(errorText(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="flex flex-col gap-3">
      <SectionHeader
        title="ثبت‌نام"
        description="کد ثبت‌نام را در کلاس اعلام کن تا فقط دانشجویان همین کلاس بپیوندند. بدون کد، هر کسی می‌تواند درخواست دهد."
      />
      <form onSubmit={save} className="grid gap-3 md:grid-cols-2">
        <Input
          label="کد ثبت‌نام"
          hint="خالی یعنی بی‌کد. دست‌کم ۴ نویسه؛ کوچک و بزرگ حرف مهم نیست."
          forceLtr
          maxLength={32}
          value={code}
          onChange={(event) => setCode(event.target.value)}
        />
        <Input
          label="ظرفیت"
          hint="خالی یعنی بی‌سقف."
          inputMode="numeric"
          value={capacity}
          onChange={(event) => setCapacity(event.target.value.replace(/[^\d۰-۹]/g, ''))}
        />
        <label className="flex items-center gap-2 text-[13.5px] md:col-span-2">
          <input
            type="checkbox"
            checked={approval}
            onChange={(event) => setApproval(event.target.checked)}
          />
          هر ثبت‌نام پیش از پیوستن باید تأیید شود
        </label>
        <div className="flex items-center gap-3 md:col-span-2">
          <Button type="submit" loading={busy}>
            ذخیره
          </Button>
          {message && (
            <span role="status" className="text-[13.5px] text-[var(--fg-success)]">
              {message}
            </span>
          )}
        </div>
      </form>
      {error && <ErrorLine>{error}</ErrorLine>}
    </Card>
  );
}

const KEYS: GradingKey[] = ['quiz', 'project', 'attendance', 'participation'];

function GradingCard() {
  const { offering, token, reload } = useOffering();
  const [weights, setWeights] = useState<Record<GradingKey, string>>(
    () =>
      Object.fromEntries(
        KEYS.map((key) => [key, String(offering.grading_policy[key] ?? 0)]),
      ) as Record<GradingKey, string>,
  );
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const numbers = KEYS.map((key) => Number(toLatinDigits(weights[key]) || 0));
  const total = numbers.reduce((sum, n) => sum + n, 0);

  async function save(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      await setGradingPolicy(
        offering.id,
        Object.fromEntries(KEYS.map((key, i) => [key, numbers[i]])) as Record<GradingKey, number>,
        token,
      );
      setMessage('وزن‌ها ذخیره شد؛ نمرهٔ یادگیری با همین وزن‌ها حساب می‌شود.');
      await reload();
    } catch (cause) {
      setError(errorText(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="flex flex-col gap-3">
      <SectionHeader
        title="وزن اجزای نمره"
        description="نمرهٔ یادگیری و پیشنهاد دفتر نمره با همین وزن‌ها ساخته می‌شوند. جمع باید ۱۰۰ باشد."
      />
      <form onSubmit={save} className="flex flex-col gap-3">
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          {KEYS.map((key) => (
            <Input
              key={key}
              label={`${GRADING_LABELS[key]} (٪)`}
              inputMode="numeric"
              value={weights[key]}
              onChange={(event) =>
                setWeights((w) => ({ ...w, [key]: event.target.value.replace(/[^\d۰-۹]/g, '') }))
              }
            />
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <span
            aria-live="polite"
            className={total === 100 ? 'text-[var(--fg-success)]' : 'text-[var(--fg-danger)]'}
          >
            جمع: {toPersianDigits(total)} از ۱۰۰
          </span>
          <Button type="submit" loading={busy} disabled={total !== 100}>
            ذخیرهٔ وزن‌ها
          </Button>
          {message && (
            <span role="status" className="text-[13.5px] text-[var(--fg-success)]">
              {message}
            </span>
          )}
        </div>
      </form>
      {error && <ErrorLine>{error}</ErrorLine>}
    </Card>
  );
}

function CopyCard() {
  const { offering, token, reload } = useOffering();
  const [sources, setSources] = useState<TeachOffering[]>([]);
  const [source, setSource] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchTeachOfferings(token)
      .then((rows) =>
        setSources(rows.filter((r) => r.id !== offering.id && r.course_id === offering.course_id)),
      )
      .catch(() => setSources([]));
  }, [token, offering.id, offering.course_id]);

  if (sources.length === 0) return null;

  async function copy() {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const { weeks_copied } = await copyContent(offering.id, source, token);
      setMessage(`${toPersianDigits(weeks_copied)} هفته به‌صورت پیش‌نویس کپی شد.`);
      await reload();
    } catch (cause) {
      setError(errorText(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="flex flex-col gap-3">
      <SectionHeader
        title="کپی محتوا از ارائهٔ قبلی"
        description="هفته‌ها، منابع و پیوندهای کتابخانه همه پیش‌نویس کپی می‌شوند؛ انتشار تصمیم تازه‌ای است."
      />
      <div className="flex flex-wrap items-end gap-3">
        <div className="min-w-[16rem] flex-1">
          <Field label="ارائهٔ مبدأ">
            <select
              className={SELECT_CLASS}
              value={source}
              onChange={(e) => setSource(e.target.value)}
            >
              <option value="">انتخاب کن…</option>
              {sources.map((row) => (
                <option key={row.id} value={row.id}>
                  {row.course_title_fa} — {row.term_title_fa}
                </option>
              ))}
            </select>
          </Field>
        </div>
        <Button variant="secondary" disabled={!source} loading={busy} onClick={copy}>
          کپی هفته‌ها
        </Button>
      </div>
      {message && (
        <p role="status" className="text-[13.5px] text-[var(--fg-success)]">
          {message}
        </p>
      )}
      {error && <ErrorLine>{error}</ErrorLine>}
    </Card>
  );
}
