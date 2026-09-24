'use client';

import { useRouter } from 'next/navigation';
import { useCallback, useEffect, useMemo, useState } from 'react';

import { MatchRing } from '@/components/domain/MatchRing';
import { Button } from '@/components/ui/Button';
import { ChoiceCard } from '@/components/ui/ChoiceCard';
import { SkillSlider } from '@/components/ui/SkillSlider';
import { ApiError, NetworkError } from '@/lib/api/client';
import {
  PRIMARY_GOAL_OPTIONS,
  type PrimaryGoal,
  type SurveyState,
  type SurveyStepResult,
  WORK_STYLE_OPTIONS,
  type WorkStyle,
  fetchSurvey,
  saveAssets,
  saveInterests,
  savePreferences,
  saveSkills,
} from '@/lib/api/profile';
import type { Recommendation } from '@/lib/api/projects';
import {
  type Asset,
  type Interest,
  type LevelLabel,
  type Skill,
  fetchAssets,
  fetchInterests,
  fetchSkills,
} from '@/lib/api/taxonomy';
import { useSession } from '@/lib/auth/use-session';
import { toLatinDigits, toPersianDigits } from '@/lib/format/digits';

import { OnboardingShell } from '../../OnboardingShell';

/**
 * چهار گام ارزیابی نیمرخ — FR-PROF-01، §3.3.
 *
 * | گام | عنوان | محتوا | تخمین |
 * |-----|-------|-------|-------|
 * | ۱ | چه می‌دانی؟ | ۱۰ مهارت هسته، مقیاس ۱-۵ | ۹۰ ثانیه |
 * | ۲ | چه داری؟ | امکانات، چندانتخابی | ۳۰ ثانیه |
 * | ۳ | چه دوست داری؟ | حوزه‌های علاقه، مقیاس ۱-۵ | ۹۰ ثانیه |
 * | ۴ | چه می‌خواهی؟ | سبک کار + هدف + زمان | ۴۵ ثانیه |
 *
 * هر گام مستقل ذخیره می‌شود (`PATCH` جزئی) و بلافاصله پیشنهاد برمی‌گرداند —
 * «لحظهٔ طلایی» §01. دکمهٔ «بعداً» در همهٔ گام‌ها هست، چون هیچ‌کدام
 * الزامی نیستند.
 */

const TOTAL_STEPS = 4;
// گام ۱ ورود اولیه، «اطلاعات پایه» است؛ گام‌های ارزیابی از ۲ شروع می‌شوند.
const SHELL_OFFSET = 1;
const SHELL_TOTAL = TOTAL_STEPS + SHELL_OFFSET;
const DEFAULT_WEEKLY_HOURS = 10;
const MAX_WEEKLY_HOURS = 80;

const STEP_META: Record<number, { title: string; description: string; seconds: number }> = {
  1: {
    title: 'چه می‌دانی؟',
    description:
      'سطح خودت را صادقانه بگو. پایین بودن یک مهارت، در را نمی‌بندد — خیلی از پروژه‌ها همان را به تو یاد می‌دهند.',
    seconds: 90,
  },
  2: {
    title: 'چه داری؟',
    description: 'بعضی پروژه‌ها به وسیله نیاز دارند. هرچه داری علامت بزن تا پیشنهاد نامربوط نگیری.',
    seconds: 30,
  },
  3: {
    title: 'چه دوست داری؟',
    description: 'علاقه مهم‌تر از مهارت است: مهارت را می‌شود ساخت، انگیزه را نه.',
    seconds: 90,
  },
  4: {
    title: 'چه می‌خواهی؟',
    description: 'هدف تو تعیین می‌کند کدام نوع پروژه به تو می‌خورد.',
    seconds: 45,
  },
};

interface Taxonomy {
  skills: Skill[];
  skillLabels: Record<number, string>;
  assets: Asset[];
  interests: Interest[];
  interestLabels: Record<number, string>;
}

function toLabelMap(labels: LevelLabel[]): Record<number, string> {
  return Object.fromEntries(labels.map((l) => [l.level, l.label]));
}

