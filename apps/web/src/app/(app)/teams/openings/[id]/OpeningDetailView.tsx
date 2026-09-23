'use client';

import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';

import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card, CardTitle } from '@/components/ui/Card';
import { SkeletonCard } from '@/components/ui/Skeleton';
import { Textarea } from '@/components/ui/Textarea';
import { ApiError, NetworkError } from '@/lib/api/client';
import {
  type OpeningApplication,
  type OpeningDetail,
  applyToOpening,
  decideApplication,
  fetchOpening,
  openingAction,
  withdrawApplication,
} from '@/lib/api/teams';
import { useSession } from '@/lib/auth/use-session';
import { formatDateLong } from '@/lib/format/date';
import { toPersianDigits } from '@/lib/format/digits';

import { OPENING_TONE } from '../OpeningsView';

/**
 * `/teams/openings/[id]` — FR-TEAM-02/03.
 *
 * بیرونی درخواست می‌دهد یا درخواست بازش را پس می‌گیرد. مدیر تیم
 * درخواست‌ها را می‌بیند و یکی را می‌پذیرد — پذیرش، عضویت در تیم است و
 * بقیهٔ درخواست‌ها را خودکار با «این جای خالی پر شد» می‌بندد.
 */
export function OpeningDetailView({ id }: { id: string }) {
  const { accessToken, loading: sessionLoading } = useSession();
  const [opening, setOpening] = useState<OpeningDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    if (sessionLoading) return;
    fetchOpening(id, accessToken)
      .then(setOpening)
      .catch((cause) => setError(messageFor(cause)));
  }, [id, accessToken, sessionLoading]);

  useEffect(load, [load]);

  async function run(action: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await action();
      setMessage('');
      load();
    } catch (cause) {
      setError(messageFor(cause));
    } finally {
      setBusy(false);
    }
  }

  if (opening === null) {
    return error ? (
      <p role="alert" className="text-[13.5px] text-[var(--danger-600)]">
        {error}
      </p>
    ) : (
      <SkeletonCard label="در حال بارگذاری آگهی" />
    );
  }

  const open = opening.effective_status === 'OPEN';
  const mine = opening.my_application;

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-2">
        <Link
          href="/teams/openings"
          className="text-[13px] text-[var(--fg-tertiary)] hover:underline"
        >
          ← آگهی‌ها
        </Link>
        <div className="flex flex-wrap items-center gap-2">
          <h1>{opening.title}</h1>
          <Badge tone={OPENING_TONE[opening.effective_status]}>{opening.status_fa}</Badge>
        </div>
        <p className="text-[14px] text-[var(--fg-secondary)]">
          {opening.target.kind === 'VENTURE' ? 'کسب‌وکار' : 'پروژه'}:{' '}
          <Link href={opening.target.href} className="font-medium hover:text-[var(--brand-700)]">
            {opening.target.title}
          </Link>
          {opening.role && ` · نقش: ${opening.role.title}`}
        </p>
      </header>

      <Card className="flex flex-col gap-3">
        <p className="whitespace-pre-line text-[15px] leading-[2]">{opening.description}</p>
        {opening.needed_skills.length > 0 && (
          <ul className="flex flex-wrap gap-1.5" aria-label="مهارت‌های لازم">
            {opening.needed_skills.map((skill) => (
              <li key={skill.id}>
                <Badge tone="neutral">{skill.title_fa}</Badge>
              </li>
            ))}
          </ul>
        )}
        <p className="text-[13px] text-[var(--fg-tertiary)]">
          {opening.commitment_hpw && `${toPersianDigits(opening.commitment_hpw)} ساعت در هفته · `}
          آگهی‌دهنده: {opening.poster.name ?? 'کاربر'} · تا {formatDateLong(opening.expires_at)}
        </p>
      </Card>

      {error && (
        <p role="alert" className="text-[13.5px] text-[var(--danger-600)]">
          {error}
        </p>
      )}

      {!opening.can_manage && accessToken && (
        <Card variant="raised" className="flex flex-col gap-3">
          {mine ? (
            <>
              <CardTitle>درخواست تو</CardTitle>
              <div className="flex items-center gap-2">
                <Badge tone={mine.status === 'ACCEPTED' ? 'success' : 'neutral'}>
                  {mine.status_fa}
                </Badge>
                <span className="text-[12.5px] text-[var(--fg-tertiary)]">
                  {formatDateLong(mine.created_at)}
                </span>
              </div>
              <p className="text-[14px] leading-[1.9]">{mine.message}</p>
              {mine.decision_note && (
                <p className="text-[13.5px] text-[var(--fg-secondary)]">{mine.decision_note}</p>
              )}
              {mine.status === 'PENDING' && (
                <Button
                  variant="ghost"
                  size="sm"
                  className="self-start"
                  loading={busy}
                  onClick={() => run(() => withdrawApplication(accessToken, mine.id))}
                >
                  پس گرفتن درخواست
                </Button>
              )}
            </>
          ) : open ? (
            <>
              <CardTitle>درخواست پیوستن</CardTitle>
              <Textarea
                label="پیام"
                hint="چند جمله: چرا برای این نقش مناسبی و چه وقتی داری؟"
                value={message}
                onChange={(event) => setMessage(event.target.value)}
                maxLength={500}
                rows={3}
              />
              <Button
                className="self-start"
                loading={busy}
                disabled={!message.trim()}
                onClick={() => run(() => applyToOpening(accessToken, opening.id, message.trim()))}
              >
                ارسال درخواست
              </Button>
            </>
          ) : (
            <p className="text-[14px] text-[var(--fg-secondary)]">
              این آگهی دیگر درخواست نمی‌پذیرد.
            </p>
          )}
        </Card>
      )}

      {opening.can_manage && accessToken && (
        <section className="flex flex-col gap-4" aria-labelledby="applications-title">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 id="applications-title" className="text-[18px] font-semibold">
              درخواست‌ها ({toPersianDigits(opening.applications.length)})
            </h2>
            <div className="flex gap-2">
              {opening.status !== 'FILLED' && (
                <Button
                  size="sm"
                  variant="secondary"
                  loading={busy}
                  onClick={() => run(() => openingAction(accessToken, opening.id, 'renew'))}
                >
                  تمدید ۳۰ روزه
                </Button>
              )}
              {opening.status === 'OPEN' && (
                <Button
                  size="sm"
                  variant="ghost"
                  loading={busy}
                  onClick={() => run(() => openingAction(accessToken, opening.id, 'close'))}
                >
                  بستن آگهی
                </Button>
              )}
            </div>
          </div>
          {opening.applications.length === 0 ? (
            <p className="text-[14px] text-[var(--fg-secondary)]">هنوز درخواستی نرسیده است.</p>
          ) : (
            <ul className="flex flex-col gap-3">
              {opening.applications.map((application) => (
                <li key={application.id}>
                  <ApplicationCard
                    application={application}
                    canAccept={opening.status === 'OPEN'}
                    busy={busy}
                    onDecide={(decision, note) =>
                      run(() => decideApplication(accessToken, application.id, decision, note))
                    }
                  />
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
    </div>
  );
}

function ApplicationCard({
  application,
  canAccept,
  busy,
  onDecide,
}: {
  application: OpeningApplication;
  canAccept: boolean;
  busy: boolean;
  onDecide: (decision: 'ACCEPTED' | 'DECLINED', note?: string) => void;
}) {
  const [note, setNote] = useState('');
  const pending = application.status === 'PENDING';
  return (
    <Card className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-[15px] font-semibold">
          {application.applicant.name ?? application.applicant.username}
          {application.applicant.username && (
            <span className="ms-2 text-[12.5px] font-normal text-[var(--fg-tertiary)]" dir="ltr">
              @{application.applicant.username}
            </span>
          )}
        </p>
        <Badge
          tone={pending ? 'warning' : application.status === 'ACCEPTED' ? 'success' : 'neutral'}
        >
          {application.status_fa}
        </Badge>
      </div>
      <p className="text-[14px] leading-[1.9]">{application.message}</p>
      {application.decision_note && (
        <p className="text-[13px] text-[var(--fg-secondary)]">{application.decision_note}</p>
      )}
      {pending && (
        <>
          <Textarea
            label="یادداشت (اختیاری)"
            value={note}
            onChange={(event) => setNote(event.target.value)}
            maxLength={500}
            rows={2}
          />
          <div className="flex gap-2">
            {canAccept && (
              <Button size="sm" loading={busy} onClick={() => onDecide('ACCEPTED', note)}>
                پذیرش و افزودن به تیم
              </Button>
            )}
            <Button
              size="sm"
              variant="secondary"
              loading={busy}
              onClick={() => onDecide('DECLINED', note)}
            >
              رد
            </Button>
          </div>
        </>
      )}
    </Card>
  );
}

function messageFor(cause: unknown): string {
  if (cause instanceof ApiError || cause instanceof NetworkError) return cause.message;
  return 'کار انجام نشد. کمی بعد دوباره تلاش کن.';
}
