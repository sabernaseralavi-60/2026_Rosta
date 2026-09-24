'use client';

import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';

import { Badge, type BadgeTone } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card, CardDescription, CardTitle } from '@/components/ui/Card';
import { ChipGroup, type ChipOption } from '@/components/ui/ChipGroup';
import { EmptyState } from '@/components/ui/EmptyState';
import { Input } from '@/components/ui/Input';
import { SkeletonCard } from '@/components/ui/Skeleton';
import { Textarea } from '@/components/ui/Textarea';
import { ApiError, NetworkError } from '@/lib/api/client';
import { type Skill, fetchSkills } from '@/lib/api/taxonomy';
import {
  type EffectiveOpeningStatus,
  type ManagedTeam,
  type MyApplication,
  type Opening,
  type TargetKind,
  createOpening,
  fetchManagedTeams,
  fetchMyOpeningApplications,
  fetchOpenings,
} from '@/lib/api/teams';
import { useSession } from '@/lib/auth/use-session';
import { formatDateLong } from '@/lib/format/date';
import { toPersianDigits } from '@/lib/format/digits';

/**
 * `/teams/openings` — آگهی نیاز به هم‌تیمی، FR-TEAM-02.
 *
 * آگهی مال تیم یک پروژه یا کسب‌وکار است؛ دکمهٔ «ثبت آگهی» فقط برای کسی
 * پیدا می‌شود که تیمی را مدیریت می‌کند. با ثبت، سرور دانشجویان هم‌خوان را
 * خبردار می‌کند. آگهی ۳۰ روز باز می‌ماند و تمدیدپذیر است.
 */

const SEARCH_DEBOUNCE_MS = 350;

type Filter = '' | TargetKind | 'MINE';

const FILTERS: ChipOption<Filter>[] = [
  { value: '', label: 'همه' },
  { value: 'PROJECT', label: 'پروژه' },
  { value: 'VENTURE', label: 'کسب‌وکار' },
  { value: 'MINE', label: 'آگهی‌های من' },
];

export const OPENING_TONE: Record<EffectiveOpeningStatus, BadgeTone> = {
  OPEN: 'success',
  FILLED: 'brand',
  CLOSED: 'neutral',
  EXPIRED: 'warning',
};

