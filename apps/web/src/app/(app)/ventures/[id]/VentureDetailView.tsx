'use client';

import Link from 'next/link';
import { type FormEvent, useCallback, useEffect, useState } from 'react';

import { StageTrack } from '@/components/domain/StageTrack';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card, CardDescription, CardTitle } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { SkeletonCard, SkeletonText } from '@/components/ui/Skeleton';
import { Textarea } from '@/components/ui/Textarea';
import { ApiError, NetworkError } from '@/lib/api/client';
import {
  type Invitation,
  type StageAction,
  type VentureDetail,
  cancelInvitation,
  changeVentureStage,
  fetchVenture,
  fetchVentureInvitations,
  inviteToTeam,
  leaveVenture,
} from '@/lib/api/ventures';
import { useSession } from '@/lib/auth/use-session';
import { formatDateLong } from '@/lib/format/date';
import { formatNumber, formatRial, toPersianDigits } from '@/lib/format/digits';

import { VentureForm } from '../new/VentureForm';

/**
 * `/ventures/[id]` — FR-VEN-01، §7.7.
 *
 * قلب صفحه «گام بعد» است: معیارهای خروج مرحلهٔ فعلی با پیشرفت هرکدام
 * («۶ از ۱۰ جلسهٔ تأییدشده»)، تا بنیان‌گذار بداند دقیقاً چه کم دارد.
 * این بخش و جمع فروش فقط برای اعضا و مدیران است؛ سرور برای بقیه `null`
 * می‌فرستد.
 */
