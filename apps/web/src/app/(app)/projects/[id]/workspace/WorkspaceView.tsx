'use client';

import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';

import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card, CardDescription, CardTitle } from '@/components/ui/Card';
import { SkeletonCard, SkeletonText } from '@/components/ui/Skeleton';
import { ApiError, NetworkError } from '@/lib/api/client';
import { type ProjectDetail, fetchProject } from '@/lib/api/projects';
import {
  type Activity,
  type Message,
  type Milestone,
  type Task,
  type Team,
  fetchActivity,
  fetchMessages,
  fetchMilestones,
  fetchTasks,
  fetchTeam,
  transitionProject,
} from '@/lib/api/workspace';
import { readSession } from '@/lib/auth/session';
import { useSession } from '@/lib/auth/use-session';
import { cn } from '@/lib/cn';
import { toPersianDigits } from '@/lib/format/digits';

import { MetricsView } from '@/components/domain/MetricsView';

import { ActivityTab, DiscussionTab } from './DiscussionTab';
import { MilestonesTab } from './MilestonesTab';
import { ReflectionCard } from './ReflectionCard';
import { TasksTab } from './TasksTab';
import { TeamTab } from './TeamTab';

/**
 * `/projects/[id]/workspace` — §3.4 «فضای کاری پروژه».
 *
 * پنج بخش در یک صفحه با زبانه، نه پنج صفحهٔ جدا: عضو تیم در یک نشست کاری
 * بین مرحله و وظیفه و گفتگو می‌رود و می‌آید، و هر بار بارگذاری کامل
 * صفحه، کار را کُند می‌کند.
 *
 * دسترسی را **سرور** تعیین می‌کند: اگر کاربر عضو نباشد، هر پنج فراخوان
 * ۴۰۳ می‌گیرند و همین‌جا یک پیام روشن نمایش داده می‌شود. کلاینت درباره
 * نقش تصمیم نمی‌گیرد (§6.4).
 */

type TabKey = 'milestones' | 'team' | 'tasks' | 'discussion' | 'activity' | 'metrics';

const TABS: { key: TabKey; label: string }[] = [
  { key: 'milestones', label: 'مراحل' },
  { key: 'team', label: 'تیم' },
  { key: 'tasks', label: 'وظایف' },
  { key: 'discussion', label: 'گفتگو' },
  { key: 'activity', label: 'فعالیت' },
];

/** FR-VEN-02 — پروژهٔ کارآفرینی تماس، جلسه و فروش هر عضو را ثبت می‌کند. */
const VENTURE_TAB: { key: TabKey; label: string } = { key: 'metrics', label: 'فروش و فعالیت' };

const STATUS_TONES: Record<string, 'neutral' | 'success' | 'info' | 'warning'> = {
  DRAFT: 'neutral',
  OPEN: 'info',
  IN_PROGRESS: 'success',
  PAUSED: 'warning',
  COMPLETED: 'success',
  CANCELLED: 'neutral',
};

const STATUS_LABELS: Record<string, string> = {
  DRAFT: 'پیش‌نویس',
  OPEN: 'باز برای عضوگیری',
  IN_PROGRESS: 'در جریان',
  PAUSED: 'متوقف',
  COMPLETED: 'بسته شده',
  CANCELLED: 'لغو شده',
};

