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
import {
  type Topic,
  type TopicStatus,
  createTopic,
  fetchTopics,
  topicAction,
} from '@/lib/api/research';
import { useSession } from '@/lib/auth/use-session';
import { toPersianDigits } from '@/lib/format/digits';

/**
 * `/research/topics` — بانک موضوع پژوهشی، FR-RES-03.
 *
 * موضوع باز اول می‌آید (سرور مرتب کرده). رزرو یک کلیک است و اتمی: اگر
 * کسی زودتر رزرو کرده باشد، پیام سرور همان را می‌گوید. پیشنهاد دانشجو تا
 * تأیید استاد فقط برای خودش دیده می‌شود.
 */

const SEARCH_DEBOUNCE_MS = 350;

type Filter = '' | TopicStatus | 'MINE';

const FILTERS: ChipOption<Filter>[] = [
  { value: '', label: 'همه' },
  { value: 'OPEN', label: 'باز' },
  { value: 'RESERVED', label: 'رزروشده' },
  { value: 'TAKEN', label: 'در حال انجام' },
  { value: 'MINE', label: 'موضوع‌های من' },
];

export const TOPIC_TONE: Record<TopicStatus, BadgeTone> = {
  PROPOSED: 'info',
  OPEN: 'success',
  RESERVED: 'warning',
  TAKEN: 'research',
  CLOSED: 'neutral',
};

