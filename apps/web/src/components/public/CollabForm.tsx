'use client';

import { useState } from 'react';

import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Textarea } from '@/components/ui/Textarea';
import { ApiError } from '@/lib/api/client';
import {
  COLLAB_WAYS,
  type CollaborationPayload,
  HOURS,
  submitCollaboration,
  type Submission,
} from '@/lib/api/intake';

import { ChipMulti, Field, Honeypot, SELECT_CLASS, StepBar, SuccessCard } from './FormParts';

/** فرم «همکاری با ما» — فایل مشخصات فاز ۰، بند ۲۳. چهار گام، همه‌چیز اختیاری به‌جز معرفی و تماس. */
const STEPS = ['معرفی و تخصص', 'مهارت و سابقه', 'نوع همکاری', 'نمونه‌کار و تماس'] as const;

export function CollabForm() {
  const [step, setStep] = useState(0);
  const [intro, setIntro] = useState('');
  const [specialty, setSpecialty] = useState('');
  const [skills, setSkills] = useState('');
  const [experience, setExperience] = useState('');
  const [interests, setInterests] = useState('');
  const [ways, setWays] = useState<string[]>([]);
  const [hours, setHours] = useState('');
  const [portfolio, setPortfolio] = useState('');
  const [name, setName] = useState('');
  const [mobile, setMobile] = useState('');
  const [email, setEmail] = useState('');
  const [trap, setTrap] = useState('');

  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState('');
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<Submission | null>(null);

  function validate(target: number): boolean {
    const next: Record<string, string> = {};
    if (target === 0 && intro.trim().length < 5) next.intro = 'یک معرفی کوتاه بنویسید.';
    if (target === 3) {
      if (name.trim().length < 2) next.name = 'نام را بنویسید.';
      if (!mobile.trim() && !email.trim()) next.mobile = 'شمارهٔ موبایل یا ایمیل لازم است.';
    }
    setErrors(next);
    return Object.keys(next).length === 0;
  }

  async function send() {
    if (!validate(0)) {
      setStep(0);
      return;
    }
    if (!validate(3)) return;
    setBusy(true);
    setFormError('');
    const payload: CollaborationPayload = {
      intro: intro.trim(),
      specialty: specialty.trim() || undefined,
      skills: skills.trim() || undefined,
      experience: experience.trim() || undefined,
      interests: interests.trim() || undefined,
      ways,
      hours_per_week: (hours || undefined) as CollaborationPayload['hours_per_week'],
      portfolio_url: portfolio.trim() || undefined,
      name: name.trim(),
      mobile: mobile.trim() || undefined,
      email: email.trim() || undefined,
      website: trap,
    };
    try {
      setDone(await submitCollaboration(payload));
    } catch (error) {
      if (error instanceof ApiError && error.status === 422) {
        setErrors(error.fieldErrors);
        setFormError('برخی موارد نیاز به اصلاح دارد.');
        if (error.fieldErrors.intro) setStep(0);
      } else if (error instanceof ApiError && error.isRateLimited) {
        setFormError('درخواست‌های زیادی فرستاده‌اید. کمی بعد دوباره امتحان کنید.');
      } else {
        setFormError(error instanceof Error ? error.message : 'ارسال انجام نشد.');
      }
    } finally {
      setBusy(false);
    }
  }

  if (done) return <SuccessCard icon="🤝" title="درخواست همکاری ثبت شد" result={done} />;

  return (
    <div className="flex flex-col gap-6">
      <StepBar steps={STEPS} current={step} />
      <form
        onSubmit={(event) => {
          event.preventDefault();
          if (step < STEPS.length - 1) {
            if (validate(step)) setStep(step + 1);
          } else void send();
        }}
        noValidate
        className="relative flex flex-col gap-6 rounded-[var(--radius-xl)] border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-6 shadow-[var(--shadow-md)] md:p-8"
      >
        <Honeypot value={trap} onChange={setTrap} />

        {step === 0 && (
          <>
            <Textarea
              label="یک معرفی کوتاه"
              hint="چه کاری می‌کنید و به چه چیزی علاقه دارید؟"
              value={intro}
              onChange={(event) => setIntro(event.target.value)}
              maxLength={4000}
              rows={5}
              error={errors.intro}
            />
            <Input
              label="تخصص اصلی"
              value={specialty}
              onChange={(event) => setSpecialty(event.target.value)}
              placeholder="مثلاً: تحلیل داده حمل‌ونقل"
              error={errors.specialty}
            />
          </>
        )}

        {step === 1 && (
          <>
            <Input
              label="مهارت‌ها"
              value={skills}
              onChange={(event) => setSkills(event.target.value)}
              hint="با ویرگول جدا کنید."
              placeholder="Python، R، GIS، SUMO…"
              error={errors.skills}
            />
            <Textarea
              label="سابقه"
              value={experience}
              onChange={(event) => setExperience(event.target.value)}
              maxLength={2000}
              rows={4}
            />
            <Input
              label="علایق"
              value={interests}
              onChange={(event) => setInterests(event.target.value)}
              error={errors.interests}
            />
          </>
        )}

        {step === 2 && (
          <>
            <Field label="نوع همکاری" hint="چندتا می‌توانید انتخاب کنید.">
              <ChipMulti
                label="نوع همکاری"
                options={COLLAB_WAYS.map((w) => ({ value: w, label: w }))}
                value={ways}
                onChange={setWays}
              />
            </Field>
            <Field label="ظرفیت زمانی">
              <select
                className={SELECT_CLASS}
                value={hours}
                onChange={(e) => setHours(e.target.value)}
              >
                <option value="">انتخاب کنید…</option>
                {HOURS.map((h) => (
                  <option key={h.value} value={h.value}>
                    {h.label}
                  </option>
                ))}
              </select>
            </Field>
          </>
        )}

        {step === 3 && (
          <div className="grid gap-4 md:grid-cols-2">
            <Input
              label="پیوند نمونه‌کار یا رزومه"
              value={portfolio}
              onChange={(event) => setPortfolio(event.target.value)}
              forceLtr
              placeholder="https://"
              hint="آدرس باید با https:// شروع شود."
              error={errors.portfolio_url}
            />
            <Input
              label="نام"
              value={name}
              onChange={(event) => setName(event.target.value)}
              autoComplete="name"
              error={errors.name}
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
              ارسال درخواست همکاری
            </Button>
          )}
        </div>
      </form>
    </div>
  );
}