export function WorkspaceView({ id }: { id: string }) {
  const { accessToken, loading: sessionLoading } = useSession();

  const [tab, setTab] = useState<TabKey>('milestones');
  const [project, setProject] = useState<ProjectDetail | null>(null);
  const [milestones, setMilestones] = useState<Milestone[]>([]);
  const [team, setTeam] = useState<Team | null>(null);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [messages, setMessages] = useState<Message[]>([]);
  const [activity, setActivity] = useState<Activity[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [denied, setDenied] = useState(false);
  const [loading, setLoading] = useState(true);

  const currentUserId = readSession()?.user.id ?? null;

  const load = useCallback(async () => {
    if (!accessToken) return;
    try {
      const [detail, milestoneRows, teamData, taskRows, messageRows, activityRows] =
        await Promise.all([
          fetchProject(id, accessToken),
          fetchMilestones(id, accessToken),
          fetchTeam(id, accessToken),
          fetchTasks(id, accessToken),
          fetchMessages(id, accessToken),
          fetchActivity(id, accessToken),
        ]);
      setProject(detail);
      setMilestones(milestoneRows);
      setTeam(teamData);
      setTasks(taskRows);
      setMessages(messageRows);
      setActivity(activityRows);
      setError(null);
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 403) {
        setDenied(true);
      } else {
        setError(messageFor(cause));
      }
    } finally {
      setLoading(false);
    }
  }, [accessToken, id]);

  useEffect(() => {
    if (sessionLoading) return;
    void load();
  }, [load, sessionLoading]);

  if (denied) {
    return (
      <Card className="flex flex-col gap-3">
        <CardTitle as="h1">این فضای کاری برای تیم پروژه است</CardTitle>
        <CardDescription>
          برای دیدن مراحل، وظایف و گفتگو باید عضو تیم باشی. از صفحهٔ پروژه می‌توانی درخواست پیوستن
          بدهی.
        </CardDescription>
        <Button asChild variant="secondary" className="self-start">
          <Link href={`/projects/${id}`}>صفحهٔ پروژه</Link>
        </Button>
      </Card>
    );
  }

  if (loading || !project) {
    return (
      <div className="flex flex-col gap-4">
        <SkeletonText label="در حال بارگذاری فضای کاری" />
        <SkeletonCard />
      </div>
    );
  }

  // مدیر پروژه از `lead_id` شناخته می‌شود، نه فقط از عضویت تیم: پروژهٔ
  // `DRAFT` هنوز تیم ندارد (§7.12) و اگر فقط عضویت را ببینیم، سازنده
  // دکمهٔ «انتشار» پروژهٔ خودش را نمی‌بیند.
  const isLead =
    currentUserId !== null &&
    (project.lead_id === currentUserId ||
      team?.members.some(
        (member) =>
          member.user_id === currentUserId && member.is_lead && member.status === 'ACTIVE',
      ) === true);
  const isMember =
    currentUserId !== null &&
    team?.members.some(
      (member) => member.user_id === currentUserId && member.status === 'ACTIVE',
    ) === true;

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone={STATUS_TONES[project.status] ?? 'neutral'}>
            {STATUS_LABELS[project.status] ?? project.status}
          </Badge>
          <Badge tone="brand">{project.kind_fa}</Badge>
          {team && <Badge tone="neutral">{toPersianDigits(team.active_members)} عضو</Badge>}
        </div>
        <h1>{project.title_fa}</h1>
        <div className="flex flex-wrap gap-2">
          <Button asChild variant="ghost" size="sm">
            <Link href={`/projects/${id}`}>صفحهٔ عمومی پروژه</Link>
          </Button>
          {project.workflow === 'CITY' && (
            <Button asChild variant="secondary" size="sm">
              <Link href={`/projects/${id}/city`}>گردش‌کار شهر هوشمند</Link>
            </Button>
          )}
          <Button asChild variant="ghost" size="sm">
            <Link href={`/projects/${id}/files`}>کتابخانهٔ فایل</Link>
          </Button>
          {isLead && (
            <Button asChild variant="ghost" size="sm">
              <Link href={`/projects/${id}/applications`}>درخواست‌های پیوستن</Link>
            </Button>
          )}
        </div>
      </header>

      {isLead && <LeadActions project={project} accessToken={accessToken!} onChanged={load} />}

      {project.status === 'COMPLETED' && isMember && (
        <ReflectionCard projectId={id} accessToken={accessToken!} />
      )}

      {error && (
        <p role="alert" className="text-[13.5px] text-[var(--fg-danger)]">
          {error}
        </p>
      )}

      <div
        role="tablist"
        aria-label="بخش‌های فضای کاری"
        className="flex flex-wrap gap-1 border-b border-[var(--border-subtle)]"
      >
        {(project?.kind === 'A_VENTURE' ? [...TABS, VENTURE_TAB] : TABS).map((item) => (
          <button
            key={item.key}
            role="tab"
            type="button"
            aria-selected={tab === item.key}
            onClick={() => setTab(item.key)}
            className={cn(
              'relative -mb-px px-3 py-2 text-[14px] font-medium transition-colors',
              tab === item.key
                ? 'border-b-2 border-[var(--brand-600)] text-[var(--fg-brand)]'
                : 'text-[var(--fg-secondary)] hover:text-[var(--fg-primary)]',
            )}
          >
            {item.label}
          </button>
        ))}
      </div>

      <div role="tabpanel">
        {tab === 'milestones' && (
          <MilestonesTab
            projectId={id}
            milestones={milestones}
            canReview={isLead}
            isMember={isMember}
            accessToken={accessToken!}
            onChanged={load}
          />
        )}
        {tab === 'team' && team && (
          <TeamTab
            projectId={id}
            team={team}
            currentUserId={currentUserId}
            canRemove={isLead}
            accessToken={accessToken!}
            onChanged={load}
          />
        )}
        {tab === 'tasks' && (
          <TasksTab
            projectId={id}
            tasks={tasks}
            team={team}
            milestones={milestones}
            accessToken={accessToken!}
            onChanged={load}
          />
        )}
        {tab === 'discussion' && (
          <DiscussionTab
            projectId={id}
            messages={messages}
            currentUserId={currentUserId}
            isLead={isLead}
            accessToken={accessToken!}
            onChanged={load}
          />
        )}
        {tab === 'activity' && <ActivityTab activity={activity} />}
        {tab === 'metrics' && <MetricsView owner={{ kind: 'project', id }} embedded />}
      </div>
    </div>
  );
}