export function TopicsView() {
  const { accessToken, loading: sessionLoading } = useSession();
  const [topics, setTopics] = useState<Topic[] | null>(null);
  const [total, setTotal] = useState(0);
  const [filter, setFilter] = useState<Filter>('');
  const [query, setQuery] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [proposing, setProposing] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

  const reload = useCallback(() => setReloadKey((key) => key + 1), []);

  useEffect(() => {
    if (sessionLoading) return;
    let cancelled = false;
    const timer = setTimeout(() => {
      fetchTopics(
        {
          ...(filter === 'MINE' ? { mine: true } : filter ? { status: filter } : {}),
          ...(query.trim() ? { q: query.trim() } : {}),
        },
        accessToken,
      )
        .then((page) => {
          if (cancelled) return;
          setTopics(page.items);
          setTotal(page.total);
          setError(null);
        })
        .catch((cause) => {
          if (cancelled) return;
          setError(messageFor(cause));
          setTopics([]);
        });
    }, SEARCH_DEBOUNCE_MS);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [filter, query, accessToken, sessionLoading, reloadKey]);

  async function act(topic: Topic, action: 'reserve' | 'release') {
    if (!accessToken) return;
    try {
      await topicAction(accessToken, topic.id, action);
      reload();
    } catch (cause) {
      setError(messageFor(cause));
    }
  }

  return (
    <div className="flex flex-col gap-8">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="flex flex-col gap-1">
          <Link href="/research" className="text-[13px] text-[var(--fg-tertiary)] hover:underline">
            ← مسیر پژوهش
          </Link>
          <h1>بانک موضوع پژوهشی</h1>
          <p className="text-[15px] text-[var(--fg-secondary)]">
            موضوعی را رزرو کن تا کسی موازی کار نکند. رزرو بی‌تحرک پس از ۳۰ روز آزاد می‌شود.
          </p>
        </div>
        {!proposing && <Button onClick={() => setProposing(true)}>پیشنهاد موضوع</Button>}
      </header>

      {proposing && accessToken && (
        <ProposeForm
          accessToken={accessToken}
          onDone={() => {
            setProposing(false);
            setFilter('MINE');
            reload();
          }}
          onCancel={() => setProposing(false)}
        />
      )}

      <section className="flex flex-col gap-4">
        <Input
          label="جستجو"
          hint="عنوان یا شرح موضوع"
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        <ChipGroup label="فیلتر موضوع" options={FILTERS} value={filter} onChange={setFilter} />
        {error && (
          <p role="alert" className="text-[13.5px] text-[var(--danger-600)]">
            {error}
          </p>
        )}
        {topics === null ? (
          <SkeletonCard label="در حال بارگذاری موضوع‌ها" />
        ) : topics.length === 0 ? (
          <EmptyState
            title="موضوعی پیدا نشد"
            description="موضوع خودت را پیشنهاد بده؛ پس از تأیید استاد به بانک اضافه می‌شود."
          />
        ) : (
          <>
            <p className="text-[13px] text-[var(--fg-tertiary)]">{toPersianDigits(total)} موضوع</p>
            <ul className="grid gap-4 md:grid-cols-2">
              {topics.map((topic) => (
                <li key={topic.id}>
                  <TopicCard topic={topic} onAct={act} />
                </li>
              ))}
            </ul>
          </>
        )}
      </section>
    </div>
  );
}

function TopicCard({
  topic,
  onAct,
}: {
  topic: Topic;
  onAct: (topic: Topic, action: 'reserve' | 'release') => void;
}) {
  return (
    <Card variant="interactive" className="flex h-full flex-col gap-3">
      <div className="flex flex-wrap items-center gap-1.5">
        <Badge tone={TOPIC_TONE[topic.status]}>
          {topic.reserved_by_me ? 'رزرو تو' : topic.status_fa}
        </Badge>
        {topic.level && <Badge tone="neutral">سطح {toPersianDigits(topic.level)}</Badge>}
      </div>
      <Link
        href={`/research/topics/${topic.id}`}
        className="text-[16px] font-semibold text-[var(--fg-primary)] hover:text-[var(--brand-700)]"
      >
        {topic.title}
      </Link>
      <p className="line-clamp-3 text-[14px] leading-[1.9] text-[var(--fg-secondary)]">
        {topic.description}
      </p>
      <div className="mt-auto flex flex-wrap items-center justify-between gap-2">
        <span className="text-[12.5px] text-[var(--fg-tertiary)]">
          پیشنهاد: {topic.proposer.name ?? 'کاربر'}
          {topic.idle_days_left !== null &&
            ` · ${toPersianDigits(topic.idle_days_left)} روز تا آزاد شدن`}
        </span>
        {topic.can_reserve && (
          <Button size="sm" onClick={() => onAct(topic, 'reserve')}>
            رزرو
          </Button>
        )}
        {topic.can_release && topic.reserved_by_me && (
          <Button size="sm" variant="ghost" onClick={() => onAct(topic, 'release')}>
            آزاد کردن
          </Button>
        )}
      </div>
    </Card>
  );
}

function ProposeForm({
  accessToken,
  onDone,
  onCancel,
}: {
  accessToken: string;
  onDone: () => void;
  onCancel: () => void;
}) {
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [prerequisites, setPrerequisites] = useState('');
  const [level, setLevel] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await createTopic(accessToken, {
        title: title.trim(),
        description: description.trim(),
        prerequisites: prerequisites.trim() || null,
        level: level ? Number(level) : null,
      });
      onDone();
    } catch (cause) {
      setError(messageFor(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card variant="raised" className="flex flex-col gap-4">
      <CardTitle>پیشنهاد موضوع پژوهشی</CardTitle>
      <CardDescription>
        استاد پیشنهاد را بررسی می‌کند؛ اگر پذیرفته شود، ۳۰ امتیاز پژوهش می‌گیری.
      </CardDescription>
      <form onSubmit={handleSubmit} className="flex flex-col gap-3">
        <Input
          label="عنوان"
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          minLength={5}
          maxLength={200}
          required
        />
        <Textarea
          label="شرح"
          hint="مسئله چیست، چرا مهم است و چه داده‌ای لازم دارد؟"
          value={description}
          onChange={(event) => setDescription(event.target.value)}
          minLength={20}
          maxLength={4000}
          rows={4}
          required
        />
        <Textarea
          label="پیش‌نیاز (اختیاری)"
          hint="مهارت یا درسی که پیش از شروع لازم است"
          value={prerequisites}
          onChange={(event) => setPrerequisites(event.target.value)}
          maxLength={1000}
          rows={2}
        />
        <div className="flex flex-col gap-1.5">
          <label htmlFor="topic-level" className="text-[13.5px] font-medium">
            سطح پیشنهادی (اختیاری)
          </label>
          <select
            id="topic-level"
            value={level}
            onChange={(event) => setLevel(event.target.value)}
            className="h-10 rounded-[var(--radius-md)] border border-[var(--border-default)] bg-[var(--bg-surface)] px-3 text-[14px]"
          >
            <option value="">فرقی ندارد</option>
            <option value="1">۱ — مرور ادبیات</option>
            <option value="2">۲ — تحلیل داده</option>
            <option value="3">۳ — مقالهٔ کنفرانس</option>
            <option value="4">۴ — مقالهٔ Q1</option>
          </select>
        </div>
        {error && (
          <p role="alert" className="text-[13.5px] text-[var(--danger-600)]">
            {error}
          </p>
        )}
        <div className="flex gap-2">
          <Button type="submit" loading={busy}>
            ثبت
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