export function OpeningsView() {
  const { accessToken, loading: sessionLoading } = useSession();
  const [openings, setOpenings] = useState<Opening[] | null>(null);
  const [total, setTotal] = useState(0);
  const [filter, setFilter] = useState<Filter>('');
  const [query, setQuery] = useState('');
  const [teams, setTeams] = useState<ManagedTeam[]>([]);
  const [applications, setApplications] = useState<MyApplication[]>([]);
  const [posting, setPosting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  const reload = useCallback(() => setReloadKey((key) => key + 1), []);

  useEffect(() => {
    if (sessionLoading || !accessToken) return;
    fetchManagedTeams(accessToken)
      .then(setTeams)
      .catch(() => setTeams([]));
    fetchMyOpeningApplications(accessToken)
      .then(setApplications)
      .catch(() => setApplications([]));
  }, [accessToken, sessionLoading, reloadKey]);

  useEffect(() => {
    if (sessionLoading) return;
    let cancelled = false;
    const timer = setTimeout(() => {
      fetchOpenings(
        {
          ...(filter === 'MINE' ? { mine: true } : filter ? { kind: filter } : {}),
          ...(query.trim() ? { q: query.trim() } : {}),
        },
        accessToken,
      )
        .then((page) => {
          if (cancelled) return;
          setOpenings(page.items);
          setTotal(page.total);
          setError(null);
        })
        .catch((cause) => {
          if (cancelled) return;
          setError(messageFor(cause));
          setOpenings([]);
        });
    }, SEARCH_DEBOUNCE_MS);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [filter, query, accessToken, sessionLoading, reloadKey]);

  const pending = applications.filter((a) => a.status === 'PENDING');

  return (
    <div className="flex flex-col gap-8">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="flex flex-col gap-1">
          <h1>آگهی‌های هم‌تیمی</h1>
          <p className="text-[15px] text-[var(--fg-secondary)]">
            تیم‌هایی که یک نقش خالی دارند. درخواست بده، یا برای تیم خودت آگهی ثبت کن.
          </p>
        </div>
        <div className="flex gap-2">
          <Button asChild variant="secondary">
            <Link href="/teams/find">جستجوی هم‌تیمی</Link>
          </Button>
          {teams.length > 0 && !posting && (
            <Button onClick={() => setPosting(true)}>ثبت آگهی</Button>
          )}
        </div>
      </header>

      {posting && accessToken && (
        <OpeningForm
          accessToken={accessToken}
          teams={teams}
          onDone={() => {
            setPosting(false);
            setFilter('MINE');
            reload();
          }}
          onCancel={() => setPosting(false)}
        />
      )}

      {pending.length > 0 && (
        <section className="flex flex-col gap-3" aria-labelledby="my-apps">
          <h2 id="my-apps" className="text-[18px] font-semibold">
            درخواست‌های باز من
          </h2>
          <ul className="flex flex-col gap-2">
            {pending.map((app) => (
              <li key={app.id}>
                <Card className="flex flex-wrap items-center justify-between gap-2">
                  <Link
                    href={`/teams/openings/${app.opening_id}`}
                    className="text-[14.5px] font-medium hover:text-[var(--fg-brand)]"
                  >
                    {app.opening_title} — {app.target.title}
                  </Link>
                  <Badge tone="warning">{app.status_fa}</Badge>
                </Card>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="flex flex-col gap-4">
        <Input
          label="جستجو"
          hint="نقش یا شرح آگهی"
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        <ChipGroup label="فیلتر آگهی" options={FILTERS} value={filter} onChange={setFilter} />
        {error && (
          <p role="alert" className="text-[13.5px] text-[var(--fg-danger)]">
            {error}
          </p>
        )}
        {openings === null ? (
          <SkeletonCard label="در حال بارگذاری آگهی‌ها" />
        ) : openings.length === 0 ? (
          <EmptyState
            title="آگهی بازی نیست"
            description="اگر تیمی را مدیریت می‌کنی، اولین آگهی را ثبت کن."
          />
        ) : (
          <>
            <p className="text-[13px] text-[var(--fg-tertiary)]">{toPersianDigits(total)} آگهی</p>
            <ul className="grid gap-4 md:grid-cols-2">
              {openings.map((opening) => (
                <li key={opening.id}>
                  <OpeningCard opening={opening} />
                </li>
              ))}
            </ul>
          </>
        )}
      </section>
    </div>
  );
}

function OpeningCard({ opening }: { opening: Opening }) {
  return (
    <Card variant="interactive" className="flex h-full flex-col gap-3">
      <div className="flex flex-wrap items-center gap-1.5">
        <Badge tone={OPENING_TONE[opening.effective_status]}>{opening.status_fa}</Badge>
        <Badge tone={opening.target.kind === 'VENTURE' ? 'accent' : 'neutral'}>
          {opening.target.kind === 'VENTURE' ? 'کسب‌وکار' : 'پروژه'}
        </Badge>
        {opening.has_applied && <Badge tone="info">درخواست داده‌ای</Badge>}
      </div>
      <Link
        href={`/teams/openings/${opening.id}`}
        className="text-[16px] font-semibold text-[var(--fg-primary)] hover:text-[var(--fg-brand)]"
      >
        {opening.title}
      </Link>
      <p className="text-[13.5px] text-[var(--fg-secondary)]">{opening.target.title}</p>
      <p className="line-clamp-2 text-[14px] leading-[1.9] text-[var(--fg-secondary)]">
        {opening.description}
      </p>
      {opening.needed_skills.length > 0 && (
        <ul className="flex flex-wrap gap-1.5">
          {opening.needed_skills.map((skill) => (
            <li key={skill.id}>
              <Badge tone="neutral">{skill.title_fa}</Badge>
            </li>
          ))}
        </ul>
      )}
      <p className="mt-auto text-[12.5px] text-[var(--fg-tertiary)]">
        {opening.commitment_hpw && `${toPersianDigits(opening.commitment_hpw)} ساعت در هفته · `}
        تا {formatDateLong(opening.expires_at)}
        {opening.pending_count !== null &&
          ` · ${toPersianDigits(opening.pending_count)} درخواست در انتظار`}
      </p>
    </Card>
  );
}

function OpeningForm({
  accessToken,
  teams,
  onDone,
  onCancel,
}: {
  accessToken: string;
  teams: ManagedTeam[];
  onDone: () => void;
  onCancel: () => void;
}) {
  const [skills, setSkills] = useState<Skill[]>([]);
  const [teamKey, setTeamKey] = useState(`${teams[0]?.kind}:${teams[0]?.id}`);
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [needed, setNeeded] = useState<string[]>([]);
  const [hours, setHours] = useState('');
  const [roleId, setRoleId] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchSkills()
      .then((list) => setSkills(list.items))
      .catch(() => setSkills([]));
  }, []);

  const [kind, teamId] = teamKey.split(':') as [TargetKind, string];
  const team = teams.find((t) => t.id === teamId);

  function toggle(id: string) {
    setNeeded((prev) =>
      prev.includes(id) ? prev.filter((s) => s !== id) : prev.length < 10 ? [...prev, id] : prev,
    );
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await createOpening(accessToken, {
        ...(kind === 'PROJECT' ? { project_id: teamId } : { venture_id: teamId }),
        title: title.trim(),
        description: description.trim(),
        needed_skill_ids: needed,
        commitment_hpw: hours ? Number(hours) : null,
        role_id: roleId || null,
      });
      onDone();
    } catch (cause) {
      setError(messageFor(cause));
    } finally {
      setBusy(false);
    }
  }

  const selectClass =
    'h-10 rounded-[var(--radius-md)] border border-[var(--border-default)] bg-[var(--bg-surface)] px-3 text-[14px]';

  return (
    <Card variant="raised" className="flex flex-col gap-4">
      <CardTitle>آگهی نیاز به هم‌تیمی</CardTitle>
      <CardDescription>
        دانشجویانی که مهارت لازم را در سطح ۳ به بالا دارند، اعلان می‌گیرند.
      </CardDescription>
      <form onSubmit={handleSubmit} className="flex flex-col gap-3">
        <div className="flex flex-col gap-1.5">
          <label htmlFor="opening-team" className="text-[13.5px] font-medium">
            برای تیم
          </label>
          <select
            id="opening-team"
            value={teamKey}
            onChange={(event) => {
              setTeamKey(event.target.value);
              setRoleId('');
            }}
            className={selectClass}
          >
            {teams.map((t) => (
              <option key={t.id} value={`${t.kind}:${t.id}`}>
                {t.kind === 'VENTURE' ? 'کسب‌وکار' : 'پروژه'} — {t.title}
              </option>
            ))}
          </select>
        </div>
        <Input
          label="نقش مورد نیاز"
          hint="مثلاً «تحلیلگر GIS» یا «بازاریاب آنلاین»"
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          maxLength={120}
          required
        />
        <Textarea
          label="شرح"
          hint="چه کاری باید انجام شود و چرا این نقش مهم است؟"
          value={description}
          onChange={(event) => setDescription(event.target.value)}
          maxLength={2000}
          rows={4}
          required
        />
        {team && team.roles.length > 0 && (
          <div className="flex flex-col gap-1.5">
            <label htmlFor="opening-role" className="text-[13.5px] font-medium">
              نقش پروژه (اختیاری)
            </label>
            <select
              id="opening-role"
              value={roleId}
              onChange={(event) => setRoleId(event.target.value)}
              className={selectClass}
            >
              <option value="">بدون نقش مشخص</option>
              {team.roles.map((role) => (
                <option key={role.id} value={role.id}>
                  {role.title}
                </option>
              ))}
            </select>
          </div>
        )}
        <Input
          label="تعهد زمانی (ساعت در هفته، اختیاری)"
          value={hours}
          onChange={(event) => setHours(event.target.value.replace(/[^0-9]/g, ''))}
          inputMode="numeric"
        />
        <fieldset className="flex flex-col gap-2">
          <legend className="mb-1 text-[13.5px] font-medium">مهارت‌های لازم</legend>
          <div className="flex flex-wrap gap-2">
            {skills.map((skill) => (
              <button
                key={skill.id}
                type="button"
                aria-pressed={needed.includes(skill.id)}
                onClick={() => toggle(skill.id)}
                className={
                  needed.includes(skill.id)
                    ? 'h-8 rounded-[var(--radius-full)] border border-[var(--brand-600)] bg-[var(--brand-50)] px-3 text-[13px] text-[var(--fg-brand)]'
                    : 'h-8 rounded-[var(--radius-full)] border border-[var(--border-default)] px-3 text-[13px] text-[var(--fg-secondary)]'
                }
              >
                {skill.title_fa}
              </button>
            ))}
          </div>
        </fieldset>
        {error && (
          <p role="alert" className="text-[13.5px] text-[var(--fg-danger)]">
            {error}
          </p>
        )}
        <div className="flex gap-2">
          <Button type="submit" loading={busy}>
            ثبت آگهی
          </Button>
          <Button type="button" variant="ghost" onClick={onCancel}>
            انصراف
          </Button>
        </div>
      </form>
    </Card>
  );
}

function messageFor(cause: unknown): string {
  if (cause instanceof ApiError || cause instanceof NetworkError) return cause.message;
  return 'کار انجام نشد. کمی بعد دوباره تلاش کن.';
}
