'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';

import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { Input } from '@/components/ui/Input';
import { SkeletonCard } from '@/components/ui/Skeleton';
import { ApiError, NetworkError } from '@/lib/api/client';
import { updateProfile } from '@/lib/api/profile';
import { type Skill, fetchSkills } from '@/lib/api/taxonomy';
import {
  type ManagedTeam,
  type TeamSearch,
  type Teammate,
  fetchManagedTeams,
  inviteToProject,
  searchTeammates,
} from '@/lib/api/teams';
import { useSession } from '@/lib/auth/use-session';
import { toPersianDigits } from '@/lib/format/digits';

import { CompositionPanel } from './CompositionPanel';

/**
 * `/teams/find` — جستجوی هم‌تیمی، FR-TEAM-01، §8.14.
 *
 * با انتخاب یکی از پروژه‌هایم، نتیجه‌ها بر پایهٔ **مکملیت** مرتب می‌شوند:
 * «این فرد مهارتی دارد که تیم تو ندارد». بدون پروژه، هر نتیجه می‌گوید در
 * چه چیزی از خودم قوی‌تر است. فقط نیمرخ‌های عمومی پیدا می‌شوند — و اگر
 * نیمرخ خودم خصوصی است، همین‌جا با یک کلید عمومی‌اش می‌کنم.
 */

const SEARCH_DEBOUNCE_MS = 350;

