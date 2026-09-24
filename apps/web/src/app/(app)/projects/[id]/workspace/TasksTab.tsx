'use client';

import { useState } from 'react';

import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { ApiError, NetworkError } from '@/lib/api/client';
import {
  type Milestone,
  type Task,
  type TaskStatus,
  type Team,
  createTask,
  deleteTask,
  updateTask,
} from '@/lib/api/workspace';
import { formatDateLong } from '@/lib/format/date';
import { toPersianDigits } from '@/lib/format/digits';

/**
 * تختهٔ وظایف — FR-PRJ-06، M2-10.
 *
 * سه ستون، بدون کشیدن و رها کردن. جابه‌جایی با دکمه انجام می‌شود:
 * drag-and-drop روی موبایل و با صفحه‌خوان کار نمی‌کند (§10.8) و ارزشش
 * را در فاز ۱ ندارد.
 *
 * هر عضو تیم هر وظیفه را جابه‌جا می‌کند، نه فقط مسئولش — این تختهٔ تیم
 * است، نه صندوق شخصی.
 */

const COLUMNS: { status: TaskStatus; title: string }[] = [
  { status: 'TODO', title: 'انجام نشده' },
  { status: 'DOING', title: 'در حال انجام' },
  { status: 'DONE', title: 'انجام شد' },
];

const NEXT: Record<TaskStatus, TaskStatus | null> = {
  TODO: 'DOING',
  DOING: 'DONE',
  DONE: null,
};

const PREVIOUS: Record<TaskStatus, TaskStatus | null> = {
  TODO: null,
  DOING: 'TODO',
  DONE: 'DOING',
};

