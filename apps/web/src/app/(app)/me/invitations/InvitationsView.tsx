'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useCallback, useEffect, useState } from 'react';

import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { SkeletonCard } from '@/components/ui/Skeleton';
import { ApiError, NetworkError } from '@/lib/api/client';
import {
  type Invitation,
  acceptInvitation,
  declineInvitation,
  fetchMyInvitations,
} from '@/lib/api/ventures';
import { useSession } from '@/lib/auth/use-session';
import { formatDeadline } from '@/lib/format/date';

/**
 * `/me/invitations` — FR-TEAM-03.
 *
 * دعوت ۱۴ روز اعتبار دارد و مهلتش کنار هر دعوت نشان داده می‌شود. پذیرفتن
 * کاربر را مستقیم به صفحهٔ پروژه یا کسب‌وکار می‌برد.
 */

const SOURCE_LABEL: Record<Invitation['source'], string | null> = {
  DIRECT: null,
  IDEA_PROMOTION: 'از ایدهٔ خودت',
  OPENING: 'پاسخ به آگهی',
};

export function InvitationsView() {
  const router = useRouter();
  const { accessToken, loading: sessionLoading } = useSession();
  const [items, setItems] = useState<Invitation[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(() => {
    if (sessionLoading || !accessToken) return;
    fetchMyInvitations(accessToken)
      .then(setItems)
      .catch((cause) => setError(messageFor(cause)));
  }, [accessToken, sessionLoading]);

  useEffect(load, [load]);

  async function answer(invitation: Invitation, accept: boolean) {
    if (!accessToken) return;
    setBusy(invitation.id);
    try {
      if (accept) {
        const result = await acceptInvitation(accessToken, invitation.id);
        router.push(result.href);
        return;
      }
      await declineInvitation(accessToken, invitation.id);
      load();
    } catch (cause) {
      setError(messageFor(cause));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-1">
        <h1>دعوت‌های من</h1>
        <p className="text-[15px] text-[var(--fg-secondary)]">
          کسی تو را به تیمش خوانده. پیش از پذیرفتن، صفحهٔ پروژه یا کسب‌وکار را ببین.
        </p>
      </header>
      {error && (
        <p role="alert" className="text-[13.5px] text-[var(--fg-danger)]">
          {error}
        </p>
      )}
      {items === null ? (
        !error && <SkeletonCard label="در حال بارگذاری دعوت‌ها" />
      ) : items.length === 0 ? (
        <EmptyState
          title="دعوت بازی نداری"
          description="وقتی کسی تو را به تیمش دعوت کند، اینجا می‌بینی. تا آن موقع، پروژه‌های باز را ببین."
          action={
            <Button asChild variant="secondary">
              <Link href="/projects">پروژه‌های باز</Link>
            </Button>
          }
        />
      ) : (
        <ul className="flex flex-col gap-4">
          {items.map((invitation) => {
            const deadline = formatDeadline(invitation.expires_at);
            const source = SOURCE_LABEL[invitation.source];
            return (
              <li key={invitation.id}>
                <Card className="flex flex-col gap-3">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <Badge tone={invitation.target_type === 'VENTURE' ? 'accent' : 'brand'}>
                      {invitation.target_type === 'VENTURE' ? 'کسب‌وکار' : 'پروژه'}
                    </Badge>
                    {source && <Badge tone="success">{source}</Badge>}
                    <Badge tone={deadline.isOverdue ? 'danger' : 'neutral'}>{deadline.label}</Badge>
                  </div>
                  <Link
                    href={invitation.href}
                    className="text-[16.5px] font-semibold hover:text-[var(--fg-brand)]"
                  >
                    {invitation.target_title}
                  </Link>
                  <p className="text-[13.5px] text-[var(--fg-secondary)]">
                    دعوت از {invitation.inviter_name ?? 'یک کاربر'}
                    {invitation.role_title && ` برای نقش «${invitation.role_title}»`}
                  </p>
                  {invitation.message && (
                    <p className="text-[14.5px] leading-[1.9]">«{invitation.message}»</p>
                  )}
                  <div className="flex gap-2">
                    <Button
                      size="sm"
                      loading={busy === invitation.id}
                      onClick={() => answer(invitation, true)}
                    >
                      می‌پذیرم
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      disabled={busy === invitation.id}
                      onClick={() => answer(invitation, false)}
                    >
                      نه، ممنون
                    </Button>
                  </div>
                </Card>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

function messageFor(cause: unknown): string {
  if (cause instanceof ApiError || cause instanceof NetworkError) return cause.message;
  return 'کار انجام نشد. کمی بعد دوباره تلاش کن.';
}