export function SurveySteps({ step }: { step: number }) {
  const router = useRouter();
  const { accessToken, loading: sessionLoading } = useSession();

  const [taxonomy, setTaxonomy] = useState<Taxonomy | null>(null);
  const [state, setState] = useState<SurveyState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [preview, setPreview] = useState<Recommendation[]>([]);

  // پاسخ‌های در حال ویرایش
  const [skills, setSkills] = useState<Record<string, number>>({});
  const [showAllSkills, setShowAllSkills] = useState(false);
  const [assetIds, setAssetIds] = useState<string[]>([]);
  const [interests, setInterests] = useState<Record<string, number>>({});
  const [workStyle, setWorkStyle] = useState<WorkStyle | null>(null);
  const [primaryGoal, setPrimaryGoal] = useState<PrimaryGoal | null>(null);
  const [weeklyHours, setWeeklyHours] = useState<string>('');

  useEffect(() => {
    if (!accessToken) return;
    let cancelled = false;

    Promise.all([fetchSkills(), fetchAssets(), fetchInterests(), fetchSurvey(accessToken)])
      .then(([skillList, assetList, interestList, survey]) => {
        if (cancelled) return;
        setTaxonomy({
          skills: skillList.items,
          skillLabels: toLabelMap(skillList.level_labels),
          assets: assetList,
          interests: interestList.items,
          interestLabels: toLabelMap(interestList.level_labels),
        });
        setState(survey);
        // پاسخ‌های قبلی بازیابی می‌شوند: «بستن مرورگر داده را از بین نمی‌برد».
        setSkills(Object.fromEntries(survey.skills.map((s) => [s.skill_id, s.level])));
        setAssetIds(survey.asset_ids);
        setInterests(Object.fromEntries(survey.interests.map((i) => [i.interest_id, i.level])));
        setWorkStyle(survey.work_style);
        setPrimaryGoal(survey.primary_goal);
        setWeeklyHours(survey.weekly_hours === null ? '' : String(survey.weekly_hours));
      })
      .catch((cause) => !cancelled && setError(messageFor(cause)));

    return () => {
      cancelled = true;
    };
  }, [accessToken]);

  const goNext = useCallback(
    (result?: SurveyStepResult) => {
      if (result) setPreview(result.preview_recommendations);
      if (step >= TOTAL_STEPS) {
        router.push('/onboarding/results');
      } else {
        router.push(`/onboarding/survey/${step + 1}`);
      }
    },
    [router, step],
  );

  const save = useCallback(async () => {
    if (!accessToken) return;
    setError(null);
    setSaving(true);
    try {
      let result: SurveyStepResult;
      switch (step) {
        case 1:
          result = await saveSkills(
            Object.entries(skills).map(([skill_id, level]) => ({ skill_id, level })),
            accessToken,
          );
          break;
        case 2:
          result = await saveAssets(assetIds, accessToken);
          break;
        case 3:
          result = await saveInterests(
            Object.entries(interests).map(([interest_id, level]) => ({ interest_id, level })),
            accessToken,
          );
          break;
        default: {
          const hours = toLatinDigits(weeklyHours).trim();
          result = await savePreferences(
            {
              ...(workStyle ? { work_style: workStyle } : {}),
              ...(primaryGoal ? { primary_goal: primaryGoal } : {}),
              ...(hours ? { weekly_hours: Math.min(MAX_WEEKLY_HOURS, Number(hours)) } : {}),
            },
            accessToken,
          );
        }
      }
      goNext(result);
    } catch (cause) {
      setError(messageFor(cause));
      setSaving(false);
    }
  }, [accessToken, assetIds, goNext, interests, primaryGoal, skills, step, weeklyHours, workStyle]);

  const visibleSkills = useMemo(() => {
    if (!taxonomy) return [];
    return showAllSkills ? taxonomy.skills : taxonomy.skills.filter((s) => s.is_core);
  }, [showAllSkills, taxonomy]);

  if (sessionLoading || !taxonomy || !state) {
    return <div className="h-72" aria-busy="true" aria-label="در حال بارگذاری" />;
  }

  const meta = STEP_META[step];
  // صفحه عدد گام را پیش از رندر اعتبارسنجی کرده؛ این نگهبان فقط برای
  // تایپ است تا دسترسی به کلید ناموجود بی‌صدا نماند.
  if (!meta) return null;

  const answered = answeredCount(step, { skills, assetIds, interests, workStyle, primaryGoal });

  return (
    <OnboardingShell
      title={meta.title}
      description={meta.description}
      step={step + SHELL_OFFSET}
      totalSteps={SHELL_TOTAL}
      estimatedSeconds={meta.seconds}
      footer={
        <>
          {error && (
            <p role="alert" className="text-[13.5px] text-[var(--fg-danger)]">
              {error}
            </p>
          )}

          <Button size="lg" fullWidth loading={saving} onClick={save}>
            {step >= TOTAL_STEPS ? 'ببین چه پیشنهادهایی داری' : 'ذخیره و ادامه'}
          </Button>

          {/* §3.3 — «دکمهٔ بعداً در همهٔ گام‌های غیر الزامی.» */}
          <Button variant="ghost" fullWidth onClick={() => goNext()} disabled={saving}>
            {step >= TOTAL_STEPS ? 'بعداً کامل می‌کنم' : 'این گام را رد کن'}
          </Button>

          {preview.length > 0 && <PreviewStrip items={preview} />}
        </>
      }
    >
      {step === 1 && (
        <div className="flex flex-col divide-y divide-[var(--border-subtle)]">
          {visibleSkills.map((skill) => (
            <SkillSlider
              key={skill.id}
              label={skill.title_fa}
              value={skills[skill.id] ?? null}
              onChange={(level) => setSkills((prev) => ({ ...prev, [skill.id]: level }))}
              levelLabels={taxonomy.skillLabels}
            />
          ))}
          {!showAllSkills && (
            <button
              type="button"
              onClick={() => setShowAllSkills(true)}
              className="mt-3 self-start text-[14px] font-medium text-[var(--fg-brand)] hover:underline"
            >
              مهارت‌های بیشتر ({toPersianDigits(taxonomy.skills.length - visibleSkills.length)}{' '}
              مورد)
            </button>
          )}
        </div>
      )}

      {step === 2 && (
        <div className="grid gap-2.5 sm:grid-cols-2">
          {taxonomy.assets.map((asset) => (
            <ChoiceCard
              key={asset.id}
              name="assets"
              value={asset.id}
              checked={assetIds.includes(asset.id)}
              onChange={(id) =>
                setAssetIds((prev) =>
                  prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
                )
              }
              label={asset.title_fa}
            />
          ))}
        </div>
      )}

      {step === 3 && (
        <div className="flex flex-col divide-y divide-[var(--border-subtle)]">
          {taxonomy.interests.map((interest) => (
            <SkillSlider
              key={interest.id}
              label={interest.title_fa}
              value={interests[interest.id] ?? null}
              onChange={(level) => setInterests((prev) => ({ ...prev, [interest.id]: level }))}
              levelLabels={taxonomy.interestLabels}
            />
          ))}
        </div>
      )}

      {step === 4 && (
        <div className="flex flex-col gap-6">
          <fieldset className="flex flex-col gap-2.5">
            <legend className="mb-2 text-[15px] font-medium text-[var(--fg-primary)]">
              ترجیح می‌دهم…
            </legend>
            {WORK_STYLE_OPTIONS.map((option) => (
              <ChoiceCard
                key={option.value}
                type="radio"
                name="work-style"
                value={option.value}
                checked={workStyle === option.value}
                onChange={(value) => setWorkStyle(value as WorkStyle)}
                label={option.label}
              />
            ))}
          </fieldset>

          <fieldset className="flex flex-col gap-2.5">
            <legend className="mb-2 text-[15px] font-medium text-[var(--fg-primary)]">
              هدف اصلی‌ام
            </legend>
            {PRIMARY_GOAL_OPTIONS.map((option) => (
              <ChoiceCard
                key={option.value}
                type="radio"
                name="primary-goal"
                value={option.value}
                checked={primaryGoal === option.value}
                onChange={(value) => setPrimaryGoal(value as PrimaryGoal)}
                label={option.label}
                hint={option.hint}
              />
            ))}
          </fieldset>

          <div className="flex flex-col gap-1.5">
            <label
              htmlFor="weekly-hours"
              className="text-[15px] font-medium text-[var(--fg-primary)]"
            >
              در هفته چند ساعت وقت داری؟
            </label>
            <p className="text-[12.5px] text-[var(--fg-tertiary)]">
              اگر مطمئن نیستی، {toPersianDigits(DEFAULT_WEEKLY_HOURS)} بگذار. بعداً قابل تغییر است.
            </p>
            <input
              id="weekly-hours"
              inputMode="numeric"
              value={weeklyHours}
              onChange={(e) => setWeeklyHours(e.target.value)}
              placeholder={String(DEFAULT_WEEKLY_HOURS)}
              className="h-11 w-32 rounded-[var(--radius-md)] border border-[var(--border-default)] bg-[var(--bg-surface)] px-3 text-[15px] tabular-nums text-[var(--fg-primary)]"
            />
          </div>
        </div>
      )}

      {answered > 0 && (
        <p className="text-[12.5px] text-[var(--fg-tertiary)]">
          {toPersianDigits(answered)} مورد پاسخ داده‌ای.
        </p>
      )}
    </OnboardingShell>
  );
}