export function TasksTab({
  projectId,
  tasks,
  team,
  milestones,
  accessToken,
  onChanged,
}: {
  projectId: string;
  tasks: Task[];
  team: Team | null;
  milestones: Milestone[];
  accessToken: string;
  onChanged: () => void;
}) {
  const [title, setTitle] = useState('');
  const [assignee, setAssignee] = useState('');
  const [milestoneId, setMilestoneId] = useState('');
  const [dueOn, setDueOn] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const members = team?.members.filter((member) => member.status === 'ACTIVE') ?? [];

  async function handleCreate(event: React.FormEvent) {
    event.preventDefault();
    if (!title.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await createTask(
        projectId,
        {
          title: title.trim(),
          assignee_id: assignee || null,
          milestone_id: milestoneId || null,
          due_on: dueOn || null,
        },
        accessToken,
      );
      setTitle('');
      setAssignee('');
      setMilestoneId('');
      setDueOn('');
      onChanged();
    } catch (cause) {
      setError(messageFor(cause));
    } finally {
      setBusy(false);
    }
  }

  async function move(task: Task, status: TaskStatus) {
    setError(null);
    try {
      await updateTask(
        projectId,
        task.id,
        {
          title: task.title,
          description: task.description,
          assignee_id: task.assignee_id,
          milestone_id: task.milestone_id,
          due_on: task.due_on,
          status,
          sort_order: task.sort_order,
        },
        accessToken,
      );
      onChanged();
    } catch (cause) {
      setError(messageFor(cause));
    }
  }

  async function remove(task: Task) {
    setError(null);
    try {
      await deleteTask(projectId, task.id, accessToken);
      onChanged();
    } catch (cause) {
      setError(messageFor(cause));
    }
  }

  return (
    <div className="flex flex-col gap-5">
      <Card className="flex flex-col gap-3">
        <form onSubmit={handleCreate} className="flex flex-col gap-3">
          <Input
            label="وظیفهٔ تازه"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            placeholder="مثلاً: تماس با ده مشتری"
            maxLength={200}
          />

          <div className="grid gap-3 sm:grid-cols-3">
            <label className="flex flex-col gap-1.5">
              <span className="text-[13.5px] font-medium text-[var(--fg-primary)]">مسئول</span>
              <select
                value={assignee}
                onChange={(event) => setAssignee(event.target.value)}
                className="h-11 rounded-[var(--radius-md)] border border-[var(--border-default)] bg-[var(--bg-surface)] px-3 text-[14px]"
              >
                <option value="">بدون مسئول</option>
                {members.map((member) => (
                  <option key={member.user_id} value={member.user_id}>
                    {member.full_name ?? member.username ?? 'عضو تیم'}
                  </option>
                ))}
              </select>
            </label>

            <label className="flex flex-col gap-1.5">
              <span className="text-[13.5px] font-medium text-[var(--fg-primary)]">مرحله</span>
              <select
                value={milestoneId}
                onChange={(event) => setMilestoneId(event.target.value)}
                className="h-11 rounded-[var(--radius-md)] border border-[var(--border-default)] bg-[var(--bg-surface)] px-3 text-[14px]"
              >
                <option value="">بدون مرحله</option>
                {milestones.map((milestone) => (
                  <option key={milestone.id} value={milestone.id}>
                    {milestone.title_fa}
                  </option>
                ))}
              </select>
            </label>

            <label className="flex flex-col gap-1.5">
              <span className="text-[13.5px] font-medium text-[var(--fg-primary)]">مهلت</span>
              <input
                type="date"
                value={dueOn}
                onChange={(event) => setDueOn(event.target.value)}
                className="h-11 rounded-[var(--radius-md)] border border-[var(--border-default)] bg-[var(--bg-surface)] px-3 text-[14px]"
              />
            </label>
          </div>

          <Button type="submit" size="sm" className="self-start" loading={busy}>
            افزودن
          </Button>
        </form>
      </Card>

      {error && (
        <p role="alert" className="text-[13px] text-[var(--fg-danger)]">
          {error}
        </p>
      )}

      <div className="grid gap-4 md:grid-cols-3">
        {COLUMNS.map((column) => {
          const items = tasks.filter((task) => task.status === column.status);
          return (
            <section key={column.status} className="flex flex-col gap-2">
              <h3 className="flex items-center gap-2 text-[14px] font-semibold text-[var(--fg-primary)]">
                {column.title}
                <span className="text-[12.5px] font-normal text-[var(--fg-tertiary)]">
                  {toPersianDigits(items.length)}
                </span>
              </h3>

              {items.length === 0 ? (
                <p className="rounded-[var(--radius-md)] border border-dashed border-[var(--border-subtle)] p-4 text-center text-[12.5px] text-[var(--fg-tertiary)]">
                  خالی
                </p>
              ) : (
                <ul className="flex flex-col gap-2">
                  {items.map((task) => (
                    <li key={task.id}>
                      <Card className="flex flex-col gap-2 p-4">
                        <p className="text-[14px] text-[var(--fg-primary)]">{task.title}</p>
                        <div className="flex flex-wrap gap-x-3 gap-y-1 text-[12px] text-[var(--fg-tertiary)]">
                          {task.assignee_name && <span>{task.assignee_name}</span>}
                          {task.due_on && <span>مهلت {formatDateLong(task.due_on)}</span>}
                        </div>
                        <div className="flex flex-wrap gap-1">
                          {PREVIOUS[task.status] && (
                            <Button
                              size="sm"
                              variant="ghost"
                              onClick={() => move(task, PREVIOUS[task.status]!)}
                            >
                              برگرداندن
                            </Button>
                          )}
                          {NEXT[task.status] && (
                            <Button
                              size="sm"
                              variant="ghost"
                              onClick={() => move(task, NEXT[task.status]!)}
                            >
                              بردن به «{COLUMNS.find((c) => c.status === NEXT[task.status])?.title}»
                            </Button>
                          )}
                          <Button size="sm" variant="ghost" onClick={() => remove(task)}>
                            حذف
                          </Button>
                        </div>
                      </Card>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          );
        })}
      </div>
    </div>
  );
}

function messageFor(cause: unknown): string {
  if (cause instanceof ApiError || cause instanceof NetworkError) return cause.message;
  return 'انجام نشد. کمی بعد دوباره تلاش کن.';
}