/**
 * گذارهای وضعیت پروژه — §7.4.
 *
 * فقط گذارهای **مجاز از وضعیت فعلی** نمایش داده می‌شوند. دکمهٔ غیرفعالی
 * که همیشه هست، کاربر را وادار می‌کند حدس بزند چرا کار نمی‌کند.
 */
function LeadActions({
  project,
  accessToken,
  onChanged,
}: {
  project: ProjectDetail;
  accessToken: string;
  onChanged: () => void;
}) {
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function run(
    action: 'publish' | 'start' | 'pause' | 'resume' | 'cancel' | 'complete',
    body?: Record<string, unknown>,
  ) {
    setBusy(action);
    setError(null);
    try {
      await transitionProject(project.id, action, accessToken, body);
      onChanged();
    } catch (cause) {
      setError(messageFor(cause));
    } finally {
      setBusy(null);
    }
  }

  function withReason(action: 'pause' | 'cancel', question: string): () => void {
    return () => {
      const reason = window.prompt(question);
      if (!reason || reason.trim().length < 3) return;
      void run(action, { reason: reason.trim() });
    };
  }

  function closeProject() {
    const report = window.prompt('گزارش نهایی پروژه را بنویس (دست‌کم ده نویسه):');
    if (!report || report.trim().length < 10) return;
    void run('complete', { final_report: report.trim() });
  }

  const actions: { key: string; label: string; onClick: () => void }[] = [];
  if (project.status === 'DRAFT') {
    actions.push({ key: 'publish', label: 'انتشار پروژه', onClick: () => void run('publish') });
  }
  if (project.status === 'OPEN') {
    actions.push({ key: 'start', label: 'شروع کار', onClick: () => void run('start') });
    actions.push({
      key: 'pause',
      label: 'توقف موقت',
      onClick: withReason('pause', 'دلیل توقف پروژه چیست؟'),
    });
  }
  if (project.status === 'IN_PROGRESS') {
    actions.push({ key: 'complete', label: 'بستن پروژه', onClick: closeProject });
    actions.push({
      key: 'pause',
      label: 'توقف موقت',
      onClick: withReason('pause', 'دلیل توقف پروژه چیست؟'),
    });
  }
  if (project.status === 'PAUSED') {
    actions.push({ key: 'resume', label: 'از سرگیری', onClick: () => void run('resume') });
  }
  if (!['COMPLETED', 'CANCELLED'].includes(project.status)) {
    actions.push({
      key: 'cancel',
      label: 'لغو پروژه',
      onClick: withReason('cancel', 'دلیل لغو پروژه چیست؟'),
    });
  }

  if (actions.length === 0) return null;

  return (
    <Card className="flex flex-col gap-2">
      <CardTitle>مدیریت پروژه</CardTitle>
      <div className="flex flex-wrap gap-2">
        {actions.map((action) => (
          <Button
            key={action.key}
            size="sm"
            variant={action.key === 'cancel' ? 'ghost' : 'secondary'}
            loading={busy === action.key}
            onClick={action.onClick}
          >
            {action.label}
          </Button>
        ))}
      </div>
      {error && (
        <p role="alert" className="text-[13px] text-[var(--fg-danger)]">
          {error}
        </p>
      )}
      {project.status === 'CANCELLED' && (
        <p className="text-[12.5px] text-[var(--fg-tertiary)]">
          امتیاز مراحل تأییدشده حفظ می‌شود؛ شکست پروژه تقصیر اعضا نیست.
        </p>
      )}
    </Card>
  );
}

function messageFor(cause: unknown): string {
  if (cause instanceof ApiError || cause instanceof NetworkError) return cause.message;
  return 'فضای کاری بارگذاری نشد. کمی بعد دوباره تلاش کن.';
}
