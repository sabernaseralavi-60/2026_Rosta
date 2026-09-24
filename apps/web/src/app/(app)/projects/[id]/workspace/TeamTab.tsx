'use client';

import { useState } from 'react';

import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { ApiError, NetworkError } from '@/lib/api/client';
import { type Team, leaveTeam, removeMember } from '@/lib/api/workspace';
import { formatDateLong } from '@/lib/format/date';
import { toPersianDigits } from '@/lib/format/digits';

/**
 * تیم پروژه — FR-TEAM-03.
 *
 * حذف عضو و ترک تیم هر دو **دلیل اجباری** دارند. کسی که از تیم کنار
 * گذاشته می‌شود حق دارد بداند چرا؛ و مدیری که باید دلیل بنویسد، کمتر
 * بی‌دلیل حذف می‌کند.
 */

export function TeamTab({
  projectId,
  team,
  currentUserId,
  canRemove,
  accessToken,
  onChanged,
}: {
  projectId: string;
  team: Team;
  currentUserId: string | null;
  canRemove: boolean;
  accessToken: string;
  onChanged: () => void;
}) {
  const [error, setError] = useState<string | null>(null);
  const active = team.members.filter((member) => member.status === 'ACTIVE');
  const past = team.members.filter((member) => member.status !== 'ACTIVE');
  const me = active.find((member) => member.user_id === currentUserId);

  async function handleRemove(userId: string) {
    const reason = window.prompt('دلیل حذف این عضو چیست؟ (برای خودِ او نوشته می‌شود)');
    if (!reason || reason.trim().length < 3) return;
    setError(null);
    try {
      await removeMember(projectId, userId, reason.trim(), accessToken);
      onChanged();
    } catch (cause) {
      setError(messageFor(cause));
    }
  }

  async function handleLeave() {
    const reason = window.prompt('چرا این تیم را ترک می‌کنی؟');
    if (!reason || reason.trim().length < 3) return;
    setError(null);
    try {
      await leaveTeam(projectId, reason.trim(), accessToken);
      onChanged();
    } catch (cause) {
      setError(messageFor(cause));
    }
  }

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center gap-2 text-[13.5px] text-[var(--fg-secondary)]">
        <span>{team.name}</span>
        <Badge tone="neutral">{toPersianDigits(team.active_members)} عضو فعال</Badge>
        <Badge tone={team.open_seats > 0 ? 'success' : 'neutral'}>
          {team.open_seats > 0 ? `${toPersianDigits(team.open_seats)} جای خالی` : 'ظرفیت تکمیل'}
        </Badge>
      </div>

      {error && (
        <p role="alert" className="text-[13px] text-[var(--fg-danger)]">
          {error}
        </p>
      )}

      <ul className="flex flex-col gap-2">
        {active.map((member) => (
          <li key={member.user_id}>
            <Card className="flex flex-wrap items-center justify-between gap-3 p-4">
              <div className="flex flex-col gap-0.5">
                <div className="flex items-center gap-2">
                  <span className="text-[14.5px] font-medium text-[var(--fg-primary)]">
                    {member.full_name ?? member.username ?? 'عضو تیم'}
                  </span>
                  {member.is_lead && <Badge tone="brand">مدیر پروژه</Badge>}
                  {member.role_title_fa && <Badge tone="accent">{member.role_title_fa}</Badge>}
                </div>
                <span className="text-[12.5px] text-[var(--fg-tertiary)]">
                  عضو از {formatDateLong(member.joined_at)}
                </span>
              </div>

              {canRemove && !member.is_lead && (
                <Button variant="ghost" size="sm" onClick={() => handleRemove(member.user_id)}>
                  حذف از تیم
                </Button>
              )}
            </Card>
          </li>
        ))}
      </ul>

      {past.length > 0 && (
        <details>
          <summary className="cursor-pointer text-[13.5px] font-medium text-[var(--fg-secondary)]">
            اعضای پیشین ({toPersianDigits(past.length)})
          </summary>
          <ul className="mt-2 flex flex-col gap-1.5">
            {past.map((member) => (
              <li
                key={member.user_id}
                className="flex flex-wrap items-center gap-2 text-[13px] text-[var(--fg-tertiary)]"
              >
                <span>{member.full_name ?? member.username ?? 'عضو پیشین'}</span>
                <Badge tone="neutral">
                  {member.status === 'LEFT' ? 'تیم را ترک کرد' : 'کنار گذاشته شد'}
                </Badge>
                {member.left_at && <span>{formatDateLong(member.left_at)}</span>}
              </li>
            ))}
          </ul>
        </details>
      )}

      {me && !me.is_lead && (
        <Button variant="secondary" size="sm" className="self-start" onClick={handleLeave}>
          ترک تیم
        </Button>
      )}
    </div>
  );
}

function messageFor(cause: unknown): string {
  if (cause instanceof ApiError || cause instanceof NetworkError) return cause.message;
  return 'انجام نشد. کمی بعد دوباره تلاش کن.';
}