export function FindTeammatesView() {
  const { accessToken, loading: sessionLoading } = useSession();
  const [skills, setSkills] = useState<Skill[]>([]);
  const [teams, setTeams] = useState<ManagedTeam[]>([]);
  const [skillId, setSkillId] = useState('');
  const [minLevel, setMinLevel] = useState('3');
  const [projectId, setProjectId] = useState('');
  const [query, setQuery] = useState('');
  const [result, setResult] = useState<TeamSearch | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    fetchSkills()
      .then((list) => setSkills(list.items))
      .catch(() => setSkills([]));
  }, []);

  useEffect(() => {
    if (sessionLoading || !accessToken) return;
    fetchManagedTeams(accessToken)
      .then((list) => setTeams(list.filter((team) => team.kind === 'PROJECT')))
      .catch(() => setTeams([]));
  }, [accessToken, sessionLoading]);

  useEffect(() => {
    if (sessionLoading || !accessToken) return;
    let cancelled = false;
    const timer = setTimeout(() => {
      searchTeammates(accessToken, {
        ...(skillId ? { skill_id: skillId, min_level: Number(minLevel) } : {}),
        ...(projectId ? { complement_project_id: projectId } : {}),
        ...(query.trim() ? { q: query.trim() } : {}),
      })
        .then((page) => {
          if (cancelled) return;
          setResult(page);
          setError(null);
        })
        .catch((cause) => {
          if (!cancelled) setError(messageFor(cause));
        });
    }, SEARCH_DEBOUNCE_MS);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [accessToken, sessionLoading, skillId, minLevel, projectId, query, reloadKey]);

  async function makePublic() {
    if (!accessToken) return;
    try {
      await updateProfile({ is_public: true }, accessToken);
      setReloadKey((key) => key + 1);
    } catch (cause) {
      setError(messageFor(cause));
    }
  }

  const selectClass =
    'h-10 rounded-[var(--radius-md)] border border-[var(--border-default)] bg-[var(--bg-surface)] px-3 text-[14px]';

  return (
    <div className="flex flex-col gap-8">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="flex flex-col gap-1">
          <h1>جستجوی هم‌تیمی</h1>
          <p className="text-[15px] text-[var(--fg-secondary)]">
            کسی را پیدا کن که مهارتی دارد که تیمت ندارد — نه کسی شبیه خودت.
          </p>
        </div>
        <Button asChild variant="secondary">
          <Link href="/teams/openings">آگهی‌های هم‌تیمی</Link>
        </Button>
      </header>

      {result && !result.context.my_profile_is_public && (
        <Card className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-[14px] leading-[1.9] text-[var(--fg-secondary)]">
            نیمرخ تو خصوصی است؛ دیگران در جستجو پیدایت نمی‌کنند. با عمومی کردنش نام، دانشگاه،
            مهارت‌ها و امکاناتت برای دانشجویان دیده می‌شود — شماره و ایمیلت هرگز.
          </p>
          <Button size="sm" onClick={makePublic}>
            نیمرخم عمومی شود
          </Button>
        </Card>
      )}

      <section className="grid gap-3 md:grid-cols-4" aria-label="فیلترها">
        {teams.length > 0 && (
          <div className="flex flex-col gap-1.5 md:col-span-4">
            <label htmlFor="team-context" className="text-[13.5px] font-medium">
              مکمل تیم کدام پروژه؟
            </label>
            <select
              id="team-context"
              value={projectId}
              onChange={(event) => setProjectId(event.target.value)}
              className={selectClass}
            >
              <option value="">هیچ‌کدام — مقایسه با خودم</option>
              {teams.map((team) => (
                <option key={team.id} value={team.id}>
                  {team.title}
                </option>
              ))}
            </select>
          </div>
        )}
        <div className="flex flex-col gap-1.5 md:col-span-2">
          <label htmlFor="skill-filter" className="text-[13.5px] font-medium">
            مهارت
          </label>
          <select
            id="skill-filter"
            value={skillId}
            onChange={(event) => setSkillId(event.target.value)}
            className={selectClass}
          >
            <option value="">هر مهارتی</option>
            {skills.map((skill) => (
              <option key={skill.id} value={skill.id}>
                {skill.title_fa}
              </option>
            ))}
          </select>
        </div>
        <div className="flex flex-col gap-1.5">
          <label htmlFor="min-level" className="text-[13.5px] font-medium">
            دست‌کم سطح
          </label>
          <select
            id="min-level"
            value={minLevel}
            onChange={(event) => setMinLevel(event.target.value)}
            disabled={!skillId}
            className={selectClass}
          >
            {[1, 2, 3, 4, 5].map((level) => (
              <option key={level} value={level}>
                {toPersianDigits(level)}
              </option>
            ))}
          </select>
        </div>
        <Input
          label="نام"
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
      </section>

      {result?.context.project && (
        <Card className="flex flex-col gap-2">
          <p className="text-[14px] font-semibold">کمبودهای تیم «{result.context.project.title}»</p>
          {result.context.gaps.length === 0 ? (
            <p className="text-[13.5px] text-[var(--fg-secondary)]">
              تیم همهٔ مهارت‌های لازم پروژه را دارد؛ نتیجه‌ها بدون عدد مکملیت‌اند.
            </p>
          ) : (
            <ul className="flex flex-wrap gap-1.5">
              {result.context.gaps.map((gap) => (
                <li key={gap.title_fa}>
                  <Badge tone="warning">
                    {gap.title_fa} · سطح {toPersianDigits(gap.min_level)}
                  </Badge>
                </li>
              ))}
            </ul>
          )}
        </Card>
      )}

      {result?.context.project && result.context.can_invite && accessToken && (
        <CompositionPanel projectId={result.context.project.id} accessToken={accessToken} />
      )}

      {error && (
        <p role="alert" className="text-[13.5px] text-[var(--fg-danger)]">
          {error}
        </p>
      )}
      {result === null ? (
        !error && <SkeletonCard label="در حال جستجو" />
      ) : result.items.length === 0 ? (
        <EmptyState
          title="کسی با این فیلتر پیدا نشد"
          description="فقط دانشجویانی که نیمرخشان را عمومی کرده‌اند در جستجو هستند. آگهی هم‌تیمی بده تا دانشجویان هم‌خوان خبردار شوند."
          action={
            <Button asChild>
              <Link href="/teams/openings">ثبت آگهی</Link>
            </Button>
          }
        />
      ) : (
        <>
          <p className="text-[13px] text-[var(--fg-tertiary)]">
            {toPersianDigits(result.total)} نفر
          </p>
          <ul className="grid gap-4 md:grid-cols-2">
            {result.items.map((mate) => (
              <li key={mate.user.id}>
                <TeammateCard
                  mate={mate}
                  projectId={result.context.can_invite ? result.context.project?.id : undefined}
                  accessToken={accessToken}
                />
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

function TeammateCard({
  mate,
  projectId,
  accessToken,
}: {
  mate: Teammate;
  projectId?: string;
  accessToken: string | null;
}) {
  const [invited, setInvited] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function invite() {
    if (!accessToken || !projectId || !mate.user.username) return;
    try {
      await inviteToProject(accessToken, projectId, mate.user.username);
      setInvited(true);
    } catch (cause) {
      setError(messageFor(cause));
    }
  }

  const reason = mate.complement_reason ?? mate.stronger_reason;

  return (
    <Card className="flex h-full flex-col gap-3">
      <div className="flex items-start justify-between gap-3">
        <div className="flex flex-col gap-0.5">
          <p className="text-[16px] font-semibold">{mate.user.display_name}</p>
          <p className="text-[12.5px] text-[var(--fg-tertiary)]">
            {[
              mate.user.university,
              mate.weekly_hours !== null
                ? `${toPersianDigits(mate.weekly_hours)} ساعت در هفته`
                : null,
            ]
              .filter(Boolean)
              .join(' · ')}
          </p>
        </div>
        {mate.complement_score !== null && (
          <div className="flex flex-col items-center" aria-label="امتیاز مکملیت">
            <span className="text-[20px] font-bold text-[var(--fg-brand)]">
              {toPersianDigits(Math.round(mate.complement_score))}
            </span>
            <span className="text-[11px] text-[var(--fg-tertiary)]">مکملیت</span>
          </div>
        )}
      </div>
      {reason && (
        <p className="rounded-[var(--radius-md)] bg-[var(--brand-50)] p-2.5 text-[13.5px] leading-[1.9] text-[var(--fg-brand)]">
          {reason}
        </p>
      )}
      {mate.bio && (
        <p className="line-clamp-2 text-[13.5px] leading-[1.9] text-[var(--fg-secondary)]">
          {mate.bio}
        </p>
      )}
      <ul className="flex flex-wrap gap-1.5" aria-label="مهارت‌ها">
        {mate.top_skills.map((skill) => (
          <li key={skill.skill_id}>
            <Badge tone={skill.verified ? 'success' : 'neutral'}>
              {skill.title_fa} {toPersianDigits(skill.level)}
              {skill.verified && ' ✓'}
            </Badge>
          </li>
        ))}
      </ul>
      {mate.assets.length > 0 && (
        <p className="text-[12.5px] text-[var(--fg-tertiary)]">امکانات: {mate.assets.join('، ')}</p>
      )}
      <div className="mt-auto flex flex-wrap items-center gap-2">
        {mate.shares_course && <Badge tone="info">درس مشترک</Badge>}
        {projectId && mate.user.username && (
          <Button size="sm" onClick={invite} disabled={invited}>
            {invited ? 'دعوت فرستاده شد' : 'دعوت به تیم'}
          </Button>
        )}
      </div>
      {error && (
        <p role="alert" className="text-[13px] text-[var(--fg-danger)]">
          {error}
        </p>
      )}
    </Card>
  );
}

function messageFor(cause: unknown): string {
  if (cause instanceof ApiError || cause instanceof NetworkError) return cause.message;
  return 'کار انجام نشد. کمی بعد دوباره تلاش کن.';
}