/** نوار پیشنهاد فوری پس از ذخیره — «لحظهٔ طلایی» §01. */
function PreviewStrip({ items }: { items: Recommendation[] }) {
  return (
    <div className="mt-2 flex flex-col gap-2 rounded-[var(--radius-lg)] bg-[var(--brand-50)] p-4">
      <p className="text-[13.5px] font-medium text-[var(--fg-brand)]">
        همین حالا {toPersianDigits(items.length)} پروژه به تو می‌خورد:
      </p>
      <ul className="flex flex-col gap-1.5">
        {items.map((item) => (
          <li key={item.project.id} className="flex items-center gap-2.5">
            <MatchRing score={item.match_score} size="sm" />
            <span className="text-[13.5px] text-[var(--fg-primary)]">{item.project.title_fa}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function answeredCount(
  step: number,
  data: {
    skills: Record<string, number>;
    assetIds: string[];
    interests: Record<string, number>;
    workStyle: WorkStyle | null;
    primaryGoal: PrimaryGoal | null;
  },
): number {
  switch (step) {
    case 1:
      return Object.keys(data.skills).length;
    case 2:
      return data.assetIds.length;
    case 3:
      return Object.keys(data.interests).length;
    default:
      return (data.workStyle ? 1 : 0) + (data.primaryGoal ? 1 : 0);
  }
}

function messageFor(cause: unknown): string {
  if (cause instanceof ApiError || cause instanceof NetworkError) return cause.message;
  return 'خطای غیرمنتظره‌ای رخ داد. دوباره تلاش کن.';
}
