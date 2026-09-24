'use client';

import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';

import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { ApiError, NetworkError } from '@/lib/api/client';
import { DEGREE_OPTIONS, type DegreeLevel, updateProfile } from '@/lib/api/profile';
import { searchUniversities, type University } from '@/lib/api/taxonomy';
import { useSession } from '@/lib/auth/use-session';
import { toLatinDigits } from '@/lib/format/digits';

import { OnboardingShell } from '../OnboardingShell';

/**
 * `/onboarding/basic` — §3.3، §7.1.
 *
 * شش فیلد، زیر سقف هفت‌تایی ناحیه. نام و نام خانوادگی اجباری‌اند چون
 * `resolve()` در §7.1 بدون آن‌ها کاربر را در `BASIC_INFO_REQUIRED` نگه
 * می‌دارد؛ بقیه اختیاری است.
 */

const SEARCH_DEBOUNCE_MS = 300;
const MIN_QUERY_LENGTH = 2;

export function BasicInfoForm() {
  const router = useRouter();
  const { accessToken, loading } = useSession();

  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [fieldOfStudy, setFieldOfStudy] = useState('');
  const [degreeLevel, setDegreeLevel] = useState<DegreeLevel | ''>('');
  const [entryYear, setEntryYear] = useState('');

  const [universityQuery, setUniversityQuery] = useState('');
  const [universities, setUniversities] = useState<University[]>([]);
  const [university, setUniversity] = useState<University | null>(null);

  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // جستجوی دانشگاه با تأخیر، تا هر حرف یک درخواست نزند.
  useEffect(() => {
    if (university || universityQuery.trim().length < MIN_QUERY_LENGTH) {
      setUniversities([]);
      return;
    }
    const timer = setTimeout(() => {
      searchUniversities(universityQuery)
        .then(setUniversities)
        .catch(() => setUniversities([]));
    }, SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [universityQuery, university]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!accessToken) return;

    setError(null);
    setSubmitting(true);
    try {
      const year = toLatinDigits(entryYear).trim();
      await updateProfile(
        {
          first_name: firstName.trim(),
          last_name: lastName.trim(),
          ...(fieldOfStudy.trim() ? { field_of_study: fieldOfStudy.trim() } : {}),
          ...(degreeLevel ? { degree_level: degreeLevel } : {}),
          ...(university ? { university_id: university.id } : {}),
          ...(year ? { entry_year: Number(year) } : {}),
        },
        accessToken,
      );
      router.push('/onboarding/survey/1');
    } catch (cause) {
      setError(messageFor(cause));
      setSubmitting(false);
    }
  }

  if (loading) return <div className="h-64" aria-busy="true" />;

  const canSubmit = firstName.trim().length > 0 && lastName.trim().length > 0;

  return (
    <OnboardingShell
      title="اول خودت را معرفی کن"
      description="این اطلاعات برای صدور گواهی و ارتباط استاد با تو لازم است."
      step={1}
      totalSteps={5}
    >
      <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
        <div className="grid gap-4 sm:grid-cols-2">
          <Input
            label="نام"
            value={firstName}
            onChange={(e) => setFirstName(e.target.value)}
            autoComplete="given-name"
            required
          />
          <Input
            label="نام خانوادگی"
            value={lastName}
            onChange={(e) => setLastName(e.target.value)}
            autoComplete="family-name"
            required
          />
        </div>

        <div className="flex flex-col gap-1.5">
          <Input
            label="دانشگاه"
            hint="بخشی از نام را بنویس تا پیدا شود. اگر دانشجو نیستی، خالی بگذار."
            value={university ? university.title_fa : universityQuery}
            onChange={(e) => {
              setUniversity(null);
              setUniversityQuery(e.target.value);
            }}
            autoComplete="off"
          />
          {universities.length > 0 && (
            <ul className="flex flex-col overflow-hidden rounded-[var(--radius-md)] border border-[var(--border-default)] bg-[var(--bg-surface)]">
              {universities.slice(0, 6).map((item) => (
                <li key={item.id}>
                  <button
                    type="button"
                    onClick={() => {
                      setUniversity(item);
                      setUniversities([]);
                    }}
                    className="w-full px-3 py-2.5 text-start text-[14px] text-[var(--fg-primary)] hover:bg-[var(--bg-sunken)]"
                  >
                    {item.title_fa}
                    {item.city && <span className="text-[var(--fg-tertiary)]"> — {item.city}</span>}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        <Input
          label="رشتهٔ تحصیلی"
          value={fieldOfStudy}
          onChange={(e) => setFieldOfStudy(e.target.value)}
        />

        <div className="grid gap-4 sm:grid-cols-2">
          <div className="flex flex-col gap-1.5">
            <label
              htmlFor="degree-level"
              className="text-[13.5px] font-medium text-[var(--fg-primary)]"
            >
              مقطع
            </label>
            <select
              id="degree-level"
              value={degreeLevel}
              onChange={(e) => setDegreeLevel(e.target.value as DegreeLevel | '')}
              className="h-11 rounded-[var(--radius-md)] border border-[var(--border-default)] bg-[var(--bg-surface)] px-3 text-[15px] text-[var(--fg-primary)]"
            >
              <option value="">انتخاب کن</option>
              {DEGREE_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>

          <Input
            label="سال ورود"
            hint="شمسی، مثلاً ۱۴۰۲"
            inputMode="numeric"
            value={entryYear}
            onChange={(e) => setEntryYear(e.target.value)}
          />
        </div>

        {error && (
          <p role="alert" className="text-[13.5px] text-[var(--fg-danger)]">
            {error}
          </p>
        )}

        <Button type="submit" size="lg" fullWidth loading={submitting} disabled={!canSubmit}>
          ادامه
        </Button>
      </form>
    </OnboardingShell>
  );
}

function messageFor(cause: unknown): string {
  if (cause instanceof ApiError || cause instanceof NetworkError) return cause.message;
  return 'خطای غیرمنتظره‌ای رخ داد. دوباره تلاش کن.';
}
