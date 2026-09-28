'use client';

import { useState } from 'react';

import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Textarea } from '@/components/ui/Textarea';
import { ChipGroup } from '@/components/ui/ChipGroup';
import { ApiError } from '@/lib/api/client';
import {
  INTAKE_EXAMPLES,
  type IntakePayload,
  NEED_TYPES,
  type NeedType,
  SERVICES,
  type Service,
  submitIntake,
  type Submission,
} from '@/lib/api/intake';

import { ChipMulti, Field, Honeypot, SELECT_CLASS, StepBar, SuccessCard } from './FormParts';

/**
 * فرم «مسئله یا نیاز خود را مطرح کنید» — فایل مشخصات فاز ۰، بند ۲۰ تا ۲۲.
 *
 * چهار گام، همه‌چیز را یکجا نشان نمی‌دهیم (Progressive Disclosure): «Data دارید؟»
 * فقط برای Data / AI / پژوهش می‌آید. هر خطای سرور زیر فیلد خودش نشان داده می‌شود.
 */
const STEPS = ['نیاز', 'جزئیات', 'زمان و بودجه', 'تماس'] as const;

const TIMELINES = ['کمتر از ۲ هفته', '۱ تا ۳ ماه', 'بیش از ۳ ماه', 'فرقی ندارد'];
const BUDGETS = ['هنوز نمی‌دانم', 'تا ۱۰ میلیون تومان', '۱۰ تا ۵۰ میلیون', 'بیش از ۵۰ میلیون'];
const SECTORS = [
  'عمران و حمل‌ونقل',
  'کشاورزی',
  'صنعت و معدن',
  'آموزش',
  'گردشگری',
  'شهرداری و مدیریت شهری',
  'سایر',
];

