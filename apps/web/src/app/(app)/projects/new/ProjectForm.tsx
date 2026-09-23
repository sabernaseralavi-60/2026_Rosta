'use client';

import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';

import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card, CardDescription, CardTitle } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { Textarea } from '@/components/ui/Textarea';
import { ApiError, NetworkError } from '@/lib/api/client';
import type { ProjectKind, WorkStyle } from '@/lib/api/projects';
import { type Skill, fetchSkills } from '@/lib/api/taxonomy';
import { createMilestone, createProject } from '@/lib/api/workspace';
import { readSession } from '@/lib/auth/session';
import { useSession } from '@/lib/auth/use-session';
import { toPersianDigits } from '@/lib/format/digits';

/**
 * `/projects/new` — FR-PRJ-01.
 *
 * پروژه با مرحله‌هایش **در یک فرم** ساخته می‌شود، نه در دو گام. §7.4
 * انتشار را مشروط به داشتن دست‌کم یک مرحله و یک مهارت می‌کند؛ اگر فرم
 * این دو را نگیرد، سازنده پروژه‌ای می‌سازد که بلافاصله نمی‌تواند منتشر
 * کند و دلیلش را هم نمی‌داند.
 *
 * نوع پروژه بر اساس نقش کاربر محدود می‌شود، ولی تصمیم نهایی با سرور
 * است (§6.4): اینجا فقط گزینه‌هایی که احتمالاً مجازند نشان داده می‌شوند
 * و پیام ۴۰۳ سرور هم نمایش داده می‌شود.
 */

const KINDS: { value: ProjectKind; label: string; hint: string }[] = [
  { value: 'D_PERSONAL', label: 'پروژهٔ شخصی', hint: 'برای همه باز است.' },
  { value: 'A_VENTURE', label: 'کارآفرینی', hint: 'نیازمند نقش منتور، استاد یا مدیر.' },
  { value: 'B_RESEARCH', label: 'پژوهشی', hint: 'نیازمند نقش منتور، استاد یا مدیر.' },
  { value: 'C_PROBLEM', label: 'حل مسئلهٔ واقعی', hint: 'نیازمند نقش منتور، استاد یا مدیر.' },
];

const WORK_STYLES: { value: WorkStyle; label: string }[] = [
  { value: 'TEAM', label: 'تیمی' },
  { value: 'SOLO', label: 'انفرادی' },
  { value: 'EITHER', label: 'فرقی ندارد' },
];

const MANAGED_ROLES = ['MENTOR', 'INSTRUCTOR', 'COORDINATOR', 'ADMIN'];

interface MilestoneDraft {
  title_fa: string;
  description: string;
  points: string;
  due_on: string;
}

const EMPTY_MILESTONE: MilestoneDraft = {
  title_fa: '',
  description: '',
  points: '0',
  due_on: '',
};

