'use client';

import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';

import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card, CardTitle } from '@/components/ui/Card';
import { SkeletonCard } from '@/components/ui/Skeleton';
import { Textarea } from '@/components/ui/Textarea';
import { ApiError, NetworkError } from '@/lib/api/client';
import { type Topic, closeTopic, fetchTopic, reviewTopic, topicAction } from '@/lib/api/research';
import { useSession } from '@/lib/auth/use-session';
import { formatDateLong } from '@/lib/format/date';
import { toPersianDigits } from '@/lib/format/digits';

import { TOPIC_TONE } from '../TopicsView';

/**
 * `/research/topics/[id]` — FR-RES-03.
 *
 * دانشجو رزرو می‌کند یا آزاد؛ استاد پیشنهاد را می‌پذیرد یا با دلیل رد
 * می‌کند، موضوع را می‌بندد یا دوباره باز می‌کند. نام رزروکننده فقط برای
 * کادر آموزشی می‌آید — سرور همین را تضمین کرده است.
 */
export function TopicDetailView({ id }: { id: string }) {
  const { accessToken, loading: sessionLoading } = useSession();
  const [topic, setTopic] = useState<Topic | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    if (sessionLoading) return;
    fetchTopic(id, accessToken)
      .then(setTopic)
      .catch((cause) => setError(messageFor(cause)));
  }, [id, accessToken, sessionLoading]);

  useEffect(load, [load]);

  async function run(action: (token: string) => Promise<Topic>) {
    if (!accessToken) return;
    setBusy(true);
    setError(null);
    try {
      setTopic(await action(accessToken));
      setNote('');
    } catch (cause) {
      setError(messageFor(cause));
    } finally {
      setBusy(false);
    }
  }

  if (topic === null) {
    return error ? (
      <p role="alert" className="text-[13.5px] text-[var(--danger-600)]">
        {error}
      </p>
    ) : (
      <SkeletonCard label="در حال بارگذاری موضوع" />
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-2">
        <Link
          href="/research/topics"
          className="text-[13px] text-[var(--fg-tertiary)] hover:underline"
        >
          ← بانک موضوع
        </Link>
        <div className="flex flex-wrap items-center gap-2">
          <h1>{topic.title}</h1>
          <Badge tone={TOPIC_TONE[topic.status]}>
            {topic.reserved_by_me ? 'رزرو تو' : topic.status_fa}
          </Badge>
          {topic.level && <Badge tone="neutral">سطح {toPersianDigits(topic.level)}</Badge>}
        </div>
        <p className="text-[13px] text-[var(--fg-tertiary)]">
          پیشنهاد {topic.proposer.name ?? 'کاربر'} · {formatDateLong(topic.created_at)}
        </p>
      </header>

      <Card className="flex flex-col gap-4">
        <p className="whitespace-pre-line text-[15px] leading-[2]">{topic.description}</p>
        {topic.prerequisites && (
          <div className="flex flex-col gap-1">
            <p className="text-[13.5px] font-semibold">پیش‌نیاز</p>
            <p className="text-[14px] leading-[1.9] text-[var(--fg-secondary)]">
              {topic.prerequisites}
            </p>
          </div>
        )}
        {topic.reserved_by && (
          <p className="text-[13.5px] text-[var(--fg-secondary)]">
            رزرو: {topic.reserved_by.name ?? topic.reserved_by.username}
            {topic.reserved_at && ` از ${formatDateLong(topic.reserved_at)}`}
          </p>
        )}
        {topic.idle_days_left !== null && (
          <p className="text-[13.5px] text-[var(--warning-600)]">
            اگر تا {toPersianDigits(topic.idle_days_left)} روز دیگر تحویلی از مسیر پژوهش نفرستی،
            رزرو آزاد می‌شود.
          </p>
        )}
        {topic.review_note && (
          <p className="rounded-[var(--radius-md)] bg-[var(--bg-sunken)] p-3 text-[13.5px]">
            <span className="font-semibold">یادداشت استاد: </span>
            {topic.review_note}
          </p>
        )}
        <div className="flex flex-wrap gap-2">
          {topic.can_reserve && (
            <Button
              loading={busy}
              onClick={() => run((token) => topicAction(token, topic.id, 'reserve'))}
            >
              رزرو این موضوع
            </Button>
          )}
          {topic.can_release && (
            <Button
              variant="secondary"
              loading={busy}
              onClick={() => run((token) => topicAction(token, topic.id, 'release'))}
            >
              آزاد کردن رزرو
            </Button>
          )}
          {topic.reserved_by_me && (
            <Button asChild variant="ghost">
              <Link href="/research">رفتن به مسیر پژوهش</Link>
            </Button>
          )}
        </div>
        {error && (
          <p role="alert" className="text-[13.5px] text-[var(--danger-600)]">
            {error}
          </p>
        )}
      </Card>

      {topic.can_manage && (
        <Card variant="raised" className="flex flex-col gap-3">
          <CardTitle>مدیریت موضوع</CardTitle>
          <Textarea
            label="یادداشت"
            hint="برای رد پیشنهاد یا بستن موضوع لازم است"
            value={note}
            onChange={(event) => setNote(event.target.value)}
            maxLength={1000}
            rows={2}
          />
          <div className="flex flex-wrap gap-2">
            {topic.status === 'PROPOSED' && (
              <>
                <Button
                  loading={busy}
                  onClick={() => run((token) => reviewTopic(token, topic.id, 'APPROVE', note))}
                >
                  پذیرش و افزودن به بانک
                </Button>
                <Button
                  variant="danger"
                  loading={busy}
                  disabled={!note.trim()}
                  onClick={() => run((token) => reviewTopic(token, topic.id, 'REJECT', note))}
                >
                  رد پیشنهاد
                </Button>
              </>
            )}
            {topic.status !== 'CLOSED' && topic.status !== 'PROPOSED' && (
              <Button
                variant="secondary"
                loading={busy}
                disabled={!note.trim()}
                onClick={() => run((token) => closeTopic(token, topic.id, note))}
              >
                بستن موضوع
              </Button>
            )}
            {(topic.status === 'CLOSED' || topic.status === 'TAKEN') && (
              <Button
                variant="secondary"
                loading={busy}
                onClick={() => run((token) => topicAction(token, topic.id, 'reopen'))}
              >
                بازگرداندن به بانک
              </Button>
            )}
          </div>
        </Card>
      )}
    </div>
  );
}

function messageFor(cause: unknown): string {
  if (cause instanceof ApiError || cause instanceof NetworkError) return cause.message;
  return 'کار انجام نشد. کمی بعد دوباره تلاش کن.';
}