export function IntakeForm() {
  const [step, setStep] = useState(0);
  const [needType, setNeedType] = useState<NeedType | ''>('');
  const [services, setServices] = useState<Service[]>([]);
  const [summary, setSummary] = useState('');
  const [expected, setExpected] = useState('');
  const [sector, setSector] = useState('');
  const [hasData, setHasData] = useState<'YES' | 'NO' | 'UNSURE' | ''>('');
  const [timeline, setTimeline] = useState('');
  const [budget, setBudget] = useState('');
  const [name, setName] = useState('');
  const [organization, setOrganization] = useState('');
  const [mobile, setMobile] = useState('');
  const [email, setEmail] = useState('');
  const [notes, setNotes] = useState('');
  const [trap, setTrap] = useState('');

  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState('');
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<Submission | null>(null);

  const needsData =
    needType === 'Research' ||
    services.some((s) => ['Data Analysis', 'AI', 'Research'].includes(s));

  function applyExample(example: (typeof INTAKE_EXAMPLES)[number]) {
    setSummary(example.text);
    setNeedType(example.type);
    setServices(example.services);
    setErrors({});
  }

  function validate(target: number): boolean {
    const next: Record<string, string> = {};
    if (target === 0) {
      if (!needType) next.need_type = 'نوع نیاز را انتخاب کنید.';
      if (summary.trim().length < 5) next.summary = 'چند کلمه دربارهٔ کاری که می‌خواهید بنویسید.';
    }
    if (target === 3) {
      if (name.trim().length < 2) next.name = 'نام را بنویسید.';
      if (!mobile.trim() && !email.trim()) next.mobile = 'شمارهٔ موبایل یا ایمیل لازم است.';
    }
    setErrors(next);
    return Object.keys(next).length === 0;
  }

  function next() {
    if (validate(step)) setStep(step + 1);
  }

  async function send() {
    if (!validate(0)) {
      setStep(0);
      return;
    }
    if (!validate(3)) return;
    setBusy(true);
    setFormError('');
    const payload: IntakePayload = {
      need_type: needType as NeedType,
      services,
      summary: summary.trim(),
      expected_result: expected.trim() || undefined,
      sector: sector || undefined,
      has_data: needsData && hasData ? hasData : undefined,
      timeline: timeline || undefined,
      budget: budget || undefined,
      notes: notes.trim() || undefined,
      name: name.trim(),
      organization: organization.trim() || undefined,
      mobile: mobile.trim() || undefined,
      email: email.trim() || undefined,
      website: trap,
    };
    try {
      setDone(await submitIntake(payload));
    } catch (error) {
      if (error instanceof ApiError && error.status === 422) {
        setErrors(error.fieldErrors);
        setFormError('برخی موارد نیاز به اصلاح دارد.');
        const fields = Object.keys(error.fieldErrors);
        if (fields.some((f) => ['need_type', 'summary', 'services'].includes(f))) setStep(0);
      } else if (error instanceof ApiError && error.isRateLimited) {
        setFormError('درخواست‌های زیادی فرستاده‌اید. کمی بعد دوباره امتحان کنید.');
      } else {
        setFormError(error instanceof Error ? error.message : 'ارسال انجام نشد.');
      }
    } finally {
      setBusy(false);
    }
  }

  if (done) return <SuccessCard icon="✅" title="مسئلهٔ شما ثبت شد" result={done} />;

  return (
    <div className="flex flex-col gap-6">
      <section
        aria-labelledby="examples-title"
        className="rounded-[var(--radius-xl)] bg-[var(--brand-50)] p-5 md:p-6"
      >
        <h2 id="examples-title" className="text-[16px] text-[var(--fg-brand)]">
          چه چیزی می‌توانید مطرح کنید؟
        </h2>
        <p className="mt-1 text-[13px] text-[var(--fg-secondary)]">
          روی یکی از نمونه‌ها بزنید تا فرم برایتان پیش‌پر شود.
        </p>
        <ul className="mt-4 flex flex-wrap gap-2">
          {INTAKE_EXAMPLES.map((example) => (
            <li key={example.text}>
              <button
                type="button"
                onClick={() => applyExample(example)}
                className="rounded-[var(--radius-lg)] border border-[var(--border-default)] bg-[var(--bg-surface)] px-4 py-2 text-start text-[13.5px] leading-[1.8] text-[var(--fg-secondary)] hover:border-[var(--brand-600)] hover:text-[var(--fg-primary)]"
              >
                «{example.text}»
              </button>
            </li>
          ))}
        </ul>
      </section>

      <StepBar steps={STEPS} current={step} />

      <form
        onSubmit={(event) => {
          event.preventDefault();
          if (step < STEPS.length - 1) next();
          else void send();
        }}
        noValidate
        className="relative flex flex-col gap-6 rounded-[var(--radius-xl)] border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-6 shadow-[var(--shadow-md)] md:p-8"
      >
        <Honeypot value={trap} onChange={setTrap} />

        {step === 0 && (
          <>
            <Field label="نوع نیاز من" error={errors.need_type}>
              <ChipGroup
                label="نوع نیاز"
                options={NEED_TYPES.map((t) => ({ value: t.value, label: t.label }))}
                value={needType as NeedType}
                onChange={setNeedType}
              />
            </Field>
            <Textarea
              label="چه کاری می‌خواهید انجام شود؟"
              hint="به زبان خودتان بنویسید؛ کوتاه هم کافی است."
              value={summary}
              onChange={(event) => setSummary(event.target.value)}
              maxLength={4000}
              rows={5}
              error={errors.summary}
            />
          </>
        )}

        {step === 1 && (
          <>
            <Field
              label="کدام خدمات به کار شما می‌خورد؟"
              hint="چندتا می‌توانید انتخاب کنید."
              error={errors.services}
            >
              <ChipMulti
                label="خدمات"
                options={SERVICES.map((s) => ({ value: s, label: s }))}
                value={services}
                onChange={setServices}
              />
            </Field>
            <Field label="حوزهٔ فعالیت">
              <select
                className={SELECT_CLASS}
                value={sector}
                onChange={(event) => setSector(event.target.value)}
              >
                <option value="">انتخاب کنید…</option>
                {SECTORS.map((s) => (
                  <option key={s}>{s}</option>
                ))}
              </select>
            </Field>
            <Textarea
              label="نتیجهٔ مورد انتظار چیست؟"
              hint="مثلاً یک گزارش تحلیلی، داشبورد یا مقاله."
              value={expected}
              onChange={(event) => setExpected(event.target.value)}
              maxLength={2000}
              rows={3}
            />
            {needsData && (
              <div className="rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--brand-50)] p-4">
                <Field label="آیا Data دارید؟">
                  <select
                    className={SELECT_CLASS}
                    value={hasData}
                    onChange={(event) => setHasData(event.target.value as typeof hasData)}
                  >
                    <option value="">انتخاب کنید…</option>
                    <option value="YES">بله، دارم</option>
                    <option value="NO">خیر، باید تهیه شود</option>
                    <option value="UNSURE">مطمئن نیستم</option>
                  </select>
                </Field>
              </div>
            )}
          </>
        )}

        {step === 2 && (
          <>
            <Field label="زمان مورد نظر">
              <select
                className={SELECT_CLASS}
                value={timeline}
                onChange={(e) => setTimeline(e.target.value)}
              >
                <option value="">انتخاب کنید…</option>
                {TIMELINES.map((t) => (
                  <option key={t}>{t}</option>
                ))}
              </select>
            </Field>
            <Field label="بودجهٔ تقریبی" hint="اختیاری؛ برای پیشنهاد دقیق‌تر.">
              <select
                className={SELECT_CLASS}
                value={budget}
                onChange={(e) => setBudget(e.target.value)}
              >
                <option value="">انتخاب کنید…</option>
                {BUDGETS.map((b) => (
                  <option key={b}>{b}</option>
                ))}
              </select>
            </Field>
          </>
        )}

        {step === 3 && (
          <>
            <div className="grid gap-4 md:grid-cols-2">
              <Input
                label="نام"
                value={name}
                onChange={(event) => setName(event.target.value)}
                autoComplete="name"
                error={errors.name}
              />
              <Input
                label="سازمان / شرکت (اختیاری)"
                value={organization}
                onChange={(event) => setOrganization(event.target.value)}
                autoComplete="organization"
                error={errors.organization}
              />
              <Input
                label="شمارهٔ موبایل"
                value={mobile}
                onChange={(event) => setMobile(event.target.value)}
                forceLtr
                inputMode="tel"
                autoComplete="tel"
                placeholder="09…"
                error={errors.mobile}
              />
              <Input
                label="ایمیل"
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                forceLtr
                autoComplete="email"
                error={errors.email}
              />
            </div>
            <Textarea
              label="توضیح تکمیلی"
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
              maxLength={2000}
              rows={3}
            />
            <p className="text-[13px] leading-[1.9] text-[var(--fg-tertiary)]">
              اگر شمارهٔ شما قبلاً در سامانه تأیید شده باشد، درخواست به کد شخصی شما وصل می‌شود.
              ثبت‌نام لازم نیست.
            </p>
          </>
        )}

        {formError && (
          <p role="alert" className="text-[14px] text-[var(--fg-danger)]">
            {formError}
          </p>
        )}

        <div className="flex items-center justify-between gap-3 border-t border-[var(--border-subtle)] pt-5">
          <Button
            type="button"
            variant="secondary"
            onClick={() => setStep(step - 1)}
            disabled={step === 0}
          >
            قبلی
          </Button>
          {step < STEPS.length - 1 ? (
            <Button type="submit">ادامه</Button>
          ) : (
            <Button type="submit" loading={busy} loadingLabel="در حال ارسال…">
              ارسال مسئله
            </Button>
          )}
        </div>
      </form>
    </div>
  );
}