export function ProjectForm() {
  const router = useRouter();
  const { accessToken, loading: sessionLoading } = useSession();

  const [skills, setSkills] = useState<Skill[]>([]);
  const [title, setTitle] = useState('');
  const [summary, setSummary] = useState('');
  const [description, setDescription] = useState('');
  const [kind, setKind] = useState<ProjectKind>('D_PERSONAL');
  const [expectedOutput, setExpectedOutput] = useState('');
  const [difficulty, setDifficulty] = useState(3);
  const [workStyle, setWorkStyle] = useState<WorkStyle>('TEAM');
  const [teamMin, setTeamMin] = useState(1);
  const [teamMax, setTeamMax] = useState(3);
  const [hours, setHours] = useState('8');
  const [tags, setTags] = useState('');
  const [selectedSkills, setSelectedSkills] = useState<Record<string, number>>({});
  const [milestones, setMilestones] = useState<MilestoneDraft[]>([{ ...EMPTY_MILESTONE }]);
  const [cityWorkflow, setCityWorkflow] = useState(false);
  const [startsOn, setStartsOn] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const roles = readSession()?.user.roles ?? [];
  const canCreateManaged = roles.some((role) => MANAGED_ROLES.includes(role));

  useEffect(() => {
    fetchSkills()
      .then((list) => setSkills(list.items))
      .catch(() => undefined);
  }, []);

  const filledMilestones = milestones.filter((milestone) => milestone.title_fa.trim());
  // الگوی شهر هوشمند هشت مرحلهٔ ثابتش را خودش می‌سازد (ADR-0016).
  const useCity = kind === 'C_PROBLEM' && cityWorkflow;
  const skillCount = Object.keys(selectedSkills).length;
  const ready =
    title.trim().length >= 3 &&
    summary.trim().length >= 10 &&
    description.trim().length >= 10 &&
    expectedOutput.trim().length >= 3 &&
    skillCount > 0 &&
    (useCity || filledMilestones.length > 0);

  function toggleSkill(id: string) {
    setSelectedSkills((current) => {
      const next = { ...current };
      if (id in next) delete next[id];
      else next[id] = 3;
      return next;
    });
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!accessToken || !ready) return;
    setBusy(true);
    setError(null);
    try {
      const project = await createProject(
        {
          title_fa: title.trim(),
          summary: summary.trim(),
          description: description.trim(),
          kind,
          expected_output: expectedOutput.trim(),
          difficulty,
          work_style: workStyle,
          team_size_min: teamMin,
          team_size_max: Math.max(teamMin, teamMax),
          time_commitment_hpw: hours.trim() ? Number(hours) : null,
          tags: tags
            .split('،')
            .flatMap((part) => part.split(','))
            .map((part) => part.trim())
            .filter(Boolean)
            .slice(0, 10),
          rewards: {},
          starts_on: useCity && startsOn ? startsOn : null,
          deadline_on: null,
          applications_close_at: null,
          required_skills: Object.entries(selectedSkills).map(([skill_id, min_level]) => ({
            skill_id,
            min_level,
            weight: 1,
            is_teachable: false,
          })),
          required_assets: [],
          interests: [],
          roles: [],
          workflow: useCity ? 'CITY' : null,
        },
        accessToken,
      );

      // مرحله‌ها پس از ساخت پروژه ثبت می‌شوند: قرارداد §5.7 برای هر
      // مرحله یک درخواست جدا دارد و ترتیبشان مهم است.
      for (const [index, milestone] of (useCity ? [] : filledMilestones).entries()) {
        await createMilestone(
          project.id,
          {
            title_fa: milestone.title_fa.trim(),
            description: milestone.description.trim() || null,
            sort_order: index + 1,
            points: milestone.points.trim() ? Number(milestone.points) : 0,
            due_on: milestone.due_on || null,
          },
          accessToken,
        );
      }

      router.push(`/projects/${project.id}/workspace`);
    } catch (cause) {
      setError(messageFor(cause));
      setBusy(false);
    }
  }

  if (sessionLoading) return null;

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-6">
      <Card className="flex flex-col gap-4">
        <CardTitle>پروژه چیست؟</CardTitle>

        <Input
          label="عنوان"
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          maxLength={200}
          required
        />

        <Textarea
          label="خلاصه"
          hint="یک یا دو جمله؛ همین در کارت پروژه دیده می‌شود."
          value={summary}
          onChange={(event) => setSummary(event.target.value)}
          maxLength={280}
          rows={2}
          required
        />

        <Textarea
          label="شرح کامل"
          hint="دانشجو بر اساس همین تصمیم می‌گیرد: مسئله چیست، کار چیست، نتیجه چه می‌شود."
          value={description}
          onChange={(event) => setDescription(event.target.value)}
          rows={6}
          required
        />

        <Textarea
          label="در پایان چه تحویل می‌شود؟"
          hint="مقاله؟ فروش؟ نرم‌افزار؟ گزارش؟"
          value={expectedOutput}
          onChange={(event) => setExpectedOutput(event.target.value)}
          maxLength={1000}
          rows={2}
          required
        />
      </Card>

      <Card className="flex flex-col gap-4">
        <CardTitle>نوع و شرایط</CardTitle>

        <fieldset className="flex flex-col gap-2">
          <legend className="text-[13.5px] font-medium text-[var(--fg-primary)]">نوع پروژه</legend>
          <div className="grid gap-2 sm:grid-cols-2">
            {KINDS.map((option) => {
              const locked = option.value !== 'D_PERSONAL' && !canCreateManaged;
              return (
                <label
                  key={option.value}
                  className={`flex cursor-pointer flex-col gap-0.5 rounded-[var(--radius-md)] border p-3 ${
                    kind === option.value
                      ? 'border-[var(--brand-500)] bg-[var(--brand-50)]'
                      : 'border-[var(--border-default)]'
                  } ${locked ? 'opacity-60' : ''}`}
                >
                  <span className="flex items-center gap-2 text-[14px] font-medium text-[var(--fg-primary)]">
                    <input
                      type="radio"
                      name="kind"
                      checked={kind === option.value}
                      onChange={() => setKind(option.value)}
                      disabled={locked}
                      className="sr-only"
                    />
                    {option.label}
                    {locked && <Badge tone="neutral">دسترسی ندارید</Badge>}
                  </span>
                  <span className="text-[12.5px] text-[var(--fg-tertiary)]">{option.hint}</span>
                </label>
              );
            })}
          </div>
        </fieldset>

        {kind === 'C_PROBLEM' && (
          <div className="flex flex-col gap-3 rounded-[var(--radius-md)] border border-[var(--border-subtle)] p-3">
            <label className="flex items-start gap-2 text-[14px]">
              <input
                type="checkbox"
                className="mt-1.5"
                checked={cityWorkflow}
                onChange={(event) => setCityWorkflow(event.target.checked)}
              />
              <span>
                <span className="font-medium">با الگوی گردش‌کار شهر هوشمند</span>
                <span className="block text-[12.5px] text-[var(--fg-tertiary)]">
                  هشت مرحلهٔ ثابت از انتخاب محدوده تا داشبورد شهرداری، هرکدام با چک‌لیست کیفیت و
                  مسئول — مراحل را خودت تعریف نمی‌کنی.
                </span>
              </span>
            </label>
            {cityWorkflow && (
              <Input
                label="تاریخ شروع"
                hint="مهلت هر هشت مرحله از همین تاریخ حساب می‌شود (۱۶ هفته)."
                type="date"
                value={startsOn}
                onChange={(event) => setStartsOn(event.target.value)}
                forceLtr
              />
            )}
          </div>
        )}

        <div className="grid gap-4 sm:grid-cols-2">
          <label className="flex flex-col gap-1.5">
            <span className="text-[13.5px] font-medium text-[var(--fg-primary)]">سبک کار</span>
            <select
              value={workStyle}
              onChange={(event) => setWorkStyle(event.target.value as WorkStyle)}
              className="h-11 rounded-[var(--radius-md)] border border-[var(--border-default)] bg-[var(--bg-surface)] px-3 text-[14px]"
            >
              {WORK_STYLES.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>

          <label className="flex flex-col gap-1.5">
            <span className="text-[13.5px] font-medium text-[var(--fg-primary)]">
              دشواری: {toPersianDigits(difficulty)} از ۵
            </span>
            <input
              type="range"
              min={1}
              max={5}
              value={difficulty}
              onChange={(event) => setDifficulty(Number(event.target.value))}
              className="h-11"
            />
          </label>

          <Input
            label="اندازهٔ حداقل تیم"
            type="number"
            min={1}
            max={20}
            value={teamMin}
            onChange={(event) => setTeamMin(Number(event.target.value) || 1)}
          />

          <Input
            label="اندازهٔ حداکثر تیم"
            hint="مدیر پروژه هم در این عدد حساب می‌شود."
            type="number"
            min={1}
            max={20}
            value={teamMax}
            onChange={(event) => setTeamMax(Number(event.target.value) || 1)}
          />

          <Input
            label="ساعت در هفته"
            type="number"
            min={1}
            max={60}
            value={hours}
            onChange={(event) => setHours(event.target.value)}
          />

          <Input
            label="برچسب‌ها"
            hint="با ویرگول جدا کن."
            value={tags}
            onChange={(event) => setTags(event.target.value)}
          />
        </div>
      </Card>

      <Card className="flex flex-col gap-3">
        <div className="flex flex-col gap-1">
          <CardTitle>مهارت‌های لازم</CardTitle>
          <CardDescription>
            بدون دست‌کم یک مهارت، توصیه‌گر نمی‌داند این پروژه را به چه کسی پیشنهاد بدهد —
            و پروژه منتشر نمی‌شود.
          </CardDescription>
        </div>

        <div className="flex flex-wrap gap-1.5">
          {skills.map((skill) => {
            const selected = skill.id in selectedSkills;
            return (
              <button
                key={skill.id}
                type="button"
                onClick={() => toggleSkill(skill.id)}
                aria-pressed={selected}
                className={`rounded-[var(--radius-full)] border px-3 py-1 text-[13px] ${
                  selected
                    ? 'border-[var(--brand-500)] bg-[var(--brand-50)] text-[var(--brand-700)]'
                    : 'border-[var(--border-default)] text-[var(--fg-secondary)]'
                }`}
              >
                {skill.title_fa}
              </button>
            );
          })}
        </div>

        {Object.entries(selectedSkills).map(([skillId, level]) => {
          const skill = skills.find((item) => item.id === skillId);
          if (!skill) return null;
          return (
            <label key={skillId} className="flex items-center gap-3 text-[13.5px]">
              <span className="w-32 shrink-0 text-[var(--fg-primary)]">{skill.title_fa}</span>
              <input
                type="range"
                min={1}
                max={5}
                value={level}
                onChange={(event) =>
                  setSelectedSkills((current) => ({
                    ...current,
                    [skillId]: Number(event.target.value),
                  }))
                }
                className="flex-1"
              />
              <span className="w-24 text-[12.5px] text-[var(--fg-tertiary)]">
                حداقل سطح {toPersianDigits(level)}
              </span>
            </label>
          );
        })}
      </Card>

      {!useCity && (
      <Card className="flex flex-col gap-4">
        <div className="flex flex-col gap-1">
          <CardTitle>مراحل</CardTitle>
          <CardDescription>
            هر مرحله یک تحویل‌دادنی دارد. دست‌کم یکی لازم است تا پروژه قابل انتشار باشد.
          </CardDescription>
        </div>

        {milestones.map((milestone, index) => (
          <div key={index} className="flex flex-col gap-3 rounded-[var(--radius-md)] border border-[var(--border-subtle)] p-4">
            <Input
              label={`مرحلهٔ ${toPersianDigits(index + 1)}`}
              value={milestone.title_fa}
              onChange={(event) =>
                setMilestones((current) =>
                  current.map((item, itemIndex) =>
                    itemIndex === index ? { ...item, title_fa: event.target.value } : item,
                  ),
                )
              }
              maxLength={200}
            />
            <Textarea
              label="شرح"
              value={milestone.description}
              onChange={(event) =>
                setMilestones((current) =>
                  current.map((item, itemIndex) =>
                    itemIndex === index ? { ...item, description: event.target.value } : item,
                  ),
                )
              }
              rows={2}
            />
            <div className="grid gap-3 sm:grid-cols-2">
              <Input
                label="بارم امتیاز"
                type="number"
                min={0}
                value={milestone.points}
                onChange={(event) =>
                  setMilestones((current) =>
                    current.map((item, itemIndex) =>
                      itemIndex === index ? { ...item, points: event.target.value } : item,
                    ),
                  )
                }
              />
              <label className="flex flex-col gap-1.5">
                <span className="text-[13.5px] font-medium text-[var(--fg-primary)]">مهلت</span>
                <input
                  type="date"
                  value={milestone.due_on}
                  onChange={(event) =>
                    setMilestones((current) =>
                      current.map((item, itemIndex) =>
                        itemIndex === index ? { ...item, due_on: event.target.value } : item,
                      ),
                    )
                  }
                  className="h-11 rounded-[var(--radius-md)] border border-[var(--border-default)] bg-[var(--bg-surface)] px-3 text-[14px]"
                />
              </label>
            </div>
            {milestones.length > 1 && (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="self-start"
                onClick={() =>
                  setMilestones((current) => current.filter((_, i) => i !== index))
                }
              >
                حذف این مرحله
              </Button>
            )}
          </div>
        ))}

        <Button
          type="button"
          variant="secondary"
          size="sm"
          className="self-start"
          onClick={() => setMilestones((current) => [...current, { ...EMPTY_MILESTONE }])}
        >
          افزودن مرحله
        </Button>
      </Card>
      )}

      {error && (
        <p role="alert" className="text-[14px] text-[var(--danger-600)]">
          {error}
        </p>
      )}

      <div className="flex flex-col gap-2">
        <Button type="submit" size="lg" loading={busy} disabled={!ready}>
          ساخت پروژه
        </Button>
        <p className="text-[12.5px] text-[var(--fg-tertiary)]">
          پروژه به‌صورت پیش‌نویس ساخته می‌شود؛ تا وقتی منتشرش نکنی در بانک پروژه دیده نمی‌شود.
        </p>
      </div>
    </form>
  );
}

function messageFor(cause: unknown): string {
  if (cause instanceof ApiError || cause instanceof NetworkError) return cause.message;
  return 'پروژه ساخته نشد. کمی بعد دوباره تلاش کن.';
}