export function VentureDetailView({ id }: { id: string }) {
  const { accessToken, loading: sessionLoading } = useSession();
  const [venture, setVenture] = useState<VentureDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);

  const load = useCallback(() => {
    if (sessionLoading) return;
    fetchVenture(id, accessToken)
      .then((detail) => {
        setVenture(detail);
        setError(null);
      })
      .catch((cause) => setError(messageFor(cause)));
  }, [accessToken, id, sessionLoading]);

  useEffect(load, [load]);

  if (error && !venture) {
    return (
      <div className="flex flex-col gap-4">
        <p role="alert" className="text-[15px] text-[var(--danger-600)]">
          {error}
        </p>
        <Button asChild variant="secondary" className="self-start">
          <Link href="/ventures">بازگشت به کسب‌وکارها</Link>
        </Button>
      </div>
    );
  }
  if (!venture) {
    return (
      <div className="flex flex-col gap-4">
        <SkeletonText label="در حال بارگذاری کسب‌وکار" />
        <SkeletonCard />
      </div>
    );
  }

  const insider = venture.is_member || venture.can_manage;

  return (
    <article className="flex flex-col gap-8">
      <nav aria-label="مسیر" className="text-[13px] text-[var(--fg-tertiary)]">
        <Link href="/ventures" className="hover:text-[var(--brand-700)]">
          کسب‌وکارها
        </Link>{' '}
        ‹ {venture.name}
      </nav>

      <header className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-1.5">
          <Badge tone="accent">{venture.stage_fa}</Badge>
          {venture.looking_for_cofounder && <Badge tone="brand">دنبال هم‌بنیان‌گذار</Badge>}
        </div>
        <h1>{venture.name}</h1>
        <p className="text-[15.5px] leading-[1.95] text-[var(--fg-secondary)]">{venture.pitch}</p>
        <StageTrack stage={venture.stage} pausedFrom={venture.paused_from_stage} />
        {venture.origin_idea_id && (
          <Link
            href={`/ideas/${venture.origin_idea_id}`}
            className="self-start text-[13px] font-medium text-[var(--brand-700)] hover:underline"
          >
            از بانک ایده آمده است ←
          </Link>
        )}
      </header>

      {error && (
        <p role="alert" className="text-[13.5px] text-[var(--danger-600)]">
          {error}
        </p>
      )}

      {insider && accessToken && venture.readiness && (
        <NextStepCard
          venture={venture}
          accessToken={accessToken}
          onChanged={setVenture}
          onError={setError}
        />
      )}

      {insider && venture.totals && (
        <Card className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <CardTitle>فعالیت و فروش تأییدشده</CardTitle>
            <Button asChild variant="secondary" size="sm">
              <Link href={`/ventures/${venture.id}/metrics`}>ثبت و دیدن همه</Link>
            </Button>
          </div>
          <TotalsList totals={venture.totals} />
        </Card>
      )}

      {editing && venture.can_manage ? (
        <Card>
          <VentureForm
            initial={venture}
            onSaved={(saved) => {
              setVenture(saved);
              setEditing(false);
            }}
          />
        </Card>
      ) : (
        <section className="flex flex-col gap-5">
          <div className="flex items-center justify-between gap-3">
            <h2 className="text-[19px] font-semibold">دربارهٔ کسب‌وکار</h2>
            {venture.can_manage && venture.stage !== 'CLOSED' && (
              <Button variant="secondary" size="sm" onClick={() => setEditing(true)}>
                ویرایش
              </Button>
            )}
          </div>
          <Field title="مسئله" value={venture.problem} />
          <Field title="شرح" value={venture.description} />
          <Field title="بازار هدف" value={venture.target_market} />
          <Field title="مدل درآمد" value={venture.revenue_model} />
          <Field title="وضعیت فعلی" value={venture.current_status} />
          {venture.needed_roles.length > 0 && (
            <Field title="نقش‌های مورد نیاز" value={venture.needed_roles.join('، ')} />
          )}
        </section>
      )}

      <TeamSection
        venture={venture}
        accessToken={accessToken}
        onChanged={load}
        onError={setError}
      />

      {venture.projects.length > 0 && (
        <section className="flex flex-col gap-3">
          <h2 className="text-[19px] font-semibold">پروژه‌های این کسب‌وکار</h2>
          <ul className="flex flex-col gap-2">
            {venture.projects.map((project) => (
              <li key={project.id}>
                <Link
                  href={`/projects/${project.id}`}
                  className="text-[14.5px] font-medium text-[var(--brand-700)] hover:underline"
                >
                  {project.title_fa}
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}

      {venture.history.length > 0 && (
        <section className="flex flex-col gap-3">
          <h2 className="text-[19px] font-semibold">تاریخچهٔ مراحل</h2>
          <ol className="flex flex-col gap-2 text-[14px]">
            {venture.history.map((change) => (
              <li key={change.id} className="flex flex-wrap gap-x-2">
                <span className="font-medium">
                  {change.from_stage_fa} ← {change.to_stage_fa}
                </span>
                <span className="text-[var(--fg-tertiary)]">
                  {formatDateLong(change.created_at)}
                  {change.changed_by_name && ` · ${change.changed_by_name}`}
                </span>
                {change.reason && (
                  <span className="text-[var(--fg-secondary)]">— {change.reason}</span>
                )}
              </li>
            ))}
          </ol>
        </section>
      )}
    </article>
  );
}

function Field({ title, value }: { title: string; value: string | null }) {
  return (
    <div className="flex flex-col gap-1">
      <h3 className="text-[14px] font-semibold text-[var(--fg-secondary)]">{title}</h3>
      <p className="whitespace-pre-line text-[15px] leading-[1.95]">
        {value ?? <span className="text-[var(--fg-tertiary)]">هنوز نوشته نشده.</span>}
      </p>
    </div>
  );
}

const METRIC_LABELS: Record<string, string> = {
  CALLS: 'تماس فروش',
  MEETINGS: 'جلسه با مشتری',
  LEADS: 'سرنخ',
  SALES_COUNT: 'فروش',
  SALES_AMOUNT: 'مبلغ فروش',
  CONTENT_PIECES: 'محتوا',
  CUSTOMERS: 'مشتری تکرارشونده',
};

function TotalsList({ totals }: { totals: VentureDetail['totals'] }) {
  const entries = Object.entries(totals?.verified ?? {});
  if (entries.length === 0) {
    return (
      <p className="text-[14px] text-[var(--fg-tertiary)]">
        هنوز هیچ فعالیتی تأیید نشده. تماس، جلسه و فروش را ثبت کن تا منتور تأیید کند.
      </p>
    );
  }
  return (
    <dl className="grid gap-3 sm:grid-cols-3">
      {entries.map(([metric, value]) => (
        <div key={metric} className="flex flex-col gap-0.5">
          <dt className="text-[12.5px] text-[var(--fg-tertiary)]">
            {METRIC_LABELS[metric] ?? metric}
          </dt>
          <dd className="text-[17px] font-semibold tabular-nums">
            {metric === 'SALES_AMOUNT' ? formatRial(value ?? 0) : formatNumber(value ?? 0)}
          </dd>
        </div>
      ))}
    </dl>
  );
}

function NextStepCard({
  venture,
  accessToken,
  onChanged,
  onError,
}: {
  venture: VentureDetail;
  accessToken: string;
  onChanged: (venture: VentureDetail) => void;
  onError: (message: string) => void;
}) {
  const readiness = venture.readiness!;
  const [busy, setBusy] = useState<StageAction | null>(null);
  const [reason, setReason] = useState('');
  const [asking, setAsking] = useState<'PAUSE' | 'CLOSE' | null>(null);

  async function run(action: StageAction, withReason?: string) {
    setBusy(action);
    try {
      onChanged(await changeVentureStage(accessToken, venture.id, action, withReason));
      setAsking(null);
      setReason('');
    } catch (cause) {
      onError(messageFor(cause));
    } finally {
      setBusy(null);
    }
  }

  return (
    <Card variant="raised" className="flex flex-col gap-4">
      {venture.stage === 'PAUSED' ? (
        <CardTitle>این کسب‌وکار متوقف است</CardTitle>
      ) : venture.stage === 'CLOSED' ? (
        <CardTitle>این کسب‌وکار بسته شده است</CardTitle>
      ) : readiness.next_stage ? (
        <>
          <div className="flex flex-col gap-1">
            <CardTitle>گام بعد: {readiness.next_stage_fa}</CardTitle>
            <CardDescription>
              {readiness.ready
                ? 'همهٔ معیارها برقرار است؛ می‌توانی ارتقا بدهی.'
                : 'برای رفتن به گام بعد، این‌ها لازم است:'}
            </CardDescription>
          </div>
          <ul className="flex flex-col gap-2">
            {readiness.criteria.map((criterion) => (
              <li key={criterion.code} className="flex items-start gap-2 text-[14px] leading-[1.9]">
                <span
                  aria-hidden="true"
                  className={
                    criterion.met ? 'text-[var(--success-600)]' : 'text-[var(--fg-tertiary)]'
                  }
                >
                  {criterion.met ? '✓' : '○'}
                </span>
                <span className="flex-1">
                  {criterion.text}
                  {criterion.target > 1 && (
                    <span className="ms-2 text-[12.5px] tabular-nums text-[var(--fg-tertiary)]">
                      ({toPersianDigits(formatNumber(criterion.current))} از{' '}
                      {toPersianDigits(formatNumber(criterion.target))})
                    </span>
                  )}
                  <span className="sr-only">{criterion.met ? ' — انجام شد' : ' — مانده'}</span>
                </span>
              </li>
            ))}
          </ul>
        </>
      ) : (
        <CardTitle>این کسب‌وکار در بالاترین مرحلهٔ رشد است</CardTitle>
      )}

      {venture.can_manage && (
        <div className="flex flex-wrap gap-2">
          {readiness.next_stage && venture.stage !== 'PAUSED' && (
            <Button
              size="sm"
              disabled={!readiness.ready}
              loading={busy === 'ADVANCE'}
              onClick={() => run('ADVANCE')}
            >
              ارتقا به {readiness.next_stage_fa}
            </Button>
          )}
          {venture.stage === 'PAUSED' && (
            <Button size="sm" loading={busy === 'RESUME'} onClick={() => run('RESUME')}>
              ازسرگیری
            </Button>
          )}
          {venture.stage !== 'PAUSED' && venture.stage !== 'CLOSED' && (
            <Button variant="secondary" size="sm" onClick={() => setAsking('PAUSE')}>
              توقف موقت
            </Button>
          )}
          {venture.stage !== 'CLOSED' && (
            <Button variant="ghost" size="sm" onClick={() => setAsking('CLOSE')}>
              بستن کسب‌وکار
            </Button>
          )}
        </div>
      )}

      {asking && (
        <form
          className="flex flex-col gap-3"
          onSubmit={(event) => {
            event.preventDefault();
            void run(asking, reason.trim());
          }}
        >
          <Textarea
            label={asking === 'PAUSE' ? 'چرا متوقف می‌کنی؟' : 'چرا می‌بندی؟'}
            rows={2}
            maxLength={500}
            value={reason}
            onChange={(event) => setReason(event.target.value)}
          />
          <div className="flex gap-2">
            <Button
              type="submit"
              size="sm"
              variant={asking === 'CLOSE' ? 'danger' : 'primary'}
              loading={busy === asking}
              disabled={!reason.trim()}
            >
              {asking === 'PAUSE' ? 'توقف' : 'بستن'}
            </Button>
            <Button type="button" size="sm" variant="ghost" onClick={() => setAsking(null)}>
              انصراف
            </Button>
          </div>
        </form>
      )}
    </Card>
  );
}

function TeamSection({
  venture,
  accessToken,
  onChanged,
  onError,
}: {
  venture: VentureDetail;
  accessToken: string | null;
  onChanged: () => void;
  onError: (message: string) => void;
}) {
  const [username, setUsername] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [invitations, setInvitations] = useState<Invitation[]>([]);
  const canInvite = venture.can_manage && venture.stage !== 'CLOSED' && accessToken;

  const loadInvitations = useCallback(() => {
    if (!canInvite || !accessToken) return;
    fetchVentureInvitations(accessToken, venture.id)
      .then(setInvitations)
      .catch(() => setInvitations([]));
  }, [accessToken, canInvite, venture.id]);

  useEffect(loadInvitations, [loadInvitations]);

  async function invite(event: FormEvent) {
    event.preventDefault();
    if (!accessToken) return;
    setBusy(true);
    try {
      await inviteToTeam(
        accessToken,
        { kind: 'venture', id: venture.id },
        {
          username: username.trim().replace(/^@/, ''),
          message: message.trim() || null,
        },
      );
      setUsername('');
      setMessage('');
      loadInvitations();
    } catch (cause) {
      onError(messageFor(cause));
    } finally {
      setBusy(false);
    }
  }

  async function leave() {
    if (!accessToken || !window.confirm('از تیم این کسب‌وکار خارج می‌شوی؟')) return;
    try {
      await leaveVenture(accessToken, venture.id);
      onChanged();
    } catch (cause) {
      onError(messageFor(cause));
    }
  }

  return (
    <section className="flex flex-col gap-4">
      <h2 className="text-[19px] font-semibold">
        تیم ({toPersianDigits(venture.member_count)} نفر)
      </h2>
      <ul className="flex flex-col gap-2">
        {venture.members.map((member) => (
          <li key={member.user_id} className="flex items-center gap-2 text-[14.5px]">
            <span className="font-medium">{member.name ?? member.username ?? 'عضو'}</span>
            {member.is_founder && <Badge tone="accent">بنیان‌گذار</Badge>}
          </li>
        ))}
      </ul>
      {venture.is_member && !venture.can_manage && (
        <Button variant="ghost" size="sm" className="self-start" onClick={leave}>
          ترک تیم
        </Button>
      )}

      {canInvite && (
        <Card className="flex flex-col gap-4">
          <form onSubmit={invite} className="flex flex-col gap-3">
            <CardTitle>دعوت هم‌تیمی</CardTitle>
            <Input
              label="نام کاربری"
              hint="همان که در نشانی نیمرخ عمومی می‌آید"
              forceLtr
              value={username}
              onChange={(event) => setUsername(event.target.value)}
            />
            <Textarea
              label="پیام دعوت"
              rows={2}
              maxLength={500}
              value={message}
              onChange={(event) => setMessage(event.target.value)}
            />
            <Button
              type="submit"
              size="sm"
              loading={busy}
              disabled={username.trim().length < 3}
              className="self-start"
            >
              فرستادن دعوت
            </Button>
          </form>
          {invitations.length > 0 && (
            <ul className="flex flex-col gap-2 text-[13.5px]">
              {invitations.map((invitation) => (
                <li key={invitation.id} className="flex items-center justify-between gap-2">
                  <span>
                    {invitation.invitee_name ?? 'کاربر'} — در انتظار پاسخ تا{' '}
                    {formatDateLong(invitation.expires_at)}
                  </span>
                  <button
                    type="button"
                    className="font-medium text-[var(--danger-600)] hover:underline"
                    onClick={async () => {
                      if (!accessToken) return;
                      await cancelInvitation(accessToken, invitation.id).catch((cause) =>
                        onError(messageFor(cause)),
                      );
                      loadInvitations();
                    }}
                  >
                    لغو
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Card>
      )}
    </section>
  );
}

function messageFor(cause: unknown): string {
  if (cause instanceof ApiError || cause instanceof NetworkError) return cause.message;
  return 'کار انجام نشد. کمی بعد دوباره تلاش کن.';
}
